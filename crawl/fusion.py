"""Emit a Fusion composition: one Loader per panel, merged over black.

Every Merge's Center is an expression of `time`, so the crawl is a pure linear
function of the frame number with an exact integer pixel step; there are no
keyframes to drift. Panel `i` with top `top_i` and height `h_i` sits at

    Center.Y = ((time - head) * speed - (top_i + h_i / 2)) / frame_height

which puts the top of the content just below the frame at `head` and moves it
`speed` px per frame. Panel tops and heights are even so the foreground lands
on whole pixels and the Merge never resamples.

Two files are written from the same node list:
  <name>.comp     a full composition for Fusion Studio
  <name>.setting  the node tree alone; paste into a Resolve Fusion page
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence, Tuple

from .layout import Layout
from .look import Look
from .timing import Solution, Timing


def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def tools_block(panels: Sequence[Tuple[int, int]], panel_paths: Sequence[str], look: Look,
                sol: Solution, timing: Timing) -> str:
    total = sol.total_frames
    last = total - 1
    out: List[str] = []
    out.append("\tTools = ordered() {")

    out.append(f"""\t\tCrawlBG = Background {{
\t\t\tInputs = {{
\t\t\t\tGlobalIn = Input {{ Value = 0, }},
\t\t\t\tGlobalOut = Input {{ Value = {last}, }},
\t\t\t\tWidth = Input {{ Value = {look.width}, }},
\t\t\t\tHeight = Input {{ Value = {look.height}, }},
\t\t\t\tDepth = Input {{ Value = 1, }},
\t\t\t\tTopLeftRed = Input {{ Value = 0, }},
\t\t\t\tTopLeftGreen = Input {{ Value = 0, }},
\t\t\t\tTopLeftBlue = Input {{ Value = 0, }},
\t\t\t\tTopLeftAlpha = Input {{ Value = 1, }},
\t\t\t}},
\t\t\tViewInfo = OperatorInfo {{ Pos = {{ 0, 0 }} }},
\t\t}},""")

    prev = "CrawlBG"
    for i, ((top, bottom), path) in enumerate(zip(panels, panel_paths)):
        n = i + 1
        h = bottom - top
        centre = top + h / 2
        loader = f"CrawlPanel{n}"
        merge = f"CrawlMerge{n}"
        expr = f"Point(0.5, ((time - {timing.head_hold}) * {sol.speed} - {centre:g}) / {look.height})"

        out.append(f"""\t\t{loader} = Loader {{
\t\t\tClips = {{
\t\t\t\tClip {{
\t\t\t\t\tID = "Clip1",
\t\t\t\t\tFilename = {_q(str(path))},
\t\t\t\t\tFormatID = "PNGFormat",
\t\t\t\t\tStartFrame = -1,
\t\t\t\t\tLengthSetManually = true,
\t\t\t\t\tTrimIn = 0,
\t\t\t\t\tTrimOut = 0,
\t\t\t\t\tExtendFirst = 0,
\t\t\t\t\tExtendLast = {last},
\t\t\t\t\tLoop = 1,
\t\t\t\t\tAspectMode = 0,
\t\t\t\t\tDepth = 0,
\t\t\t\t\tTimeCode = 0,
\t\t\t\t\tGlobalStart = 0,
\t\t\t\t\tGlobalEnd = {last}
\t\t\t\t}}
\t\t\t}},
\t\t\tInputs = {{
\t\t\t\tGlobalIn = Input {{ Value = 0, }},
\t\t\t\tGlobalOut = Input {{ Value = {last}, }},
\t\t\t\tLoop = Input {{ Value = 1, }},
\t\t\t\tHoldLastFrame = Input {{ Value = {last}, }},
\t\t\t\tPostMultiplyByAlpha = Input {{ Value = 0, }},
\t\t\t}},
\t\t\tViewInfo = OperatorInfo {{ Pos = {{ {220 * n}, 120 }} }},
\t\t}},""")

        out.append(f"""\t\t{merge} = Merge {{
\t\t\tInputs = {{
\t\t\t\tBackground = Input {{ SourceOp = "{prev}", Source = "Output", }},
\t\t\t\tForeground = Input {{ SourceOp = "{loader}", Source = "Output", }},
\t\t\t\tCenter = Input {{ Expression = {_q(expr)}, }},
\t\t\t\tPerformDepthMerge = Input {{ Value = 0, }},
\t\t\t}},
\t\t\tViewInfo = OperatorInfo {{ Pos = {{ {220 * n}, 0 }} }},
\t\t}},""")
        prev = merge

    out.append("\t},")
    out.append(f'\tActiveTool = "{prev}"')
    return "\n".join(out), prev


def emit(L: Layout, look: Look, sol: Solution, timing: Timing, panel_paths: Sequence[str],
         out_stem: str) -> List[Path]:
    """Write <out_stem>.comp and <out_stem>.setting; return their paths."""
    for top, bottom in L.panels:
        if top % 2 or (bottom - top) % 2:
            raise ValueError("panel bounds must be even for pixel-exact placement")

    tools, _ = tools_block(L.panels, [str(p) for p in panel_paths], look, sol, timing)
    last = sol.total_frames - 1

    comp = f"""Composition {{
\tCurrentTime = 0,
\tRenderRange = {{ 0, {last} }},
\tGlobalRange = {{ 0, {last} }},
\tPlaybackUpdateMode = 0,
\tVersion = "18.0",
\tPrefs = {{
\t\tComp = {{
\t\t\tFrameFormat = {{
\t\t\t\tWidth = {look.width},
\t\t\t\tHeight = {look.height},
\t\t\t\tRate = {timing.fps:g},
\t\t\t\tAspectX = 1,
\t\t\t\tAspectY = 1,
\t\t\t\tDepthFull = 3,
\t\t\t\tDepthInteractive = 3,
\t\t\t\tDepthPreview = 3,
\t\t\t\tDepthLock = true,
\t\t\t}},
\t\t}},
\t}},
{tools}
}}
"""
    setting = f"{{\n{tools}\n}}\n"

    comp_path = Path(out_stem + ".comp")
    setting_path = Path(out_stem + ".setting")
    comp_path.write_text(comp)
    setting_path.write_text(setting)
    return [comp_path, setting_path]
