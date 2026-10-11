"""Blocks → baseline positions, column balancing, panel breaks.

Positions are integer pixels at delivery size, measured from the top of the
content. The pen advances in floating point and each baseline is rounded, so
the content height stays linear in the spacing scale `flex` (per-line rounding
would drift by hundreds of pixels over a long crawl).

    layout(crawl, look, flex)           → Layout
    measure(crawl, look)                → (fixed_px, flex_px) for the timing solver
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
import copy
from typing import List, Optional, Tuple

from . import logos, text
from .look import Look
from .model import Crawl, Header, Legal, ListBlock, LogoRow, RolePair, Group


LOGO_ROW_MAX = 0.8   # widest a logo row may be, as a fraction of the frame width


@dataclass
class Line:
    text: str
    style: str      # key in Look.styles()
    x: int          # anchor x
    y: int          # baseline y
    anchor: str     # 'ls' left / 'ms' middle / 'rs' right (Pillow anchors)
    row: int = 0
    target: str = ''


@dataclass
class LogoItem:
    label: str
    path: Optional[str]
    x: int          # left
    y: int          # top
    w: int
    h: int
    invert: bool = False
    crop: Optional[Tuple[int, int, int, int]] = None   # ink box in the source file
    dx: int = 0     # manual offset already included in x / y
    dy: int = 0
    black: float = 0.0   # levels, applied after invert
    white: float = 1.0
    mode: str = "original"
    row: int = 0


@dataclass
class Layout:
    width: int
    content_height: int                  # tight: last glyph/logo bottom
    lines: List[Line] = field(default_factory=list)
    logos: List[LogoItem] = field(default_factory=list)
    groups: List[Tuple[int, int]] = field(default_factory=list)   # (top, bottom) per group
    panels: List[Tuple[int, int]] = field(default_factory=list)   # (top, bottom) per panel
    row_positions: dict = field(default_factory=dict)  # source row → content y
    target_height: int = 0               # padded height the crawl actually uses

    def lines_in(self, top: int, bottom: int, margin: int = 0) -> List[Line]:
        """Lines whose baseline is in [top, bottom), widened by `margin` so a
        slice also draws glyphs that hang over its edges from either side."""
        return [l for l in self.lines if top - margin <= l.y < bottom + margin]

    def logos_in(self, top: int, bottom: int) -> List[LogoItem]:
        return [l for l in self.logos if l.y < bottom and l.y + l.h > top]


# --------------------------------------------------------------------------- #

def layout(crawl: Crawl, look: Look, flex: float = 1.0, column_width=None, alignment="center") -> Layout:
    if crawl.arrangements:
        return _arranged_layout(crawl, look, flex)
    styles = look.styles()
    asc = {k: text.metrics(s)[0] for k, s in styles.items()}
    desc = {k: text.metrics(s)[1] for k, s in styles.items()}
    L = Layout(width=look.width, content_height=0)

    pen = 0.0           # top of the next line's box
    bottom = 0          # lowest ink so far
    role_x = look.center_x - look.gutter // 2
    name_x = look.center_x + look.gutter // 2

    def put(s: str, style: str, x: int, anchor: str, y: float, source_row=None) -> None:
        nonlocal bottom
        baseline = int(round(y + asc[style]))
        row = b.row if source_row is None else source_row
        L.row_positions.setdefault(row, baseline)
        target = "header" if isinstance(b, Header) else "role" if isinstance(b, Legal) else style.removeprefix("music_")
        L.lines.append(Line(text.display_text(styles[style], s), style, x, baseline, anchor, row, target))
        bottom = max(bottom, baseline + desc[style])

    first_group = True
    for g in crawl.groups:
        if not first_group:
            music_group = any(isinstance(b, RolePair) and b.music for b in g.blocks)
            pen += (look.music_group_gap if music_group else look.group_gap) * flex
        first_group = False
        g_top = int(math.floor(pen))

        for b in g.blocks:
            if isinstance(b, Header):
                style = "header" if b.level == 1 else "song"
                music_title = b.level == 2 and any(isinstance(item, RolePair) and item.music for item in g.blocks)
                pen += (0 if music_title else look.header_gap_before) * flex
                title_lines = text.wrap(styles[style], b.text, column_width) if column_width else [b.text]
                for title_line in title_lines:
                    put(title_line, style, 0 if column_width and alignment == "left" else look.center_x,
                        "ls" if column_width and alignment == "left" else "ms", pen)
                    pen += styles[style].leading * flex
                pen += (look.music_title_gap if music_title else look.header_gap_after) * flex

            elif isinstance(b, RolePair):
                if b.music or column_width:
                    role_style, name_style = ("music_role", "music_name") if b.music else ("role", "name")
                    label_width = text.width(styles[role_style], b.role) if b.role else 0
                    gap = look.music_inline_gap if b.role else 0
                    label = b.role
                    # A long role in a narrow block sits above its names;
                    # do not let it spill into the neighboring column.
                    if column_width and label_width + gap > column_width * .7:
                        for role_line in text.wrap(styles[role_style], label, column_width):
                            put(role_line, role_style, 0 if alignment == "left" else look.center_x,
                                "ls" if alignment == "left" else "ms", pen)
                            pen += styles[role_style].leading * flex
                        label = ""
                        label_width = gap = 0
                    names = b.names or [""]
                    for index, name in enumerate(names):
                        label = label if index == 0 else ""
                        label_w = label_width if label else 0
                        inline_gap = gap if label else 0
                        available = max(100, (column_width or look.music_width) - label_w - inline_gap)
                        for wrapped_index, line in enumerate(text.wrap(styles[name_style], name, available)):
                            current_label = label if wrapped_index == 0 else ""
                            lw = label_w if current_label else 0
                            sp = inline_gap if current_label else 0
                            width = lw + sp + text.width(styles[name_style], line)
                            left = 0 if column_width and alignment == "left" else look.center_x - width / 2
                            if current_label:
                                put(current_label, role_style, left, "ls",
                                    pen + asc[name_style] - asc[role_style])
                            if line:
                                put(line, name_style, left + lw + sp, "ls", pen)
                            pen += styles[name_style].leading * flex
                    continue
                if b.role:
                    # Role shares the first name's baseline.
                    y_base = pen + asc["name"] - asc["role"]
                    put(b.role, "role", role_x, "rs", y_base)
                if b.names:
                    for n in b.names:
                        put(n, "name", name_x, "ls", pen)
                        pen += styles["name"].leading * flex
                else:
                    pen += styles["name"].leading * flex

            elif isinstance(b, ListBlock):
                if column_width:
                    for name_index, name in enumerate(b.names):
                        for line in text.wrap(look.list, name, column_width):
                            put(line, "list", 0 if alignment == "left" else look.center_x,
                                "ls" if alignment == "left" else "ms", pen, b.row + name_index)
                            pen += look.list.leading * flex
                else:
                    pen = _list(L, b, look, flex, pen, put)

            elif isinstance(b, LogoRow):
                L.row_positions.setdefault(b.row, round(pen))
                pen += look.logo_gap * flex
                # Each logo has its own height (scale); the row is as tall as
                # the tallest and the others centre on it. dx/dy then nudge a
                # logo off that automatic spot without moving anything else.
                sizes = [logos.size(lg.path, look.logo_height, look.logo_balance, lg.scale, lg.invert, lg.black)
                         for lg in b.logos]
                widths, heights = [w for w, _ in sizes], [hh for _, hh in sizes]
                total = sum(widths) + look.logo_gap * (len(widths) - 1)
                logo_gap = look.logo_gap
                # A row never runs wider than its column, or 80% of the frame.
                max_row = column_width or look.width * LOGO_ROW_MAX
                if total > max_row:
                    ratio = max_row / total
                    widths = [max(1, int(w * ratio)) for w in widths]
                    heights = [max(1, int(hh * ratio)) for hh in heights]
                    logo_gap *= ratio
                    total = sum(widths) + logo_gap * (len(widths) - 1)
                h = max(heights)
                x = 0 if column_width and alignment == "left" else look.center_x - total / 2
                y = int(round(pen))
                for lg, w, hh in zip(b.logos, widths, heights):
                    item_y = y + (h - hh) // 2 + lg.dy
                    L.logos.append(LogoItem(lg.label, lg.path, int(round(x)) + lg.dx, item_y, w, hh, lg.invert,
                                            logos.ink_box(lg.path, lg.invert, lg.black), lg.dx, lg.dy,
                                            lg.black, lg.white, lg.mode, b.row))
                    bottom = max(bottom, item_y + hh)
                    x += w + logo_gap
                bottom = max(bottom, y + h)
                pen += h + look.logo_gap * flex

            elif isinstance(b, Legal):
                for ln in text.wrap(styles["legal"], b.text, look.legal_width):
                    put(ln, "legal", 0 if column_width and alignment == "left" else look.center_x,
                        "ls" if column_width and alignment == "left" else "ms", pen)
                    pen += styles["legal"].leading * flex

        L.groups.append((g_top, max(bottom, int(math.ceil(pen)))))

    L.content_height = bottom
    L.target_height = bottom
    return L


def _arranged_layout(crawl: Crawl, look: Look, flex: float) -> Layout:
    """Compose grid rows, retaining each grid row as a safe panel-break unit."""
    arrangements = sorted(crawl.arrangements, key=lambda a: a['start'])
    for index, item in enumerate(arrangements):
        if item['start'] < 0 or item['end'] < item['start'] or not (1 if item.get('logo_grid') else 2) <= item['columns'] <= 6:
            raise ValueError('Invalid side-by-side arrangement. Edit or remove it in Credits.')
        if index and arrangements[index - 1]['end'] >= item['start']:
            raise ValueError('Side-by-side arrangements cannot overlap.')
    result = Layout(look.width, 0)
    pen = 0.0
    index = 0

    def paste(part, x, y):
        result.lines.extend(replace(line, x=line.x + x, y=line.y + y) for line in part.lines)
        result.row_positions.update({row: value + y for row, value in part.row_positions.items()})
        result.logos.extend(replace(logo, x=logo.x + x, y=logo.y + y) for logo in part.logos)
        result.content_height = max(result.content_height, y + part.content_height)

    while index < len(crawl.groups):
        group = crawl.groups[index]
        item = next((a for a in arrangements if a['start'] <= group.first_row - 1 <= a['end']), None)
        gap = look.music_group_gap if any(isinstance(b, RolePair) and b.music for b in group.blocks) else look.group_gap
        if result.groups:
            pen += gap * flex
        if item is None:
            part = layout(Crawl(groups=[group]), look, flex)
            y = round(pen)
            paste(part, 0, y)
            pen += max(part.content_height, part.groups[-1][1])
            result.groups.append((y, max(result.content_height, math.ceil(pen))))
            index += 1
            continue
        selected = []
        while index < len(crawl.groups) and crawl.groups[index].first_row - 1 <= item['end']:
            selected.append(crawl.groups[index])
            index += 1
        if item.get('logo_grid'):
            if any(not isinstance(block, LogoRow) for group in selected for block in group.blocks):
                raise ValueError('A logo layout can only contain logo rows. Move text outside its range.')
            artwork = [logo for group in selected for block in group.blocks for logo in block.logos]
            order = item.get('logo_order', [])
            artwork.sort(key=lambda logo: order.index(logo.label) if logo.label in order else len(order))
            selected = [Group([LogoRow([logo], row=logo.row)]) for logo in artwork]
        columns = item['columns']
        gutter = item.get('gap', 120)
        full_width = min(look.width * .9, 2 * min(look.center_x, look.width - look.center_x))
        width = int((full_width - (columns - 1) * gutter) / columns)
        if width < 200:
            raise ValueError('Side-by-side columns are too narrow. Reduce the gap or number of columns.')
        left = look.center_x - (columns * width + (columns - 1) * gutter) / 2
        local_look = copy.deepcopy(look)
        local_look.width = width
        local_look.center_x = width / 2
        local_look.music_width = local_look.legal_width = local_look.list_width = width
        grid_group_start = len(result.groups)
        grid_top = round(pen)
        for start in range(0, len(selected), columns):
            if start:
                pen += gap * flex
            y = round(pen)
            row_height = 0
            members = selected[start:start + columns]
            row_left = look.center_x - (len(members) * width + (len(members) - 1) * gutter) / 2
            for col, member in enumerate(members):
                part = layout(Crawl(groups=[member]), local_look, flex, width, item.get('alignment', 'center'))
                paste(part, round(row_left + col * (width + gutter)), y)
                if item.get('logo_grid'):
                    # Manual moves must not shift the automatic positions of
                    # later rows. Reserve the moved bounds after the full grid.
                    natural_bottom = max((logo.y-logo.dy+logo.h for logo in part.logos), default=0)
                    row_height = max(row_height, natural_bottom + local_look.logo_gap * flex)
                else:
                    row_height = max(row_height, part.content_height, part.groups[-1][1])
            pen += row_height
            result.groups.append((y, max(result.content_height, math.ceil(pen))))
        if item.get('logo_grid'):
            pen = max(pen, result.content_height)
            # The composition can have art dragged across grid-row boundaries;
            # preserve it as one panel-break unit.
            result.groups[grid_group_start:] = [(grid_top, math.ceil(pen))]
    result.target_height = result.content_height
    return result


def _list(L: Layout, b: ListBlock, look: Look, flex: float, pen: float, put) -> float:
    cols = max(1, b.columns)
    n = len(b.names)
    rows = math.ceil(n / cols)
    col_w = (look.list_width - (cols - 1) * look.list_column_gap) / cols
    left = look.center_x - look.list_width / 2
    lead = look.list.leading * flex
    for c in range(cols):
        cx = int(round(left + c * (col_w + look.list_column_gap) + col_w / 2))
        for r, name in enumerate(b.names[c * rows:(c + 1) * rows]):
            put(name, "list", cx, "ms", pen + r * lead, b.row + c * rows + r)
    return pen + rows * lead


# --------------------------------------------------------------------------- #

def measure(crawl: Crawl, look: Look) -> Tuple[int, int]:
    """(fixed_px, flex_px): content height is fixed + flex * scale.

    Measured at flex 1 and 2 rather than 0 and 1: at flex 0 every line piles
    onto the same pen position and the tallest style, not the last one, sets
    the bottom, which would skew the intercept.
    """
    h1 = layout(crawl, look, flex=1.0).content_height
    h2 = layout(crawl, look, flex=2.0).content_height
    flex_px = h2 - h1
    return h1 - flex_px, flex_px


def fit(crawl: Crawl, look: Look, flex: float, target_height: int) -> Layout:
    """Lay out at `flex` and pad to the solver's exact height."""
    L = layout(crawl, look, flex)
    if L.content_height > target_height:
        # Rounding can overshoot by a pixel or two; let it be, the last frame
        # is black either way. Anything larger means the solver was wrong.
        if L.content_height - target_height > 4:
            raise ValueError(f"layout {L.content_height}px exceeds target {target_height}px")
        target_height = L.content_height
    # Even, so every panel can be even-sized and land on whole pixels in Fusion.
    L.target_height = target_height + (target_height % 2)
    return L


