"""Draw a Layout into panel images.

Each panel is a slice (top, bottom) of the content. Panels are rendered
content-only, no black padding, and later butted edge to edge in Fusion.

Formats
  rgba8   8-bit RGBA PNG, text colour with alpha. Default.
  luma16  16-bit greyscale PNG (text as white matte). Good for HDR grades where
          the white level is set in the comp.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

import numpy as np
from PIL import Image, ImageChops, ImageDraw

from . import logos, text
from .layout import Layout, Line, LogoItem
from .look import Look

FORMATS = ("rgba8", "luma16")


def render_panel(L: Layout, look: Look, top: int, bottom: int, scale: float = 1.0,
                 supersample: int = 1, colour: bool = True) -> Image.Image:
    """Return an 'RGBA' (colour=True) or 'L' image of content rows [top, bottom)."""
    ss = max(1, int(supersample))
    s = scale * ss
    W = max(1, int(round(look.width * s)))
    H = max(1, int(round((bottom - top) * s)))

    matte = Image.new("L", (W, H), 0)
    dm = ImageDraw.Draw(matte)
    rgb = Image.new("RGB", (W, H), (0, 0, 0)) if colour else None
    dc = ImageDraw.Draw(rgb) if rgb else None
    styles = look.styles()

    # Glyphs reach above and below their baseline; two font sizes covers any
    # ascender/descender plus tracking artefacts.
    margin = 2 * max(s.size for s in styles.values())
    for ln in L.lines_in(top, bottom, margin):
        st = styles[ln.style]
        font = text.font_for(st, s)
        x = ln.x * s
        y = (ln.y - top) * s
        fill = tuple(int(round(c * 255)) for c in st.color)
        _draw_text(dm, font, st, ln, x, y, s, 255)
        if dc:
            _draw_text(dc, font, st, ln, x, y, s, fill)

    for lg in L.logos_in(top, bottom):
        _draw_logo(matte, rgb, lg, top, s, look)

    if ss > 1:
        size = (max(1, int(round(look.width * scale))), max(1, int(round((bottom - top) * scale))))
        matte = matte.resize(size, Image.LANCZOS)
        if rgb:
            rgb = rgb.resize(size, Image.LANCZOS)

    if not colour:
        return matte
    r, g, b = rgb.split()
    return Image.merge("RGBA", (r, g, b, matte))


def _draw_text(d: ImageDraw.ImageDraw, font, st, ln: Line, x: float, y: float, s: float, fill):
    parts = list(text.runs(st, ln.text))
    if len(parts) > 1 or (parts and parts[0][1] != ln.text):
        total = text.width(st, ln.text, s)
        if ln.anchor[0] == "m":
            x -= total / 2
        elif ln.anchor[0] == "r":
            x -= total
        for part_style, value in parts:
            part = Line(value, ln.style, 0, 0, "ls")
            _draw_text(d, text.font_for(part_style, s), part_style, part, x, y, s, fill)
            x += text.width(part_style, value, s) + st.tracking * s
        return
    if st.tracking == 0:
        d.text((x, y), ln.text, font=font, fill=fill, anchor=ln.anchor)
        return
    # Tracked text: place glyph by glyph. Anchor decides where the run starts.
    adv = text.advances(st, ln.text, s)
    total = sum(adv)
    if ln.anchor[0] == "m":
        x -= total / 2
    elif ln.anchor[0] == "r":
        x -= total
    for ch, a in zip(ln.text, adv):
        d.text((x, y), ch, font=font, fill=fill, anchor="ls")
        x += a


def _draw_logo(matte: Image.Image, rgb: Optional[Image.Image], lg: LogoItem, top: int, s: float, look: Look):
    x, y = int(round(lg.x * s)), int(round((lg.y - top) * s))
    w, h = max(1, int(round(lg.w * s))), max(1, int(round(lg.h * s)))
    if lg.path:
        try:
            with Image.open(lg.path) as im:
                im = im.convert("RGBA")
                if lg.crop:
                    im = im.crop(lg.crop)
                im = im.resize((w, h), Image.LANCZOS)
                if lg.invert:
                    r, g, b, alpha = im.split()
                    im = Image.merge("RGBA", (*ImageChops.invert(Image.merge("RGB", (r, g, b))).split(), alpha))
                im = logos.apply_levels(im, lg.black, lg.white)
                if lg.mode == "grayscale":
                    gray = im.convert("L")
                    im = Image.merge("RGBA", (gray, gray, gray, im.getchannel("A")))
                lum = im.convert("L")
                a = im.split()[3]
                m = Image.fromarray((np.asarray(lum, np.uint16) * np.asarray(a, np.uint16) // 255).astype(np.uint8))
                matte.paste(m, (x, y), a)
                if rgb:
                    rgb.paste(im.convert("RGB"), (x, y), a)
            return
        except Exception:
            pass
    # Placeholder: outlined box with the slot label.
    stroke = max(1, int(round(2 * s)))
    for img, col in ((matte, 255), (rgb, (255, 255, 255))):
        if img is None:
            continue
        d = ImageDraw.Draw(img)
        d.rectangle([x, y, x + w - 1, y + h - 1], outline=col, width=stroke)
        font = text.font_for(look.role, s * 0.7)
        d.text((x + w / 2, y + h / 2), lg.label, font=font, fill=col, anchor="mm")


# --------------------------------------------------------------------------- #

def save_panel(img: Image.Image, path: Path, fmt: str = "rgba8") -> None:
    if fmt == "rgba8":
        img.convert("RGBA").save(path, "PNG", compress_level=6)
    elif fmt == "luma16":
        matte = img.split()[3] if img.mode == "RGBA" else img.convert("L")
        arr = (np.asarray(matte, dtype=np.uint16) * 257)
        Image.fromarray(arr, mode="I;16").save(path, "PNG", compress_level=6)
    else:
        raise ValueError(f"unknown format {fmt!r}")


def render_all(L: Layout, look: Look, out_dir: str, basename: str = "crawl",
               fmt: str = "rgba8", progress: Optional[Callable[[int, int], None]] = None) -> List[Path]:
    """Render every panel in L.panels to out_dir/<basename>_p01.png … Returns the paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    n = len(L.panels)
    for i, (top, bottom) in enumerate(L.panels):
        img = render_panel(L, look, top, bottom, 1.0, look.supersample, colour=(fmt == "rgba8"))
        p = out / f"{basename}_p{i + 1:02d}.png"
        save_panel(img, p, fmt)
        paths.append(p)
        if progress:
            progress(i + 1, n)
    return paths


def render_preview(L: Layout, look: Look, scale: float = 0.25) -> Image.Image:
    """Whole crawl as one greyscale image, for the UI. Supersampled: small type
    drawn directly at quarter scale looks ragged."""
    from .export import needs_colour
    image = render_panel(L, look, 0, L.target_height, scale, 2, colour=needs_colour(look, L))
    return image.convert("RGB") if image.mode == "RGBA" else image
