# VUCA Leadership Newsletter Generator — Agent Skill

## Overview

This skill enables you to generate professional VUCA Leadership newsletters from any source material: PDF reports, PPTX presentations, DOCX documents, raw text, or live web intelligence. The output can be an **HTML newsletter** (for email / web display) or a **Word DOCX file** (for distribution / printing), with embedded images from slide decks when available.

This skill was developed and refined across 10+ real newsletter productions covering:
- Iran War energy crisis intelligence
- Algorithmic warfare analysis
- Human behaviour and loneliness research
- Global energy market briefings
- Geopolitical scenario analysis (Managed Instability)
- War lessons learned from 30-day field analysis

---

## Agent Instructions

When the user provides source material and asks for a VUCA newsletter, follow this exact process:

---

## Step 1 — Read and Parse the Source Material

### If the input is a `.docx` file:
```bash
pandoc /path/to/file.docx -t plain
```

### If the input is a `.pdf` file:
The PDF may already be rendered visually (e.g. a slide deck exported to PDF). Check page count first:
```bash
python3 -c "
from pdf2image import convert_from_path
pages = convert_from_path('/path/to/file.pdf', dpi=72)
print(f'{len(pages)} pages')
"
```
Extract text:
```bash
pdftotext /path/to/file.pdf -
```

### If the input is a `.pptx` file:
Convert to PDF first, then to slide images:
```bash
python /path/to/soffice.py --headless --convert-to pdf /path/to/file.pptx --outdir /home/claude/

python3 -c "
from pdf2image import convert_from_path
import os
pages = convert_from_path('/home/claude/file.pdf', dpi=150)
os.makedirs('/home/claude/slides', exist_ok=True)
for i, page in enumerate(pages):
    page.save(f'/home/claude/slides/slide_{i+1:02d}.png', 'PNG')
    print(f'slide_{i+1:02d}: {page.size}')
print(f'Total: {len(pages)} slides')
"
```

### If the input is a `.txt` file:
Read directly — no conversion needed.

### If there is no input file (current events brief):
Use web search to gather 4–6 current high-quality signals relevant to the topic, then proceed.

---

## Step 2 — Analyse Content Structure

After reading the source, identify:

1. **Core theme** — what is the main subject? (energy crisis / geopolitics / human behaviour / war analysis / market intelligence)
2. **VUCA mapping** — how does the content map to V, U, C, A? Find at least one concrete example per dimension
3. **Key statistics** — extract 4–8 numbers/metrics that can appear as visual stat blocks
4. **Section structure** — identify 4–7 major topics that become newsletter sections
5. **Slide assignment** — if slides are available, assign 1–2 slides per section thematically
6. **Leadership prescriptions** — extract or derive 5–7 actionable leadership responses

---

## Step 3 — Choose Output Format

| Format | When to use | Tool |
|--------|-------------|------|
| **HTML** | Web display, email, browser reading | Create `.html` file |
| **DOCX** | Word document, printing, distribution | Use `docx` npm package |
| **Both** | When user wants both formats | Generate HTML first, then DOCX |

Default: **HTML** unless user specifies Word/docx or the source contains slides to embed.

---

## Step 4A — Generate HTML Newsletter

### Design System

Every HTML newsletter uses this consistent visual language:

```css
/* Core palette — adjust accent colors per topic */
:root {
  --bg:    #f2efe9;    /* warm paper background */
  --paper: #faf8f4;    /* card background */
  --ink:   #0f0f0f;    /* primary text */
  --deep:  #111827;    /* masthead/dark sections */
  --red:   #b91c1c;    /* danger / conflict topics */
  --amber: #b45309;    /* energy / economics */
  --teal:  #1e3a5f;    /* stability / strategy */
  --gold:  #d97706;    /* opportunity / winners */
  --mist:  #6b7280;    /* secondary text */
}
```

