"""Runtime ↔ speed ↔ content height.

The crawl travels `content_height + frame_height` pixels over its run: the top
of the content starts just below the frame and the bottom ends just above it.
Speed is always an integer number of pixels per frame, so the layout's flexible
spacing (leading, gaps) is scaled to make the height land on the frame count.

    travel = content_height + frame_height = speed * travel_frames

Two modes:
  runtime  user gives runtime + fps → solve integer speed and a spacing scale
  manual   user gives speed + spacing scale → runtime is whatever results
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import List, Optional


@dataclass
class Timing:
    fps: float = 23.976
    mode: str = "runtime"        # "runtime" | "manual"
    runtime_frames: int = 5035   # target total frames (runtime mode)
    speed: int = 10              # px/frame (manual mode input; solved in runtime mode)
    flex: float = 1.0            # spacing scale (manual mode input; solved in runtime mode)
    head_hold: int = 0           # black frames before the crawl enters
    tail_hold: int = 0           # black frames after the crawl exits
    flex_min: float = 0.7        # solver limits for the spacing scale
    flex_max: float = 1.6

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @property
    def travel_frames(self) -> int:
        return self.runtime_frames - self.head_hold - self.tail_hold


@dataclass
class Solution:
    speed: int
    flex: float
    travel_frames: int
    content_height: int         # exact height the layout must hit
    total_frames: int
    fps: float
    warnings: List[str]

    @property
    def seconds(self) -> float:
        return self.total_frames / self.fps

    @property
    def timecode(self) -> str:
        return frames_to_tc(self.total_frames, self.fps)

    def seconds_on_screen(self, frame_height: int) -> float:
        """How long any one line is visible."""
        return frame_height / self.speed / self.fps


def solve(t: Timing, fixed_px: int, flex_px: int, frame_height: int) -> Solution:
    """Pick integer speed + spacing scale for the given layout measurements.

    fixed_px  content height that doesn't scale (glyphs, logos, legal lines)
    flex_px   spacing that scales with `flex` (leading, gaps), measured at flex=1
    """
    warnings: List[str] = []

    if t.mode == "manual":
        speed = max(1, int(t.speed))
        flex = t.flex
        content = int(round(fixed_px + flex * flex_px))
        travel_frames = math.ceil((content + frame_height) / speed)
        # Snap content height up so travel is an exact multiple of speed.
        content = speed * travel_frames - frame_height
        total = travel_frames + t.head_hold + t.tail_hold
        return Solution(speed, flex, travel_frames, content, total, t.fps, warnings)

    F = t.travel_frames
    if F <= 0:
        raise ValueError("runtime must be longer than head + tail holds")

    natural = fixed_px + flex_px + frame_height  # travel at flex = 1
    s0 = max(1, round(natural / F))

    best: Optional[tuple] = None
    for speed in sorted({s0 - 1, s0, s0 + 1, s0 + 2} - {0, -1}):
        if speed < 1:
            continue
        needed_flex_px = speed * F - frame_height - fixed_px
        flex = needed_flex_px / flex_px if flex_px else 1.0
        clamped = min(max(flex, t.flex_min), t.flex_max)
        score = abs(math.log(max(clamped, 1e-6)))  # prefer flex closest to 1
        cand = (abs(clamped - flex) > 1e-9, score, speed, flex, clamped)
        if best is None or cand[:2] < best[:2]:
            best = cand

    out_of_range, _, speed, flex, clamped = best
    if out_of_range:
        warnings.append(
            f"spacing scale {flex:.2f} is outside {t.flex_min}-{t.flex_max}; "
            f"clamped to {clamped:.2f}. Change runtime, sizes, or the flex limits."
        )
        flex = clamped
    content = speed * F - frame_height
    total = F + t.head_hold + t.tail_hold
    return Solution(speed, flex, F, content, total, t.fps, warnings)


# --------------------------------------------------------------------------- #

def tc_to_frames(tc: str, fps: float) -> int:
    """'3:30', '0:03:30', '3:30.5', '210s' or '5035f' → frames.

    Durations are real seconds × fps (3:30 at 23.976 = 5035 frames), matching
    the sample timing specification, not nominal-rate timecode.
    """
    tc = tc.strip().lower()
    if tc.endswith("s"):
        return int(round(float(tc[:-1]) * fps))
    if tc.endswith("f"):
        return int(tc[:-1])
    secs = 0.0
    for p in tc.split(":"):
        secs = secs * 60 + float(p)
    return int(round(secs * fps))


def frames_to_tc(frames: int, fps: float) -> str:
    secs = frames / fps
    m, s = divmod(secs, 60)
    h, m = divmod(int(m), 60)
    whole = int(s)
    frac_frames = int(round((s - whole) * fps))
    if h:
        return f"{h}:{m:02d}:{whole:02d}+{frac_frames:02d}f"
    return f"{m}:{whole:02d}+{frac_frames:02d}f"
