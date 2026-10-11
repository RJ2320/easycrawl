"""Sheet → data model.

The credits template fixes what each column means:

    Col B  role / title            (also: single-column lists, legal, logos)
    Col C  centered header, or song title
    Col D  name(s); '\\n' inside a cell stacks names under one role

Blank rows separate groups. A long run of rows that only have Col B filled is a
single-column list (brand partners, special thanks) and becomes a ListBlock.

Sheets that don't follow the template can still be read: the credits can be
in other columns (found automatically, or named with a column spec such as
"A,B,C" or "B,C,D-F" when the names run across several columns), can start
below a few title rows, and can be on any worksheet of a workbook.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .model import Crawl, Group, Header, Legal, ListBlock, Logo, LogoRow, RolePair

COL_B, COL_C, COL_D = 1, 2, 3

# Runs of Col-B-only rows at least this long are lists, shorter ones are roles
# that are missing their names (which lint will flag).
LIST_MIN_RUN = 6

# Rows this long, or with a copyright mark, are legal text rather than a role.
LEGAL_MIN_CHARS = 90
LEGAL_RE = re.compile(r"©|\(c\)|copyright|all rights reserved", re.I)

# "[Logo: Studio]" / "[STUDIO LOGO]" / "Logo: Studio"; several on one row
# separated by "|" are set side by side: "[Logo: A] | [Logo: B]"
LOGO_RE = re.compile(r"^\s*(\[.*\]|logo\s*:.*)\s*$", re.I)
LOGO_SPLIT_RE = re.compile(r"\s*\|\s*")


def logo_labels(text: str) -> List[str]:
    """Labels of the logo slots on a row, or [] if it isn't a logo row."""
    parts = [p for p in LOGO_SPLIT_RE.split(text.strip()) if p]
    if not parts or not all(LOGO_RE.match(p) for p in parts):
        return []
    return [re.sub(r"^\s*(\[\s*)?(logo\s*:\s*)?", "", p, flags=re.I).rstrip("] ").strip() for p in parts]


Row = Tuple[str, str, str]  # (B, C, D), already stripped


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #

MAX_COLS = 12         # columns A–L are looked at; the template uses B–D
SHIFT_MARGIN = 1.25   # another 3-column window must hold this much more text to be "the" columns
SUMMARY_AFTER = 8     # more ignored cells than this are reported once, not row by row
TEMPLATE_COLUMNS = "B,C,D"
PREVIEW_ROWS = 3      # rows of text shown per worksheet when choosing one

# Worksheet names that mark the credits tab, most to least likely.
SHEET_NAMES = ("crawl", "end crawl", "credits", "end credits", "roller")


@dataclass
class ImportNote:
    """Something the reader did, or could not do, to make an off-template sheet fit."""
    row: int          # 1-based sheet row
    message: str


@dataclass
class SheetInfo:
    """A worksheet in a workbook (a CSV has one, unnamed)."""
    name: str
    filled: int                      # rows with any text
    preview: List[str] = field(default_factory=list)   # the first few rows' text, for picking a sheet


class SheetNotFound(ValueError):
    """The named worksheet isn't in the workbook."""

    def __init__(self, name: str, available: List[str]):
        super().__init__(f"Worksheet {name!r} not found. Available worksheets: {', '.join(available)}")
        self.name, self.available = name, available


def is_workbook(path: str) -> bool:
    return Path(path).suffix.lower() in (".xlsx", ".xlsm")


def read_rows(path: str, sheet: Optional[str] = "Crawl") -> List[Row]:
    """Return one (B, C, D) tuple per sheet row. Index 0 is sheet row 1."""
    return read_sheet(path, sheet)[0]


def read_sheet(path: str, sheet: Optional[str] = "Crawl", columns: str = "",
               start_row: int = 1) -> Tuple[List[Row], List[ImportNote]]:
    """Read a sheet that may not follow the template exactly.

    The template keeps credits in columns B–D. Real sheets drift: a paragraph
    typed in column A, or the whole table one column over. Rather than drop
    what is outside B–D, this
      - finds which three adjacent columns actually hold the credits (or uses
        `columns`, a spec such as "A,B,C" or "B,C,D-F", when given),
      - moves a stray cell into the first of them when its row is otherwise
        empty (legal text in column A becomes a normal legal row),
      - and returns a note for everything it moved or had to leave out.

    `sheet` names the worksheet of a workbook; None or "" picks the likeliest
    one (see `guess_sheet`). Rows above `start_row` are left blank.
    """
    return normalize_grid(read_grid(path, sheet), columns, start_row)


