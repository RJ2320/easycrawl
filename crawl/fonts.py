"""Find installed fonts by family + style, since Pillow only takes file paths.

Scans the usual macOS/Linux/Windows font folders plus Adobe Fonts' sync folder
and reads each file's name table. Results are cached for the process.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

FONT_EXTS = {".ttf", ".otf", ".ttc"}


def font_dirs() -> List[Path]:
    home = Path.home()
    dirs: List[Path] = []
    if sys.platform == "darwin":
        dirs += [
            home / "Library/Fonts",
            Path("/Library/Fonts"),
            Path("/System/Library/Fonts"),
            Path("/System/Library/Fonts/Supplemental"),
            home / "Library/Application Support/Adobe/CoreSync/plugins/livetype/.r",
        ]
    elif sys.platform.startswith("win"):
        dirs += [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
                 home / "AppData/Local/Microsoft/Windows/Fonts"]
    else:
        dirs += [home / ".fonts", home / ".local/share/fonts", Path("/usr/share/fonts"),
                 Path("/usr/local/share/fonts")]
    extra = os.environ.get("CRAWL_FONT_DIRS")
    if extra:
        dirs += [Path(p) for p in extra.split(os.pathsep) if p]
    return [d for d in dirs if d.is_dir()]


@dataclass(frozen=True)
class FontFace:
    family: str
    style: str
    path: str
    index: int = 0   # face index inside a .ttc

    @property
    def full_name(self) -> str:
        return f"{self.family} {self.style}".strip()


def _read_faces(path: Path) -> List[FontFace]:
    from fontTools.ttLib import TTCollection, TTFont

    faces: List[FontFace] = []
    try:
        if path.suffix.lower() == ".ttc":
            coll = TTCollection(str(path), lazy=True)
            fonts, closer = coll.fonts, coll.close
        else:
            single = TTFont(str(path), lazy=True)
            fonts, closer = [single], single.close
        for idx, f in enumerate(fonts):
            name = f["name"]
            # Typographic family/subfamily (16/17) beat legacy (1/2) when present.
            fam = name.getDebugName(16) or name.getDebugName(1)
            sty = name.getDebugName(17) or name.getDebugName(2)
            if fam:
                faces.append(FontFace(fam.strip(), (sty or "Regular").strip(), str(path), idx))
        closer()
    except Exception:
        pass
    return faces


@lru_cache(maxsize=1)
def all_faces() -> List[FontFace]:
    faces: List[FontFace] = []
    seen = set()
    for d in font_dirs():
        for p in d.rglob("*"):
            if p.suffix.lower() in FONT_EXTS and p not in seen:
                seen.add(p)
                faces += _read_faces(p)
    faces.sort(key=lambda f: (f.family.lower(), f.style.lower()))
    return faces


def families() -> Dict[str, List[FontFace]]:
    out: Dict[str, List[FontFace]] = {}
    for f in all_faces():
        out.setdefault(f.family, []).append(f)
    return out


def find(family: str, style: str = "Regular") -> Optional[FontFace]:
    """Case-insensitive family + style lookup; falls back to any style of the family."""
    fam, sty = family.strip().lower(), style.strip().lower()
    candidates = [f for f in all_faces() if f.family.lower() == fam]
    for f in candidates:
        if f.style.lower() == sty:
            return f
    for f in candidates:  # "DemiBold" vs "Demi Bold"
        if f.style.lower().replace(" ", "") == sty.replace(" ", ""):
            return f
    return candidates[0] if candidates else None


DEFAULT_FAMILY = "Helvetica Neue"
# What the default look falls back to on a machine without Helvetica Neue
# (Windows, Linux). A project that names its own font never falls back.
FALLBACK_FAMILIES = ("Helvetica", "Arial", "Segoe UI", "Liberation Sans", "DejaVu Sans", "Noto Sans", "Roboto")


def resolve_default(spec: str) -> Optional[FontFace]:
    """The default family's spec on a machine that doesn't have it: the same
    weight from the first fallback family installed."""
    fam, _, style = spec.partition(":")
    if fam.strip() != DEFAULT_FAMILY:
        return None
    style = style or "Regular"
    for family in FALLBACK_FAMILIES:
        face = find(family, style) or find(family, "Regular" if style == "Medium" else style)
        if face:
            return face
    return None


def resolve(spec: str) -> Optional[FontFace]:
    """Accept a file path, or 'Family Style' / 'Family:Style'."""
    if os.path.isfile(spec):
        faces = _read_faces(Path(spec))
        return faces[0] if faces else FontFace("?", "?", spec)
    if ":" in spec:
        fam, sty = spec.split(":", 1)
        return find(fam, sty)
    # Try progressively shorter family names: "Urbane Demi Bold" -> family "Urbane", style "Demi Bold"
    words = spec.split()
    for k in range(len(words), 0, -1):
        f = find(" ".join(words[:k]), " ".join(words[k:]) or "Regular")
        if f:
            return f
    return None
