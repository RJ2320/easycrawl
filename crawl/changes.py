"""Bring a revised credits sheet into a crawl that is already built.

Three versions of the rows are involved:

    base      what the client last sent (snapshot taken at import / last update)
    current   the project's rows now: base plus edits made in the app
    new       the revised sheet

Comparing base with new gives the *client's* changes. Each one is located in
`current` by lining base up with current, so edits made in the app (a typo
fixed, a logo row added) are kept, and only what the client changed is
offered. Where the client changed rows that were also edited here, the change
is marked as a conflict so it gets looked at.

    changes = diff(base, current, new)
    rows, shifts = apply(current, [c for c in changes if c.accepted])
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import List, Optional, Sequence, Tuple

Row = Tuple[str, str, str]


@dataclass
class Change:
    kind: str                 # "add" | "remove" | "change"
    start: int                # zero-based range [start, end) in the current rows that is replaced
    end: int
    old: List[Row]            # the current rows in that range
    new: List[Row]            # what the client's sheet has instead
    conflict: bool = False    # these rows were also edited in the app
    sheet_row: int = 0        # 1-based row in the revised sheet (0 for a removal)
    accepted: bool = True

    def describe(self) -> str:
        where = f"row {self.start + 1}" if self.end - self.start <= 1 else f"rows {self.start + 1}–{self.end}"
        if self.kind == "add":
            return f"Add after row {self.start}: " + " / ".join(row_text(r) for r in self.new)
        if self.kind == "remove":
            return f"Remove {where}: " + " / ".join(row_text(r) for r in self.old)
        return (f"Change {where}: " + " / ".join(row_text(r) for r in self.old) +
                "  →  " + " / ".join(row_text(r) for r in self.new))


def row_text(row: Sequence[str]) -> str:
    """One line for a row: 'Role — Name, Name' or the header/list text."""
    b, c, d = (str(x).strip() for x in (list(row) + ["", "", ""])[:3])
    names = ", ".join(n.strip() for n in d.split("\n") if n.strip())
    parts = [p for p in (b, c) if p]
    left = " ".join(parts)
    if left and names:
        return f"{left} — {names}"
    return left or names or "(blank row)"


def _rows(rows) -> List[Row]:
    return [tuple((list(r) + ["", "", ""])[:3]) for r in rows]


def _opcodes(a: List[Row], b: List[Row]):
    return SequenceMatcher(None, a, b, autojunk=False).get_opcodes()


def diff(base: Optional[Sequence], current: Sequence, new: Sequence) -> List[Change]:
    """The client's changes (base → new), located in `current`.

    With no base snapshot (an older project), current stands in for it: every
    difference between the project and the new sheet is then offered.
    """
    current, new = _rows(current), _rows(new)
    base = _rows(base) if base is not None else current

    # Line base up with current. A boundary p (between base rows p-1 and p)
    # corresponds to a position in current; where rows were inserted locally at
    # that boundary it corresponds to a span, so keep both ends:
    #   before[p]  ahead of anything inserted locally at p
    #   after[p]   past it
    n, m = len(base), len(current)
    before = [m] * (n + 1)
    after = [0] * (n + 1)
    edited = [False] * n            # base row was changed or deleted locally
    inside_edit = [False] * (n + 1) # boundary lies strictly inside a locally edited run

    def at(pos: int, j: int) -> None:
        before[pos] = min(before[pos], j)
        after[pos] = max(after[pos], j)

    for tag, i1, i2, j1, j2 in _opcodes(base, current):
        at(i1, j1)
        at(i2, j2)
        for pos in range(i1 + 1, i2):
            if tag == "equal":
                at(pos, j1 + pos - i1)
            else:
                at(pos, j1)
                at(pos, j2)
                inside_edit[pos] = True
        if tag != "equal":
            for i in range(i1, i2):
                edited[i] = True

    changes: List[Change] = []
    for tag, b1, b2, n1, n2 in _opcodes(base, new):
        if tag == "equal":
            continue
        if b1 == b2:
            # The client inserted rows: they go after anything inserted here at the same spot.
            start = end = after[b1]
            conflict = inside_edit[b1]
        else:
            # Replace or delete base rows b1..b2. Rows edited here widen the span
            # to their whole local replacement; untouched ends stop short of
            # anything inserted locally beside them.
            start = before[b1] if edited[b1] else after[b1]
            end = after[b2] if edited[b2 - 1] else before[b2]
            end = max(start, end)
            conflict = any(edited[b1:b2])
        old_rows, new_rows = current[start:end], new[n1:n2]
        if conflict and old_rows == new_rows:
            continue                       # edited here to the same thing the client sent
        if tag == "replace" and len(old_rows) == len(new_rows) and not conflict:
            # Row-for-row edits are separate decisions.
            for k, (o, w) in enumerate(zip(old_rows, new_rows)):
                if o != w:
                    changes.append(Change("change", start + k, start + k + 1, [o], [w], False, n1 + k + 1))
            continue
        kind = "add" if not old_rows else "remove" if not new_rows else "change"
        changes.append(Change(kind, start, end, old_rows, new_rows, conflict, n1 + 1 if new_rows else 0))
    return changes


@dataclass
class Shift:
    """How a change moved rows, for re-pointing row ranges (arrangements, overrides)."""
    removed: List[int] = field(default_factory=list)   # zero-based rows deleted, in the rows as they were then
    inserted_at: int = 0
    inserted: int = 0


def apply(current: Sequence, changes: Sequence[Change]) -> Tuple[List[List[str]], List[Shift], List[Tuple[int, int]]]:
    """Apply accepted changes to the rows.

    Returns (rows, shifts, marks): `shifts` in the order they must be replayed
    on row-range bookkeeping (bottom of the sheet first, so earlier positions
    stay valid), and `marks` as (start, end) ranges of the rows that are new or
    different in the result.
    """
    rows = [list(r) for r in _rows(current)]
    shifts: List[Shift] = []
    for change in sorted((c for c in changes if c.accepted), key=lambda c: (c.start, c.end), reverse=True):
        rows[change.start:change.end] = [list(r) for r in change.new]
        if len(change.old) != len(change.new):
            shifts.append(Shift(list(range(change.start, change.end)), change.start, len(change.new)))

    # Where the changed rows ended up, top to bottom.
    marks: List[Tuple[int, int]] = []
    offset = 0
    for change in sorted((c for c in changes if c.accepted), key=lambda c: (c.start, c.end)):
        start = change.start + offset
        if change.new:
            marks.append((start, start + len(change.new) - 1))
        offset += len(change.new) - (change.end - change.start)
    return rows, shifts, marks


def replay(items: List[dict], shifts: Sequence[Shift]) -> None:
    """Move {start, end} row ranges the way `apply` moved the rows."""
    from . import arrangements
    for shift in shifts:
        if shift.removed:
            arrangements.delete_rows(items, shift.removed)
        for k in range(shift.inserted):
            arrangements.insert_row(items, shift.inserted_at + k)


def summary(changes: Sequence[Change]) -> str:
    """Counts in a sentence: '3 changed, 2 added, 1 removed (1 also edited here)'."""
    counts = {"change": 0, "add": 0, "remove": 0}
    for c in changes:
        counts[c.kind] += 1
    parts = [f"{counts['change']} changed", f"{counts['add']} added", f"{counts['remove']} removed"]
    text = ", ".join(p for p in parts if not p.startswith("0 ")) or "no differences"
    conflicts = sum(c.conflict for c in changes)
    if conflicts:
        text += f" ({conflicts} also edited here)"
    return text


def report(changes: Sequence[Change], title: str = "Credit changes") -> str:
    """A plain-text change list, e.g. to send back as confirmation."""
    lines = [title, summary(changes), ""]
    lines += [("  " if c.accepted else "  (not applied) ") + c.describe() for c in changes]
    return "\n".join(lines) + "\n"
