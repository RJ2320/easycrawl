"""A show project: source sheet + look + timing + output settings, and the
pipeline that turns it into a finished movie.

    project = Project.load("sample.crawl.json")
    build = prepare(project)         # ingest, lint, solve timing, layout, panels
    paths = render(project, build)   # movie (+ optional PNG panels and Fusion comp)
"""

from __future__ import annotations

import json
import os
import shutil
import copy
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import export, fusion, ingest, layout as layout_mod, lint, render as render_mod, text, timing as timing_mod
from .look import Look
from .model import Crawl
from .timing import Solution, Timing

PROJECT_SUFFIX = ".crawl.json"
ASSETS_SUFFIX = "_assets"


def _inside(path: str, folder: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(folder)]) == os.path.abspath(folder)
    except ValueError:              # different drives
        return False


def _portable(path: str, base: str) -> str:
    """A path as written to disk: relative (POSIX slashes) when inside the project folder."""
    if not path or not _inside(path, base):
        return path
    return Path(os.path.relpath(os.path.abspath(path), base)).as_posix()


def _absolute(path: str, base: str) -> str:
    if not path or os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(base, path))


@dataclass
class Project:
    source: str = ""
    # Where the sheet came from, if it was a Google Sheets link: refreshes re-download it.
    source_url: str = ""
    sheet: str = ""                 # worksheet name; "" = the likeliest one (ingest.guess_sheet)
    columns: str = ""               # "B,C,D-F" style column spec; "" = found automatically
    start_row: int = 1              # credits start here; rows above are title/notes
    list_columns: int = 3
    look: Look = field(default_factory=Look)
    timing: Timing = field(default_factory=Timing)
    max_panel: int = 16000          # GPU texture limit is 16384; leave headroom
    output_dir: str = ""
    basename: str = "crawl"
    version_output: bool = False   # choose the next v001/v002 from files in the output folder
    timestamp_output: bool = False  # append local export date/time to every output stem
    codec: str = export.DEFAULT_CODEC
    alpha: bool = False             # carry alpha (ProRes 4444 / PNG only)
    write_report: bool = False     # optional text export summary
    write_fusion: bool = False      # also write PNG panels + .comp/.setting
    fmt: str = "rgba8"              # panel format when write_fusion
    logos: Dict[str, str] = field(default_factory=dict)   # slot label → image path
    # slot label → {invert, scale, dx, dy}; only non-default values need be present
    logo_settings: Dict[str, dict] = field(default_factory=dict)

    rows: Optional[List[List[str]]] = None  # edited B/C/D rows, saved with the project

    arrangements: List[dict] = field(default_factory=list)
    # Layout overrides for Col-B-only rows: {start, end, kind} with zero-based
    # inclusive rows and kind in ingest.LAYOUT_KINDS (roles | list | center).
    overrides: List[dict] = field(default_factory=list)

    # Findings the user has looked at and accepted, by lint.Finding.key.
    dismissed: List[str] = field(default_factory=list)
    # What the reader did to fit an off-template sheet: {start, end, message}, zero-based rows.
    import_notes: List[dict] = field(default_factory=list)
    # The rows exactly as the client last sent them, so a revised sheet can be
    # merged in without losing edits made here (see changes.py).
    base_rows: Optional[List[List[str]]] = None
    # What load() had to fix (moved or missing files). Not saved.
    load_notes: List[str] = field(default_factory=list, compare=False)

    import_history: List[dict] = field(default_factory=list)

    # Named project states; their payload excludes this history to avoid recursion.
    snapshots: List[dict] = field(default_factory=list)

    _SIMPLE = ("source", "source_url", "sheet", "columns", "start_row", "list_columns", "max_panel",
               "output_dir", "basename", "timestamp_output", "version_output", "codec", "alpha", "write_fusion", "write_report", "fmt", "logos", "logo_settings", "rows", "arrangements",
               "overrides", "dismissed", "import_notes", "base_rows", "snapshots", "import_history")

    def record_import(self, rows, action="Imported", applied=0, skipped=0, deduplicate=False):
        """Keep source provenance; opening a saved project is not a new import."""
        import hashlib
        digest = hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()
        entry = dict(source=self.source, source_url=self.source_url, sheet=self.sheet,
                     columns=self.columns, start_row=self.start_row, fingerprint=digest,
                     row_count=len(rows), action=action, applied=applied, skipped=skipped,
                     imported_at=datetime.now(timezone.utc).isoformat())
        if deduplicate and self.import_history:
            last = self.import_history[-1]
            if all(last.get(k) == entry[k] for k in
                   ("source", "source_url", "sheet", "columns", "start_row", "fingerprint")):
                return False
        self.import_history.append(entry)
        return True

    def set_resolution(self, width: int, height: int, scale_look: bool = True) -> float:
        """Change the delivery size, optionally scaling everything measured in
        pixels with it: the look, hand-placed logo offsets, side-by-side gaps
        and a manually set scroll speed (so lines stay on screen as long)."""
        factor = self.look.resize(width, height, scale_look)
        if factor != 1.0:
            for cfg in self.logo_settings.values():
                cfg["dx"] = int(round(cfg.get("dx", 0) * factor))
                cfg["dy"] = int(round(cfg.get("dy", 0) * factor))
            for item in self.arrangements:
                item["gap"] = int(round(item.get("gap", 120) * factor))
            self.timing.speed = max(1, int(round(self.timing.speed * factor)))
        return factor

    def to_dict(self) -> dict:
        d = {k: getattr(self, k) for k in self._SIMPLE}
        d["look"] = self.look.to_dict()
        d["timing"] = self.timing.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        p = cls()
        for k in cls._SIMPLE:
            if k in d:
                setattr(p, k, d[k])
        if "look" in d:
            p.look = Look.from_dict(d["look"])
        if "timing" in d:
            p.timing = Timing.from_dict(d["timing"])
        return p

    def create_snapshot(self, name: str) -> dict:
        name = name.strip()
        if not name:
            raise ValueError("Give the snapshot a name.")
        state = copy.deepcopy({k: v for k, v in self.to_dict().items() if k != "snapshots"})
        # Capture actual credits even when the source has not been edited yet.
        if state["rows"] is None:
            state["rows"] = copy.deepcopy(read_source(self, self.source)[0]) if self.source else []
        snapshot = {"id": uuid4().hex, "name": name,
                    "created_at": datetime.now(timezone.utc).isoformat(), "state": state}
        self.snapshots.append(snapshot)
        return snapshot

    def restore_snapshot(self, snapshot_id: str) -> dict:
        snapshot = next(item for item in self.snapshots if item["id"] == snapshot_id)
        restored = Project.from_dict(copy.deepcopy(snapshot["state"]))
        # A restore always leaves a way back to the work it replaced.
        recovery = self.create_snapshot("Before restoring " + snapshot["name"])
        history = self.snapshots
        imports = self.import_history
        self.__dict__.update(restored.__dict__)
        self.snapshots = history
        self.import_history = imports
        return recovery

    @staticmethod
    def _map_paths(state: dict, base: str, mapper) -> None:
        state["source"] = mapper(state.get("source", ""), base)
        state["output_dir"] = mapper(state.get("output_dir", ""), base)
        state["logos"] = {label: mapper(file, base) for label, file in state.get("logos", {}).items()}

    # ---- files -------------------------------------------------------------
    #
    # In memory every path is absolute. On disk, a path inside the project
    # file's folder is written relative to it, so the folder can be moved,
    # zipped or opened on another machine with nothing to fix. Paths outside
    # the folder stay absolute; `collect()` copies those files in.

    def save(self, path: str) -> None:
        base = os.path.dirname(os.path.abspath(path))
        d = copy.deepcopy(self.to_dict())
        self._map_paths(d, base, _portable)
        for snapshot in d["snapshots"]:
            self._map_paths(snapshot["state"], base, _portable)
        Path(path).write_text(json.dumps(d, indent=2))

    @classmethod
    def load(cls, path: str) -> "Project":
        p = cls.from_dict(json.loads(Path(path).read_text()))
        base = os.path.dirname(os.path.abspath(path))
        p.source = _absolute(p.source, base)
        p.output_dir = _absolute(p.output_dir, base)
        p.logos = {label: _absolute(file, base) for label, file in p.logos.items()}
        for snapshot in p.snapshots:
            cls._map_paths(snapshot["state"], base, _absolute)
        p.load_notes = p._repair(base)
        return p

    def _repair(self, base: str) -> List[str]:
        """After loading: find files that moved, and fall back where they can't
        be found. Returns what was done, for the user to read."""
        notes: List[str] = []
        folders = [base] + sorted(str(d) for d in Path(base).glob("*" + ASSETS_SUFFIX) if d.is_dir())
        if self.source:
            folders.append(os.path.dirname(self.source))

        def find(name: str) -> Optional[str]:
            for folder in folders:
                candidate = os.path.join(folder, name)
                if os.path.isfile(candidate):
                    return candidate
            return None

        relinked, missing = [], []
        for label, file in list(self.logos.items()):
            if file and not os.path.isfile(file):
                found = find(os.path.basename(file))
                if found:
                    self.logos[label] = found
                    relinked.append(label)
                else:
                    missing.append(label)
        if relinked:
            notes.append(f"Found {len(relinked)} moved logo file{'s' if len(relinked) != 1 else ''} "
                         f"beside the project: {', '.join(relinked)}.")
        if missing:
            notes.append(f"Logo artwork not found for: {', '.join(missing)}. Choose the files again on the Logos tab.")

        if self.source and not os.path.isfile(self.source):
            found = find(os.path.basename(self.source))
            if found:
                self.source = found
            elif self.rows is None and self.base_rows is not None:
                # The sheet is gone but the project remembers what was in it.
                self.rows = [list(r) for r in self.base_rows]
                notes.append(f"{os.path.basename(self.source)} was not found; using the credits saved in the project.")
            elif self.rows is None:
                notes.append(f"{os.path.basename(self.source)} was not found.")

        if self.output_dir and not os.path.isdir(self.output_dir) \
                and not os.path.isdir(os.path.dirname(self.output_dir)):
            self.output_dir = os.path.join(base, "render")
            notes.append("The export folder does not exist on this machine; it is now 'render' beside the project.")
        return notes

    def collect(self, project_path: str) -> List[str]:
        """Copy every file the project uses that lives outside its folder into
        '<project>_assets' beside it, and point the project at the copies.
        Returns the names copied. Save afterwards to write the new paths."""
        base = os.path.dirname(os.path.abspath(project_path))
        stem = os.path.basename(project_path)
        stem = stem[:-len(PROJECT_SUFFIX)] if stem.endswith(PROJECT_SUFFIX) else os.path.splitext(stem)[0]
        assets = os.path.join(base, stem + ASSETS_SUFFIX)
        copied: List[str] = []
        placed: Dict[str, str] = {}        # original → copy, so a file used twice is copied once

        def bring(file: str) -> str:
            if not file or not os.path.isfile(file) or _inside(file, base):
                return file
            if file not in placed:
                os.makedirs(assets, exist_ok=True)
                name, n = os.path.basename(file), 2
                root, ext = os.path.splitext(name)
                while os.path.exists(os.path.join(assets, name)):
                    name = f"{root} {n}{ext}"
                    n += 1
                shutil.copy2(file, os.path.join(assets, name))
                placed[file] = os.path.join(assets, name)
                copied.append(name)
            return placed[file]

        self.logos = {label: bring(file) for label, file in self.logos.items()}
        self.source = bring(self.source)
        for snapshot in self.snapshots:
            state = snapshot["state"]
            state["source"] = bring(state.get("source", ""))
            state["logos"] = {label: bring(file) for label, file in state.get("logos", {}).items()}
        return copied


