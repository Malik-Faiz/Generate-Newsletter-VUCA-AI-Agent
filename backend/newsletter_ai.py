"""
newsletter_ai.py
─────────────────
Talks to the Google Gemini API to turn raw source material — report text
plus uploaded images — into a fully-structured VUCA Leadership newsletter,
returned as JSON. This structured JSON is then handed to docx_builder and
infographic_builder to produce the downloadable files, and rendered
directly in the frontend for the on-page preview.

Gemini has native multimodal input, so uploaded images are sent as real
inline image data in the SAME request that writes the newsletter — no
separate "vision pass" needed. The model sees the real pixels when
deciding which image belongs with which section.

The system prompt is derived from the "VUCA Leadership Newsletter
Generator" agent skill (skill.md in this folder) — the same instructions
that used to be followed manually inside a local Claude session are now
sent to the API directly.

NOTE ON COST: this uses Google AI Studio's free tier — genuinely free,
no credit card, no expiration. The real constraint is rate limits, not
tokens: roughly 10-15 requests/minute and 250-1,500 requests/day
depending on the model (check https://ai.google.dev/gemini-api/docs/rate-limits
for your project's actual current limits — Google has changed these
more than once). Since one generation is now just ONE API call (no
separate vision request), the rate gate in app.py only needs to keep
requests a few seconds apart, not the much longer wait Groq's shared
token budget used to require.
"""

import base64
import io
import json
import os
import re
import urllib.request
import urllib.error
from pathlib import Path

from PIL import Image

GEMINI_ENDPOINT_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SKILL_PATH = Path(__file__).parent / "skill.md"
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Gemini's 1M-token context window makes these generous defaults rather
# than tight survival constraints — raise them freely if you want longer
# newsletters or want more of a long report sent verbatim. The binding
# constraint on the free tier is requests-per-minute, not tokens.
MAX_SKILL_CHARS = int(os.environ.get("MAX_SKILL_CHARS", "20000"))       # skill.md is ~23KB raw; this comfortably fits the whole thing
MAX_REPORT_CHARS = int(os.environ.get("MAX_REPORT_CHARS", "30000"))     # roughly 15-20 pages of report text
MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "8000"))    # ~3,000-3,500 words of newsletter content

# Images are downsized before being sent — this controls request payload
# size and keeps things fast; Gemini doesn't need print-resolution input
# to understand what's in a slide or chart.
MAX_IMAGE_DIMENSION = int(os.environ.get("MAX_IMAGE_DIMENSION", "1200"))
IMAGE_JPEG_QUALITY = int(os.environ.get("IMAGE_JPEG_QUALITY", "80"))

TOPIC_LABELS = {
    "energy": "Energy & Oil Markets",
    "war": "Geopolitical & War Analysis",
    "psychology": "Human Behaviour & Psychology",
    "strategy": "Strategic Intelligence Briefing",
    "lessons": "Lessons Learned / Field Analysis",
    "custom": None,  # filled in from custom_topic
}

# Accent colour per topic family, matching skill.md's design guidance
TOPIC_ACCENTS = {
    "energy":     {"accent": "#B45309", "name": "amber"},
    "war":        {"accent": "#8B1A1A", "name": "red"},
    "psychology": {"accent": "#4A5E52", "name": "sage"},
    "strategy":   {"accent": "#1E3A52", "name": "steel"},
    "lessons":    {"accent": "#1E3A52", "name": "steel"},
    "custom":     {"accent": "#1E3A52", "name": "steel"},
}

_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)


def _condensed_skill_text() -> str:
    """
    Strips fenced code blocks (HTML/CSS/JS templates meant for a
    different, earlier pipeline) out of skill.md, keeping the prose
    instructions — with Gemini's large context window this is mostly a
    courtesy trim rather than a survival necessity.
    """
    if not SKILL_PATH.exists():
        return ""
    raw = SKILL_PATH.read_text(encoding="utf-8")
    stripped = _CODE_FENCE_RE.sub("", raw)
    stripped = re.sub(r"\n{3,}", "\n\n", stripped).strip()
    if len(stripped) > MAX_SKILL_CHARS:
        stripped = stripped[:MAX_SKILL_CHARS] + "\n\n[...skill excerpt truncated...]"
    return stripped


