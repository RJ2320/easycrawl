"""House style: fonts, sizes, spacing. All values are pixels at delivery size.

A Look is the per-show configuration the UI edits and saves as JSON. Spacing
values marked "flex" are scaled together by the timing solver to hit runtime.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, Tuple


@dataclass
class TextStyle:
    font: str = "Helvetica Neue:Medium"  # "Family:Style" or a file path
    size: int = 56                       # px, at delivery size
    leading: int = 80                    # px baseline to baseline (flex)
    tracking: float = 0.0                # px added between glyphs
    uppercase: bool = False
    color: Tuple[float, float, float] = (1.0, 1.0, 1.0)  # 0..1 linear-ish RGB
    italic: bool = False


@dataclass
class Look:
    # Canvas
    width: int = 3840
    height: int = 2160

    # Text styles per element
    header: TextStyle = field(default_factory=lambda: TextStyle("Helvetica Neue:Bold", 64, 96, 4.0, True))
    song: TextStyle = field(default_factory=lambda: TextStyle("Helvetica Neue:Medium", 56, 80, 0.0, False))
    role: TextStyle = field(default_factory=lambda: TextStyle("Helvetica Neue:Medium", 52, 80))
    name: TextStyle = field(default_factory=lambda: TextStyle("Helvetica Neue:Medium", 56, 80))
    list: TextStyle = field(default_factory=lambda: TextStyle("Helvetica Neue:Medium", 48, 72))
    legal: TextStyle = field(default_factory=lambda: TextStyle("Helvetica Neue:Medium", 40, 56))

    music_role: TextStyle = field(default_factory=lambda: TextStyle("Helvetica Neue:Medium", 48, 64))
    music_name: TextStyle = field(default_factory=lambda: TextStyle("Helvetica Neue:Medium", 48, 64))
    music_title_gap: int = 12
    music_group_gap: int = 96
    music_inline_gap: int = 16
    music_width: int = 3000

    # Two-column geometry: roles right-align to (center - gutter/2), names left-align to (center + gutter/2)
    center_x: int = 1920
    gutter: int = 120

    # Vertical spacing (flex = scaled by the timing solver)
    group_gap: int = 120         # blank sheet row (flex)
    header_gap_before: int = 40  # extra above a header, on top of group_gap (flex)
    header_gap_after: int = 24   # between a header and what follows (flex)
    list_column_gap: int = 160   # horizontal, between list columns
    list_width: int = 2880       # total width of the multi-column block
    legal_width: int = 2400      # wrap width for legal paragraphs
    logo_height: int = 300       # placeholder / scaled logo height
    logo_gap: int = 80           # vertical space around a logo (flex)
    logo_balance: float = 0.85   # 0 = every logo the same height, 1 = the same area (see logos.py)

    # Rendering
    supersample: int = 1         # 2 = render at 2x and downsample (smoother, slower)
    min_stroke_px: int = 2       # lint warning if a face's thin stroke is below this

    # ---- resolution --------------------------------------------------------

    # Lengths that are pixels at delivery size and so must follow a resolution change.
    _SCALED = ("music_title_gap", "music_group_gap", "music_inline_gap", "music_width", "gutter",
               "group_gap", "header_gap_before", "header_gap_after", "list_column_gap", "list_width",
               "legal_width", "logo_height", "logo_gap")

    def resize(self, width: int, height: int, scale_look: bool = True) -> float:
        """Change the delivery size. Returns the factor the look was scaled by.

        Every measurement in a Look is in pixels at the delivery size, so a new
        size leaves the type the wrong size unless it is scaled too. With
        `scale_look` the look is scaled by the change in *height* (credits are
        read against the frame's height; a wider frame of the same height
        should not make the type bigger) and the column keeps its position
        relative to the middle of the frame. Without it only the canvas changes
        and the column is re-centred by the change in width.
        """
        factor = height / self.height if scale_look else 1.0
        offset = self.center_x - self.width / 2         # how far the column sits from the middle
        if factor != 1.0:
            for style in self.styles().values():
                style.size = max(1, int(round(style.size * factor)))
                style.leading = max(1, int(round(style.leading * factor)))
                style.tracking = round(style.tracking * factor, 2)
            for name in self._SCALED:
                setattr(self, name, max(0, int(round(getattr(self, name) * factor))))
        self.width, self.height = int(width), int(height)
        self.center_x = int(round(width / 2 + offset * factor))
        return factor

    # ---- persistence -------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Look":
        kwargs = {}
        for f in fields(cls):
            if f.name not in d:
                continue
            v = d[f.name]
            if f.type == "TextStyle" or isinstance(getattr(cls(), f.name), TextStyle):
                v = TextStyle(**{k: (tuple(x) if k == "color" else x) for k, x in v.items()})
            kwargs[f.name] = v
        return cls(**kwargs)

    def save(self, path: str) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: str) -> "Look":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def styles(self) -> Dict[str, TextStyle]:
        return {"header": self.header, "song": self.song, "role": self.role,
                "name": self.name, "list": self.list, "legal": self.legal,
                "music_role": self.music_role, "music_name": self.music_name}
