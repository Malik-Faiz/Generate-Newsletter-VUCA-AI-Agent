"""
app.py
─────────────────
Flask backend for the public VUCA Newsletter Generator.

Endpoints:
  GET  /             — serves the upload page (frontend/index.html) directly,
                        so the whole app lives at one URL. GitHub Pages is
                        optional now — this exists for the simpler
                        single-deployment setup.
  GET  /health       — server / API-key / skill status, used by the frontend's
                        status dot.
  GET  /queue-status — how many seconds until the next generation slot opens
                        up, without consuming one. Used by the frontend while
                        it's waiting for its automatic retry.
  POST /generate      — accepts multipart form data (report file, image files,
                        topic/custom_topic/language/audience/tone). If another
                        generation started too recently (see "Generation queue
                        / rate gate" below), responds 429 with a wait_seconds
                        the frontend uses to retry automatically — otherwise
                        returns JSON with the structured newsletter content
                        (rendered directly in the frontend page — no separate
                        HTML file is generated) plus download URLs for the
                        Word document and infographic JPG.
  GET  /outputs/...   — serves the generated files.

Run locally:
    (put GROQ_API_KEY in backend/.env)
    python app.py
Then just open http://localhost:7755/ in a browser — the frontend is
served directly from the backend now.
"""

import os
import threading
import time
import traceback
import uuid
from pathlib import Path

from env_loader import load_env
load_env()  # reads backend/.env into os.environ, if present — must run before
            # importing newsletter_ai, which reads GROQ_MODEL etc. at import time

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

import newsletter_ai
import report_reader
import image_vision
import docx_builder
import infographic_builder

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
OUTPUTS_DIR = BASE_DIR / "outputs"
UPLOADS_TMP_DIR = BASE_DIR / "uploads_tmp"
OUTPUTS_DIR.mkdir(exist_ok=True)
UPLOADS_TMP_DIR.mkdir(exist_ok=True)

MAX_CONTENT_LENGTH = 60 * 1024 * 1024  # 60 MB total upload cap

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
CORS(app)  # in case the frontend is ever served from a different origin

# ── Generation queue / rate gate ─────────────────────────────────────
#
# Groq's free tier gives this app a shared ~8,000 tokens/minute budget
# across EVERYONE hitting this backend — not per visitor. If two people
# click Generate close together, even though Flask/gunicorn processes
# requests one at a time, both generations still land inside the same
# 60-second window and collide on that shared limit, causing a 429 from
# Groq. The fix: track the last time a generation actually started, and
# refuse (with a clear retry-after) any new one that arrives before
# enough time has passed — regardless of whether it's a literal
# concurrent request or just an unlucky-timing sequential one.
#
# This also happens to serialize genuinely simultaneous requests
# correctly, since the check-and-reserve below is done under a lock.
_rate_lock = threading.Lock()
_last_generation_start = 0.0

MIN_GENERATION_INTERVAL_SECONDS = int(os.environ.get("MIN_GENERATION_INTERVAL_SECONDS", "62"))


def _reserve_generation_slot():
    """
    Atomically checks whether enough time has passed since the last
    generation to safely start a new one without colliding on Groq's
    shared rate limit. If allowed, reserves the slot immediately
    (updates the timestamp) so a second caller checking right after
    correctly sees the reservation. Returns (allowed, wait_seconds).
    """
    global _last_generation_start
    with _rate_lock:
        now = time.time()
        elapsed = now - _last_generation_start
        if elapsed >= MIN_GENERATION_INTERVAL_SECONDS:
            _last_generation_start = now
            return True, 0.0
        return False, round(MIN_GENERATION_INTERVAL_SECONDS - elapsed, 1)


@app.route("/", methods=["GET"])
def serve_frontend():
    """
    Serves the upload page directly at the backend's own root URL, so the
    whole app lives at one single link (e.g. https://your-app.onrender.com/)
    instead of needing a separate GitHub Pages deployment. Because this is
    same-origin, the frontend's PRODUCTION_BACKEND_URL doesn't even need to
    be set — its same-origin auto-detection just works.
    """
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": "ok",
            "api_key_set": newsletter_ai.api_key_set(),
            "skill_loaded": newsletter_ai.skill_loaded(),
            "model": newsletter_ai.MODEL,
            "provider": "groq",
        }
    )


