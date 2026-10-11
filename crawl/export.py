"""Render the crawl straight to a movie file.

The whole crawl is drawn once as one tall image, padded with a frame's worth of
black above and below. Frame `f` is then a plain slice of that image, `speed`
rows further down than frame `f - 1`, piped raw into ffmpeg. No resampling
anywhere: the integer speed means every frame is pixel-identical to a crop.

    export_movie(layout, look, solution, timing, "crawl.mov", "prores422hq")
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np
from PIL import Image

from . import tools
from .layout import Layout
from .look import Look
from .render import render_panel
from .timing import Solution, Timing


@dataclass(frozen=True)
class Codec:
    key: str
    label: str
    ext: str
    alpha: bool                      # can carry an alpha channel
    args: List[str]                  # encoder args without alpha
    alpha_args: List[str]            # encoder args with alpha (if alpha)


CODECS: Dict[str, Codec] = {
    "prores4444": Codec("prores4444", "ProRes 4444", ".mov", True,
                        ["-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuv444p10le"],
                        ["-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le"]),
    "prores422hq": Codec("prores422hq", "ProRes 422 HQ", ".mov", False,
                         ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"], []),
    "h264": Codec("h264", "H.264 (review)", ".mp4", False,
                  ["-c:v", "libx264", "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p"], []),
    "png": Codec("png", "PNG sequence", "", True,
                 ["-c:v", "png", "-pix_fmt", "rgb24"], ["-c:v", "png", "-pix_fmt", "rgba"]),
}
DEFAULT_CODEC = "prores422hq"

# Tag Rec.709 both on the frames (setparams) and the stream; either alone is
# dropped by some muxers.
_COLOUR = ["-vf", "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv",
           "-color_range", "tv", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]


class ExportCancelled(Exception):
    """The export was stopped on request; anything half-written has been removed."""


def find_ffmpeg() -> Optional[str]:
    return tools.ffmpeg()


def _rate(fps: float) -> str:
    """ffmpeg-friendly rate: 23.976 → 24000/1001."""
    for ntsc in (24, 30, 60):
        if abs(fps - ntsc * 1000 / 1001) < 0.002:
            return f"{ntsc * 1000}/1001"
    fr = Fraction(fps).limit_denominator(1001)
    return f"{fr.numerator}/{fr.denominator}"


# --------------------------------------------------------------------------- #

def render_strip(L: Layout, look: Look, colour: bool,
                 progress: Optional[Callable[[str, int, int], None]] = None,
                 cancel: Optional[Callable[[], bool]] = None) -> np.ndarray:
    """The whole crawl as one array, with a frame of black above and below.

    Shape (frame_h + H + frame_h, W) uint8 for grey, (…, W, 4) for RGBA.
    Drawn panel by panel so peak memory is the strip, not the strip twice.
    """
    H, W, fh = L.target_height, look.width, look.height
    shape = (fh + H + fh, W, 4) if colour else (fh + H + fh, W)
    strip = np.zeros(shape, np.uint8)
    chunk = 8192
    tops = list(range(0, H, chunk))
    for i, top in enumerate(tops):
        if cancel and cancel():
            raise ExportCancelled()
        bottom = min(H, top + chunk)
        img = render_panel(L, look, top, bottom, 1.0, look.supersample, colour=colour)
        strip[fh + top: fh + bottom] = np.asarray(img)
        if progress:
            progress("draw", i + 1, len(tops))
    return strip


def _is_chromatic(path: str) -> bool:
    """True if the artwork has any real colour (not just greys)."""
    try:
        with Image.open(path) as im:
            im = im.convert("RGBA")
            im.thumbnail((128, 128))
            a = np.asarray(im, np.int16)
        visible = a[..., 3] > 8
        rgb = a[..., :3][visible]
        return bool(rgb.size) and int((rgb.max(axis=1) - rgb.min(axis=1)).max()) > 12
    except Exception:
        return False


def needs_colour(look: Look, L: Optional[Layout] = None) -> bool:
    """Grey is enough unless a text style or a logo actually has colour."""
    if any(tuple(s.color) != (1.0, 1.0, 1.0) for s in look.styles().values()):
        return True
    return bool(L) and any(lg.path and _is_chromatic(lg.path) for lg in L.logos)


def export_movie(L: Layout, look: Look, sol: Solution, timing: Timing, out_path: str,
                 codec: str = DEFAULT_CODEC, alpha: bool = False,
                 progress: Optional[Callable[[str, int, int], None]] = None,
                 ffmpeg: Optional[str] = None,
                 cancel: Optional[Callable[[], bool]] = None) -> Path:
    """Write the crawl as a movie (or PNG sequence for codec 'png'). Returns the path written.

    `cancel` is polled between frames; when it returns True the encoder is
    stopped, the partial output removed and ExportCancelled raised.
    """
    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found: install it (brew install ffmpeg) or pip install imageio-ffmpeg")
    c = CODECS[codec]
    alpha = alpha and c.alpha
    colour = alpha or needs_colour(look, L)

    out = Path(out_path)
    if c.ext and out.suffix.lower() != c.ext:
        out = out.with_suffix(c.ext)
    made_folder = codec == "png" and not out.exists()
    if codec == "png":
        out.mkdir(parents=True, exist_ok=True)
        target = str(out / (out.name + "_%05d.png"))
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        target = str(out)

    def discard():
        """Remove what a stopped export left behind. A PNG folder that already
        existed is left alone: it may hold frames from an earlier export."""
        if codec != "png":
            out.unlink(missing_ok=True)
        elif made_folder:
            shutil.rmtree(out, ignore_errors=True)

    try:
        strip = render_strip(L, look, colour, progress, cancel)
    except ExportCancelled:
        discard()
        raise
    W, fh = look.width, look.height
    if colour and not alpha:
        # Premultiplied RGBA over black is just RGB.
        strip = np.ascontiguousarray(strip[..., :3])
    pix_in = "rgba" if alpha else ("rgb24" if colour else "gray")

    enc = list(c.alpha_args if alpha else c.args)
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", pix_in, "-s", f"{W}x{fh}", "-r", _rate(timing.fps), "-i", "-",
           *enc, *_COLOUR, "-r", _rate(timing.fps)]
    if codec != "png":
        cmd += ["-movflags", "+faststart"]
    cmd.append(target)

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    total = sol.total_frames
    black = np.zeros((fh,) + strip.shape[1:], np.uint8).tobytes()
    try:
        for f in range(total):
            if cancel and cancel():
                raise ExportCancelled()
            k = f - timing.head_hold
            if k < 0 or k > sol.travel_frames:
                data = black
            else:
                start = k * sol.speed
                data = strip[start:start + fh].tobytes()
            proc.stdin.write(data)
            if progress and (f % 24 == 0 or f == total - 1):
                progress("encode", f + 1, total)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    except ExportCancelled:
        # Stop the encoder rather than let it finish a truncated file.
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        for pipe in (proc.stdin, proc.stderr):
            try:
                pipe.close()
            except OSError:
                pass
        discard()
        raise
    err = proc.stderr.read().decode(errors="replace")
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {err.strip()[-800:]}")
    return out
