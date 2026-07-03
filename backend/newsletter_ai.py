"""
newsletter_ai.py
─────────────────
Talks to Groq (free tier, OpenAI-compatible, runs open-source models on
Groq's LPU hardware) to turn raw source material (report text + real
AI-generated image descriptions) into a fully-structured VUCA Leadership
newsletter, returned as JSON. This structured JSON is then handed to
docx_builder and infographic_builder to produce the downloadable files,
and rendered directly in the frontend for the on-page preview.

The system prompt is derived from the "VUCA Leadership Newsletter
Generator" agent skill (skill.md in this folder) — the same instructions
that used to be followed manually inside a local Claude session are now
sent to the API directly.

NOTE ON GROQ'S FREE TIER: rate limits are tight and vary by model —
openai/gpt-oss-120b (the current default; Groq deprecated
llama-3.3-70b-versatile in June 2026) gets roughly 30 requests/min,
~8,000 tokens/min, ~1,000 requests/day as of mid-2026 — check
https://console.groq.com/docs/rate-limits for current numbers. To stay
comfortably inside the per-minute token budget, this module sends a
condensed version of skill.md (code samples stripped out, since they're
irrelevant to JSON content generation) and truncates the uploaded report
more aggressively than a paid-API setup would need to.
"""

import json
import os
import re
import urllib.request
import urllib.error
from pathlib import Path

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

SKILL_PATH = Path(__file__).parent / "skill.md"
# llama-3.3-70b-versatile was deprecated by Groq on June 17, 2026.
# openai/gpt-oss-120b is Groq's official recommended replacement — it
# supports the same json_object structured-output mode used here.
MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

# Keep the system + user prompt comfortably under Groq free-tier TPM caps.
MAX_SKILL_CHARS = int(os.environ.get("MAX_SKILL_CHARS", "1500"))
MAX_REPORT_CHARS = int(os.environ.get("MAX_REPORT_CHARS", "1800"))
MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "5500"))

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
    Strips fenced code blocks (HTML/CSS/JS templates meant for a different
    pipeline) out of skill.md, keeping the prose instructions — this is
    what actually matters for writing the JSON content — then truncates
    to MAX_SKILL_CHARS to fit Groq's free-tier token budget.
    """
    if not SKILL_PATH.exists():
        return ""
    raw = SKILL_PATH.read_text(encoding="utf-8")
    stripped = _CODE_FENCE_RE.sub("", raw)
    stripped = re.sub(r"\n{3,}", "\n\n", stripped).strip()
    if len(stripped) > MAX_SKILL_CHARS:
        stripped = stripped[:MAX_SKILL_CHARS] + "\n\n[...skill excerpt truncated for token budget...]"
    return stripped


def _require_api_key() -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Export it before starting the server. "
            "Get a free key at https://console.groq.com/keys"
        )
    return api_key


def api_key_set() -> bool:
    return bool(os.environ.get("GROQ_API_KEY"))


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
  "lead": "string — 4-6 substantive sentences setting the stakes, serif voice",
  "ticker_items": ["short punchy fact strings, 4-6 items"],
  "stats": [
    {"value": "string, e.g. '4.5T' or '38%'", "label": "short caption"}
    // 4 to 5 items
  ],
  "sections": [
    {
      "label": "monospace section tag, e.g. 'MARKET SIGNALS'",
      "title": "section heading",
      "paragraphs": ["3 to 4 substantive paragraphs of real analysis — each paragraph 4-6 sentences"],
      "bullets": ["2-4 concrete supporting points"],
      "pull_quote": "optional short standout quote string or null",
      "relevant_images": ["filenames of any uploaded images that genuinely relate to this section's topic — omit or leave empty if none apply; see the UPLOADED IMAGES list for what each one shows"]
    }
    // 5 sections total — this is the bulk of the newsletter,
    // treat each like a real article, not a summary blurb
  ],
  "vuca": [
    {
      "letter": "V", "word": "Volatility",
      "sub": "short definition phrase",
      "reality": "2 sentences, grounded in the source, with specifics",
      "response_title": "short framework name",
      "responses": ["3-4 concrete, actionable leadership responses"]
    },
    { "letter": "U", "word": "Uncertainty", ... },
    { "letter": "C", "word": "Complexity", ... },
    { "letter": "A", "word": "Ambiguity", ... }
  ],
  "playbook": [
    {"label": "01", "title": "short move title", "description": "1-2 sentences of real detail"}
    // 3 to 4 items
  ],
  "closing": {
    "left_title": "string", "left_text": "1-2 sentences",
    "right_title": "string", "right_text": "1-2 sentences"
  },
  "footer_source_note": "one sentence describing sourcing / methodology"
}

Every field must be filled with real, specific content derived from the
source material provided — never leave placeholders like "[TOPIC]" in
the output. If the source material is thin, use well-reasoned analysis
to fill gaps sensibly, but keep it grounded and avoid inventing
statistics that were not implied by the source.

Aim for roughly 2,200-2,600 words of total prose across all fields
combined — substantial and specific, not padded, but sized to fit
comfortably within your output budget.

CRITICAL: you have a hard output token limit. A complete, well-formed
JSON object that hits the shorter end of the length guidance is far
better than a longer one that runs out of room and gets cut off
mid-object — an incomplete JSON response will be rejected entirely. If
you sense you are running low on space, shorten remaining fields and
make sure every brace and bracket is properly closed before you stop.
Never sacrifice valid, complete JSON for extra length.
"""