def read_grid(path: str, sheet: Optional[str] = None) -> List[List[str]]:
    """The sheet's cells as text, columns A onward, one list per row."""
    p = Path(path)
    if is_workbook(path):
        return _read_xlsx_grid(p, sheet)
    return _read_csv_grid(p)


def sheets(path: str) -> List[SheetInfo]:
    """The worksheets in a file, with how much is on each."""
    if not is_workbook(path):
        return [_sheet_info("", _read_csv_grid(Path(path)))]
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=False, data_only=True)
    try:
        return [_sheet_info(ws.title, _xlsx_rows(ws)) for ws in wb.worksheets]
    finally:
        wb.close()


def _sheet_info(name: str, grid: Sequence[Sequence[str]]) -> SheetInfo:
    filled = [" · ".join(v for v in r if v) for r in grid if any(r)]
    return SheetInfo(name, len(filled), [_clip(t, 60) for t in filled[:PREVIEW_ROWS]])


def guess_sheet(infos: Sequence[SheetInfo]) -> Optional[str]:
    """The worksheet most likely to hold the credits: one named for them,
    else the one with the most on it."""
    named = {info.name.strip().lower(): info for info in infos if info.filled}
    for want in SHEET_NAMES:
        if want in named:
            return named[want].name
    for want in SHEET_NAMES:
        for key, info in named.items():
            if want in key:
                return info.name
    best = max((info for info in infos if info.filled), key=lambda info: info.filled, default=None)
    return best.name if best else (infos[0].name if infos else None)


# ---- columns ----------------------------------------------------------------

def _letter(col: int) -> str:
    return chr(ord("A") + col)


def column_index(letter: str) -> int:
    letter = letter.strip().upper()
    if not letter or not letter.isalpha():
        raise ValueError(f"not a column: {letter!r}")
    index = 0
    for ch in letter:
        index = index * 26 + ord(ch) - ord("A") + 1
    return index - 1


def parse_columns(spec: str) -> Tuple[int, int, int, int]:
    """'B,C,D' or 'B,C,D-F' → zero-based (role, header, first names column, last names column)."""
    parts = [p.strip() for p in spec.replace(";", ",").split(",")]
    if len(parts) != 3 or not all(parts):
        raise ValueError(f"columns should be three letters such as 'B,C,D' or 'B,C,D-F', not {spec!r}")
    role, header = column_index(parts[0]), column_index(parts[1])
    first, _, last = parts[2].partition("-")
    first = column_index(first)
    last = column_index(last) if last else first
    if last < first:
        first, last = last, first
    used = [role, header] + list(range(first, last + 1))
    if len(set(used)) != len(used):
        raise ValueError("the role, header and names columns must be different")
    return role, header, first, last


def format_columns(role: int, header: int, first: int, last: int) -> str:
    names = _letter(first) if last == first else f"{_letter(first)}-{_letter(last)}"
    return f"{_letter(role)},{_letter(header)},{names}"


def detect_columns(grid: Sequence[Sequence[str]]) -> str:
    """Which three adjacent columns hold the credits: B–D unless another window clearly holds more."""
    width = max(max((len(r) for r in grid), default=0), 4)
    counts = [sum(1 for r in grid if c < len(r) and r[c]) for c in range(width)]

    def score(start: int) -> int:
        return sum(counts[start:start + 3])
    best = max(range(width - 2), key=score)
    start = best if best != COL_B and score(best) > score(COL_B) * SHIFT_MARGIN else COL_B
    return format_columns(start, start + 1, start + 2, start + 2)


