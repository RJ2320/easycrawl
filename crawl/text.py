"""Font loading and text measurement shared by layout and render."""

from __future__ import annotations

from functools import lru_cache
from dataclasses import replace
import re
from typing import List, Optional

from PIL import ImageFont

# Pillow imports `packaging` lazily inside truetype(). In the app that call runs
# on a worker thread, and on macOS a first-time read of a new file from a
# background thread can be refused (EPERM). Importing here, on the main thread
# at startup, makes Pillow's lazy import a no-op.
try:
    import packaging.version  # noqa: F401
except ImportError:
    pass

from . import fonts
from .look import TextStyle


class FontError(Exception):
    pass


@lru_cache(maxsize=256)
def _load(spec: str, size: int) -> ImageFont.FreeTypeFont:
    face = fonts.resolve(spec) or fonts.resolve_default(spec)
    if face is None:
        raise FontError(f"font not found: {spec!r}")
    try:
        return ImageFont.truetype(face.path, size, index=face.index)
    except OSError as e:
        raise FontError(f"can't open {face.path}: {e}") from e


def font_for(style: TextStyle, scale: float = 1.0) -> ImageFont.FreeTypeFont:
    spec = bold_spec(style.font) if style.bold else style.font
    return _load(italic_spec(spec) if style.italic else spec, max(1, int(round(style.size * scale))))


@lru_cache(maxsize=16384)
def ink_bounds(font, value):
    """Reuse glyph measurements across timing trials and preview rebuilds."""
    return font.getbbox(value,anchor='ls')


@lru_cache(maxsize=16384)
def advance_width(font,value):
    return font.getlength(value)


@lru_cache(maxsize=128)
def bold_spec(spec: str) -> str:
    face = fonts.resolve(spec) or fonts.resolve_default(spec)
    if face is None:
        raise FontError(f"font not found: {spec!r}")
    if any(word in face.style.lower() for word in ('bold', 'black', 'heavy')):
        return spec
    candidates = [f for f in fonts.all_faces() if f.family == face.family
                  and 'bold' in f.style.lower()]
    if not candidates:
        raise FontError(f"No bold face for {face.family}. Choose a font with a bold style.")
    italic = any(word in face.style.lower() for word in ('italic', 'oblique'))
    candidates.sort(key=lambda f: (any(word in f.style.lower() for word in ('italic', 'oblique')) != italic,
                                   f.style.lower() != 'bold', len(f.style)))
    return f"{candidates[0].family}:{candidates[0].style}"


@lru_cache(maxsize=128)
def face_variant(spec: str, bold=None, italic=None) -> str:
    """Remove explicit weight/slant overrides using a real family face."""
    face = fonts.resolve(spec) or fonts.resolve_default(spec)
    if face is None:
        raise FontError(f"font not found: {spec!r}")
    def matches(candidate):
        weight = any(word in candidate.style.lower() for word in ('bold','black','heavy'))
        slant = any(word in candidate.style.lower() for word in ('italic','oblique'))
        return (bold is None or weight == bold) and (italic is None or slant == italic)
    if matches(face):
        return spec
    candidates = [candidate for candidate in fonts.all_faces() if candidate.family == face.family and matches(candidate)]
    if not candidates:
        raise FontError(f'No matching regular/upright face for {face.family}. Choose a different font style.')
    def base(value):
        return re.sub(r'bold|black|heavy|italic|oblique|regular|roman|normal|\s','',value.lower())
    candidates.sort(key=lambda candidate:(base(candidate.style)!=base(face.style),len(candidate.style)))
    return f'{candidates[0].family}:{candidates[0].style}'