**Adapt accent colors to topic:**
- War / conflict → red dominant (`#8B1A1A`)
- Energy / economics → amber dominant (`#B06000`)
- Human / psychology → sage/warm dominant (`#4A5E52`)
- Geopolitics / strategy → steel/navy dominant (`#1E3A52`)

### Required HTML Sections (in order)

```
1. MASTHEAD
   - Dark background banner
   - Newsletter name + subtitle
   - Live status indicator (pulsing dot for crisis topics)
   - Issue number + date
   - Tagline deck

2. TICKER / ALERT BAR
   - Scrolling or static highlights strip
   - Color: topic accent (red for crisis, amber for energy)

3. LEAD SECTION
   - Serif large text (Lora / Newsreader / Instrument Serif)
   - Sets the stakes in 3–4 sentences
   - Contains bold key phrase and italic hook

4. SECTION HEADERS
   - Format: "01 //" + H2 title
   - Always with bottom border rule

5. CONTENT SECTIONS (repeat per major topic)
   - Section label (monospace caps)
   - Heading
   - Body text (prose, not just bullets)
   - Data tables where appropriate
   - Stat cards / metric grids
   - Pull quotes for key statements
   - Callout boxes for warnings / insights

6. VUCA FRAMEWORK BLOCK
   - Dark banner intro for VUCA section
   - 2×2 grid: V, U, C, A blocks
   - Each block: Letter (large) + Word + Subtitle + Reality box + Response bullets

7. LEADERSHIP PLAYBOOK
   - Dark background
   - 3-column grid of moves/prescriptions
   - Each: numbered label + title + description

8. CLOSING CELLS
   - 2-column dark/light split
   - Synthesises the core insight

9. FOOTER
   - Dark background
   - Source attribution
   - Newsletter metadata
```

### HTML Template Structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>[TOPIC] — VUCA Leadership [DATE]</title>
<link href="https://fonts.googleapis.com/css2?family=[SERIF]:ital,wght@...&family=[SANS]:wght@...&family=[MONO]:wght@...&display=swap" rel="stylesheet">
<style>
  /* Full CSS with :root variables, all component styles, responsive */
</style>
</head>
<body>
  <!-- MASTHEAD -->
  <!-- TICKER -->
  <div class="container">
    <!-- LEAD -->
    <!-- SECTIONS 01–N -->
    <!-- VUCA BANNER (dark) -->
    <!-- VUCA GRID (2x2) -->
    <!-- PLAYBOOK -->
    <!-- CLOSING -->
  </div>
  <!-- FOOTER -->
</body>
</html>
```

### Font Pairing Guide

| Topic Style | Serif | Sans | Mono |
|-------------|-------|------|------|
| Intelligence / Crisis | Bebas Neue (display) | IBM Plex Sans | IBM Plex Mono |
| Geopolitical / Strategic | Syne (display) | Barlow | Barlow Mono |
| Philosophical / Human | Cormorant Garamond | Jost | Jost Mono |
| Financial / Energy | Fraunces | Space Grotesk | Space Mono |
| Classic Editorial | Playfair Display | DM Sans | DM Mono |

### VUCA Block HTML Pattern

```html
<div class="vuca-blocks">
  <div class="vuca-block" data-l="V">
    <span class="vuca-letter">V</span>
    <span class="vuca-word">Volatility</span>
    <span class="vuca-sub">Rapid, unstable, unpredictable change</span>
    <div class="vuca-reality">
      <strong>Today's Reality:</strong> [specific crisis fact from source]
    </div>
    <span class="response-label">Leadership Response: [Framework Name]</span>
    <ul>
      <li>[Actionable response 1]</li>
      <li>[Actionable response 2]</li>
      <li>[Actionable response 3]</li>
      <li>[Actionable response 4]</li>
    </ul>
  </div>
  <!-- Repeat for U, C, A -->