@dataclass
class Build:
    crawl: Crawl
    findings: List[lint.Finding]
    solution: Solution
    layout: layout_mod.Layout
    warnings: List[str] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")


def crawl_from_rows(project: Project, rows) -> Crawl:
    """Parse sheet rows and attach the project's logo artwork to its slots."""
    boundaries = {row for item in project.arrangements for row in (item["start"], item["end"] + 1)}
    kinds = {row: item["kind"] for item in project.overrides
             for row in range(item["start"], item["end"] + 1) if item["kind"] in ingest.LAYOUT_KINDS}
    crawl = ingest.parse(rows, source=project.source, list_columns=project.list_columns,
                         break_before=boundaries, kinds=kinds)
    crawl.arrangements = copy.deepcopy(project.arrangements)
    for lg in crawl.logos():
        if lg.label in project.logos:
            lg.path = project.logos[lg.label]
        cfg = project.logo_settings.get(lg.label)
        if cfg:
            lg.mode = "grayscale" if cfg.get("mode") == "grayscale" else "original"
            lg.invert = bool(cfg.get("invert", False))
            lg.scale = max(0.05, float(cfg.get("scale", 1.0)))
            lg.dx, lg.dy = int(cfg.get("dx", 0)), int(cfg.get("dy", 0))
            lg.black = min(0.95, max(0.0, float(cfg.get("black", 0)) / 100))      # stored as percentages
            lg.white = min(1.0, max(lg.black + 0.02, float(cfg.get("white", 100)) / 100))
    return crawl


