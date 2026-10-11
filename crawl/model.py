"""Data model: what a crawl is made of, independent of how it's drawn.

The sheet is parsed into a flat list of *blocks*. Blocks are grouped by blank
rows into *groups*; panel breaks may only happen between groups.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Union


@dataclass
class Header:
    """Centered section header (ALL CAPS in the sheet) or a song title (level 2)."""
    text: str
    level: int = 1
    row: int = 0


@dataclass
class RolePair:
    """A role/title on the left and one or more stacked names on the right."""
    role: str
    names: List[str]
    row: int = 0
    music: bool = False
    names_pending: bool = False   # set by a "roles" layout override: no names yet, don't flag it


@dataclass
class ListBlock:
    """A long single-column list from the sheet that gets set in N columns."""
    names: List[str]
    columns: int = 3
    row: int = 0


@dataclass
class Logo:
    """One logo slot. `path` is None while it's still a bracketed placeholder."""
    label: str
    path: Optional[str] = None
    row: int = 0
    # Manual adjustments (project.logo_settings), applied on top of the automatic row layout.
    invert: bool = False    # flip the artwork's colours, e.g. a dark logo on the black crawl
    scale: float = 1.0      # multiplies Look.logo_height for this logo
    dx: int = 0             # px offset from the automatic position
    dy: int = 0
    black: float = 0.0      # levels: this input level becomes black (0..1)…
    white: float = 1.0      # …and this one full brightness
    mode: str = "original"


@dataclass
class LogoRow:
    """One or more logos set side by side on one line: "[Logo: A] | [Logo: B]"."""
    logos: List[Logo]
    row: int = 0


@dataclass
class Legal:
    """A centered paragraph of legal text, wrapped to a max width."""
    text: str
    row: int = 0


Block = Union[Header, RolePair, ListBlock, LogoRow, Legal]


@dataclass
class Group:
    """Blocks between two blank rows. Panel breaks fall between groups."""
    blocks: List[Block] = field(default_factory=list)

    @property
    def first_row(self) -> int:
        return self.blocks[0].row if self.blocks else 0


@dataclass
class Crawl:
    groups: List[Group] = field(default_factory=list)
    source: str = ""
    arrangements: List[dict] = field(default_factory=list)

    def blocks(self):
        for g in self.groups:
            yield from g.blocks

    def logos(self):
        for b in self.blocks():
            if isinstance(b, LogoRow):
                yield from b.logos

    def counts(self) -> dict:
        c = {"headers": 0, "role_lines": 0, "list_names": 0, "logos": 0, "legal": 0, "groups": len(self.groups)}
        for b in self.blocks():
            if isinstance(b, Header):
                c["headers"] += 1
            elif isinstance(b, RolePair):
                c["role_lines"] += max(1, len(b.names))
            elif isinstance(b, ListBlock):
                c["list_names"] += len(b.names)
            elif isinstance(b, LogoRow):
                c["logos"] += len(b.logos)
            elif isinstance(b, Legal):
                c["legal"] += 1
        return c

    def describe(self) -> str:
        """'12 headings, 184 credits, 40 list names, 3 logos' — only what is there."""
        c = self.counts()
        labels = (("headers", "heading", "headings"), ("role_lines", "credit", "credits"),
                  ("list_names", "list name", "list names"), ("logos", "logo", "logos"),
                  ("legal", "legal block", "legal blocks"))
        parts = [f"{c[key]} {one if c[key] == 1 else many}" for key, one, many in labels if c[key]]
        return ", ".join(parts) or "nothing"
