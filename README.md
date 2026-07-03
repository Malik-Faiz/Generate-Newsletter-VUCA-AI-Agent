# VUCA Newsletter Generator — Public Web App

This replaces the old "manual" workflow (opening a local Claude session and
running a Python script by hand) with a real client/server app:

- **frontend/index.html** — the upload UI (drag & drop report + slide
  images, pick topic/language/audience/tone, hit Generate). Same look and
  flow as your original local tool, cleaned up for public hosting.
- **backend/** — a Flask API that:
  1. reads your uploaded PDF/DOCX/TXT/MD report and any images
  2. sends the extracted text + your VUCA skill instructions to the
     Anthropic API (Claude) to write the newsletter content as structured
     JSON
  3. renders that JSON into three downloadable files: a styled HTML
     newsletter, a Word (.docx) version, and a one-page JPG infographic

## 1. Run it locally

```bash
cd backend
cp .env.example .env      # then edit .env and paste your free GROQ_API_KEY
./start_newsletter.sh     # creates a venv, installs deps, starts the server on :7755
```

Get a free key (no credit card) at https://console.groq.com/keys.

`app.py` reads `.env` automatically on startup (via the small `env_loader.py`
helper — no `python-dotenv` dependency needed) — you don't need to
manually export the variable in your terminal each time, on Windows or
otherwise. Just make sure `.env` exists in the `backend` folder before
running `python app.py`.

Then just open `frontend/index.html` directly in your browser (double-click
it — this uses a plain `file://` page, which is simplest and has no
moving parts). The Server URL box auto-detects this and points itself at
`http://localhost:7755`; you can also type in the URL manually and press
"Check" to confirm the dot turns green.

`/health` will tell you at a glance whether the API key is set and whether
`skill.md` loaded correctly.

### If you use VS Code's Live Server extension

Opening the frontend with **Live Server instead of double-clicking the
file** works too, but has one sharp edge: Live Server auto-reloads the
browser tab whenever it sees files change in the folder it's watching.
Every time `/generate` runs, the backend writes new files into
`backend/outputs/` — if Live Server is watching your whole project
folder, it treats that as a "change" and reloads the page **mid-request**,
wiping the result right as it's about to display.

Two things already handle this for you:
- `.vscode/settings.json` at the project root tells Live Server to ignore
  the `backend/` folder entirely, and to treat `frontend/` as its root —
  this works automatically as long as you open the **whole
  `vuca-newsletter-app` folder** in VS Code (not just `frontend/` on its
  own) before starting Live Server.
- The Server URL field also auto-detects Live Server's default ports
  (5500/5501) and known frontend dev-server ports, and points itself at
  the backend's `:7755` instead of wherever the page itself is being
  served from.

If you still see the page reload and lose the result, the simplest fix
is to just skip Live Server for this project and double-click
`frontend/index.html` directly.

### A note on Groq's free tier

This backend runs on **Groq's free tier** by default — no cost, but rate
limited (roughly 30 requests/minute, ~1,000 requests/day, and a tight
~8,000 tokens/minute budget on `openai/gpt-oss-120b` as of mid-2026 —
Groq deprecated `llama-3.3-70b-versatile` in June 2026 and this is their
recommended replacement; check https://console.groq.com/docs/rate-limits
for current numbers). `newsletter_ai.py` is tuned to stay inside that
budget: it strips code samples out of `skill.md` before sending it as
the system prompt, and truncates uploaded reports to `MAX_REPORT_CHARS`
(1,800 chars by default — small, since the current tuning trades report
verbatim-detail for newsletter length; see `.env.example` for the
trade-off explanation). If you hit 429 rate-limit errors, either wait
a minute between generations, shorten your reports, or upgrade to
Groq's paid Developer tier (adds a card, ~10x the limits, 25% cheaper
per token).

Image descriptions (see "Image placement" below) use a separate vision
model call — that runs against its own rate-limit pool, so it doesn't
eat into the main content-generation budget above.

Because Groq only serves open-source models, output quality/instruction-
following on this fairly demanding structured-JSON task is a step below
what you'd get from a frontier proprietary model — good enough for
testing and personal use, worth an eye on output quality before treating
it as production-grade for external readers. If you outgrow it, swapping
back to a paid provider only means editing `newsletter_ai.py` — the
`/generate` route, and the HTML/DOCX/infographic renderers, don't change.

## 2. Publish it for free (GitHub Pages + Render)

This is the tested, no-credit-card, free-forever path: **Render** runs
the backend, **GitHub Pages** serves the frontend, straight from the
repo you already pushed.

### Step 1 — Deploy the backend to Render

1. Go to [render.com](https://render.com) and sign up (GitHub login is
   fine — no card required).
2. Click **New → Blueprint**, and connect the GitHub repo you pushed
   this project to. Render will detect `render.yaml` at the repo root
   automatically and pre-fill the service config (build command, start
   command, health check path — all already set up for you).
3. When prompted for `GROQ_API_KEY` (marked as a secret in the
   blueprint, so Render asks for it rather than reading it from the
   repo), paste your real key.
4. Click **Apply**. First deploy takes a couple of minutes. When it's
   done, you'll get a URL like `https://vuca-newsletter-backend.onrender.com`.
5. Confirm it's alive by visiting `https://your-url.onrender.com/health`
   in a browser — you should see `"status":"ok"` and `"api_key_set":true`.

**One real limitation of Render's free tier:** the service spins down
after 15 minutes with no traffic, and takes ~30-60 seconds to wake back
up on the next request. So the *first* generation after a period of
inactivity will feel slow (or the health-check dot may briefly show
offline) — that's the free tier working as expected, not a bug. It
stays fast for subsequent requests until it goes idle again.

### Step 2 — Point the frontend at your backend

Open `frontend/index.html` (and `docs/index.html`, which is the copy
GitHub Pages actually serves — keep them in sync) and find this near
the top of the `<script>` block:

```javascript
const PRODUCTION_BACKEND_URL = "";
```

Paste in your Render URL from Step 1:

```javascript
const PRODUCTION_BACKEND_URL = "https://vuca-newsletter-backend.onrender.com";
```

Commit and push both files. This matters because GitHub Pages and
Render are two different domains — without this, the page would
default to calling itself instead of your backend. (Local development
with `file://` or Live Server still works untouched; this constant is
only used once the page is actually deployed somewhere.)

### Step 3 — Enable GitHub Pages

In your GitHub repo: **Settings → Pages → Source: Deploy from a
branch → Branch: `main`, folder: `/docs` → Save**.

After a minute or so, your app is live at
`https://your-username.github.io/your-repo-name/`.

### Step 4 — Test it end to end

Open that Pages URL, check the server status dot turns green (give it
30-60 seconds if Render's backend was asleep), then generate a
newsletter for real.

### Alternative: your own server

If you'd rather run this on your own VPS/domain instead of the free
path above:

- **backend/** — run behind a real WSGI server, not `python app.py`
  directly:
  ```bash
  pip install gunicorn
  gunicorn -w 2 -b 0.0.0.0:7755 app:app
  ```
  Put a reverse proxy (nginx / Caddy) in front of it with HTTPS, and set
  `GROQ_API_KEY` as a real environment variable — never commit it to a
  public repo. If this is genuinely public-facing, also add basic
  rate-limiting or an invite gate in front of `/generate` — Groq's
  free-tier daily cap is shared across every visitor hitting your
  backend, so a handful of concurrent users can exhaust it.
- **frontend/index.html** — a single static file; set
  `PRODUCTION_BACKEND_URL` the same way as Step 2 above if frontend and
  backend aren't on the same domain. CORS is already enabled
  (`flask-cors`), so cross-origin works — just make sure the backend is
  reachable over HTTPS if the frontend is served over HTTPS (mixed
  content will otherwise be blocked).

## 3. How the AI generation works

`backend/skill.md` is your original "VUCA Leadership Newsletter Generator"
agent skill markdown, unmodified — `newsletter_ai.py` strips its code
samples out (they're irrelevant here, since fixed renderers handle all
visual output) and sends the rest as the system prompt to Groq, along
with your uploaded report text, real AI-generated image descriptions
(see "Image placement" below), and the options you picked in the UI,
asking for the newsletter content back as one structured JSON object
(title, sections, VUCA blocks, playbook, stats, per-section image
assignments, etc — see `RESPONSE_SCHEMA_INSTRUCTIONS` in that file for
the exact shape).

That JSON is then handed to renderers that do NOT call the AI again —
they're deterministic, so the same content always looks the same:

- `docx_builder.py` → the downloadable Word document
- `infographic_builder.py` → the one-page JPG summary
- `frontend/index.html`'s `renderDocPreview()` → the on-page preview
  (pure JavaScript, no separate HTML file generated server-side)

If you want to change the visual design (colors, fonts, layout), edit
those files directly — no need to touch the AI prompt. If you want to
change what the AI writes about / how it reasons about your source
material, edit `skill.md` or the schema/instructions in
`newsletter_ai.py`.

## 4. Costs & model

The backend defaults to Groq's free tier running `openai/gpt-oss-120b`
— $0 per generation. You can override the model with the `GROQ_MODEL`
environment variable. See "A note on Groq's free tier" above for the
rate limits to expect, and the `MAX_SKILL_CHARS` / `MAX_REPORT_CHARS` /
`MAX_OUTPUT_TOKENS` env vars for tuning the prompt size if you hit them.

## 5. Image placement

Uploaded images aren't just scattered round-robin across sections —
`image_vision.py` sends them to Groq's vision model (`meta-llama/llama-4-scout-17b-16e-instruct`
by default, override with `GROQ_VISION_MODEL`) to get a real one-sentence
description of what each one actually shows. Those descriptions are fed
into the main content-generation prompt, and the model assigns each
image's filename to whichever section it's genuinely relevant to (via
each section's `relevant_images` field). `newsletter_ai.py` then
validates those assignments — dropping any hallucinated filenames and
resolving duplicate claims — before `docx_builder.py` places the actual
images in the Word document, and the frontend does the same in the
on-page preview (using the files you already uploaded, client-side, so
no image bytes need to round-trip through the backend for the preview).

If the vision call fails for any reason (rate limit, network hiccup),
this fails open: images fall back to being listed as unassigned and get
appended at the end of the document, rather than blocking the whole
generation.

## A note on dependencies

`requirements.txt` intentionally only lists four packages — Flask,
flask-cors, PyMuPDF, and Pillow — all of which ship precompiled wheels
for every recent Python version, including brand-new ones. Two things
that are normally third-party libraries were written from scratch
instead:

- **DOCX writing** (`docx_writer.py`) — a small pure-Python OOXML writer
  using only `zipfile` and the standard library, instead of
  `python-docx` (which depends on `lxml`, a compiled C extension without
  wheels for the newest Python releases).
- **Groq API calls** (`newsletter_ai.py`) — plain `urllib.request` HTTP
  calls to Groq's REST endpoint, instead of the `groq` SDK (which pulls
  in `pydantic`, `httpx`, and `anyio` — `pydantic-core` is a compiled
  Rust extension with the same wheel-availability problem).

Net effect: `pip install -r requirements.txt` never needs a C/C++ or
Rust compiler on your machine, on Windows or otherwise — it just
downloads ready-made wheels.

## Files reference

```
vuca-newsletter-app/
├── render.yaml                # Render blueprint — one-click free backend deploy
├── frontend/
│   └── index.html            # working copy of the upload page (edit this one)
├── docs/
│   └── index.html            # copy GitHub Pages actually serves — keep in sync
│                              # with frontend/index.html after edits
└── backend/
    ├── app.py                # Flask routes: /health, /generate, /outputs/*
    ├── env_loader.py          # tiny dependency-free .env file loader
    ├── newsletter_ai.py       # builds prompts, calls Groq API, retry logic
    ├── image_vision.py        # Groq vision model — real image descriptions
    ├── report_reader.py       # extracts text from pdf/docx/txt/md
    ├── docx_builder.py        # JSON → Word document (content/layout logic)
    ├── docx_writer.py         # pure-Python OOXML writer (no lxml)
    ├── infographic_builder.py # JSON → JPG infographic
    ├── skill.md                # your original agent skill instructions
    ├── requirements.txt
    ├── .env.example
    └── start_newsletter.sh     # local dev launcher
```