def findings_for(project: Project, crawl: Crawl) -> List[lint.Finding]:
    """Everything worth a look: lint, plus what import had to do to an
    off-template sheet, minus what the user has already dismissed."""
    found = lint.lint(crawl)
    found += [lint.Finding("import", "warning", note["start"] + 1, note["message"], "role",
                           "import|" + note["message"]) for note in project.import_notes]
    hidden = set(project.dismissed)
    found = [f for f in found if not (f.key and f.key in hidden)]
    found.sort(key=lambda f: f.row)
    return found


def read_source(project: Project, path: str):
    """Read a sheet for this project: (rows as lists, import notes as row ranges)."""
    rows, notes = ingest.read_sheet(path, project.sheet, project.columns, project.start_row)
    return ([list(r) for r in rows],
            [dict(start=n.row - 1, end=n.row - 1, message=n.message) for n in notes])


def load_crawl(project: Project) -> Crawl:
    if project.rows is not None:
        return crawl_from_rows(project, project.rows)
    rows, notes = read_source(project, project.source)
    project.import_notes = notes        # so findings_for() reports what import had to adjust
    return crawl_from_rows(project, rows)


def prepare(project: Project, crawl: Optional[Crawl] = None) -> Build:
    """Everything except drawing pixels. Raises text.FontError if a font is missing."""
    problems = text.check_fonts(project.look.styles())
    if problems:
        raise text.FontError("; ".join(problems))

    crawl = crawl or load_crawl(project)
    findings = findings_for(project, crawl)
    fixed, flex_px = layout_mod.measure(crawl, project.look)
    sol = timing_mod.solve(project.timing, fixed, flex_px, project.look.height)
    if crawl.arrangements:
        # The tallest block in a grid row can change as spacing scales. Use
        # actual layouts to refine the linear estimate before final fitting.
        if project.timing.mode == "manual":
            height = layout_mod.layout(crawl, project.look, sol.flex).content_height
            sol.travel_frames = math.ceil((height + project.look.height) / sol.speed)
            sol.content_height = sol.travel_frames * sol.speed - project.look.height
            sol.total_frames = sol.travel_frames + project.timing.head_hold + project.timing.tail_hold
        else:
            low, high = project.timing.flex_min, project.timing.flex_max
            low_h = layout_mod.layout(crawl, project.look, low).content_height
            high_h = layout_mod.layout(crawl, project.look, high).content_height
            if low_h <= sol.content_height <= high_h:
                for _ in range(24):
                    mid = (low + high) / 2
                    if layout_mod.layout(crawl, project.look, mid).content_height <= sol.content_height:
                        low = mid
                    else:
                        high = mid
                sol.flex = low
    L = layout_mod.fit(crawl, project.look, sol.flex, sol.content_height)
    layout_mod.split_panels(L, project.max_panel)
    from .layout_checks import check_layout
    findings.extend(f for f in check_layout(L, project.look) if f.key not in project.dismissed)
    findings.sort(key=lambda f: f.row)

    warnings = list(sol.warnings)
    for top, bottom in L.panels:
        if bottom - top > project.max_panel:
            warnings.append(f"panel {top}-{bottom} exceeds {project.max_panel}px (a group is too tall)")
    on_screen = sol.seconds_on_screen(project.look.height)
    if on_screen < 5:
        warnings.append(f"lines are on screen for only {on_screen:.1f}s")
    return Build(crawl, findings, sol, L, warnings)