@app.route("/queue-status", methods=["GET"])
def queue_status():
    """Lets the frontend show an accurate countdown while waiting, without
    consuming a generation slot itself."""
    with _rate_lock:
        elapsed = time.time() - _last_generation_start
    wait_seconds = max(0.0, round(MIN_GENERATION_INTERVAL_SECONDS - elapsed, 1))
    return jsonify({"wait_seconds": wait_seconds, "available": wait_seconds <= 0})


@app.route("/generate", methods=["POST"])
def generate():
    allowed, wait_seconds = _reserve_generation_slot()
    if not allowed:
        return (
            jsonify(
                {
                    "busy": True,
                    "wait_seconds": wait_seconds,
                    "detail": (
                        "Another newsletter was generated very recently — Groq's "
                        f"shared free-tier rate limit needs about {int(wait_seconds) + 1} "
                        "more second(s) to clear before the next one can start."
                    ),
                }
            ),
            429,
        )

    job_id = uuid.uuid4().hex[:12]
    job_dir = OUTPUTS_DIR / job_id

    try:
        topic = request.form.get("topic", "strategy")
        custom_topic = request.form.get("custom_topic", "")
        language = request.form.get("language", "English")
        audience = request.form.get("audience", "General business audience")
        tone = request.form.get("tone", "Executive summary — concise, decision-oriented")

        # ── Save + extract report text ──────────────────────────────
        report_text = ""
        report_file = request.files.get("report")
        if report_file and report_file.filename:
            tmp_report_path = UPLOADS_TMP_DIR / f"{job_id}_{report_file.filename}"
            report_file.save(tmp_report_path)
            try:
                report_text = report_reader.extract_text(tmp_report_path)
            finally:
                tmp_report_path.unlink(missing_ok=True)

        # ── Save images, keep bytes for DOCX embedding ───────────────
        # A .pdf here is treated as an exported slide deck (PowerPoint /
        # Google Slides / Keynote all export to PDF in one click) — each
        # page becomes its own image, so "1 slide = 1 image" without
        # needing LibreOffice or any pptx-rendering dependency.
        images = []
        for f in request.files.getlist("images"):
            if not f or not f.filename:
                continue
            if f.filename.lower().endswith(".pdf"):
                tmp_pdf_path = UPLOADS_TMP_DIR / f"{job_id}_{f.filename}"
                f.save(tmp_pdf_path)
                try:
                    clean_stem = Path(f.filename).stem
                    pages = report_reader.extract_pdf_pages_as_images(tmp_pdf_path, base_name=clean_stem)
                    for page in pages:
                        images.append({**page, "caption": page["filename"]})
                finally:
                    tmp_pdf_path.unlink(missing_ok=True)
            else:
                raw = f.read()
                images.append({"filename": f.filename, "bytes": raw, "caption": f.filename})

        # ── Vision step: actually look at each image (best-effort — ──
        # falls back to filename-only captions if this fails for any
        # reason, so a vision hiccup never blocks the whole generation).
        if images:
            images = image_vision.describe_images(images)

        # ── Call the AI to generate structured content ──────────────
        # (the model assigns each image to whichever section it's
        # actually relevant to, based on the real descriptions above —
        # not round-robin by filename order)
        content = newsletter_ai.generate_newsletter_content(
            topic_key=topic,
            custom_topic=custom_topic,
            language=language,
            audience=audience,
            tone=tone,
            report_text=report_text,
            image_descriptions=images,
        )

        # ── Render outputs ────────────────────────────────────────────
        job_dir.mkdir(parents=True, exist_ok=True)

        docx_path = job_dir / "newsletter.docx"
        docx_builder.build_docx(content, images, docx_path)

        infographic_path = job_dir / "infographic.jpg"
        infographic_builder.build_infographic(content, infographic_path)

        # Strip internal bookkeeping keys before sending content back —
        # the frontend renders this directly in-page (no separate HTML
        # file is generated; the Word doc above is the downloadable
        # document version of the same content).
        public_content = {k: v for k, v in content.items() if not k.startswith("_")}

        return jsonify(
            {
                "title": content.get("title", "Newsletter"),
                "content": public_content,
                "docx_url": f"/outputs/{job_id}/newsletter.docx",
                "infographic_url": f"/outputs/{job_id}/infographic.jpg",
            }
        )

    except Exception as e:
        traceback.print_exc()
        return jsonify({"detail": str(e)}), 500


@app.route("/outputs/<job_id>/<filename>", methods=["GET"])
def serve_output(job_id, filename):
    directory = OUTPUTS_DIR / job_id
    return send_from_directory(directory, filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7755))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
