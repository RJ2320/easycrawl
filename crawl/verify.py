"""Measure the motion in a rendered crawl: is every frame the same step?

A crawl judders in the file only if frames are repeated, dropped, or move by
uneven amounts. This decodes the movie and measures the real vertical
displacement between each pair of consecutive frames, plus the spacing of the
frame timestamps. If both are uniform the file is clean, and any stutter seen
on playback comes from the player or display (see `Report.advice`).

    report = verify("crawl.mov")
    print(report.summary())
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from . import tools

MAX_SHIFT = 64        # px/frame searched
COLUMN = 800          # width of the strip that is decoded, px


@dataclass
class Report:
    path: str
    width: int
    height: int
    fps: float
    frames_checked: int
    shifts: Dict[int, int] = field(default_factory=dict)   # px per frame → how many frame pairs
    pts_step_ms: tuple = (0.0, 0.0)                         # (min, max) gap between frames

    @property
    def speed(self) -> Optional[int]:
        return max(self.shifts, key=self.shifts.get) if self.shifts else None

    @property
    def uniform_motion(self) -> bool:
        return len(self.shifts) == 1

    @property
    def uniform_timing(self) -> bool:
        lo, hi = self.pts_step_ms
        return hi - lo < 0.01

    @property
    def clean(self) -> bool:
        return self.uniform_motion and self.uniform_timing

    def summary(self) -> str:
        lines = [f"{self.path}: {self.width}x{self.height} @ {self.fps:.3f} fps, {self.frames_checked} frame pairs measured"]
        if not self.shifts:
            lines.append("  no moving content found in the sampled frames")
            return "\n".join(lines)
        dist = ", ".join(f"{px} px x{n}" for px, n in sorted(self.shifts.items()))
        lines.append(f"  movement per frame: {dist}")
        lines.append(f"  frame spacing: {self.pts_step_ms[0]:.3f}-{self.pts_step_ms[1]:.3f} ms "
                     f"(ideal {1000 / self.fps:.3f} ms)")
        if self.clean:
            lines.append(f"  CLEAN: every frame moves exactly {self.speed} px and frames are evenly spaced.")
            lines += ["  " + line for line in self.advice()]
        else:
            if not self.uniform_motion:
                odd = sum(n for px, n in self.shifts.items() if px != self.speed)
                lines.append(f"  UNEVEN MOTION: {odd} frame pairs do not move {self.speed} px "
                             f"(0 px = a repeated frame, double = a dropped one).")
            if not self.uniform_timing:
                lines.append("  UNEVEN TIMING: frame timestamps are not evenly spaced.")
        return "\n".join(lines)

    def advice(self) -> List[str]:
        """Why a clean file can still look like it stutters."""
        out = ["Stutter seen on playback is then from the player or display, not the file:"]
        for hz in (60, 120, 48, 24):
            ratio = hz / self.fps
            if abs(ratio - round(ratio)) > 0.02:
                out.append(f"- On a {hz} Hz display each frame can't be held for a whole number of refreshes "
                           f"({ratio:.2f}x), so frames alternate between {int(ratio)} and {int(ratio) + 1} "
                           f"refreshes. Scrolling text shows this as a regular judder.")
                break
        out.append("- A player window that isn't at 100% (or exactly 50% on a Retina screen) scales the "
                   f"{self.speed} px step to a fractional number of screen pixels, which shimmers.")
        out.append("- Judge it full-screen on a display running at a multiple of the frame rate "
                   "(24/48/120 Hz for 23.976/24), or in the finishing system's output.")
        return out


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True)


def verify(path: str, frames: int = 480, start_fraction: float = 0.15) -> Report:
    """Measure up to `frames` consecutive frames starting part-way into the movie."""
    ffmpeg, ffprobe = tools.ffmpeg(), tools.ffprobe()
    if not ffmpeg or not ffprobe:
        raise RuntimeError("verify needs ffmpeg and ffprobe (brew install ffmpeg, or the packaged app)")

    info = _run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                 "stream=width,height,r_frame_rate,nb_frames,duration", "-of", "default=nw=1", path]).stdout.decode()
    meta = dict(line.split("=", 1) for line in info.splitlines() if "=" in line)
    if "width" not in meta:
        raise RuntimeError(f"can't read a video stream from {path}")
    width, height = int(meta["width"]), int(meta["height"])
    num, den = meta["r_frame_rate"].split("/")
    fps = float(num) / float(den)
    duration = float(meta.get("duration") or 0) or 0.0
    start = duration * start_fraction if duration else 0.0

    # Frame timestamps over the same stretch.
    pts = _run([ffprobe, "-v", "error", "-select_streams", "v:0", "-read_intervals", f"{start}%+#{frames}",
                "-show_entries", "frame=pts_time", "-of", "csv=p=0", path]).stdout.decode().split()
    times = np.array([float(x.strip(",")) for x in pts if x.strip(",")])
    steps = np.diff(times) * 1000 if len(times) > 1 else np.array([1000 / fps])

    # A column down the middle of the picture, one byte per pixel.
    column = min(COLUMN, width)
    raw = _run([ffmpeg, "-v", "error", "-ss", f"{start}", "-i", path, "-frames:v", str(frames),
                "-vf", f"crop={column}:{height}:{(width - column) // 2}:0", "-pix_fmt", "gray",
                "-f", "rawvideo", "-"]).stdout
    count = len(raw) // (column * height)
    stack = np.frombuffer(raw[:count * column * height], np.uint8).reshape(count, height, column)
    profile = stack.astype(np.float32).mean(axis=2)       # brightness down each frame

    shifts: Dict[int, int] = {}
    reach = min(MAX_SHIFT, height // 4)
    for i in range(1, count):
        a, b = profile[i - 1], profile[i]
        if a.max() < 2 or b.max() < 2:
            continue                                      # black: nothing to measure
        errors = [np.abs(a[s:] - b[:height - s]).mean() for s in range(reach + 1)]
        best = int(np.argmin(errors))
        shifts[best] = shifts.get(best, 0) + 1
    return Report(path, width, height, fps, sum(shifts.values()), shifts,
                  (float(steps.min()), float(steps.max())))