def normalize_grid(grid: Sequence[Sequence[str]], columns: str = "",
                   start_row: int = 1) -> Tuple[List[Row], List[ImportNote]]:
    notes: List[ImportNote] = []
    detected = detect_columns(grid)
    role, header, first, last = parse_columns(columns or detected)
    width = max(max((len(r) for r in grid), default=0), last + 1, 4)
    grid = [list(r) + [""] * (width - len(r)) for r in grid]
    window = {role, header, *range(first, last + 1)}
    skip = max(0, int(start_row) - 1)

    if not columns and detected != TEMPLATE_COLUMNS:
        start = role
        hit = next((i for i, r in enumerate(grid) if i >= skip and any(r[c] for c in window)), 0)
        notes.append(ImportNote(hit + 1, f"This sheet's credits are in columns {_letter(start)}–{_letter(start + 2)}, "
                                         f"not B–D as in the template; they were read from there."))

    rows: List[Row] = []
    ignored: List[Tuple[int, str, str]] = []     # (row, column letter, text)
    for index, r in enumerate(grid):
        if index < skip:
            rows.append(("", "", ""))            # kept so row numbers still match the sheet
            continue
        inside = [r[role], r[header], "\n".join(r[c] for c in range(first, last + 1) if r[c])]
        outside = [(c, r[c]) for c in range(width) if c not in window and r[c]]
        if outside and not any(inside):
            # Nothing else on the row: this is the row's content, just in the wrong column.
            text = "\n".join(value for _, value in outside)
            inside[0] = text
            cols = ", ".join(_letter(c) for c, _ in outside)
            notes.append(ImportNote(index + 1, f"Text was in column {cols}, outside the template's columns; "
                                               f"moved into column B: {_clip(text)!r}"))
        else:
            ignored += [(index + 1, _letter(c), value) for c, value in outside]
        rows.append(tuple(inside))

    if len(ignored) > SUMMARY_AFTER:
        cols = ", ".join(sorted({col for _, col, _ in ignored}))
        notes.append(ImportNote(ignored[0][0], f"{len(ignored)} cells in column {cols} sit beside credits and were "
                                               f"not imported (first: {_clip(ignored[0][2])!r}). Check they are notes; "
                                               f"if they are credits, change the columns under File → Import Options."))
    else:
        notes += [ImportNote(row, f"Not imported: column {col} has {_clip(value)!r} beside this row's credits.")
                  for row, col, value in ignored]
    notes.sort(key=lambda n: n.row)
    return rows, notes


def _clip(text: str, limit: int = 48) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _cell(v) -> str:
    if v is None:
        return ""
    value = str(v).replace("\r\n", "\n").strip()
    if re.fullmatch(r"\(\s*clear\s+fields?\s*\)", value, re.I):
        return ""
    return value


def _read_csv_grid(p: Path) -> List[List[str]]:
    with open(p, newline="", encoding="utf-8-sig") as f:
        return [[_cell(v) for v in raw[:MAX_COLS]] for raw in csv.reader(f)]


def _read_xlsx_grid(p: Path, sheet: Optional[str]) -> List[List[str]]:
    import openpyxl

    wb = openpyxl.load_workbook(p, read_only=False, data_only=True)
    try:
        if sheet and sheet not in wb.sheetnames:
            raise SheetNotFound(sheet, wb.sheetnames)
        if not sheet:
            sheet = guess_sheet([_sheet_info(ws.title, _xlsx_rows(ws)) for ws in wb.worksheets])
        return _xlsx_rows(wb[sheet] if sheet else wb.worksheets[-1])
    finally:
        wb.close()


def _xlsx_rows(ws) -> List[List[str]]:
    grid: List[List[str]] = []
    dimensions = getattr(ws, "row_dimensions", None)     # not available on read-only sheets
    for row_number, raw in enumerate(ws.iter_rows(min_row=1, min_col=1, max_col=MAX_COLS, values_only=True), 1):
        dimension = dimensions.get(row_number) if dimensions is not None else None
        if dimension is not None and dimension.hidden:
            # Preserve worksheet coordinates for findings and arrangements.
            grid.append([])
            continue
        grid.append([_cell(v) for v in raw])
    return grid


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

# Layout overrides for Col-B-only rows, keyed by zero-based row (see project.overrides):
#   roles    each row is a role in the left column, names to come
#   list     set in list columns even if the run is short
#   center   one centred line per row
LAYOUT_KINDS = ("roles", "list", "center")


