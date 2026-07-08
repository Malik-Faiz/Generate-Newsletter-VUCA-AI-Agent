"""
image_vision.py
─────────────────
Uses Groq's vision-capable model to actually look at each uploaded
image and describe what's in it. Those descriptions then get fed into
the main newsletter-writing prompt so the AI can assign each image to
the section it's actually relevant to, instead of just scattering
images round-robin by filename.

Groq's vision endpoint accepts up to 5 images per request, so images
are batched in groups of 5 to minimise API calls. Each batch is
independent — if one batch fails (rate limit, timeout, bad response),
the rest still get processed instead of the whole upload silently
losing its descriptions.
"""

import base64
import io
import json
import os
import urllib.error
import urllib.request

from PIL import Image

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
# NOTE: Groq deprecates/replaces vision models on a regular cadence —
# check https://console.groq.com/docs/vision for the current lineup
# before assuming this value is still right.
VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")
MAX_IMAGES_PER_CALL = 5

# Images get downsized before being sent to the vision model — this
# matters a lot once someone uploads 10+ images (e.g. a multi-page PDF
# slide deck): full-resolution PNGs multiply up fast in both request
# payload size and server memory, and a vision model doesn't need
# print-resolution input to describe what's in a slide.
MAX_VISION_DIMENSION = int(os.environ.get("MAX_VISION_DIMENSION", "900"))
VISION_JPEG_QUALITY = int(os.environ.get("VISION_JPEG_QUALITY", "70"))


def _require_api_key() -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set.")
    return api_key


def _downsize_for_vision(image_bytes: bytes) -> bytes:
    """
    Shrinks an image to a reasonable max dimension and re-encodes as a
    moderate-quality JPEG before sending to the vision model. This is
    purely for the vision API call — the original, full-quality bytes
    are still what gets embedded in the Word document.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > MAX_VISION_DIMENSION:
            scale = MAX_VISION_DIMENSION / max(w, h)
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=VISION_JPEG_QUALITY)
        return buf.getvalue()
    except Exception:
        # If anything about downsizing fails, fall back to the original
        # bytes rather than losing the image from the vision pass.
        return image_bytes


def _mime_for(image_bytes: bytes) -> str:
    if image_bytes[:2] == b"\xff\xd8":
        return "image/jpeg"
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _describe_batch(images_batch: list) -> list:
    """images_batch: list of {'filename':..., 'bytes':...}. Returns a list
    of description strings, same length and order as images_batch."""
    api_key = _require_api_key()

    content = [
        {
            "type": "text",
            "text": (
                f"You will see {len(images_batch)} image(s), in order. For "
                "each one, write a single concise sentence (max 15 words) "
                "describing what it actually shows — the kind of visual "
                "content, key subject matter, any visible text/numbers/"
                "chart type. Respond with ONLY a JSON object of this exact "
                'shape and nothing else: {"descriptions": ["...", "...", ...]} '
                f"— the array must have exactly {len(images_batch)} strings, "
                "in the same order the images were shown."
            ),
        }
    ]
    for img in images_batch:
        vision_bytes = _downsize_for_vision(img["bytes"])
        b64 = base64.b64encode(vision_bytes).decode("ascii")
        mime = _mime_for(vision_bytes)
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
        )

    payload = json.dumps(
        {
            "model": VISION_MODEL,
            "max_tokens": 1000,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": content}],
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        GROQ_ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "vuca-newsletter-app/1.0 (+https://github.com)",
        },
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    raw = body["choices"][0]["message"]["content"] or "{}"
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    parsed = json.loads(raw)
    descriptions = parsed.get("descriptions", [])

    # Defensive: pad/truncate to match batch length exactly.
    while len(descriptions) < len(images_batch):
        descriptions.append("")
    return descriptions[: len(images_batch)]


def describe_images(images: list) -> list:
    """
    images: list of {'filename':..., 'bytes':..., 'caption':...}
    Returns the same list with each dict's 'caption' replaced by a real
    AI-generated description of the image content.

    Each batch of up to 5 images is independent: if one batch's API
    call fails (rate limit, timeout, malformed response), that batch's
    images just keep their filename as a fallback caption and the
    REMAINING batches still get processed normally. Previously a single
    failed batch aborted every batch after it, which is why uploading
    several images sometimes silently lost descriptions partway through
    — that's the specific bug this fixes.
    """
    if not images:
        return images

    for i in range(0, len(images), MAX_IMAGES_PER_CALL):
        batch = images[i : i + MAX_IMAGES_PER_CALL]
        try:
            descriptions = _describe_batch(batch)
            for img, desc in zip(batch, descriptions):
                img["caption"] = desc.strip() or img["filename"]
        except Exception:
            # This batch is best-effort — leave its filenames as
            # captions (already the default) and move on to the next
            # batch rather than abandoning everything after it.
            continue

    return images