</div>
```

### VUCA Framework Mapping Rules

For each dimension, always follow this structure:

| Dimension | Maps to | Leadership Response |
|-----------|---------|---------------------|
| **V** Volatility | Speed/magnitude of change in source | Vision + Robustness + Scenario Planning |
| **U** Uncertainty | Unpredictability / failed forecasting in source | Intelligence Systems + Epistemic Humility + Optionality |
| **C** Complexity | Interconnected cascades in source | Systems Thinking + Cross-domain Integration + Simplification |
| **A** Ambiguity | Contradictory signals / multiple valid readings | Adaptive Execution + Framing Discipline + Experimentation |

---

## Step 4B — Generate DOCX Newsletter

Use when slides need to be embedded, or user explicitly wants Word format.

### Setup

```bash
npm list -g docx || npm install -g docx
```

### Document Architecture

```javascript
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  ImageRun, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, LevelFormat, PageBreak
} = require('docx');
const fs = require('fs'), path = require('path');
```

### Page Setup (always US Letter)

```javascript
sections: [{
  properties: {
    page: {
      size: { width: 12240, height: 15840 },
      margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 }
    }
  }
}]
```

Content width = `12240 - 2160 = 9360 DXA`

### Slide Image Embedding

```javascript
function slideBlock(n, caption, slideDir = '/home/claude/slides') {
  const data = fs.readFileSync(path.join(slideDir, `slide_${String(n).padStart(2,'0')}.png`));
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 160, after: 80 },
      children: [new ImageRun({
        data,
        transformation: { width: 610, height: 343 }, // 16:9 ratio in px
        type: "png"
      })]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 200 },
      children: [new TextRun({ text: caption, font: "Arial", size: 17, italics: true, color: "666666" })]
    })
  ];
}
```

### Slide Assignment Strategy

Distribute slides across sections thematically:
- Slide 1 → Cover / Masthead area
- Slide 2 → Executive Summary
- Slides 3–4 → Section 1 (2 slides per major section)
- Slides 5–6 → Section 2
- Slides 7–9 → Section 3 (if more content)
- Slides 10–11 → Section 4
- Slides 12–13 → Section 5 / VUCA Summary
- Slide 14 → Conclusion / Closing

### Critical DOCX Rules

```
✅ Always use ShadingType.CLEAR (never SOLID — causes black backgrounds)
✅ Always set both columnWidths array AND cell width (dual width requirement)
✅ Use LevelFormat.BULLET with numbering config (never unicode • characters)
✅ PageBreak must be inside a Paragraph (never standalone)
✅ Always specify ImageRun type: "png" or "jpg"
✅ Table column widths must sum exactly to table width
✅ Use WidthType.DXA everywhere (PERCENTAGE breaks in Google Docs)
✅ Cell margins: { top: 80, bottom: 80, left: 120, right: 120 }
```

### Core DOCX Helper Functions

```javascript
// Section tag header
function tag(text, color = "#8B1A1A") {
  return new Paragraph({
    spacing: { before: 0, after: 80 },
    children: [
      new TextRun({ text: "▌ ", font: "Arial", size: 18, color }),
      new TextRun({ text: text.toUpperCase(), font: "Arial", size: 18, bold: true, color, characterSpacing: 80 })
    ]
  });
}

// Dark cover banner
function coverBanner(title, subtitle, accent) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    rows: [new TableRow({ children: [
      new TableCell({
        borders: { top: NB, bottom: NB, left: NB, right: NB },
        shading: { fill: "0B1927", type: ShadingType.CLEAR },
        margins: { top: 300, bottom: 300, left: 400, right: 400 },
        children: [
          new Paragraph({ alignment: AlignmentType.CENTER, children: [
            new TextRun({ text: "VUCA LEADERSHIP INTELLIGENCE", font: "Arial", size: 18, bold: true, color: "888888", characterSpacing: 100 })
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80 }, children: [
            new TextRun({ text: title, font: "Arial", size: 52, bold: true, color: "FFFFFF" })
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60 }, children: [
            new TextRun({ text: subtitle, font: "Arial", size: 32, bold: true, italics: true, color: accent })
          ]}),
        ]
      })
    ]})]
  });
}