def parse(rows: Sequence[Row], source: str = "", list_columns: int = 3, break_before=(),
          kinds: Optional[dict] = None) -> Crawl:
    # Also normalize embedded project rows and edits, not only file imports.
    # Keep row positions so lint continues to reference the original sheet.
    rows = [tuple(_cell(value) for value in row) for row in rows]
    kinds = kinds or {}
    crawl = Crawl(source=source)
    group = Group()

    def flush():
        nonlocal group
        if group.blocks:
            crawl.groups.append(group)
        group = Group()

    in_music = False
    in_song = False
    i = 0
    n = len(rows)
    while i < n:
        if i in break_before:
            flush()
        b, c, d = rows[i]
        rownum = i + 1

        if not (b or c or d):
            flush()
            i += 1
            continue

        labels = logo_labels(b or c) if not d else []
        if labels:
            group.blocks.append(LogoRow([Logo(label=l, row=rownum) for l in labels], row=rownum))
            i += 1
            continue

        plain_b = re.sub(r"\*([^*\n]+)\*", r"\1", b)
        plain_c = re.sub(r"\*([^*\n]+)\*", r"\1", c)
        # Music uses B for the label and C (or D) for names. C-only rows
        # within a song can be continuing writers, not new section headings.
        if plain_c.upper() == "MUSIC" and not b and not d:
            in_music, in_song = True, False
        quoted_song = bool(c and plain_c.startswith(('"', '“', "'")))
        if in_music and c and not b and not d and quoted_song:
            flush()
            in_song = True
            group.blocks.append(Header(text=c, level=2, row=rownum))
            i += 1
            continue
        if in_music and in_song and (plain_b.lower() in
                {"written by", "performed by", "produced by", "courtesy of", "published by"}
                or d or (c and not b and (not _is_caps(c) or (i > 0 and any(rows[i - 1]))))):
            group.blocks.append(RolePair(role=b, names=_split_names(d or c), row=rownum, music=True))
            i += 1
            continue
        if c and not b and not d and _is_caps(c) and plain_c.upper() != "MUSIC":
            in_music, in_song = False, False
        if b and not c and not d and plain_b.lower() not in {"written by", "performed by", "produced by", "courtesy of", "published by"}:
            in_music, in_song = False, False
        if b and c and not d:
            group.blocks.append(RolePair(role=b, names=_split_names(c), row=rownum))
            i += 1
            continue
        if c:
            group.blocks.append(Header(text=c, level=1 if _is_caps(c) else 2, row=rownum))
            i += 1
            continue
        if d:
            group.blocks.append(RolePair(role=b, names=_split_names(d), row=rownum))
            i += 1
            continue

        # Only Col B is filled from here on.
        if _looks_legal(b):
            group.blocks.append(Legal(text=b, row=rownum))
            i += 1
            continue

        kind = kinds.get(i)
        if kind == "roles":
            group.blocks.append(RolePair(role=b, names=[], row=rownum, names_pending=True))
            i += 1
            continue

        run = _b_only_run(rows, i, break_before, kinds)
        if kind in ("list", "center") or run >= LIST_MIN_RUN:
            names = [rows[j][0] for j in range(i, i + run)]
            columns = 1 if kind == "center" else list_columns
            group.blocks.append(ListBlock(names=names, columns=columns, row=rownum))
            i += run
            continue

        group.blocks.append(RolePair(role=b, names=[], row=rownum))
        i += 1

    flush()
    # Blank rows within a song are not separate side-by-side blocks.
    merged = []
    for current in crawl.groups:
        continuation = all(isinstance(block, RolePair) and block.music for block in current.blocks)
        previous_song = merged and any(isinstance(block, Header) and block.level == 2
                                      for block in merged[-1].blocks)
        boundary = merged and any(merged[-1].blocks[-1].row <= edge < current.first_row
                                  for edge in break_before)
        if continuation and previous_song and not boundary:
            merged[-1].blocks.extend(current.blocks)
        else:
            merged.append(current)
    crawl.groups = merged
    return crawl


def load(path: str, sheet: Optional[str] = "", list_columns: int = 3) -> Crawl:
    return parse(read_rows(path, sheet), source=str(path), list_columns=list_columns)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _split_names(d: str) -> List[str]:
    return [s.strip() for s in d.split("\n") if s.strip()]


def _is_caps(s: str) -> bool:
    letters = [ch for ch in s if ch.isalpha()]
    return bool(letters) and all(ch.isupper() for ch in letters)


def _looks_legal(b: str) -> bool:
    return len(b) >= LEGAL_MIN_CHARS or bool(LEGAL_RE.search(b))


def _b_only_run(rows: Sequence[Row], start: int, break_before=(), kinds: Optional[dict] = None) -> int:
    """Length of the run of rows from `start` that have only Col B filled and
    share the start row's layout kind."""
    kinds = kinds or {}
    kind = kinds.get(start)
    j = start
    while j < len(rows) and (j == start or j not in break_before):
        b, c, d = rows[j]
        if not b or c or d or _looks_legal(b) or logo_labels(b) or kinds.get(j) != kind:
            break
        j += 1
    return j - start
