"""Lint: flag data problems for a human to decide on. Never auto-fixes.

Checks
  placeholder   template leftovers ("Name 3", "(clear field)", "Production Company")
  empty         a role with no names
  duplicate     the same name twice in one list, or the same role twice
  near-dup      names that differ by a typo (edit distance) across the crawl
  logo          bracketed logo slots that still need artwork
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, List

from .model import Crawl, Header, ListBlock, RolePair

PLACEHOLDER_RE = re.compile(
    r"^(name\s*\d*|title\s*\d*|role\s*\d*|\(clear field\)|tbd|tbc|xxx+|lorem.*)$"
    r"|production company|your (company|name)|insert |placeholder",
    re.I,
)

# Roles that legitimately appear more than once (per unit, per episode, etc.)
REPEATABLE_ROLES = {"produced by", "written by", "performed by", "courtesy of"}


@dataclass
class Finding:
    check: str      # placeholder | empty | duplicate | near-dup | logo
    severity: str   # error | warning | info
    row: int
    message: str
    target: str = ""  # source-cell meaning for spreadsheet highlighting
    # What the finding is about, independent of where it is. Dismissals are
    # stored by key, so they survive inserted rows and lapse if the text changes.
    key: str = ""

    def __str__(self) -> str:
        return f"[{self.severity}] row {self.row}: {self.message}"


def lint(crawl: Crawl, near_dup_ratio: float = 0.88) -> List[Finding]:
    out: List[Finding] = []
    out += _placeholders(crawl)
    out += _empties(crawl)
    out += _duplicates(crawl)
    out += _near_duplicates(crawl, near_dup_ratio)
    out += _logos(crawl)
    out.sort(key=lambda f: f.row)
    return out


# --------------------------------------------------------------------------- #

def _placeholders(crawl: Crawl) -> List[Finding]:
    out = []
    for b in crawl.blocks():
        texts = []
        if isinstance(b, Header):
            texts = [(b.text, b.row, "header")]
        elif isinstance(b, RolePair):
            texts = [(b.role, b.row, "role")] + [(n, b.row, "name") for n in b.names]
        elif isinstance(b, ListBlock):
            texts = [(n, b.row + i, "list") for i, n in enumerate(b.names)]
        for value, row, target in texts:
            if value and PLACEHOLDER_RE.search(value):
                out.append(Finding("placeholder", "error", row, f"template leftover: {value!r}", target,
                                   f"placeholder|{_norm(value)}"))
    return out


def _empties(crawl: Crawl) -> List[Finding]:
    out = []
    for b in crawl.blocks():
        if isinstance(b, RolePair):
            if b.role and not b.names and not b.names_pending:
                out.append(Finding("empty", "error", b.row, f"{b.role!r} has no names", "name",
                                   f"empty|{_norm(b.role)}"))
            elif b.names and not b.role:
                out.append(Finding("empty", "info", b.row, f"names without a role: {', '.join(b.names)}", "role",
                                   "no-role|" + "|".join(_norm(n) for n in b.names)))
    return out


def _duplicates(crawl: Crawl) -> List[Finding]:
    out = []
    # Same name twice inside one list (special thanks etc.)
    for b in crawl.blocks():
        if isinstance(b, ListBlock):
            seen = {}
            for k, n in enumerate(b.names):
                key = _norm(n)
                if key in seen:
                    out.append(Finding("duplicate", "warning", b.row + k,
                                       f"{n!r} already listed at row {b.row + seen[key]}", "list",
                                       f"duplicate|{key}"))
                else:
                    seen[key] = k
    # Same role twice inside one group (e.g. First AD listed twice)
    for g in crawl.groups:
        seen = {}
        for b in g.blocks:
            if isinstance(b, RolePair) and b.role and _norm(b.role) not in REPEATABLE_ROLES:
                key = _norm(b.role)
                if key in seen:
                    out.append(Finding("duplicate", "warning", b.row,
                                       f"role {b.role!r} already used at row {seen[key]}", "role",
                                       f"duplicate-role|{key}|" + "|".join(_norm(n) for n in b.names)))
                else:
                    seen[key] = b.row
    return out


def _near_duplicates(crawl: Crawl, ratio: float) -> List[Finding]:
    """Names anywhere in the crawl that are one typo apart."""
    names = []  # (norm, original, row)
    for b in crawl.blocks():
        if isinstance(b, RolePair):
            names += [(_norm(n), n, b.row, "name") for n in b.names]
        elif isinstance(b, ListBlock):
            names += [(_norm(n), n, b.row + k, "list") for k, n in enumerate(b.names)]

    out = []
    seen_pairs = set()
    for i in range(len(names)):
        a_norm, a, a_row, _ = names[i]
        if len(a_norm) < 6:
            continue
        for j in range(i + 1, len(names)):
            b_norm, b, b_row, target = names[j]
            if a_norm == b_norm or a_norm[0] != b_norm[0]:
                continue
            # Compare the shorter against the same-length head of the longer, so
            # "Lelsey Bohm" still matches "Lesley Bohm Photography".
            short, long = sorted((a_norm, b_norm), key=len)
            head = long[:len(short) + 1].rstrip()
            if abs(len(short) - len(head)) > 4:
                continue
            r = SequenceMatcher(None, short, head).ratio()
            if r >= ratio and _first_word_close(a_norm, b_norm):
                key = (a_norm, b_norm)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                out.append(Finding("near-dup", "warning", b_row,
                                   f"{b!r} looks like {a!r} (row {a_row})", target,
                                   f"near-dup|{a_norm}|{b_norm}"))
    return out


def _first_word_close(a: str, b: str) -> bool:
    """Only report when the first words differ by a typo, not two different people."""
    fa, fb = a.split(" ")[0], b.split(" ")[0]
    if fa == fb:
        return True
    return SequenceMatcher(None, fa, fb).ratio() >= 0.75


def _logos(crawl: Crawl) -> List[Finding]:
    out = []
    for lg in crawl.logos():
        if not lg.path:
            out.append(Finding("logo", "warning", lg.row, f"logo slot needs artwork: {lg.label!r}", "logo",
                               f"logo|{_norm(lg.label)}"))
        elif not os.path.isfile(lg.path):
            # Otherwise it would silently render as an empty placeholder box.
            out.append(Finding("logo", "error", lg.row,
                               f"logo file not found for {lg.label!r}: {os.path.basename(lg.path)}", "logo",
                               f"logo-missing|{_norm(lg.label)}"))
    return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())