// Stats row (4 metrics)
function statsRow(items) {
  const w = Math.floor(9360 / items.length);
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: items.map(() => w),
    rows: [new TableRow({ children: items.map(it =>
      new TableCell({
        borders: { /* thin borders */ },
        width: { size: w, type: WidthType.DXA },
        shading: { fill: "F2EFE9", type: ShadingType.CLEAR },
        margins: { top: 100, bottom: 100, left: 120, right: 120 },
        children: [
          new Paragraph({ alignment: AlignmentType.CENTER, children: [
            new TextRun({ text: it.val, font: "Arial", size: 42, bold: true, color: "8B1A1A" })
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 40 }, children: [
            new TextRun({ text: it.lbl, font: "Arial", size: 17, color: "666666" })
          ]})
        ]
      })
    )})]
  });
}

// VUCA block (dark left letter + content right)
function vucaBlock(letter, word, sub, reality, responses, bg, accent) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [1280, 8080],
    rows: [new TableRow({ children: [
      new TableCell({
        // Dark panel with large letter
        shading: { fill: "0B1927", type: ShadingType.CLEAR },
        children: [
          new Paragraph({ alignment: AlignmentType.CENTER, children: [
            new TextRun({ text: letter, font: "Arial", size: 84, bold: true, color: accent })
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, children: [
            new TextRun({ text: word, font: "Arial", size: 21, bold: true, color: "FFFFFF" })
          ]}),
        ]
      }),
      new TableCell({
        // Content panel
        shading: { fill: bg, type: ShadingType.CLEAR },
        children: [
          new Paragraph({ children: [new TextRun({ text: "Current Reality:", bold: true, color: accent })]}),
          new Paragraph({ children: [new TextRun({ text: reality, italics: true, color: "444444" })]}),
          new Paragraph({ children: [new TextRun({ text: "Leadership Response:", bold: true, color: "0B4F3E" })]}),
          ...responses.map(r => new Paragraph({
            numbering: { reference: "bullets", level: 0 },
            children: [new TextRun({ text: r })]
          }))
        ]
      })
    ]})]
  });
}
```

### Validation

Always validate before presenting:

```bash
python /mnt/skills/public/docx/scripts/office/validate.py /path/to/output.docx
```

Expected output:
```
Paragraphs: 0 → N (+N)
All validations PASSED!
```

If validation fails:
```bash
python /mnt/skills/public/docx/scripts/office/unpack.py output.docx unpacked/
# Fix XML issues (usually element ordering in w:pPr)
python /mnt/skills/public/docx/scripts/office/pack.py unpacked/ output.docx --original output.docx
```

---

## Step 5 — Content Writing Rules

### The VUCA Newsletter Voice

```
✅ Analytical but accessible
✅ Specific — cite numbers, names, dates from source
✅ Action-oriented — every section ends with what to DO
✅ Honest about uncertainty — distinguish known from assumed
✅ Geopolitically aware — understand second-order effects
✅ Leadership-focused — always tie analysis back to decisions
```

### What Every Section Must Contain

1. **The Fact** — what happened / what the data shows (from source)
2. **The Meaning** — why this matters structurally, not just tactically
3. **The Cascade** — what second-order effects follow
4. **The Implication** — what a leader must do differently because of this

### Writing the VUCA Blocks

For each of V, U, C, A:

**Step 1:** Find the best concrete example from the source material
**Step 2:** Name the specific signal (not generic — use actual numbers/names)
**Step 3:** Write the "Current Reality" as 1–2 punchy sentences
**Step 4:** Derive 4–5 leadership responses that are specific to THIS crisis, not generic advice

❌ Bad: "Build resilience in your organisation"
✅ Good: "Model operations at $80, $130, and $200+ oil simultaneously — do not pick one forecast"

❌ Bad: "Be aware of uncertainty"
✅ Good: "The Brent spot / futures $32 gap is the most important signal this week — do not use futures for physical supply decisions"

### Pull Quote Selection

Choose quotes from source that:
- Are attributed to a named expert or official
- Contain a surprising or counterintuitive insight
- Compress a complex reality into a memorable phrase

Format: `"Quote text" — Name, Title/Organisation`

---

## Step 6 — Topic-Specific Templates

### Template A: Energy/Oil Market Crisis

**Sections:** Price Data → Supply Disruption → Regional Impact → Shipping/Logistics → IEA/Analyst Warnings → VUCA → Playbook

**Accent color:** `#B06000` (amber)
**Font:** Space Grotesk + Space Mono
**Key metrics:** Price levels, supply loss in bpd, vessel availability %, freight rates

