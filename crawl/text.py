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
    return _load(italic_spec(style.font) if style.italic else style.font, max(1, int(round(style.size * scale))))


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
    """Inline *italics*; unmatched asterisks remain literal."""
    start = 0
    for match in re.finditer(r"\*([^*\n]+)\*", value):
        if match.start() > start:
            yield style, value[start:match.start()]
        yield replace(style, italic=True), match.group(1)
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
    return sum(font_for(st, scale).getlength(value) + max(0, len(value) - 1) * st.tracking * scale
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
                    current += f"*{token}*" if st.italic and not style.italic else token
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