def output_dir(project: Project) -> Path:
    return Path(project.output_dir or Path(project.source).parent / "render")


def export_basename(project: Project, out: Path, now=None) -> str:
    name = project.basename
    if project.version_output:
        pattern = re.compile(re.escape(name) + r"_v(\d+)(?:[_.]|$)", re.IGNORECASE)
        versions = [int(match.group(1)) for path in out.iterdir()
                    if (match := pattern.match(path.name))] if out.exists() else []
        name += f"_v{max(versions, default=0) + 1:03d}"
    if project.timestamp_output:
        name += (now or datetime.now().astimezone()).strftime("_%Y-%m-%d_%H-%M-%S")
    return name


def render(project: Project, build: Build,
           progress: Optional[Callable[[str, int, int], None]] = None,
           cancel: Optional[Callable[[], bool]] = None) -> List[Path]:
    """Export the movie (and, if asked, panels + Fusion comp). Returns every path written.

    progress(stage, i, n) with stage in draw | encode | panel. `cancel` is
    polled throughout; if it returns True, export.ExportCancelled is raised
    and the partial movie is removed.
    """
    out = output_dir(project)
    out.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    basename = export_basename(project, out)

    movie = export.export_movie(build.layout, project.look, build.solution, project.timing,
                                str(out / basename), project.codec, project.alpha, progress,
                                cancel=cancel)
    written.append(movie)

    panels: List[Path] = []
    if project.write_fusion:
        def on_panel(i, n):
            if progress:
                progress("panel", i, n)
            if cancel and cancel() and i < n:
                raise export.ExportCancelled()
        panels = render_mod.render_all(build.layout, project.look, str(out), basename,
                                       project.fmt, on_panel)
        written += panels
        written += fusion.emit(build.layout, project.look, build.solution, project.timing,
                               [str(p.resolve()) for p in panels], str(out / basename))

    if project.write_report:
        report = out / f"{basename}_report.txt"
        write_report(project, build, report, panels, movie)
        written.append(report)
    return written