### Template B: Geopolitical/War Analysis

**Sections:** Situation Overview → Actor Analysis → Conflict Dynamics → Economic Consequences → Escalation Scenarios → VUCA → Playbook

**Accent color:** `#8B1A1A` (dark red)
**Font:** Syne + Barlow + Barlow Mono
**Key metrics:** Military assets, economic damage $, affected trade volumes, timeline days

### Template C: Human Behaviour / Psychology

**Sections:** The Phenomenon → Scientific Evidence → Social Patterns → Root Causes → Diagnosis Table → VUCA → Prescriptions

**Accent color:** `#8B3A2A` (rust)
**Font:** Cormorant Garamond + Jost + Jost Mono
**Key metrics:** Research percentages, neuroscience findings, social statistics

### Template D: Strategic Intelligence Briefing

**Sections:** Tectonic Shifts → Country/Region Analysis → Scenario Modelling → Winners/Losers → Strategic Options → VUCA → Decision Model

**Accent color:** `#0E5C52` (teal)
**Font:** Bebas Neue + IBM Plex Sans + IBM Plex Mono
**Key metrics:** Scenario probabilities, strategic positions, economic indicators

### Template E: Lessons Learned / Field Analysis

**Sections:** Context → Numbered Lessons (6–10) → Meta-Lesson → Crisis Scenario → VUCA Capabilities → Decision Model → World Shift Table

**Accent color:** `#1A344A` (slate)
**Font:** Newsreader + IBM Plex Sans + IBM Plex Mono
**Key metrics:** Lesson count, days elapsed, entities involved, capabilities required

---

## Step 7 — Quality Checklist

Before presenting the output, verify:

```
□ Every VUCA block has a SPECIFIC example from the source (not generic)
□ Leadership responses are actionable (start with a verb, contain specifics)
□ At least 4 statistics appear as visual metric blocks
□ At least 1 pull quote from named source
□ Sections are ordered: most urgent → most structural → most prescriptive
□ HTML: responsive (mobile breakpoints at 640px)
□ DOCX: validated with 0 errors
□ Slide images: captions identify the slide number and topic
□ Font pairing is consistent (serif + sans + mono)
□ No section is only bullets — prose appears in every section
□ The newsletter can stand alone without the source document
```

---

## Complete Worked Examples

All newsletters below were produced using this skill. Study them for reference:

| Source Type | Output | Theme | Format |
|-------------|--------|-------|--------|
| Raw text brief | `vuca_crisis_newsletter.html` | Iran war / economy | HTML |
| PDF presentation (15 slides) | `Algoritmik_Savas_Bulteni_Slaytli.docx` | Algorithmic warfare | DOCX with slides |
| LinkedIn article PDF | `loneliness_vuca_newsletter.html` | Human behaviour | HTML |
| PDF intelligence report (12 slides) | `energy_matrix_vuca_newsletter.html` | 2026 Energy Matrix | HTML |
| NewBase Energy PDF (18 pages) | `vuca_oil_update_apr2026.html` | Oil market crisis | HTML |
| DOCX field analysis | `war_lessons_vuca_newsletter.html` | 30 Days War Lessons | HTML |
| PPTX (14 slides) + TXT brief | `VUCA_Energy_Newsletter_2026.docx` | Energy security | DOCX with slides |
| PPTX (14 slides) + DOCX analysis | `VUCA_Yönetilen_İstikrarsizlik_2026.docx` | Managed instability | DOCX with slides |

