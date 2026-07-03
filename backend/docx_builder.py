"""
docx_builder.py
─────────────────
Renders the structured content dict (from newsletter_ai.py) into a
professional Word document, using docx_writer.py — a dependency-free
OOXML writer (no lxml, so it installs cleanly on any Python version,
including brand-new ones without precompiled wheels yet).
"""

import io
from datetime import datetime
from pathlib import Path

from PIL import Image

from docx_writer import DocxWriter, Run

COLOR_NAVY = "1A375E"
COLOR_STEEL = "2E6DA4"
COLOR_TEXT = "1E1E2E"
COLOR_MUTED = "556677"
COLOR_WHITE = "FFFFFF"

FS_BODY = 12
FS_SUBHEAD = 13
FS_HEAD = 17
FS_COVER_H = 32
FS_FOOTER = 12

ACCENT_HEX = {
    "red": "8B1A1A",
    "amber": "B45309",
    "sage": "4A5E52",
    "steel": "1E3A52",
}


def _body(doc: DocxWriter, text, color=None):
    if not text or not str(text).strip():
        return
    doc.paragraph(Run(str(text).strip(), color=color or COLOR_TEXT, size_pt=FS_BODY))


def _bullet(doc: DocxWriter, text):
    if not text or not str(text).strip():
        return
    doc.paragraph(Run("•  " + str(text).strip(), color=COLOR_TEXT, size_pt=FS_BODY), space_after_pt=4)


def _heading(doc: DocxWriter, text, level=1, color=None):
    size = FS_HEAD if level == 1 else FS_SUBHEAD
    default_color = COLOR_NAVY if level == 1 else COLOR_STEEL
    doc.paragraph(
        Run(text, bold=True, color=color or default_color, size_pt=size),
        space_before_pt=6, space_after_pt=4,
    )


def _insert_image(doc: DocxWriter, image_bytes, caption, max_w_in=6.0):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        w_in = min(img.size[0] / 96, max_w_in)
        h_in = w_in * (img.size[1] / img.size[0]) if img.size[0] else w_in * 0.6
        doc.image(png_bytes, width_in=w_in, height_in=h_in)
        if caption:
            doc.paragraph(
                Run(caption, italic=True, color=COLOR_MUTED, size_pt=FS_BODY),
                align="center", space_after_pt=10,
            )
    except Exception:
        pass


def _title_page(doc: DocxWriter, content, accent_hex):
    doc.spacer(3)
    doc.paragraph(Run("VUCA LEADERSHIP INTELLIGENCE", bold=True, color=COLOR_MUTED, size_pt=FS_BODY), align="center")
    doc.paragraph(
        Run(content.get("title", "Newsletter"), bold=True, color=COLOR_NAVY, size_pt=FS_COVER_H),
        align="center", space_before_pt=10,
    )
    doc.hrule(accent_hex, 3)
    doc.paragraph(
        Run(content.get("subtitle", ""), color=COLOR_STEEL, size_pt=16),
        align="center", space_before_pt=6, space_after_pt=32,
    )
    doc.spacer(4)
    doc.paragraph(
        Run(content.get("issue_label", datetime.now().strftime("%B %Y")), italic=True, color=accent_hex, size_pt=FS_BODY),
        align="center",
    )
    doc.paragraph(
        Run(f"Generated: {datetime.now().strftime('%d %B %Y')}", color=COLOR_MUTED, size_pt=FS_BODY),
        align="center",
    )
    doc.page_break()


def _toc(doc: DocxWriter, sections):
    doc.paragraph(Run("TABLE OF CONTENTS", bold=True, color=COLOR_NAVY, size_pt=FS_HEAD), space_after_pt=6)

    rows = [["#", "Section"]] + [[str(i + 1), s.get("title", "")] for i, s in enumerate(sections)]
    row_fills = [COLOR_NAVY] + ["EEF4FB" if i % 2 == 0 else "FFFFFF" for i in range(len(sections))]
    text_colors = [COLOR_WHITE] + [None] * len(sections)
    doc.table(
        rows,
        col_widths_dxa=[900, 8460],
        row_fills=row_fills,
        text_colors=text_colors,
        bold_rows={0},
        align="left",
    )
    doc.page_break()


