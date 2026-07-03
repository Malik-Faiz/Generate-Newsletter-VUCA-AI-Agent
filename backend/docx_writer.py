"""
docx_writer.py
─────────────────
A minimal, dependency-free .docx writer. A .docx file is just a ZIP of
XML parts — this builds those parts with plain string templates and
Python's built-in `zipfile` / `xml.sax.saxutils.escape`, with no
compiled extensions (no lxml, no C build step). This exists specifically
so the app installs cleanly on brand-new Python versions (like 3.15 at
the time of writing) where packages such as lxml don't yet ship
precompiled Windows wheels and would otherwise require a C++ compiler
to build from source.

It supports exactly what docx_builder.py needs: styled paragraphs and
runs (bold/italic/color/size), page breaks, horizontal rules, shaded
tables, and inline images — nothing more.

Usage:
    doc = DocxWriter()
    doc.paragraph([Run("Hello", bold=True, color="1A375E", size=17)])
    doc.page_break()
    doc.table(rows=[["#", "Section"], ["1", "Intro"]], fills=["1A375E", None])
    doc.image(png_bytes, width_emu=..., height_emu=...)
    doc.save("out.docx")
"""

import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from xml.sax.saxutils import escape as _xesc

EMU_PER_INCH = 914400
TWIPS_PER_PT = 20  # w:sz / spacing units are twentieths of a point
HALFPT_PER_PT = 2  # run font size (w:sz) is in half-points

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="png" ContentType="image/png"/>
<Default Extension="jpeg" ContentType="image/jpeg"/>
<Default Extension="jpg" ContentType="image/jpeg"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

RELS_ROOT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

