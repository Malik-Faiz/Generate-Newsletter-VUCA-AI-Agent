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
import docx_builder
import infographic_builder

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
OUTPUTS_DIR = BASE_DIR / "outputs"
UPLOADS_TMP_DIR = BASE_DIR / "uploads_tmp"
OUTPUTS_DIR.mkdir(exist_ok=True)
UPLOADS_TMP_DIR.mkdir(exist_ok=True)

MAX_CONTENT_LENGTH = 60 * 1024 * 1024  # 60 MB total upload cap

# Cap on total images processed per generation, counting each PDF page
# as one image once expanded. Gemini accepts many images per request,
# but this still exists as a sane, predictable ceiling — larger batches
# still mean bigger requests and longer document-build time. Raise via
# env var if your use case genuinely needs more.
MAX_IMAGES = int(os.environ.get("MAX_IMAGES", "16"))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
CORS(app)  # in case the frontend is ever served from a different origin

# ── Generation queue / rate gate ─────────────────────────────────────
#
# Google's Gemini free tier limits requests-per-minute (roughly 10-15
# RPM depending on model — check https://ai.google.dev/gemini-api/docs/rate-limits
# for your project's actual current limit) rather than a tight shared
# token budget the way Groq's free tier did. Since one generation is now
# a single API call (no separate vision request), spacing generations a
# few seconds apart keeps this comfortably under even a 10 RPM limit.
# This also serialises genuinely simultaneous requests correctly, since
# the check-and-reserve below is done under a lock.
_rate_lock = threading.Lock()
_last_generation_start = 0.0

MIN_GENERATION_INTERVAL_SECONDS = int(os.environ.get("MIN_GENERATION_INTERVAL_SECONDS", "6"))


def _reserve_generation_slot():
    """
    Atomically checks whether enough time has passed since the last
    generation to safely start a new one without exceeding Gemini's
    free-tier requests-per-minute limit. If allowed, reserves the slot
    immediately (updates the timestamp) so a second caller checking
    right after correctly sees the reservation. Returns
    (allowed, wait_seconds).
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
            "provider": "gemini",
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
                        "Another generation just started — Gemini's free-tier "
                        f"rate limit needs about {int(wait_seconds) + 1} more "
                        "second(s) before the next one can start."
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

        if len(images) > MAX_IMAGES:
            return (
                jsonify(
                    {
                        "detail": (
                            f"Too many images/slides for one generation ({len(images)} "
                            f"— limit is {MAX_IMAGES}, counting each PDF page as one "
                            "image). This limit exists because per-image AI calls, "
                            "prompt size, and document-building time all compound "
                            "with more images, risking timeouts on a free-tier "
                            "deployment. Please remove some images (or split a large "
                            "slide-deck PDF into two smaller ones) and try again."
                        )
                    }
                ),
                400,
            )

        # ── Call the AI to generate structured content ──────────────
        # Gemini sees the actual uploaded images directly in this one
        # call (native multimodal) and assigns each to whichever
        # section it's actually relevant to — no separate vision pass.
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
        # document version of the same content). unassigned_images is
        # kept (renamed, without the underscore prefix) specifically so
        # the frontend can still show images the AI didn't confidently
        # assign to a section — previously those were invisible in the
        # on-page preview even though they were included in the Word doc,
        # which looked like uploaded images had simply vanished.
        public_content = {k: v for k, v in content.items() if not k.startswith("_")}
        public_content["unassigned_images"] = content.get("_unassigned_images", [])

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
    app.run(
        host="0.0.0.0",
        port=port,
        debug=os.environ.get("FLASK_DEBUG") == "1",
        # use_reloader=False: the reloader watches the whole project
        # folder for changes and restarts the server on any change —
        # but /generate writes new files into backend/outputs/ on every
        # successful run, which the reloader was treating as "a change"
        # and restarting mid-response, wiping the result the frontend
        # was about to show. Debug mode's error pages still work fine
        # without the reloader.
        use_reloader=False,
    )