def build_system_prompt(language: str) -> str:
    skill_text = _condensed_skill_text()
    return (
        "You are the VUCA Leadership Newsletter agent. Use the following "
        "condensed skill instructions to decide on content, structure, "
        "and tone (code/template samples have been stripped out — a "
        "separate fixed renderer handles all visual output, so focus "
        "entirely on writing sharp, specific, well-organised editorial "
        "content):\n\n"
        f"{skill_text}\n\n"
        "---\n"
        f"Write the entire newsletter in {language}. All JSON keys stay in "
        "English exactly as specified, but all string values (titles, "
        "body text, labels) must be written in the target language.\n\n"
        + RESPONSE_SCHEMA_INSTRUCTIONS
    )


def build_user_prompt(
    topic_key: str,
    custom_topic: str,
    audience: str,
    tone: str,
    report_text: str,
    image_descriptions: list[dict],
) -> str:
    topic_label = TOPIC_LABELS.get(topic_key) or custom_topic or "General Intelligence Briefing"

    parts = [
        f"TOPIC TEMPLATE: {topic_label}",
        f"TARGET AUDIENCE: {audience}",
        f"TONE: {tone}",
    ]

    if image_descriptions:
        lines = "\n".join(
            f'- filename: "{img["filename"]}" — shows: {img.get("caption", "")}'
            for img in image_descriptions
        )
        parts.append(
            "UPLOADED IMAGES (these have been analysed — each line tells "
            "you what the image actually shows). For each section in your "
            "JSON output, set that section's \"relevant_images\" field to "
            "the filename(s) of any images whose content genuinely relates "
            "to that section's topic — copy the filename exactly as shown "
            "below. Most sections may have zero relevant images; only "
            "assign an image where there's a real thematic match. Never "
            "assign the same image to more than one section.\n" + lines
        )

    if report_text.strip():
        trimmed = report_text.strip()
        if len(trimmed) > MAX_REPORT_CHARS:
            trimmed = trimmed[:MAX_REPORT_CHARS] + "\n\n[...source truncated for token budget...]"
        parts.append("SOURCE MATERIAL (extracted text):\n" + trimmed)
    else:
        parts.append(
            "No source document was uploaded. Base the newsletter on "
            "well-reasoned, general analytical knowledge of the topic "
            "template and target audience above."
        )

    parts.append(
        "Now produce the full newsletter as a single JSON object per the "
        "schema you were given."
    )
    return "\n\n".join(parts)


class GroqIncompleteJsonError(RuntimeError):
    """Raised when Groq's json_object mode rejects a response because the
    model ran out of output tokens before finishing the JSON object."""
    pass


