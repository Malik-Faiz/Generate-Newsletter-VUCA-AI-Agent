"""
report_reader.py
─────────────────
Extracts plain text from an uploaded report file (.pdf, .docx, .doc, .txt, .md).

The .docx path is a small dependency-free parser (zipfile + the stdlib
xml.etree.ElementTree) rather than python-docx, so this installs cleanly
on Python versions where lxml has no precompiled wheel yet.
"""

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import fitz  # PyMuPDF

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()

    if ext == ".pdf":
        return _extract_pdf(path)
    if ext == ".docx":
        return _extract_docx(path)
    if ext in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    if ext == ".doc":
        # Legacy .doc isn't a zip/XML format; best-effort raw read.
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""

    raise ValueError(f"Unsupported report file type: {ext}")


def extract_pdf_pages_as_images(path: Path, zoom: float = 1.8, base_name: str = None) -> list:
    """
    Renders each page of a PDF to a PNG image — used when someone uploads
    a PDF export of their slide deck (PowerPoint/Google Slides/Keynote all
    export to PDF in one click) so that "1 slide = 1 image" without
    needing LibreOffice or any pptx-rendering dependency on the server.

    Returns a list of {"filename": ..., "bytes": ...} dicts, one per page,
    in page order — ready to be merged into the same `images` list used
    for directly-uploaded image files.

    `zoom` controls render resolution (1.8 ≈ 130 DPI — a good balance of
    legibility for the vision model vs. upload/base64 size; Groq's vision
    endpoint caps requests at 20MB per image).

    `base_name` overrides the filename stem used to name each page (pass
    the original uploaded filename's stem here — the caller's on-disk
    temp path often has an internal prefix that shouldn't leak into
    user-visible filenames).
    """
    pages = []
    with fitz.open(str(path)) as doc:
        name = base_name if base_name is not None else path.stem
        matrix = fitz.Matrix(zoom, zoom)
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=matrix)
            png_bytes = pix.tobytes("png")
            pages.append({"filename": f"{name}-slide{i + 1}.png", "bytes": png_bytes})
    return pages


def _extract_pdf(path: Path) -> str:
    text_parts = []
    with fitz.open(str(path)) as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return "\n".join(text_parts)


def _extract_docx(path: Path) -> str:
    """
    A .docx is a zip archive containing word/document.xml (plus tables,
    headers, etc.). Paragraphs are <w:p> elements; text runs live in
    nested <w:t> elements. This walks the tree and reconstructs
    paragraph and table-cell text, joined by newlines — enough for this
    app's purpose of feeding readable text to the AI prompt.
    """
    parts = []
    with zipfile.ZipFile(path) as z:
        with z.open("word/document.xml") as f:
            tree = ET.parse(f)
    root = tree.getroot()
    body = root.find(f"{_W_NS}body")
    if body is None:
        return ""

    def paragraph_text(p_elem) -> str:
        texts = [t.text or "" for t in p_elem.iter(f"{_W_NS}t")]
        return "".join(texts).strip()

    for elem in body:
        tag = elem.tag
        if tag == f"{_W_NS}p":
            text = paragraph_text(elem)
            if text:
                parts.append(text)
        elif tag == f"{_W_NS}tbl":
            for row in elem.iter(f"{_W_NS}tr"):
                cells = []
                for cell in row.iter(f"{_W_NS}tc"):
                    cell_text = " ".join(
                        paragraph_text(p) for p in cell.iter(f"{_W_NS}p")
                    ).strip()
                    if cell_text:
                        cells.append(cell_text)
                if cells:
                    parts.append(" | ".join(cells))

    return "\n".join(parts)