def override_style(style: TextStyle, options) -> TextStyle:
    values = {key: options[key] for key in ('font','size','leading','tracking','bold','italic','uppercase','color') if key in options}
    if 'color' in values:
        values['color'] = tuple(values['color'])
    if not values:
        return style
    if 'size' in values and 'leading' not in values:
        values['leading'] = max(1,round(style.leading * values['size'] / style.size))
    if values.get('bold') is False or values.get('italic') is False:
        values['font'] = face_variant(values.get('font',style.font),
                                      bold=False if values.get('bold') is False else None,
                                      italic=False if values.get('italic') is False else None)
    return replace(style, **values)


@lru_cache(maxsize=128)
def italic_spec(spec: str) -> str:
    face = fonts.resolve(spec) or fonts.resolve_default(spec)
    if face is None:
        raise FontError(f"font not found: {spec!r}")
    if any(word in face.style.lower() for word in ("italic", "oblique")):
        return spec
    candidates = [f for f in fonts.all_faces() if f.family == face.family
                  and any(word in f.style.lower() for word in ("italic", "oblique"))]
    if not candidates:
        raise FontError(f"No italic face for {face.family}. Choose a font with an italic style.")
    def base(value):
        return re.sub(r"italic|oblique|regular|roman|normal|\s", "", value.lower())
    match = next((f for f in candidates if base(f.style) == base(face.style)), candidates[0])
    return f"{match.family}:{match.style}"


def runs(style: TextStyle, value: str):
    """Inline *italics* and **bold**; unmatched asterisks remain literal."""
    start = 0
    for match in re.finditer(r"\*\*\*([^*\n]+)\*\*\*|\*\*([^\n]+?)\*\*|\*([^*\n]+)\*", value):
        if match.start() > start:
            yield style, value[start:match.start()]
        if match.group(1) is not None:
            yield replace(style, bold=True, italic=True), match.group(1)
        elif match.group(2) is not None:
            yield from runs(replace(style, bold=True), match.group(2))
        else:
            yield replace(style, italic=True), match.group(3)
        start = match.end()
    if start < len(value):
        yield style, value[start:]


def metrics(style: TextStyle, scale: float = 1.0):
    """(ascent, descent) in px, positive numbers."""
    return font_for(style, scale).getmetrics()


def display_text(style: TextStyle, s: str) -> str:
    return s.upper() if style.uppercase else s


def advances(style: TextStyle, s: str, scale: float = 1.0) -> List[float]:
    """Per-character advance widths including kerning and tracking."""
    f = font_for(style, scale)
    tr = style.tracking * scale
    out: List[float] = []
    prev = 0.0
    for i in range(1, len(s) + 1):
        w = f.getlength(s[:i])
        out.append(w - prev + tr)
        prev = w
    if out:
        out[-1] -= tr  # no tracking after the last glyph
    return out


def width(style: TextStyle, s: str, scale: float = 1.0) -> float:
    s = display_text(style, s)
    if not s:
        return 0.0
    parts = list(runs(style, s))
    return sum(advance_width(font_for(st, scale),value) + max(0, len(value) - 1) * st.tracking * scale
               for st, value in parts) + max(0, len(parts) - 1) * style.tracking * scale


def wrap(style: TextStyle, s: str, max_width: float, scale: float = 1.0) -> List[str]:
    """Greedy word wrap; explicit newlines are respected."""
    lines: List[str] = []
    for para in s.split("\n"):
        words = []
        current = ""
        for st, value in runs(style, para):
            for token in re.findall(r"\s+|\S+", value):
                if token.isspace():
                    if current:
                        words.append(current)
                        current = ""
                else:
                    marker = ('**' if st.bold and not style.bold else '') + ('*' if st.italic and not style.italic else '')
                    current += f"{marker}{token}{marker}" if marker else token
        if current:
            words.append(current)
        if not words:
            lines.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            trial = f"{cur} {w}"
            if width(style, trial, scale) <= max_width:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def check_fonts(styles) -> List[str]:
    """Return a list of problems (empty if every style's font resolves)."""
    problems = []
    for name, st in styles.items():
        try:
            font_for(st)
        except FontError as e:
            problems.append(f"{name}: {e}")
    return problems