def _require_api_key() -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Get a free key (no credit card) at "
            "https://aistudio.google.com/apikey"
        )
    return api_key


def api_key_set() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def skill_loaded() -> bool:
    return SKILL_PATH.exists() and len(_condensed_skill_text()) > 200


RESPONSE_SCHEMA_INSTRUCTIONS = """
You must respond with ONE JSON object and nothing else — no markdown
fences, no commentary before or after. The JSON must match this shape
exactly:

{
  "title": "string — the newsletter's main headline",
  "subtitle": "string — one-line strapline under the title",
  "issue_label": "string, e.g. 'VUCA Leadership Intelligence — March 2026'",
  "accent_name": "one of: red, amber, sage, steel",
  "lead": "string — 5-7 substantive sentences setting the stakes, serif voice",
  "ticker_items": ["short punchy fact strings, 4-8 items"],
  "stats": [
    {"value": "string, e.g. '4.5T' or '38%'", "label": "short caption"}
    // 4 to 6 items
  ],
  "sections": [
    {
      "label": "monospace section tag, e.g. 'MARKET SIGNALS'",
      "title": "section heading",
      "paragraphs": ["3 to 5 substantive paragraphs of real analysis — each paragraph 4-6 sentences"],
      "bullets": ["3-5 concrete supporting points"],
      "pull_quote": "optional short standout quote string or null",
      "relevant_images": ["filenames of any uploaded images that genuinely relate to this section's topic — you were shown the actual images, so judge this from what they actually depict, not just their filename; omit or leave empty if none apply"]
    }
    // 6 to 7 sections total — this is the bulk of the newsletter,
    // treat each like a real article, not a summary blurb
  ],
  "vuca": [
    {
      "letter": "V", "word": "Volatility",
      "sub": "short definition phrase",
      "reality": "2-3 sentences, grounded in the source, with specifics",
      "response_title": "short framework name",
      "responses": ["4-5 concrete, actionable leadership responses"]
    },
    { "letter": "U", "word": "Uncertainty", ... },
    { "letter": "C", "word": "Complexity", ... },
    { "letter": "A", "word": "Ambiguity", ... }
  ],
  "playbook": [
    {"label": "01", "title": "short move title", "description": "2-3 sentences of real detail"}
    // 4 to 6 items
  ],
  "closing": {
    "left_title": "string", "left_text": "2-3 sentences",
    "right_title": "string", "right_text": "2-3 sentences"
  },
  "footer_source_note": "one sentence describing sourcing / methodology"
}

Every field must be filled with real, specific content derived from the
source material provided — never leave placeholders like "[TOPIC]" in
the output. If the source material is thin, use well-reasoned analysis
to fill gaps sensibly, but keep it grounded and avoid inventing
statistics that were not implied by the source.

Aim for roughly 3,000-3,500 words of total prose across all fields
combined — genuinely substantial, publication-quality depth. Do not pad
with filler; every sentence should add a fact, implication, or
recommendation.

If any images were included in this message, look at what they actually
show and assign each one's filename to the section it genuinely
illustrates via that section's "relevant_images" field. Never assign the
same image filename to more than one section, and never invent a
filename that wasn't actually provided.
"""


def build_system_prompt(language: str) -> str:
    skill_text = _condensed_skill_text()
    return (
        "You are the VUCA Leadership Newsletter agent. Use the following "
        "skill instructions to decide on content, structure, and tone "
        "(code/template samples have been stripped out — a separate "
        "fixed renderer handles all visual output, so focus entirely on "
        "writing sharp, specific, well-organised editorial content):\n\n"
        f"{skill_text}\n\n"
        "---\n"
        f"Write the entire newsletter in {language}. All JSON keys stay in "
        "English exactly as specified, but all string values (titles, "
        "body text, labels) must be written in the target language.\n\n"
        + RESPONSE_SCHEMA_INSTRUCTIONS
    )


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


