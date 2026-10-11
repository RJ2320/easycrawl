"""Background threads: rebuild (prepare + preview) and final render."""

from __future__ import annotations

import copy
import traceback
from typing import Optional

from PySide6.QtCore import QThread, Signal

from .. import export, project as proj, render as render_mod
from ..model import Crawl

PREVIEW_WIDTH = 960      # px the preview strip is drawn at, whatever the delivery size


def preview_scale(look) -> float:
    """Delivery → preview scale: sharp at any resolution without drawing more than needed."""
    return min(1.0, PREVIEW_WIDTH / look.width)


class RebuildWorker(QThread):
    """Run prepare() and render a greyscale preview off the UI thread."""

    done = Signal(object, object)   # (Build, PIL.Image preview)
    failed = Signal(str)

    def __init__(self, project: proj.Project, crawl: Crawl, parent=None, logo_layers=None):
        super().__init__(parent)
        self.project = copy.deepcopy(project)
        self.crawl = copy.deepcopy(crawl)
        self.logo_layers = dict(logo_layers or {})

    def run(self):
        try:
            build = proj.prepare(self.project, self.crawl)
            img = render_mod.render_preview(build.layout, self.project.look, preview_scale(self.project.look))
            from .logo_layers import key, prepare
            scale = preview_scale(self.project.look)
            build.logo_layers = {}
            for item in build.layout.logos:
                cache_key = key(item, scale)
                cached = self.logo_layers.get(item.label)
                if not cached or cached[0] != cache_key:
                    cached = (cache_key, prepare(item, scale))
                build.logo_layers[item.label] = cached
            self.done.emit(build, img)
        except Exception as e:  # surfaced in the status bar
            self.failed.emit(f"{e}\n{traceback.format_exc(limit=3)}")


class SheetFetchWorker(QThread):
    """Download the project's Google Sheet and say whether it differs from what was last brought in."""

    changed = Signal(str)       # path of the fresh download: its rows differ from the project's base rows
    unchanged = Signal(str)
    failed = Signal(str)

    def __init__(self, project: proj.Project, folder: str, parent=None):
        super().__init__(parent)
        self.project = copy.deepcopy(project)
        self.folder = folder

    def run(self):
        from .. import gsheets
        try:
            path = gsheets.fetch(self.project.source_url, self.folder)
            rows, _ = proj.read_source(self.project, path)
        except Exception as e:
            self.failed.emit(str(e))
            return
        if self.project.base_rows is not None and rows == [list(r) for r in self.project.base_rows]:
            self.unchanged.emit(path)
        else:
            self.changed.emit(path)


class RenderWorker(QThread):
    progress = Signal(str, int, int)
    done = Signal(list)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, project: proj.Project, build: proj.Build, parent=None):
        super().__init__(parent)
        self.project = copy.deepcopy(project)
        self.build = build
        self._stop = False

    def cancel(self):
        """Ask the export to stop; it does so at the next frame."""
        self._stop = True

    def run(self):
        try:
            paths = proj.render(self.project, self.build, lambda s, i, n: self.progress.emit(s, i, n),
                                cancel=lambda: self._stop)
            self.done.emit([str(p) for p in paths])
        except export.ExportCancelled:
            self.cancelled.emit()
        except Exception as e:
            self.failed.emit(f"{e}\n{traceback.format_exc(limit=3)}")


class UpdateCheckWorker(QThread):
    available = Signal()
    release_available = Signal(str, str)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = root

    def run(self):
        import sys
        from ..updates import update_available, latest_release
        if getattr(sys, "frozen", False):
            from .. import __version__
            release = latest_release(__version__)
            if release and not self.isInterruptionRequested():
                self.release_available.emit(*release)
            return
        if update_available(self.root) and not self.isInterruptionRequested():
            self.available.emit()
