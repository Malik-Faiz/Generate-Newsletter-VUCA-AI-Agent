"""
image_vision.py
─────────────────
Uses Groq's vision-capable model (Llama 4 Scout) to actually look at
each uploaded image and describe what's in it. Those descriptions then
get fed into the main newsletter-writing prompt so the AI can assign
each image to the section it's actually relevant to, instead of just
scattering images round-robin by filename.

Groq's vision endpoint accepts up to 5 images per request, so images
are batched in groups of 5 to minimise API calls.
"""

import base64
import json
import os
import urllib.error
import urllib.request

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
MAX_IMAGES_PER_CALL = 5


def _require_api_key() -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set.")
    return api_key


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
                "each one, write a single concise sentence (max 20 words) "
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
        b64 = base64.b64encode(img["bytes"]).decode("ascii")
        mime = _mime_for(img["bytes"])
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
    AI-generated description of the image content. If the vision call
    fails for any reason (rate limit, network, no key), falls back to
    the filename as the caption so the rest of the pipeline still works
    — this is a nice-to-have, not a hard dependency.
    """
    if not images:
        return images

    try:
        for i in range(0, len(images), MAX_IMAGES_PER_CALL):
            batch = images[i : i + MAX_IMAGES_PER_CALL]
            descriptions = _describe_batch(batch)
            for img, desc in zip(batch, descriptions):
                img["caption"] = desc.strip() or img["filename"]
        return images
    except Exception:
        # Vision is best-effort. On any failure, leave filenames as
        # captions (already the default) and let the rest of the
        # pipeline proceed with round-robin-style placement instead.
        return images
