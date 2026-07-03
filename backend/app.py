"""
app.py
─────────────────
Flask backend for the public VUCA Newsletter Generator.

Endpoints:
  GET  /           — serves the upload page (frontend/index.html) directly,
                      so the whole app lives at one URL. GitHub Pages is
                      optional now — this exists for the simpler
                      single-deployment setup.
  GET  /health     — server / API-key / skill status, used by the frontend's
                      status dot.
  POST /generate    — accepts multipart form data (report file, image files,
                      topic/custom_topic/language/audience/tone) and returns
                      JSON with the structured newsletter content (rendered
                      directly in the frontend page — no separate HTML file
                      is generated) plus download URLs for the Word document
                      and infographic JPG.
  GET  /outputs/... — serves the generated files.

Run locally:
    (put GROQ_API_KEY in backend/.env)
    python app.py
Then just open http://localhost:7755/ in a browser — the frontend is
served directly from the backend now.
"""

import os
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


@app.route("/generate", methods=["POST"])
def generate():
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
        images = []
        for f in request.files.getlist("images"):
            if not f or not f.filename:
                continue
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