def _downsize_for_gemini(image_bytes: bytes) -> bytes:
    """
    Shrinks an image to MAX_IMAGE_DIMENSION before sending it to Gemini.
    This only affects what's sent to the API — the original, full-quality
    bytes are still what gets embedded in the Word document later.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if max(img.size) > MAX_IMAGE_DIMENSION:
            scale = MAX_IMAGE_DIMENSION / max(img.size)
            img = img.resize(
                (max(1, int(img.size[0] * scale)), max(1, int(img.size[1] * scale))),
                Image.LANCZOS,
            )
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=IMAGE_JPEG_QUALITY)
        return buf.getvalue()
    except Exception:
        return image_bytes


def build_user_parts(
    topic_key: str,
    custom_topic: str,
    audience: str,
    tone: str,
    report_text: str,
    images: list[dict],
) -> list[dict]:
    """
    Returns a list of Gemini "parts" — a mix of text and inline_data
    (image) parts. Images are preceded by a text part stating the
    filename, so the model can both see the image and know which
    filename to use if it assigns that image to a section.
    """
    topic_label = TOPIC_LABELS.get(topic_key) or custom_topic or "General Intelligence Briefing"

    intro = [
        f"TOPIC TEMPLATE: {topic_label}",
        f"TARGET AUDIENCE: {audience}",
        f"TONE: {tone}",
    ]

    if report_text.strip():
        trimmed = report_text.strip()
        if len(trimmed) > MAX_REPORT_CHARS:
            trimmed = trimmed[:MAX_REPORT_CHARS] + "\n\n[...source truncated...]"
        intro.append("SOURCE MATERIAL (extracted text):\n" + trimmed)
    else:
        intro.append(
            "No source document was uploaded. Base the newsletter on "
            "well-reasoned, general analytical knowledge of the topic "
            "template and target audience above."
        )

    parts: list[dict] = [{"text": "\n\n".join(intro)}]

    if images:
        parts.append(
            {
                "text": (
                    f"\n\n{len(images)} image(s) follow, each preceded by its "
                    "filename. Look at what each one actually shows when "
                    "deciding relevant_images for your sections."
                )
            }
        )
        for img in images:
            parts.append({"text": f'Filename: "{img["filename"]}"'})
            vision_bytes = _downsize_for_gemini(img["bytes"])
            parts.append(
                {
                    "inline_data": {
                        "mime_type": _mime_for(vision_bytes),
                        "data": base64.b64encode(vision_bytes).decode("ascii"),
                    }
                }
            )

    parts.append(
        {
            "text": (
                "\n\nNow produce the full newsletter as a single JSON "
                "object per the schema you were given."
            )
        }
    )
    return parts


def _call_gemini(system_prompt: str, user_parts: list[dict], max_tokens: int) -> str:
    api_key = _require_api_key()
    endpoint = GEMINI_ENDPOINT_TEMPLATE.format(model=MODEL)

    payload = json.dumps(
        {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": user_parts}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            },
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
            "User-Agent": "vuca-newsletter-app/1.0 (+https://github.com)",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(error_body)
            message = parsed.get("error", {}).get("message", error_body)
        except json.JSONDecodeError:
            message = error_body
        if e.code in (400, 403) and "api key" in message.lower():
            raise RuntimeError(f"Gemini API error ({e.code}): Invalid API key. {message}")
        if e.code == 429:
            raise RuntimeError(
                f"Gemini rate limit hit: {message}. Free tier is limited to a "
                "handful of requests per minute — wait a moment and try again."
            )
        raise RuntimeError(f"Gemini API error ({e.code}): {message}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach Gemini API: {e.reason}")

    try:
        candidate = body["candidates"][0]
        finish_reason = candidate.get("finishReason", "")
        text_parts = [p["text"] for p in candidate["content"]["parts"] if "text" in p]
        text = "".join(text_parts)
        if finish_reason == "MAX_TOKENS" and not text.strip().endswith("}"):
            # Cut off mid-object — treat the same as a JSON parse failure
            # so the caller's retry logic kicks in.
            raise json.JSONDecodeError("Truncated at MAX_TOKENS", text, len(text))
        return text
    except (KeyError, IndexError) as e:
        # Common cause: the prompt was blocked by safety filters, in which
        # case candidates may be empty and promptFeedback explains why.
        feedback = body.get("promptFeedback", {})
        if feedback.get("blockReason"):
            raise RuntimeError(
                f"Gemini blocked this request: {feedback.get('blockReason')}. "
                "Try different source material."
            )
        raise RuntimeError(f"Unexpected Gemini response shape: {e}. Body: {body}")


_FALLBACK_LENGTH_OVERRIDE = """

