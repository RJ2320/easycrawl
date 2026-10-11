"""Where ffmpeg and ffprobe are.

Looked for, in order: a copy bundled with a packaged app (next to the
executable, or in PyInstaller's unpack folder), the PATH, and the
`imageio-ffmpeg` wheel (ffmpeg only). The result is cached per process.
"""

from __future__ import annotations

import os
import shutil
import sys
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

BUNDLE_FOLDER = "ffmpeg"     # folder of binaries inside a packaged app


def _bundle_dirs() -> List[Path]:
    dirs: List[Path] = []
    root = getattr(sys, "_MEIPASS", None)          # PyInstaller
    if root:
        dirs.append(Path(root) / BUNDLE_FOLDER)
    exe = Path(sys.executable).resolve().parent
    dirs += [exe / BUNDLE_FOLDER, exe.parent / "Resources" / BUNDLE_FOLDER]   # beside the app / in a .app bundle
    env = os.environ.get("CRAWL_FFMPEG_DIR")
    if env:
        dirs.insert(0, Path(env))
    return dirs


@lru_cache(maxsize=None)
def find(name: str) -> Optional[str]:
    """Path to `ffmpeg` or `ffprobe`, or None."""
    exe_name = name + (".exe" if sys.platform.startswith("win") else "")
    for folder in _bundle_dirs():
        candidate = folder / exe_name
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    if name == "ffmpeg":
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return None
    return None


def ffmpeg() -> Optional[str]:
    return find("ffmpeg")


def ffprobe() -> Optional[str]:
    return find("ffprobe")