# --------------------------------------------------------------------------- #

def split_panels(L: Layout, max_panel: int = 16000) -> List[Tuple[int, int]]:
    """Break the content into panels at group boundaries, each ≤ max_panel px.

    Aims for equal-height panels using the fewest that fit; if a single group
    is taller than max_panel the break falls inside it (and we warn upstream).
    """
    H = L.target_height + (L.target_height % 2)
    L.target_height = H
    # Candidate cut points: midway through each gap between groups, kept even.
    cuts = [((L.groups[i][1] + L.groups[i + 1][0]) // 4) * 2 for i in range(len(L.groups) - 1)]
    cuts = [c for c in cuts if 0 < c < H]
    n = max(1, math.ceil(H / max_panel))
    while True:
        bounds = _try_split(H, cuts, n, max_panel)
        if bounds or n > len(cuts) + 1:
            break
        n += 1
    if not bounds:
        # Fall back to hard cuts if the groups themselves are too tall.
        step = math.ceil(H / n / 2) * 2
        bounds = [(i * step, min(H, (i + 1) * step)) for i in range(n)]
    L.panels = bounds
    return bounds


def _try_split(H: int, cuts: List[int], n: int, max_panel: int):
    if n == 1:
        return [(0, H)] if H <= max_panel else None
    target = H / n
    bounds = []
    top = 0
    for k in range(1, n):
        want = k * target
        ok = [c for c in cuts if top < c and c - top <= max_panel]
        if not ok:
            return None
        cut = min(ok, key=lambda c: abs(c - want))
        bounds.append((top, cut))
        top = cut
    if H - top > max_panel:
        return None
    bounds.append((top, H))
    return bounds