IMPORTANT — LENGTH OVERRIDE: your previous attempt did not return
complete, valid JSON (likely cut off before finishing). This time,
write shorter: only 4 sections (not 6-7) with 2-3 paragraphs each,
3 responses per VUCA block, 3 playbook items. Total prose across all
fields should be roughly 1,200-1,500 words. Completing a valid,
properly-closed JSON object matters far more than length.
"""


def _parse_json_response(raw_text: str) -> dict:
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.lower().startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()
    return json.loads(raw_text)


def _reconcile_image_assignments(content: dict, images: list[dict]) -> None:
    """
    Mutates content in place: validates each section's relevant_images
    against filenames that were actually uploaded (drops hallucinated
    ones), and ensures no image is claimed by more than one section
    (first section wins). Any uploaded image the model didn't assign
    anywhere gets listed in content["_unassigned_images"] so the caller
    can still include it (e.g. appended at the end of the document)
    rather than silently dropping it.
    """
    valid_filenames = {img["filename"] for img in images}
    claimed = set()
    sections = content.get("sections") or []

    for sec in sections:
        if not isinstance(sec, dict):
            continue
        raw = sec.get("relevant_images") or []
        if not isinstance(raw, list):
            raw = []
        kept = []
        for fname in raw:
            if fname in valid_filenames and fname not in claimed:
                kept.append(fname)
                claimed.add(fname)
        sec["relevant_images"] = kept

    content["_unassigned_images"] = [
        img["filename"] for img in images if img["filename"] not in claimed
    ]


def generate_newsletter_content(
    topic_key: str,
    custom_topic: str,
    language: str,
    audience: str,
    tone: str,
    report_text: str,
    image_descriptions: list[dict],
) -> dict:
    """
    Calls the Gemini API and returns the parsed newsletter JSON dict.

    `image_descriptions` is named this way for backward compatibility
    with app.py's call site, but each entry's actual image bytes (not
    just a text description) get sent to Gemini directly — see
    build_user_parts(). The dicts just need "filename" and "bytes".

    If the model's response doesn't parse as valid JSON (e.g. it got cut
    off before finishing), this retries once with a much smaller ask so
    the person gets a shorter but complete newsletter instead of a hard
    failure.
    """
    images = image_descriptions  # kept the parameter name for app.py compatibility
    system_prompt = build_system_prompt(language)
    user_parts = build_user_parts(
        topic_key, custom_topic, audience, tone, report_text, images
    )

    try:
        raw_text = _call_gemini(system_prompt, user_parts, MAX_OUTPUT_TOKENS)
        content = _parse_json_response(raw_text)
    except json.JSONDecodeError:
        fallback_system_prompt = system_prompt + _FALLBACK_LENGTH_OVERRIDE
        raw_text = _call_gemini(fallback_system_prompt, user_parts, MAX_OUTPUT_TOKENS)
        try:
            content = _parse_json_response(raw_text)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Model did not return valid JSON, even after a shorter retry: {e}. "
                f"Raw start: {raw_text[:300]}"
            )

    _reconcile_image_assignments(content, images)

    if not content.get("accent_name"):
        content["accent_name"] = TOPIC_ACCENTS.get(topic_key, TOPIC_ACCENTS["strategy"])["name"]

    content["_topic_key"] = topic_key
    content["_accent_hex"] = TOPIC_ACCENTS.get(topic_key, TOPIC_ACCENTS["strategy"])["accent"]

    return content