def _call_groq(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    api_key = _require_api_key()
    payload = json.dumps(
        {
            "model": MODEL,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
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
            # Groq's API sits behind Cloudflare, which blocks urllib's
            # default "Python-urllib/x.y" User-Agent as bot traffic
            # (Cloudflare error 1010). A normal-looking UA avoids that.
            "User-Agent": "vuca-newsletter-app/1.0 (+https://github.com)",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(error_body)
            message = parsed.get("error", {}).get("message", error_body)
        except json.JSONDecodeError:
            message = error_body
        if e.code == 429:
            raise RuntimeError(
                f"Groq rate limit hit: {message}. Wait a minute and try again, "
                "or lower MAX_REPORT_CHARS / MAX_OUTPUT_TOKENS."
            )
        if e.code == 400 and "failed to generate json" in message.lower():
            # The model ran out of max_tokens mid-object; Groq's json_object
            # mode refuses to return the truncated result. This is
            # recoverable — generate_newsletter_content retries once with
            # a smaller ask.
            raise GroqIncompleteJsonError(message)
        raise RuntimeError(f"Groq API error ({e.code}): {message}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach Groq API: {e.reason}")

    try:
        return body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Groq response shape: {e}. Body: {body}")


_FALLBACK_LENGTH_OVERRIDE = """

IMPORTANT — LENGTH OVERRIDE: your previous attempt ran out of output
space before finishing valid JSON. This time, write MUCH shorter: only
3 sections (not 4) with 1-2 short paragraphs each, 2-3 responses per
VUCA block, 3 playbook items. Total prose across all fields should be
roughly 600-800 words. Completing a valid, properly-closed JSON object
matters far more than length — be terse.
"""


def _parse_json_response(raw_text: str) -> dict:
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.lower().startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()
    return json.loads(raw_text)


def _reconcile_image_assignments(content: dict, image_descriptions: list[dict]) -> None:
    """
    Mutates content in place: validates each section's relevant_images
    against filenames that were actually uploaded (drops hallucinated
    ones), and ensures no image is claimed by more than one section
    (first section wins). Any uploaded image the model didn't assign
    anywhere gets listed in content["_unassigned_images"] so the caller
    can fall back to round-robin placement for those specifically,
    rather than silently dropping them.
    """
    valid_filenames = {img["filename"] for img in image_descriptions}
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
        img["filename"] for img in image_descriptions if img["filename"] not in claimed
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
    Calls the Groq API and returns the parsed newsletter JSON dict.

    If the model runs out of its output-token budget mid-object (Groq
    rejects this outright in json_object mode), this automatically
    retries once with a much smaller ask so the person doesn't just see
    a hard failure — they get a shorter but complete newsletter instead.
    """
    system_prompt = build_system_prompt(language)
    user_prompt = build_user_prompt(
        topic_key, custom_topic, audience, tone, report_text, image_descriptions
    )

    try:
        raw_text = _call_groq(system_prompt, user_prompt, MAX_OUTPUT_TOKENS)
        content = _parse_json_response(raw_text)
    except (GroqIncompleteJsonError, json.JSONDecodeError):
        # Retry once with a deliberately smaller ask — same input, a
        # stricter length instruction appended to the system prompt.
        fallback_system_prompt = system_prompt + _FALLBACK_LENGTH_OVERRIDE
        raw_text = _call_groq(fallback_system_prompt, user_prompt, MAX_OUTPUT_TOKENS)
        try:
            content = _parse_json_response(raw_text)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Model did not return valid JSON, even after a shorter retry: {e}. "
                f"Raw start: {raw_text[:300]}"
            )

    _reconcile_image_assignments(content, image_descriptions)

    # Fill sensible defaults / accent colour fallback.
    if not content.get("accent_name"):
        content["accent_name"] = TOPIC_ACCENTS.get(topic_key, TOPIC_ACCENTS["strategy"])["name"]

    content["_topic_key"] = topic_key
    content["_accent_hex"] = TOPIC_ACCENTS.get(topic_key, TOPIC_ACCENTS["strategy"])["accent"]

    return content