def _vuca_section(doc: DocxWriter, vuca_blocks, accent_hex):
    _heading(doc, "The VUCA Framework", level=1)
    doc.hrule(accent_hex, 2)
    for block in vuca_blocks:
        doc.paragraph(
            Run(f"{block.get('letter','')} — {block.get('word','')}", bold=True, color=COLOR_NAVY, size_pt=FS_SUBHEAD)
        )
        _body(doc, block.get("sub", ""), color=COLOR_MUTED)
        _body(doc, "Today's reality: " + block.get("reality", ""))
        doc.paragraph(
            Run("Leadership Response: " + block.get("response_title", ""), bold=True, color=COLOR_STEEL, size_pt=FS_BODY)
        )
        for resp in block.get("responses", []) or []:
            _bullet(doc, resp)
        doc.spacer(1)


def build_docx(content: dict, images: list, output_path: Path) -> Path:
    accent_hex = ACCENT_HEX.get(content.get("accent_name", "steel"), ACCENT_HEX["steel"])
    doc = DocxWriter()

    sections = content.get("sections", []) or []

    _title_page(doc, content, accent_hex)
    _toc(doc, sections)

    _heading(doc, "Lead", level=1)
    doc.hrule(accent_hex, 2)
    _body(doc, content.get("lead", ""))
    doc.spacer(1)

    stats = content.get("stats", []) or []
    if stats:
        _heading(doc, "Key Figures", level=2)
        for s in stats:
            _bullet(doc, f"{s.get('value','')} — {s.get('label','')}")
        doc.spacer(1)

    images_by_filename = {img["filename"]: img for img in images}
    assigned_filenames = set()
    for sec in sections:
        for fname in sec.get("relevant_images", []) or []:
            assigned_filenames.add(fname)

    for i, sec in enumerate(sections):
        _heading(doc, f"{i+1}. {sec.get('title','')}", level=1)
        doc.hrule(COLOR_STEEL, 1)
        for para in sec.get("paragraphs", []) or []:
            _body(doc, para)
        for b in sec.get("bullets", []) or []:
            _bullet(doc, b)
        quote = sec.get("pull_quote")
        if quote:
            _body(doc, f"\u201c{quote}\u201d", color=COLOR_STEEL)
        for fname in sec.get("relevant_images", []) or []:
            img = images_by_filename.get(fname)
            if img:
                _insert_image(doc, img["bytes"], img.get("caption", ""))
        doc.spacer(1)

    # Any uploaded image the model didn't assign to a specific section
    # (content["_unassigned_images"], set by newsletter_ai's reconciliation
    # step) still gets included, appended at the end, rather than silently
    # dropped.
    unassigned = content.get("_unassigned_images") or [
        img["filename"] for img in images if img["filename"] not in assigned_filenames
    ]
    for fname in unassigned:
        img = images_by_filename.get(fname)
        if img:
            _insert_image(doc, img["bytes"], img.get("caption", ""))

    _vuca_section(doc, content.get("vuca", []) or [], accent_hex)

    playbook = content.get("playbook", []) or []
    if playbook:
        _heading(doc, "Leadership Playbook", level=1)
        doc.hrule(accent_hex, 2)
        for move in playbook:
            doc.paragraph(
                Run(f"{move.get('label','')}  {move.get('title','')}", bold=True, color=COLOR_NAVY, size_pt=FS_SUBHEAD)
            )
            _body(doc, move.get("description", ""))
        doc.spacer(1)

    closing = content.get("closing", {}) or {}
    if closing:
        _heading(doc, "Closing", level=1)
        doc.hrule(accent_hex, 2)
        _body(doc, closing.get("left_title", ""), color=COLOR_NAVY)
        _body(doc, closing.get("left_text", ""))
        _body(doc, closing.get("right_title", ""), color=COLOR_NAVY)
        _body(doc, closing.get("right_text", ""))

    doc.paragraph(
        Run(
            f"{content.get('title','')} | {content.get('issue_label','')} | "
            f"Generated {datetime.now().strftime('%d %B %Y')}",
            italic=True, color=COLOR_MUTED, size_pt=FS_FOOTER,
        ),
        align="center", space_before_pt=8,
    )

    doc.save(str(output_path))
    return output_path