def write_report(project: Project, build: Build, path: Path, panels: List[Path],
                 movie: Optional[Path] = None) -> None:
    s = build.solution
    lines = [
        f"Crawl report — {Path(project.source).name}",
        "",
        f"Delivery      {project.look.width} x {project.look.height} @ {project.timing.fps:g}",
        f"Runtime       {s.timecode}  ({s.total_frames} frames, {s.seconds:.2f} s)",
        f"Speed         {s.speed} px/frame  ({s.seconds_on_screen(project.look.height):.1f} s on screen)",
        f"Spacing scale {s.flex:.3f}",
        f"Content       {build.layout.content_height} px (padded to {build.layout.target_height})",
        f"Travel        {build.layout.target_height + project.look.height} px over {s.travel_frames} frames",
        f"Head/tail     {project.timing.head_hold} / {project.timing.tail_hold} frames",
    ]
    if movie:
        lines += [f"Movie         {movie.name}  ({export.CODECS[project.codec].label}"
                  f"{', alpha' if project.alpha and export.CODECS[project.codec].alpha else ''})"]
    if panels:
        lines += ["", "Panels"]
        for p, (top, bottom) in zip(panels, build.layout.panels):
            lines.append(f"  {p.name:24s} rows {top:6d}-{bottom:6d}  ({bottom - top} px)")
    c = build.crawl.counts()
    lines += ["", "Counts", "  " + ", ".join(f"{k} {v}" for k, v in c.items())]
    if build.warnings:
        lines += ["", "Warnings"] + [f"  {w}" for w in build.warnings]
    if build.findings:
        lines += ["", f"Errors and possible problems ({len(build.findings)})"] + [f"  {f}" for f in build.findings]
    path.write_text("\n".join(lines) + "\n")
