"""
infographic_builder.py
─────────────────
Renders a single-page JPG infographic summarising the newsletter: title,
key stats, and the 2x2 VUCA grid. Uses PIL only (no external fonts
required — falls back to the default bitmap font if no TTF is found so
this works out-of-the-box on a bare server).
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 1500

ACCENT_HEX = {
    "red": (139, 26, 26),
    "amber": (180, 83, 9),
    "sage": (74, 94, 82),
    "steel": (30, 58, 82),
}
DARK = (11, 25, 39)
TEXT = (30, 30, 46)
MUTED = (85, 102, 119)
WHITE = (255, 255, 255)
PAPER = (250, 248, 244)

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(size, bold=False):
    for path in _FONT_CANDIDATES:
        if bold and "Bold" not in path:
            continue
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap(draw, text, font, max_width):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def build_infographic(content: dict, output_path: Path) -> Path:
    accent = ACCENT_HEX.get(content.get("accent_name", "steel"), ACCENT_HEX["steel"])
    img = Image.new("RGB", (W, H), PAPER)
    draw = ImageDraw.Draw(img)

    f_kicker = _font(20, bold=True)
    f_title = _font(46, bold=True)
    f_sub = _font(22)
    f_stat_val = _font(34, bold=True)
    f_stat_lbl = _font(14)
    f_letter = _font(56, bold=True)
    f_word = _font(20, bold=True)
    f_body = _font(14)

    # Masthead
    draw.rectangle([0, 0, W, 190], fill=DARK)
    draw.text((60, 30), "VUCA LEADERSHIP INTELLIGENCE", font=f_kicker, fill=(156, 163, 175))
    title = content.get("title", "Newsletter")
    for i, line in enumerate(_wrap(draw, title, f_title, W - 120)[:2]):
        draw.text((60, 60 + i * 52), line, font=f_title, fill=WHITE)
    subtitle_lines = _wrap(draw, content.get("subtitle", ""), f_sub, W - 120)
    if subtitle_lines:
        draw.text((60, 155), subtitle_lines[0], font=f_sub, fill=accent)

    # Stats row
    stats = (content.get("stats") or [])[:4]
    if stats:
        y0 = 220
        card_w = (W - 120 - (len(stats) - 1) * 16) // len(stats)
        for i, s in enumerate(stats):
            x0 = 60 + i * (card_w + 16)
            draw.rounded_rectangle([x0, y0, x0 + card_w, y0 + 110], radius=10, fill=WHITE, outline=(217, 212, 201))
            val = str(s.get("value", ""))
            vw = draw.textlength(val, font=f_stat_val)
            draw.text((x0 + (card_w - vw) / 2, y0 + 18), val, font=f_stat_val, fill=accent)
            lbl_lines = _wrap(draw, str(s.get("label", "")), f_stat_lbl, card_w - 16)[:2]
            for j, line in enumerate(lbl_lines):
                lw = draw.textlength(line, font=f_stat_lbl)
                draw.text((x0 + (card_w - lw) / 2, y0 + 66 + j * 16), line, font=f_stat_lbl, fill=MUTED)

    # VUCA 2x2 grid
    grid_top = 360
    cell_w = (W - 120 - 16) // 2
    cell_h = 400
    vuca = (content.get("vuca") or [])[:4]
    positions = [(60, grid_top), (60 + cell_w + 16, grid_top),
                 (60, grid_top + cell_h + 16), (60 + cell_w + 16, grid_top + cell_h + 16)]

    for block, (x0, y0) in zip(vuca, positions):
        draw.rounded_rectangle([x0, y0, x0 + cell_w, y0 + cell_h], radius=10, fill=WHITE, outline=(217, 212, 201))
        pad = 20
        draw.text((x0 + pad, y0 + pad), block.get("letter", ""), font=f_letter, fill=accent)
        draw.text((x0 + pad, y0 + pad + 66), block.get("word", ""), font=f_word, fill=TEXT)
        sub_lines = _wrap(draw, block.get("sub", ""), f_body, cell_w - pad * 2)[:2]
        yy = y0 + pad + 96
        for line in sub_lines:
            draw.text((x0 + pad, yy), line, font=f_body, fill=MUTED)
            yy += 18
        yy += 8
        reality = "Reality: " + block.get("reality", "")
        for line in _wrap(draw, reality, f_body, cell_w - pad * 2)[:4]:
            draw.text((x0 + pad, yy), line, font=f_body, fill=TEXT)
            yy += 18
        yy += 8
        for resp in (block.get("responses") or [])[:3]:
            bullet_lines = _wrap(draw, "• " + resp, f_body, cell_w - pad * 2)[:2]
            for line in bullet_lines:
                if yy > y0 + cell_h - 20:
                    break
                draw.text((x0 + pad, yy), line, font=f_body, fill=TEXT)
                yy += 18

    # Footer
    footer_y = grid_top + 2 * cell_h + 32
    draw.rectangle([0, footer_y, W, footer_y + 60], fill=DARK)
    footer_text = f"{content.get('issue_label','')}"
    draw.text((60, footer_y + 20), footer_text, font=f_stat_lbl, fill=(156, 163, 175))

    final_h = footer_y + 60
    img = img.crop((0, 0, W, final_h))
    img.save(str(output_path), format="JPEG", quality=90)
    return output_path
