"""Command line: lint a sheet, check timing, render panels + Fusion comp.

    python -m crawl lint   sheet.csv
    python -m crawl fit    sheet.csv --runtime 3:30 --fps 23.976 [--look sample.json]
    python -m crawl render sheet.csv --runtime 3:30 --out render/ [--codec prores4444 --alpha]
    python -m crawl render project.crawl.json [--fusion]
    python -m crawl verify crawl.mov          measure the motion in a rendered file
    python -m crawl fonts  [query]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import export, fonts, project as proj, text
from .look import Look
from .timing import tc_to_frames


def _project_from_args(a) -> proj.Project:
    if a.source.endswith(proj.PROJECT_SUFFIX):
        p = proj.Project.load(a.source)
    else:
        p = proj.Project(source=a.source)
    if getattr(a, "sheet", None) is not None:
        p.sheet = a.sheet
    if getattr(a, "columns", None):
        p.columns = a.columns
    if getattr(a, "start_row", None):
        p.start_row = a.start_row
    if getattr(a, "look", None):
        p.look = Look.load(a.look)
    if getattr(a, "fps", None):
        p.timing.fps = a.fps
    if getattr(a, "runtime", None):
        p.timing.mode = "runtime"
        p.timing.runtime_frames = tc_to_frames(a.runtime, p.timing.fps)
    if getattr(a, "speed", None):
        p.timing.mode = "manual"
        p.timing.speed = a.speed
    if getattr(a, "flex", None) is not None:
        p.timing.flex = a.flex
    if getattr(a, "out", None):
        p.output_dir = a.out
    if getattr(a, "name", None):
        p.basename = a.name
    if getattr(a, "codec", None):
        p.codec = a.codec
    if getattr(a, "alpha", False):
        p.alpha = True
    if getattr(a, "fusion", False):
        p.write_fusion = True
    if getattr(a, "fmt", None):
        p.fmt = a.fmt
    if getattr(a, "max_panel", None):
        p.max_panel = a.max_panel
    return p


def cmd_lint(a) -> int:
    p = _project_from_args(a)
    crawl = proj.load_crawl(p)
    findings = proj.findings_for(p, crawl)
    c = crawl.counts()
    print(f"{Path(p.source).name}: " + ", ".join(f"{v} {k}" for k, v in c.items()))
    for f in findings:
        print(" ", f)
    errors = sum(1 for f in findings if f.severity == "error")
    dismissed = f", {len(p.dismissed)} dismissed" if p.dismissed else ""
    print(f"{len(findings)} findings, {errors} errors{dismissed}")
    return 1 if errors else 0


def cmd_fit(a) -> int:
    p = _project_from_args(a)
    try:
        b = proj.prepare(p)
    except text.FontError as e:
        print(f"font problem: {e}", file=sys.stderr)
        return 2
    s = b.solution
    print(f"speed {s.speed} px/frame, spacing x{s.flex:.3f}, content {b.layout.content_height} px "
          f"(target {s.content_height}), {s.total_frames} frames = {s.timecode} @ {s.fps:g}")
    print(f"{s.seconds_on_screen(p.look.height):.1f} s on screen per line; "
          f"{len(b.layout.panels)} panels: " + ", ".join(f"{t}-{bt}" for t, bt in b.layout.panels))
    for w in b.warnings:
        print("  warning:", w)
    print(f"lint: {len(b.findings)} findings, {b.errors} errors (run `lint` for detail)")
    return 0


def cmd_render(a) -> int:
    p = _project_from_args(a)
    try:
        b = proj.prepare(p)
    except text.FontError as e:
        print(f"font problem: {e}", file=sys.stderr)
        return 2
    if b.errors and not a.force:
        print(f"{b.errors} lint errors; fix the sheet or pass --force", file=sys.stderr)
        for f in b.findings:
            if f.severity == "error":
                print(" ", f, file=sys.stderr)
        return 1

    def progress(stage, i, n):
        end = "\n" if i == n else "\r"
        print(f"  {stage} {i}/{n}   ", end=end, flush=True)

    s = b.solution
    print(f"{s.timecode} · {s.speed} px/frame · spacing ×{s.flex:.3f} · {p.codec}"
          f"{' +alpha' if p.alpha else ''}{' +fusion' if p.write_fusion else ''}")
    paths = proj.render(p, b, progress)
    for pth in paths:
        print(pth)
    return 0


def cmd_verify(a) -> int:
    from .verify import verify
    try:
        report = verify(a.movie, frames=a.frames)
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 2
    print(report.summary())
    return 0 if report.clean else 1


def cmd_fonts(a) -> int:
    q = (a.query or "").lower()
    for fam, faces in fonts.families().items():
        if q and q not in fam.lower():
            continue
        print(f"{fam}: " + ", ".join(f.style for f in faces))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="crawl", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("source", help="sheet (.csv/.xlsx) or project (.crawl.json)")
        sp.add_argument("--sheet", help="worksheet name in a workbook (default: the likeliest one)")
        sp.add_argument("--columns", help="which columns hold role, heading and names, e.g. B,C,D or A,B,C-E")
        sp.add_argument("--start-row", type=int, dest="start_row", help="first row of credits (rows above are skipped)")
        sp.add_argument("--look", help="look JSON")
        sp.add_argument("--fps", type=float)
        sp.add_argument("--runtime", help="target runtime, e.g. 3:30 or 210s or 5035f")
        sp.add_argument("--speed", type=int, help="manual px/frame (switches to manual mode)")
        sp.add_argument("--flex", type=float, help="manual spacing scale")
        sp.add_argument("--max-panel", type=int, dest="max_panel")

    common(sub.add_parser("lint", help="flag data problems"))
    common(sub.add_parser("fit", help="solve timing and print the plan"))
    r = sub.add_parser("render", help="render the crawl to a movie")
    common(r)
    r.add_argument("--out", help="output directory")
    r.add_argument("--name", help="base file name (default: crawl)")
    r.add_argument("--codec", choices=list(export.CODECS), help=", ".join(
        f"{k}={c.label}" for k, c in export.CODECS.items()))
    r.add_argument("--alpha", action="store_true", help="carry alpha (ProRes 4444 / PNG)")
    r.add_argument("--fusion", action="store_true", help="also write PNG panels + Fusion .comp/.setting")
    r.add_argument("--fmt", choices=("rgba8", "luma16"), help="panel format with --fusion")
    r.add_argument("--force", action="store_true", help="render despite lint errors")
    v = sub.add_parser("verify", help="measure per-frame motion in a rendered movie")
    v.add_argument("movie")
    v.add_argument("--frames", type=int, default=480, help="consecutive frames to measure (default 480)")
    f = sub.add_parser("fonts", help="list installed font families")
    f.add_argument("query", nargs="?")

    a = ap.parse_args(argv)
    return {"lint": cmd_lint, "fit": cmd_fit, "render": cmd_render, "verify": cmd_verify, "fonts": cmd_fonts}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
