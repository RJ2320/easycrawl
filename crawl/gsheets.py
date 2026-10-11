"""Credits that live in Google Sheets.

A sheet shared as "Anyone with the link can view" can be downloaded as a
workbook without signing in, so a pasted link is as good as a file: the
whole workbook (every tab) comes down as .xlsx and goes through the normal
reader. Refreshing re-downloads it and the usual revision merge shows what
changed. Sheets that are not shared need a Google sign-in, which this does
not do; the error says what to change in the sharing settings instead.
"""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional, Tuple

LINK_RE = re.compile(r"docs\.google\.com/spreadsheets/(?:u/\d+/)?d/(?:e/)?([A-Za-z0-9_-]{20,})")
GID_RE = re.compile(r"[#?&]gid=(\d+)")
TIMEOUT = 30
SHARE_HINT = ("In Google Sheets choose Share, set General access to \"Anyone with the link\" "
              "(Viewer is enough), then try again.")


class GoogleSheetError(Exception):
    pass


def is_link(text: str) -> bool:
    return bool(LINK_RE.search(text or ""))


def parse(url: str) -> Tuple[str, Optional[str]]:
    """(document id, tab gid or None) from any Google Sheets URL."""
    m = LINK_RE.search(url or "")
    if not m:
        raise GoogleSheetError("That isn't a Google Sheets link. It should look like "
                               "https://docs.google.com/spreadsheets/d/…/edit")
    gid = GID_RE.search(url)
    return m.group(1), (gid.group(1) if gid else None)


def canonical(url: str) -> str:
    """The link without view state, so the same sheet is recognised however it was copied."""
    doc, gid = parse(url)
    return f"https://docs.google.com/spreadsheets/d/{doc}/edit" + (f"#gid={gid}" if gid else "")


def export_url(url: str) -> str:
    doc, _ = parse(url)
    return f"https://docs.google.com/spreadsheets/d/{doc}/export?format=xlsx"


def filename(url: str) -> str:
    doc, _ = parse(url)
    return f"google-sheet-{doc[:12]}.xlsx"


Opener = Callable[..., object]


def _urlopen(request, timeout):
    """urlopen with certifi's root certificates: a packaged app has no system
    CA bundle to fall back on, so HTTPS would otherwise fail to verify."""
    try:
        import certifi
        import ssl
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = None
    return urllib.request.urlopen(request, timeout=timeout, context=context)


def fetch(url: str, folder: str, opener: Optional[Opener] = None) -> str:
    """Download the workbook behind `url` into `folder`; returns the .xlsx path.

    `opener(request, timeout=...)` stands in for urllib.request.urlopen in tests.
    """
    opener = opener or _urlopen
    request = urllib.request.Request(export_url(url), headers={"User-Agent": "EasyCrawl"})
    try:
        with opener(request, timeout=TIMEOUT) as response:   # type: ignore[arg-type]
            final = getattr(response, "url", "") or getattr(response, "geturl", lambda: "")()
            kind = response.headers.get("Content-Type", "") if hasattr(response, "headers") else ""
            data = response.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise GoogleSheetError("Google won't hand out this sheet without a sign-in, so it isn't shared. "
                                   + SHARE_HINT) from e
        if e.code == 404:
            raise GoogleSheetError("Google has no sheet at that link. Check it was copied completely.") from e
        raise GoogleSheetError(f"Google replied {e.code} {e.reason}.") from e
    except urllib.error.URLError as e:
        raise GoogleSheetError(f"Couldn't reach Google Sheets: {e.reason}. Check the internet connection.") from e
    except OSError as e:
        raise GoogleSheetError(f"Couldn't reach Google Sheets: {e}.") from e

    if "accounts.google.com" in (final or "") or "text/html" in kind or data[:5].lower() == b"<!doc" \
            or data[:5].lower() == b"<html":
        raise GoogleSheetError("Google asked for a sign-in instead of sending the sheet, so it isn't shared. "
                               + SHARE_HINT)
    if data[:2] != b"PK":
        raise GoogleSheetError("Google sent something that isn't a workbook. Try the link again in a browser.")

    os.makedirs(folder, exist_ok=True)
    path = Path(folder) / filename(url)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return str(path)
