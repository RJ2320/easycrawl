"""Download static ffmpeg + ffprobe for this platform into packaging/ffmpeg/.

They are bundled into the app so users need not install ffmpeg. The builds
are GPL (they include x264 for H.264); see the README's licence note.
"""
import io
import os
import platform
import ssl
import certifi
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "ffmpeg"

MAC_ARCH = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "amd64"
MAC = {name: f"https://ffmpeg.martin-riedl.de/redirect/latest/macos/{MAC_ARCH}/release/{name}.zip"
       for name in ("ffmpeg", "ffprobe")}
WIN = "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip"
LINUX = "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-linux64-gpl.tar.xz"


def fetch(url: str) -> bytes:
    print("downloading", url)
    request = urllib.request.Request(url, headers={"User-Agent": "EasyCrawl-build"})
    with urllib.request.urlopen(request, timeout=120, context=ssl.create_default_context(cafile=certifi.where())) as r:
        return r.read()


def write(name: str, data: bytes) -> None:
    path = OUT / name
    path.write_bytes(data)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print(f"  {name}: {len(data) // 1_000_000} MB")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    exe = ".exe" if sys.platform.startswith("win") else ""
    if all((OUT / (n + exe)).is_file() for n in ("ffmpeg", "ffprobe")):
        print("ffmpeg and ffprobe already in", OUT)
        return
    if sys.platform == "darwin":
        for name, url in MAC.items():
            with zipfile.ZipFile(io.BytesIO(fetch(url))) as z:
                member = next(m for m in z.namelist() if Path(m).name == name)
                write(name, z.read(member))
    elif sys.platform.startswith("win"):
        with zipfile.ZipFile(io.BytesIO(fetch(WIN))) as z:
            for name in ("ffmpeg.exe", "ffprobe.exe"):
                member = next(m for m in z.namelist() if m.endswith("/bin/" + name))
                write(name, z.read(member))
    else:
        with tarfile.open(fileobj=io.BytesIO(fetch(LINUX)), mode="r:xz") as t:
            for name in ("ffmpeg", "ffprobe"):
                member = next(m for m in t.getmembers() if m.name.endswith("/bin/" + name))
                write(name, t.extractfile(member).read())


if __name__ == "__main__":
    main()
