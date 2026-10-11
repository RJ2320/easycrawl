"""Draw the app icon: a dark rounded tile with three light lines, like credits mid-scroll.

Writes icon.png (1024 px) beside this file, plus icon.icns on macOS and icon.ico
on Windows. Original artwork, generated so there is nothing to keep in sync.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
BG, TILE, LINE, ACCENT = (0, 0, 0, 0), (24, 25, 29, 255), (232, 233, 236, 255), (76, 159, 254, 255)


def draw(px: int) -> Image.Image:
    im = Image.new("RGBA", (px, px), BG)
    d = ImageDraw.Draw(im)
    pad = px * 0.08
    d.rounded_rectangle([pad, pad, px - pad, px - pad], radius=px * 0.2, fill=TILE)
    # Three centred lines of different lengths, the middle one the brightest,
    # and a short accent line: a crawl passing through the frame.
    cx = px / 2
    for y, w, colour in ((0.33, 0.46, (160, 162, 168, 255)), (0.50, 0.62, LINE), (0.67, 0.38, (160, 162, 168, 255))):
        h = px * 0.055
        d.rounded_rectangle([cx - px * w / 2, px * y - h / 2, cx + px * w / 2, px * y + h / 2], radius=h / 2, fill=colour)
    d.rounded_rectangle([cx - px * 0.09, px * 0.80, cx + px * 0.09, px * 0.80 + px * 0.04], radius=px * 0.02, fill=ACCENT)
    return im


def main() -> None:
    master = draw(1024)
    master.save(HERE / "icon.png")
    assets = HERE.parent / "crawl" / "ui" / "assets"
    assets.mkdir(exist_ok=True)
    master.save(assets / "icon.png")
    if sys.platform == "darwin":
        with tempfile.TemporaryDirectory() as tmp:
            iconset = Path(tmp) / "icon.iconset"
            iconset.mkdir()
            for size in (16, 32, 128, 256, 512):
                draw(size).save(iconset / f"icon_{size}x{size}.png")
                draw(size * 2).save(iconset / f"icon_{size}x{size}@2x.png")
            subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "icon.icns")], check=True)
    elif sys.platform.startswith("win"):
        master.save(HERE / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
        master.save(assets / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    print("icon written to", HERE)


if __name__ == "__main__":
    main()