DOCUMENT_HEADER = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<w:body>"""

DOCUMENT_FOOTER_TEMPLATE = """<w:sectPr>
<w:pgSz w:w="12240" w:h="15840"/>
<w:pgMar w:top="1134" w:right="1417" w:bottom="1134" w:left="1417" w:header="720" w:footer="720" w:gutter="0"/>
</w:sectPr>
</w:body>
</w:document>"""


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    color: str = None       # hex, no '#', e.g. "1A375E"
    size_pt: float = 12
    all_caps: bool = False


def _rpr(run: Run) -> str:
    parts = ["<w:rPr>"]
    if run.bold:
        parts.append("<w:b/>")
    if run.italic:
        parts.append("<w:i/>")
    if run.all_caps:
        parts.append("<w:caps/>")
    if run.color:
        parts.append(f'<w:color w:val="{run.color}"/>')
    parts.append(f'<w:sz w:val="{int(run.size_pt * HALFPT_PER_PT)}"/>')
    parts.append("</w:rPr>")
    return "".join(parts)


def _run_xml(run: Run) -> str:
    text = _xesc(run.text)
    return f'<w:r>{_rpr(run)}<w:t xml:space="preserve">{text}</w:t></w:r>'


class DocxWriter:
    def __init__(self):
        self._body_parts = []
        self._media = []  # list of (filename, bytes)
        self._rels = []   # list of (rId, type, target) for document.xml.rels
        self._next_rid = 1
        self._next_image_idx = 1

    # ── low-level paragraph/table builders ──────────────────────────

    def paragraph(
        self,
        runs,
        align: str = None,          # "center" | "left" | None
        line_spacing: float = 1.2,
        space_before_pt: float = 0,
        space_after_pt: float = 6,
        border_bottom_color: str = None,
        border_bottom_pt: float = 1.5,
    ):
        if isinstance(runs, Run):
            runs = [runs]
        ppr = ["<w:pPr>"]
        if align:
            ppr.append(f'<w:jc w:val="{align}"/>')
        ppr.append(
            f'<w:spacing w:before="{int(space_before_pt * TWIPS_PER_PT)}" '
            f'w:after="{int(space_after_pt * TWIPS_PER_PT)}" '
            f'w:line="{int(240 * line_spacing)}" w:lineRule="auto"/>'
        )
        if border_bottom_color:
            sz = int(border_bottom_pt * 8)
            ppr.append(
                f'<w:pBdr><w:bottom w:val="single" w:sz="{sz}" w:space="1" '
                f'w:color="{border_bottom_color}"/></w:pBdr>'
            )
        ppr.append("</w:pPr>")
        runs_xml = "".join(_run_xml(r) for r in runs) if runs else ""
        self._body_parts.append(f'<w:p>{"".join(ppr)}{runs_xml}</w:p>')

    def spacer(self, lines: int = 1):
        for _ in range(lines):
            self.paragraph([], space_after_pt=6)

    def page_break(self):
        self._body_parts.append(
            '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
        )

    def hrule(self, color: str = "1A375E", thickness_pt: float = 1.5):
        self.paragraph(
            [], space_before_pt=2, space_after_pt=2,
            border_bottom_color=color, border_bottom_pt=thickness_pt,
        )

    def table(
        self,
        rows,                        # list[list[str]]
        col_widths_dxa=None,         # list[int], must sum to table width
        header_fill: str = None,     # hex for row 0 background
        row_fills=None,              # list[str|None] per row (overrides header_fill for row 0 if given)
        text_colors=None,            # list[str|None] per row, run color
        bold_rows=None,              # set of row indices to bold
        align: str = "left",
        font_size_pt: float = 12,
        table_width_dxa: int = 9360,
    ):
        n_cols = max(len(r) for r in rows) if rows else 1
        if not col_widths_dxa:
            w = table_width_dxa // n_cols
            col_widths_dxa = [w] * n_cols

        grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in col_widths_dxa)
        tbl = [
            "<w:tbl>",
            "<w:tblPr>",
            f'<w:tblW w:w="{table_width_dxa}" w:type="dxa"/>',
            '<w:tblBorders>'
            '<w:top w:val="single" w:sz="4" w:space="0" w:color="D0DCE8"/>'
            '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="D0DCE8"/>'
            '<w:left w:val="single" w:sz="4" w:space="0" w:color="D0DCE8"/>'
            '<w:right w:val="single" w:sz="4" w:space="0" w:color="D0DCE8"/>'
            '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="D0DCE8"/>'
            '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="D0DCE8"/>'
            "</w:tblBorders>",
            "</w:tblPr>",
            f"<w:tblGrid>{grid}</w:tblGrid>",
        ]

        for ri, row in enumerate(rows):
            fill = None
            if row_fills and ri < len(row_fills):
                fill = row_fills[ri]
            elif ri == 0 and header_fill:
                fill = header_fill
            text_color = text_colors[ri] if text_colors and ri < len(text_colors) else None
            is_bold = bool(bold_rows and ri in bold_rows)

            tbl.append("<w:tr>")
            for ci in range(n_cols):
                cell_text = row[ci] if ci < len(row) else ""
                w = col_widths_dxa[ci] if ci < len(col_widths_dxa) else (table_width_dxa // n_cols)
                tcpr = [f'<w:tcW w:w="{w}" w:type="dxa"/>']
                if fill:
                    tcpr.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>')
                run = Run(
                    str(cell_text), bold=is_bold, color=text_color, size_pt=font_size_pt
                )
                ppr = f'<w:pPr><w:jc w:val="{align}"/></w:pPr>'
                tbl.append(
                    f"<w:tc><w:tcPr>{''.join(tcpr)}</w:tcPr>"
                    f"<w:p>{ppr}{_run_xml(run)}</w:p></w:tc>"
                )
            tbl.append("</w:tr>")

        tbl.append("</w:tbl>")
        # A table must be followed by at least an empty paragraph in OOXML.
        self._body_parts.append("".join(tbl))
        self._body_parts.append("<w:p/>")

    def image(self, image_bytes: bytes, width_in: float, height_in: float, filename_hint: str = "image"):
        ext = "png"
        if image_bytes[:2] == b"\xff\xd8":
            ext = "jpeg"
        idx = self._next_image_idx
        self._next_image_idx += 1
        fname = f"image{idx}.{ext}"
        self._media.append((fname, image_bytes))

        rid = f"rId{self._next_rid}"
        self._next_rid += 1
        self._rels.append(
            (rid, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image", f"media/{fname}")
        )

        cx = int(width_in * EMU_PER_INCH)
        cy = int(height_in * EMU_PER_INCH)
        drawing = f"""<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:drawing>
<wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
           xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
           xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
<wp:extent cx="{cx}" cy="{cy}"/>
<wp:docPr id="{idx}" name="{fname}"/>
<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
<pic:pic><pic:nvPicPr><pic:cNvPr id="{idx}" name="{fname}"/><pic:cNvPicPr/></pic:nvPicPr>
<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>
<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>
</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>"""
        self._body_parts.append(drawing)

    # ── serialisation ─────────────────────────────────────────────

    def _document_rels_xml(self) -> str:
        rels = "".join(
            f'<Relationship Id="{rid}" Type="{rtype}" Target="{target}"/>'
            for rid, rtype, target in self._rels
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{rels}</Relationships>"
        )

    def save(self, path):
        document_xml = (
            DOCUMENT_HEADER + "".join(self._body_parts) + DOCUMENT_FOOTER_TEMPLATE
        )

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", CONTENT_TYPES)
            z.writestr("_rels/.rels", RELS_ROOT)
            z.writestr("word/document.xml", document_xml)
            if self._rels:
                z.writestr("word/_rels/document.xml.rels", self._document_rels_xml())
            for fname, data in self._media:
                z.writestr(f"word/media/{fname}", data)

        with open(path, "wb") as f:
            f.write(buf.getvalue())
        return path