---

## Prompt Engineering for Best Results

When calling this agent, structure your request as:

```
Generate a VUCA Leadership newsletter from [source].

Topic: [energy / geopolitics / human behaviour / war / strategy]
Format: [HTML or DOCX]
Language: [English / Turkish / other]
Audience: [energy professionals / C-suite / general / oil & gas]
Tone: [intelligence briefing / thought leadership / field analysis]
Slides available: [yes/no — if yes, list file]
```

**Example prompt:**
```
Generate a VUCA Leadership newsletter from the attached PDF intelligence report.
Topic: Geopolitical energy security
Format: DOCX with slides embedded
Language: English
Audience: Energy sector executives and investors
Tone: Intelligence briefing — direct, data-driven
Slides available: Yes (same PDF)
```

---

## Author Context

**Newsletter Series:** VUCA Leadership Intelligence
**Publisher:** Serdar Kaya — AI Investor / Advisor / VUCA Leadership Coach
**Platform:** LinkedIn Newsletter (1,000+ subscribers)
**Company:** Grenergy LLC / Ynaptics
**Style:** Strategic intelligence meets leadership development
**Signature phrase:** "Preparedness is power. Adaptability is the moat."

Always attribute as: *VUCA Leadership Intelligence · [Date] · Serdar Kaya*

---

## Error Recovery

### "Slides not rendering in DOCX"
```bash
# Check image was loaded correctly
python3 -c "
import os
files = os.listdir('/home/claude/slides')
print(sorted(files))
"
# Ensure ImageRun type is specified: type: 'png'
```

### "DOCX validation fails"
```bash
# Most common fix: pBdr element ordering (top, left, bottom, right)
python3 -c "
import re
with open('unpacked/word/document.xml') as f: doc = f.read()
def fix_pbdr(m):
    block = m.group(0)
    top = re.search(r'<w:top[^/]*/>', block)
    left = re.search(r'<w:left[^/]*/>', block)
    bottom = re.search(r'<w:bottom[^/]*/>', block)
    right = re.search(r'<w:right[^/]*/>', block)
    result = '<w:pBdr>'
    for el in [top, left, bottom, right]:
        if el: result += el.group(0)
    return result + '</w:pBdr>'
doc = re.sub(r'<w:pBdr>.*?</w:pBdr>', fix_pbdr, doc, flags=re.DOTALL)
with open('unpacked/word/document.xml', 'w') as f: f.write(doc)
"
```

### "HTML looks wrong on mobile"
Add this media query to ensure grid collapses:
```css
@media (max-width: 640px) {
  .vuca-grid, .playbook-grid, .closing,
  .stat-grid, .country-grid { grid-template-columns: 1fr !important; }
}
```

### "PPTX conversion fails"
```bash
# Check LibreOffice availability
python /mnt/skills/public/docx/scripts/office/soffice.py --version
# Alternative: use pdf2image directly if PDF already exists
```

---

## Maintenance Notes

- Node.js `docx` package version: 9.6.1 (tested)
- `pdf2image` + `poppler-utils` required for slide extraction
- LibreOffice required for PPTX→PDF conversion
- Google Fonts CDN used for typography (requires internet)
- All EMU calculations: 914400 EMU = 1 inch; image width 6.5" = 5,943,600 EMU

---

*VUCA Leadership Newsletter Agent Skill · Version 1.0 · June 2026*
*Developed through iterative production of 10+ real intelligence newsletters*
