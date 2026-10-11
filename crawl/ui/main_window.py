"""Main window: sheet in, controls on the left, live preview in the middle."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QUrl, QProcess, QSettings, QStandardPaths, Qt, QTimer, Signal
from PySide6.QtGui import QDesktopServices, QAction, QColor, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog,
                               QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton, QRadioButton,
                               QScrollArea, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from .. import export, gsheets, ingest, project as proj
from ..timing import frames_to_tc, tc_to_frames
from . import theme
from .import_dialog import ImportDialog
from .relink_dialog import RelinkDialog
from .. import relink
from .snapshot_dialog import SnapshotDialog
from .sheet_editor import SheetEditor
from .music_panel import MusicPanel
from .logo_workspace import LogoWorkspace
from .widgets import LOGO_DEFAULTS, PreviewPanel, StyleEditor, _dspin, _spin
from .worker import RebuildWorker, RenderWorker, SheetFetchWorker, UpdateCheckWorker

FPS_CHOICES = [23.976, 24.0, 25.0, 29.97, 30.0, 48.0, 50.0, 59.94, 60.0]

RESOLUTIONS = [("UHD 4K", 3840, 2160), ("DCI 4K", 4096, 2160), ("HD", 1920, 1080), ("DCI 2K", 2048, 1080)]
IMAGE_SUFFIXES = (".png", ".tif", ".tiff", ".jpg", ".jpeg")
SHEET_SUFFIXES = (".csv", ".xlsx", ".xlsm")
RECENT_LIMIT = 8
WATCH_INTERVAL_MS = 60_000      # how often a Google Sheet is checked for changes


def _runtime_text(frames: int, fps: float) -> str:
    """'3:30' when the runtime is whole seconds, otherwise '5035f'."""
    secs = frames / fps
    if abs(secs - round(secs)) < 0.5 / fps:
        m, s = divmod(int(round(secs)), 60)
        return f"{m}:{s:02d}"
    return f"{frames}f"


# --------------------------------------------------------------------------- #
# Control panels
# --------------------------------------------------------------------------- #

class TimingPanel(QWidget):
    changed = Signal()

    def __init__(self, project: proj.Project, parent=None):
        super().__init__(parent)
        self.project = project
        t = project.timing

        self.fit = QRadioButton("Fit runtime")
        self.manual = QRadioButton("Manual speed")
        grp = QButtonGroup(self)
        grp.addButton(self.fit)
        grp.addButton(self.manual)

        self.fps = QComboBox()
        self.fps.setEditable(True)
        self.fps.addItems([f"{f:g}" for f in FPS_CHOICES])
        self.runtime = QLineEdit()
        self.runtime.setPlaceholderText("3:30  or  210s  or  5035f")
        self.speed = _spin(1, 100, " px/frame")
        self.flex = _dspin(0.3, 3.0, 0.05, " ×")
        self.head = _spin(0, 10000, " frames")
        self.tail = _spin(0, 10000, " frames")
        self.flex_min = _dspin(0.1, 3.0, 0.05, " ×")
        self.flex_max = _dspin(0.1, 5.0, 0.05, " ×")
        self.max_panel = _spin(2000, 16384, " px")

        form = QFormLayout()
        mode = QHBoxLayout()
        mode.addWidget(self.fit)
        mode.addWidget(self.manual)
        form.addRow("Mode", mode)
        form.addRow("Frame rate", self.fps)
        form.addRow("Runtime", self.runtime)
        form.addRow("Speed", self.speed)
        form.addRow("Spacing", self.flex)
        form.addRow("Head hold", self.head)
        form.addRow("Tail hold", self.tail)
        limits = QHBoxLayout()
        limits.addWidget(self.flex_min)
        limits.addWidget(QLabel("to"))
        limits.addWidget(self.flex_max)
        form.addRow("Spacing limits", limits)
        form.addRow("Max panel", self.max_panel)

        self.result = QLabel("—")
        self.result.setWordWrap(True)
        self.result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box = QGroupBox("Result")
        bl = QVBoxLayout(box)
        bl.addWidget(self.result)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)
        lay.addLayout(form)
        lay.addWidget(box)
        lay.addStretch(1)

        self.load()
        for w in (self.fit, self.manual):
            w.toggled.connect(self._apply)
        self.fps.currentTextChanged.connect(self._apply)
        self.runtime.editingFinished.connect(self._apply)
        for w in (self.speed, self.flex, self.head, self.tail, self.flex_min, self.flex_max, self.max_panel):
            w.valueChanged.connect(self._apply)

    def load(self):
        t = self.project.timing
        for w in (self.fit, self.manual, self.fps, self.runtime, self.speed, self.flex, self.head,
                  self.tail, self.flex_min, self.flex_max, self.max_panel):
            w.blockSignals(True)
        (self.fit if t.mode == "runtime" else self.manual).setChecked(True)
        self.fps.setEditText(f"{t.fps:g}")
        self.runtime.setText(_runtime_text(t.runtime_frames, t.fps))
        self.speed.setValue(t.speed)
        self.flex.setValue(t.flex)
        self.head.setValue(t.head_hold)
        self.tail.setValue(t.tail_hold)
        self.flex_min.setValue(t.flex_min)
        self.flex_max.setValue(t.flex_max)
        self.max_panel.setValue(self.project.max_panel)
        for w in (self.fit, self.manual, self.fps, self.runtime, self.speed, self.flex, self.head,
                  self.tail, self.flex_min, self.flex_max, self.max_panel):
            w.blockSignals(False)
        self._mode_enable()

    def _mode_enable(self):
        fit = self.fit.isChecked()
        self.runtime.setEnabled(fit)
        self.flex_min.setEnabled(fit)
        self.flex_max.setEnabled(fit)
        self.speed.setEnabled(not fit)
        self.flex.setEnabled(not fit)

    def _apply(self, *_):
        t = self.project.timing
        t.mode = "runtime" if self.fit.isChecked() else "manual"
        try:
            t.fps = float(self.fps.currentText())
        except ValueError:
            pass
        try:
            if self.runtime.text().strip():
                t.runtime_frames = tc_to_frames(self.runtime.text(), t.fps)
        except ValueError:
            pass
        t.speed = self.speed.value()
        t.flex = self.flex.value()
        t.head_hold = self.head.value()
        t.tail_hold = self.tail.value()
        t.flex_min = self.flex_min.value()
        t.flex_max = self.flex_max.value()
        self.project.max_panel = self.max_panel.value()
        self._mode_enable()
        self.changed.emit()

    def show_result(self, build: Optional[proj.Build], error: Optional[str] = None):
        if error:
            self.result.setText(f"<span style='color:{theme.ERROR}'>{error}</span>")
            return
        if not build:
            self.result.setText("—")
            return
        s, L, look = build.solution, build.layout, self.project.look
        panels = ", ".join(f"{b - a}" for a, b in L.panels)
        txt = (f"<b>{s.timecode}</b> &nbsp; {s.total_frames} frames @ {s.fps:g}<br>"
               f"<b>{s.speed} px/frame</b> &nbsp; {s.seconds_on_screen(look.height):.1f} s on screen<br>"
               f"spacing ×{s.flex:.3f} &nbsp; content {L.content_height} px<br>"
               f"{len(L.panels)} panel{'s' if len(L.panels) != 1 else ''}: {panels} px")
        if build.warnings:
            txt += f"<br><span style='color:{theme.WARNING}'>" + "<br>".join(build.warnings) + "</span>"
        c = build.crawl.counts()
        txt += (f"<br><span style='color:{theme.MUTED}'>{c['headers']} headers · {c['role_lines']} role lines · "
                f"{c['list_names']} list names · {c['logos']} logos · {c['groups']} groups</span>")
        self.result.setText(txt)


class LookPanel(QWidget):
    changed = Signal()

    def __init__(self, project: proj.Project, parent=None):
        super().__init__(parent)
        self.project = project
        look = project.look

        self.center_x = _spin(0, 8192, " px")
        self.gutter = _spin(0, 1000, " px")
        self.group_gap = _spin(0, 1000, " px")
        self.header_before = _spin(0, 1000, " px")
        self.header_after = _spin(0, 1000, " px")
        self.list_width = _spin(200, 8192, " px")
        self.list_gap = _spin(0, 1000, " px")
        self.list_columns = _spin(1, 6, "")
        self.legal_width = _spin(200, 8192, " px")
        self.logo_height = _spin(20, 2000, " px")
        self.logo_gap = _spin(0, 1000, " px")
        self.logo_balance = _spin(0, 100, " %")
        self.logo_balance.setSingleStep(10)
        self.logo_balance.setToolTip("How logos of different shapes are sized against each other.\n"
                                     "0 %: all the same height (wide logos dominate).\n"
                                     "100 %: all the same area (wide logos shorter, compact ones taller).")
        self.supersample = _spin(1, 4, " ×")

        geo = QGroupBox("Geometry")
        g = QFormLayout(geo)
        g.addRow("Column centre", self.center_x)
        g.addRow("Gutter", self.gutter)
        g.addRow("Group gap", self.group_gap)
        hg = QHBoxLayout()
        hg.addWidget(self.header_before)
        hg.addWidget(QLabel("after"))
        hg.addWidget(self.header_after)
        g.addRow("Header gap before", hg)
        lw = QHBoxLayout()
        lw.addWidget(self.list_width)
        lw.addWidget(QLabel("gap"))
        lw.addWidget(self.list_gap)
        lw.addWidget(QLabel("cols"))
        lw.addWidget(self.list_columns)
        g.addRow("List width", lw)
        g.addRow("Legal width", self.legal_width)
        lg = QHBoxLayout()
        lg.addWidget(self.logo_height)
        lg.addWidget(QLabel("gap"))
        lg.addWidget(self.logo_gap)
        lg.addWidget(QLabel("even out"))
        lg.addWidget(self.logo_balance)
        g.addRow("Logo height", lg)
        g.addRow("Supersample", self.supersample)

        self.editors = {
            "header": StyleEditor("Section header", look.header),
            "role": StyleEditor("Role (left column)", look.role),
            "name": StyleEditor("Name (right column)", look.name),
            "list": StyleEditor("List (thanks, partners)", look.list),
            "legal": StyleEditor("Legal", look.legal),
        }

        inner = QWidget()
        il = QVBoxLayout(inner)
        for ed in self.editors.values():
            il.addWidget(ed)
            ed.changed.connect(self.changed)
        il.addWidget(geo)
        il.addStretch(1)
        il.setContentsMargins(14, 4, 14, 14)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(inner)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll)

        self.load()
        for w in self._geo_widgets():
            w.valueChanged.connect(self._apply)

    def _geo_widgets(self):
        return (self.center_x, self.gutter, self.group_gap,
                self.header_before, self.header_after, self.list_width, self.list_gap,
                self.list_columns, self.legal_width, self.logo_height, self.logo_gap, self.logo_balance,
                self.supersample)

    def load(self):
        look = self.project.look
        for w in self._geo_widgets():
            w.blockSignals(True)
        self.center_x.setValue(look.center_x)
        self.gutter.setValue(look.gutter)
        self.group_gap.setValue(look.group_gap)
        self.header_before.setValue(look.header_gap_before)
        self.header_after.setValue(look.header_gap_after)
        self.list_width.setValue(look.list_width)
        self.list_gap.setValue(look.list_column_gap)
        self.list_columns.setValue(self.project.list_columns)
        self.legal_width.setValue(look.legal_width)
        self.logo_height.setValue(look.logo_height)
        self.logo_gap.setValue(look.logo_gap)
        self.logo_balance.setValue(int(round(look.logo_balance * 100)))
        self.supersample.setValue(look.supersample)
        for w in self._geo_widgets():
            w.blockSignals(False)
        for key, ed in self.editors.items():
            ed.load(getattr(look, key))

    def _apply(self, *_):
        look = self.project.look
        look.center_x = self.center_x.value()
        look.gutter = self.gutter.value()
        look.group_gap = self.group_gap.value()
        look.header_gap_before = self.header_before.value()
        look.header_gap_after = self.header_after.value()
        look.list_width = self.list_width.value()
        look.list_column_gap = self.list_gap.value()
        self.project.list_columns = self.list_columns.value()
        look.legal_width = self.legal_width.value()
        look.logo_height = self.logo_height.value()
        look.logo_gap = self.logo_gap.value()
        look.logo_balance = self.logo_balance.value() / 100
        look.supersample = self.supersample.value()
        self.changed.emit()


class OutputPanel(QWidget):
    changed = Signal()
    render_requested = Signal()
    logo_setting_requested = Signal(str, dict)   # label, partial {invert, scale, dx, dy}
    resolution_requested = Signal(int, int)      # the window asks about scaling the look, then applies
    fps_requested = Signal(str)

    def __init__(self, project: proj.Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.resolution = QComboBox()
        for name, w, h in RESOLUTIONS:
            self.resolution.addItem(f"{name}  ·  {w} × {h}", f"{w}x{h}")
        self.resolution.addItem("Custom…", "")
        self.custom_w = _spin(320, 8192, " px")
        self.custom_h = _spin(180, 4320, " px")
        self.custom = QWidget()
        cl = QHBoxLayout(self.custom)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(self.custom_w)
        cl.addWidget(QLabel("×"))
        cl.addWidget(self.custom_h)
        cl.addStretch(1)
        self.fps = QComboBox()
        self.fps.setEditable(True)
        self.fps.addItems([f"{f:g}" for f in FPS_CHOICES])
        self.fps.setToolTip("Frames per second. The runtime stays the same; the frame count follows.")
        self.out_dir = QLineEdit()
        self.browse = QPushButton("…")
        self.basename = QLineEdit()
        self.version_output = QCheckBox("Use the next version number (v001, v002…)")
        self.version_output.setToolTip("Finds the next available version in the output folder when export starts.")
        self.timestamp_output = QCheckBox("Add date and time to output names")
        self.timestamp_output.setToolTip("Example: crawl_2026-10-07_14-30-05.mov. Uses local time when export starts.")
        self.codec = QComboBox()
        for key, c in export.CODECS.items():
            self.codec.addItem(c.label, key)
        self.alpha = QCheckBox("Carry alpha (ProRes 4444 / PNG only)")
        self.report = QCheckBox("Write export report")
        self.report.setToolTip("Write a text summary of export settings, credit counts, and warnings.")
        self.fusion = QCheckBox("Also write PNG panels + Fusion comp")
        self.fmt = QComboBox()
        self.fmt.addItems(["rgba8", "luma16"])
        self.fmt.setToolTip("Panel format: rgba8 coloured text with alpha, luma16 16-bit white matte")

        form = QFormLayout()
        form.addRow("Resolution", self.resolution)
        form.addRow("", self.custom)
        form.addRow("Frame rate", self.fps)
        od = QHBoxLayout()
        od.addWidget(self.out_dir, 1)
        od.addWidget(self.browse)
        form.addRow("Output folder", od)
        form.addRow("File name", self.basename)
        form.addRow("", self.version_output)
        form.addRow("", self.timestamp_output)
        form.addRow("Codec", self.codec)
        form.addRow("", self.alpha)
        fu = QHBoxLayout()
        fu.addWidget(self.fusion)
        fu.addWidget(self.fmt)
        form.addRow("", fu)
        form.addRow("", self.report)

        self.logos_box = QGroupBox("Logo slots")
        self.logos_layout = QFormLayout(self.logos_box)

        self.render_btn = QPushButton("Export movie")
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.result = QLabel("")
        self.result.setWordWrap(True)
        self.result.setTextInteractionFlags(Qt.TextSelectableByMouse)

        # The Export button itself is in the window header; this tab is its settings.
        self.render_btn.setVisible(False)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)
        lay.addLayout(form)
        lay.addWidget(self.logos_box)
        lay.addWidget(self.progress)
        lay.addWidget(self.result)
        lay.addStretch(1)

        self.load()
        self.resolution.activated.connect(self._resolution_picked)
        self.custom_w.editingFinished.connect(self._custom_edited)
        self.custom_h.editingFinished.connect(self._custom_edited)
        self.fps.activated.connect(lambda *_: self.fps_requested.emit(self.fps.currentText()))
        self.fps.lineEdit().editingFinished.connect(lambda: self.fps_requested.emit(self.fps.currentText()))
        self.browse.clicked.connect(self._browse)
        self.out_dir.editingFinished.connect(self._apply)
        self.basename.editingFinished.connect(self._apply)
        self.timestamp_output.toggled.connect(self._apply)
        self.version_output.toggled.connect(self._apply)
        self.codec.currentIndexChanged.connect(self._apply)
        self.alpha.toggled.connect(self._apply)
        self.fusion.toggled.connect(self._apply)
        self.report.toggled.connect(self._apply)
        self.fmt.currentTextChanged.connect(self._apply)
        self.render_btn.clicked.connect(self.render_requested)

    def sync_delivery(self):
        """Show the project's resolution and frame rate (they can change elsewhere)."""
        look = self.project.look
        widgets = (self.resolution, self.custom_w, self.custom_h, self.fps)
        for widget in widgets:
            widget.blockSignals(True)
        index = self.resolution.findData(f"{look.width}x{look.height}")
        self.resolution.setCurrentIndex(index if index >= 0 else self.resolution.count() - 1)
        self.custom.setVisible(index < 0)
        self.custom_w.setValue(look.width)
        self.custom_h.setValue(look.height)
        self.fps.setEditText(f"{self.project.timing.fps:g}")
        for widget in widgets:
            widget.blockSignals(False)

    def selected_size(self):
        """(width, height) of the chosen preset, or None for Custom."""
        key = self.resolution.currentData()
        return tuple(int(v) for v in key.split("x")) if key else None

    def _resolution_picked(self, index: int):
        size = self.selected_size()
        if size is None:
            self.custom.setVisible(True)          # nothing changes until a size is typed
            self.custom_w.setFocus()
            return
        self.resolution_requested.emit(*size)

    def _custom_edited(self):
        size = (self.custom_w.value(), self.custom_h.value())
        if size != (self.project.look.width, self.project.look.height):
            self.resolution_requested.emit(*size)

    def load(self):
        self.sync_delivery()
        widgets = (self.out_dir, self.basename, self.timestamp_output, self.version_output, self.codec, self.alpha, self.fusion, self.report, self.fmt)
        for widget in widgets:
            widget.blockSignals(True)
        p = self.project
        self.out_dir.setText(p.output_dir)
        self.basename.setText(p.basename)
        self.timestamp_output.setChecked(p.timestamp_output)
        self.version_output.setChecked(p.version_output)
        i = self.codec.findData(p.codec)
        self.codec.setCurrentIndex(max(0, i))
        self.alpha.setChecked(p.alpha)
        self.fusion.setChecked(p.write_fusion)
        self.report.setChecked(p.write_report)
        self.fmt.setCurrentText(p.fmt)
        for widget in widgets:
            widget.blockSignals(False)
        self._enable()

    def _enable(self):
        c = export.CODECS[self.codec.currentData()]
        self.alpha.setEnabled(c.alpha)
        self.fmt.setEnabled(self.fusion.isChecked())
        self.render_btn.setText("Export PNG sequence" if c.key == "png" else f"Export {c.label}")

    def _apply(self, *_):
        p = self.project
        p.output_dir = self.out_dir.text().strip()
        p.basename = self.basename.text().strip() or "crawl"
        p.timestamp_output = self.timestamp_output.isChecked()
        p.version_output = self.version_output.isChecked()
        p.codec = self.codec.currentData()
        p.alpha = self.alpha.isChecked()
        p.write_fusion = self.fusion.isChecked()
        p.write_report = self.report.isChecked()
        p.fmt = self.fmt.currentText()
        self._enable()
        self.changed.emit()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Output folder", self.out_dir.text())
        if d:
            self.out_dir.setText(d)
            self._apply()

    def set_logo_slots(self, crawl):
        while self.logos_layout.rowCount():
            self.logos_layout.removeRow(0)
        labels = list(dict.fromkeys(lg.label for lg in crawl.logos())) if crawl else []
        self.logos_box.setVisible(False)  # Artwork is managed in the dedicated Logos workspace.
        self._invert_boxes = {}
        for label in labels:
            btn = QPushButton(os.path.basename(self.project.logos.get(label, "")) or "Choose image…")
            btn.clicked.connect(lambda _=False, l=label, b=btn: self._pick_logo(l, b))
            invert = QCheckBox("Invert")
            invert.setToolTip("Flip the artwork's colours — for a dark logo on the black crawl.\n"
                              "Click a logo in the preview to move or resize it.")
            invert.setChecked(bool(self.project.logo_settings.get(label, {}).get("invert")))
            invert.toggled.connect(lambda on, l=label: self.logo_setting_requested.emit(l, {"invert": on}))
            row = QHBoxLayout()
            row.addWidget(btn, 1)
            row.addWidget(invert)
            self.logos_layout.addRow(label, row)
            self._invert_boxes[label] = invert

    def sync_logo_invert(self, label: str, on: bool):
        """Reflect a change made elsewhere (the preview's logo bar) without re-emitting."""
        box = getattr(self, "_invert_boxes", {}).get(label)
        if box is not None and box.isChecked() != on:
            box.blockSignals(True)
            box.setChecked(on)
            box.blockSignals(False)

    def _pick_logo(self, label: str, btn: QPushButton):
        path, _ = QFileDialog.getOpenFileName(self, f"Logo for {label}", "", "Images (*.png *.tif *.tiff *.jpg)")
        if path:
            self.project.logos[label] = path
            btn.setText(os.path.basename(path))
            self.changed.emit()


# --------------------------------------------------------------------------- #
# Main window
# --------------------------------------------------------------------------- #

class MainWindow(QMainWindow):
    def __init__(self, project: Optional[proj.Project] = None):
        super().__init__()
        self.project = project or proj.Project()
        self.project_path: Optional[str] = None
        self.crawl = None
        self.build: Optional[proj.Build] = None
        self._worker: Optional[RebuildWorker] = None
        self._dirty = False
        self._render_worker: Optional[RenderWorker] = None
        self._pending_finding_row = None
        self._sticky_message = ""
        self._fetch_worker: Optional[SheetFetchWorker] = None
        self._update_check_worker = None
        self._pending_url = ""          # set while a Google download is being loaded as the source
        self._fetch_manual = False
        self._offered_path: Optional[str] = None     # Google download already announced in the banner
        self.setAcceptDrops(True)

        self.timing_panel = TimingPanel(self.project)
        self.look_panel = LookPanel(self.project)
        self.output_panel = OutputPanel(self.project)
        self.preview = PreviewPanel()
        self.music_panel = MusicPanel(self.project)
        self.sheet_editor = SheetEditor(self.project)
        self.logo_workspace = LogoWorkspace(self.project, self.sheet_editor)

        # Tabs follow the work: get the credits right, style them, time them, export.
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(self.sheet_editor, "Credits")
        self.look_tabs = QTabWidget()
        self.look_tabs.setDocumentMode(True)
        self.look_tabs.addTab(self.look_panel, "General")
        self.look_tabs.addTab(self.music_panel, "Music")
        tabs.addTab(self.logo_workspace, "Logos")
        tabs.addTab(self.look_tabs, "Look")
        tabs.addTab(self.timing_panel, "Timing")
        tabs.addTab(self.output_panel, "Export")
        tabs.setMinimumWidth(440)
        self.tabs = tabs

        split = QSplitter()
        self._panel_split = split
        self._expanded_panel = None
        split.setChildrenCollapsible(False)
        split.setHandleWidth(1)
        split.addWidget(tabs)
        self.preview_stack = QStackedWidget()
        self.preview_stack.addWidget(self.preview)
        self.preview_stack.addWidget(self.logo_workspace.canvas)
        split.addWidget(self.preview_stack)
        tabs.currentChanged.connect(self._workspace_changed)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([540, 960])

        central = QWidget()
        column = QVBoxLayout(central)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self._app_header = self._header()
        column.addWidget(self._app_header)
        column.addWidget(self._update_notice())
        column.addWidget(self._banner())
        column.addWidget(split, 1)
        self.setCentralWidget(central)
        self.resize(1500, 900)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._rebuild)
        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(WATCH_INTERVAL_MS)
        self._watch_timer.timeout.connect(lambda: self._fetch_google(manual=False))

        for panel in (self.timing_panel, self.look_panel, self.output_panel, self.music_panel):
            panel.changed.connect(self._panel_changed)
        self._panel_last = self._panel_state()
        self.output_panel.render_requested.connect(self.render)
        self.output_panel.logo_setting_requested.connect(self.set_logo_setting)
        self.output_panel.resolution_requested.connect(self.change_resolution)
        self.output_panel.fps_requested.connect(self.timing_panel.fps.setEditText)
        self.sheet_editor.changed.connect(self._credits_changed)
        self.sheet_editor.finding_selected.connect(self.jump_to_finding)
        self.sheet_editor.import_history_requested.connect(self.show_import_history)
        self.sheet_editor.preview_requested.connect(self.seek_row)
        self.preview.view.credit_selected.connect(self._select_preview_credit)
        self.sheet_editor.restored.connect(self._history_restored)
        self.sheet_editor.history_changed.connect(self._sync_history)
        self.sheet_editor.open_requested.connect(self.open_sheet)
        self.sheet_editor.link_requested.connect(self.open_google_sheet)
        self.sheet_editor.blank_requested.connect(self.new_blank)
        self.sheet_editor.dismissed_changed.connect(self._dismissed_changed)
        self.preview.view.logo_selected.connect(self._logo_selected)
        self.preview.view.logo_moved.connect(self._logo_moved)
        self.preview.logo_bar.changed.connect(self.set_logo_setting)
        self.preview.logo_bar.auto_requested.connect(self.auto_logo_levels)
        self.logo_workspace.setting_changed.connect(self.set_logo_setting)
        self.logo_workspace.auto_requested.connect(self.auto_logo_levels)
        self.logo_workspace.moved.connect(self._logo_moved)
        self.logo_workspace.batch_settings.connect(self.set_logo_settings_batch)
        self.logo_workspace.changed.connect(self._logo_artwork_changed)
        self.logo_workspace.show_row.connect(self._show_logo_location)

        self.sheet_editor.expand_button.clicked.connect(lambda: self._toggle_panel_expansion("sheet"))
        self.preview.expand_button.clicked.connect(lambda: self._toggle_panel_expansion("preview"))
        self._exit_expansion = QAction("Exit expanded view", self)
        self._exit_expansion.setShortcut("Esc")
        self._exit_expansion.setEnabled(False)
        self._exit_expansion.triggered.connect(self._restore_panel_layout)
        self.addAction(self._exit_expansion)
        self._menus()
        QTimer.singleShot(1000, self._check_for_app_updates)
        self._unsaved = False
        self._sync_export_label()
        self._sync_history()
        self._sync_ready()
        self._title()
        if self.project.source or self.project.rows is not None:
            self.load_sheet(self.project.source, preserve_edits=True)
            self._unsaved = False
        self._sync_google()

    def _toggle_panel_expansion(self, panel):
        if self._expanded_panel is not None:
            self._restore_panel_layout()
            return
        self._panel_restore = (self.windowState(), self._panel_split.sizes(),
                               self.tabs.currentIndex(), self.preview_stack.currentIndex())
        self._expanded_panel = panel
        self._exit_expansion.setEnabled(True)
        self._app_header.hide()
        self.tabs.tabBar().hide()
        if panel == "sheet":
            self.tabs.setCurrentWidget(self.sheet_editor)
            self.preview_stack.hide()
            self.sheet_editor.expand_button.setText("Restore")
            self.sheet_editor.expand_button.setToolTip("Return to the normal layout (Esc)")
        else:
            self.preview_stack.setCurrentWidget(self.preview)
            self.tabs.hide()
            self.preview.expand_button.setText("Restore")
            self.preview.expand_button.setToolTip("Return to the normal layout (Esc)")
        self.showFullScreen()

    def _restore_panel_layout(self):
        if self._expanded_panel is None:
            return
        state, sizes, tab, preview = self._panel_restore
        self._expanded_panel = None
        self._exit_expansion.setEnabled(False)
        self.tabs.show()
        self.preview_stack.show()
        self.tabs.tabBar().show()
        self._app_header.show()
        self.tabs.setCurrentIndex(tab)
        self.preview_stack.setCurrentIndex(preview)
        self.setWindowState(state)
        self._panel_split.setSizes(sizes)
        self.sheet_editor.expand_button.setText("Expand")
        self.sheet_editor.expand_button.setToolTip("Show the spreadsheet full screen")
        self.preview.expand_button.setText("Expand")
        self.preview.expand_button.setToolTip("Show the crawl preview full screen")

    # ---- header ------------------------------------------------------------

    def _header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("header")
        header.setAttribute(Qt.WA_StyledBackground, True)
        self.title_label = QLabel()
        self.title_label.setObjectName("title")
        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("subtitle")
        self.format_chip = QLabel()
        self.format_chip.setProperty("role", "chip")
        self.format_chip.setToolTip("Resolution and frame rate — set on the Export tab")
        self.chips = []
        for tip in ("Runtime", "Scroll speed", "Spacing scale chosen to hit the runtime"):
            chip = QLabel("—")
            chip.setProperty("role", "chip")
            chip.setToolTip(tip)
            chip.setVisible(False)
            self.chips.append(chip)
        self.header_progress = QProgressBar()
        self.header_progress.setFixedWidth(240)
        self.header_progress.setVisible(False)
        self.export_btn = QPushButton("Export")
        self.export_btn.setProperty("primary", True)
        self.export_btn.setToolTip("Render the crawl to a movie  (Ctrl+R)\nCodec and folder are on the Export tab.")
        self.export_btn.clicked.connect(self._export_clicked)
        row = QHBoxLayout(header)
        row.setContentsMargins(14, 8, 12, 8)
        row.setSpacing(8)
        row.addWidget(self.title_label)
        row.addWidget(self.subtitle_label)
        row.addStretch(1)
        row.addWidget(self.format_chip)
        for chip in self.chips:
            row.addWidget(chip)
        row.addSpacing(6)
        row.addWidget(self.header_progress)
        row.addWidget(self.export_btn)
        return header

    def _banner(self) -> QWidget:
        """A strip under the header for things that happened on their own, e.g. the Google Sheet changed."""
        banner = QFrame()
        banner.setObjectName("banner")
        banner.setAttribute(Qt.WA_StyledBackground, True)
        self.banner_label = QLabel()
        self.banner_label.setWordWrap(True)
        self.banner_review = QPushButton("Review changes…")
        self.banner_review.setProperty("primary", True)
        self.banner_review.clicked.connect(self._review_offered)
        later = QPushButton("Later")
        later.clicked.connect(lambda: self.banner.setVisible(False))
        row = QHBoxLayout(banner)
        row.setContentsMargins(14, 6, 12, 6)
        row.setSpacing(8)
        row.addWidget(self.banner_label, 1)
        row.addWidget(self.banner_review)
        row.addWidget(later)
        banner.setVisible(False)
        self.banner = banner
        return banner

    def _update_notice(self):
        self.update_banner = QFrame()
        row = QHBoxLayout(self.update_banner)
        self.update_notice_label = QLabel("An EasyCrawl update is available.")
        row.addWidget(self.update_notice_label, 1)
        install = QPushButton("Update EasyCrawl…")
        install.clicked.connect(self.update_app)
        row.addWidget(install)
        later = QPushButton("Later")
        later.clicked.connect(self.update_banner.hide)
        row.addWidget(later)
        self.update_banner.hide()
        return self.update_banner

    def _check_for_app_updates(self):
        # Source-checkout updater; packaged releases use a different installation flow.
        root = Path(__file__).resolve().parents[2]
        if ((sys.platform != "win32" and not (sys.platform == "darwin" and getattr(sys, "frozen", False)))
                or QApplication.platformName() in ("offscreen", "minimal")
                or (not getattr(sys, "frozen", False) and not (root / ".git").exists()) or self._update_check_worker is not None):
            return
        worker = UpdateCheckWorker(root, self)
        worker.available.connect(self.update_banner.show)
        worker.release_available.connect(self._release_update_available)
        self._update_check_worker = worker
        worker.start()

    def _release_update_available(self, version, url):
        self._installer_url = url
        self.update_notice_label.setText(f"EasyCrawl {version} is available. Download the update to install it.")
        self.update_banner.show()

    def _exporting(self) -> bool:
        return bool(self._render_worker and self._render_worker.isRunning())

    def _export_clicked(self):
        """The header button exports, and while an export runs it cancels."""
        if self._exporting():
            self.cancel_export()
        else:
            self.render()

    def _sync_export_label(self):
        codec = export.CODECS[self.project.codec]
        if not self._exporting():          # while exporting the button reads "Cancel export"
            self.export_btn.setText("Export PNG sequence" if codec.key == "png" else f"Export {codec.label}")
        look = self.project.look
        self.format_chip.setText(f"{look.width} × {look.height}  ·  {self.project.timing.fps:g} fps")
        self.output_panel.sync_delivery()

    def _set_chips(self, values):
        for chip, value in zip(self.chips, values):
            chip.setText(value)
            chip.setVisible(bool(value))

    def _sync_ready(self):
        """Export and the transport need a finished layout."""
        if not self._exporting():          # during an export the button stays live, as Cancel
            self.export_btn.setEnabled(self.build is not None)
        self.preview.play.setEnabled(self.preview.slider.maximum() > 0)
        self.preview.slider.setEnabled(self.preview.slider.maximum() > 0)

    # ---- unsaved state -----------------------------------------------------

    @property
    def _unsaved(self) -> bool:
        return self.isWindowModified()

    @_unsaved.setter
    def _unsaved(self, on: bool):
        self.setWindowModified(bool(on))     # the dot in the title bar

    def _mark_unsaved(self):
        self._unsaved = True

    def _panel_state(self):
        """(what affects the picture, what only affects the export) as comparable strings."""
        p = self.project
        picture = json.dumps([p.look.to_dict(), p.timing.to_dict(), p.list_columns, p.max_panel, p.logos],
                             sort_keys=True)
        output = json.dumps([p.output_dir, p.basename, p.timestamp_output, p.version_output, p.codec, p.alpha, p.write_fusion, p.write_report, p.fmt])
        return picture, output

    def change_resolution(self, width: int, height: int, scale_look=None):
        """Switch delivery size. Asks whether the look should scale with it
        (pass scale_look to skip the question)."""
        look = self.project.look
        if (width, height) == (look.width, look.height):
            return
        if scale_look is None:
            scale_look = True
            if height != look.height:
                factor = height / look.height
                box = QMessageBox(self)
                box.setWindowTitle("Change resolution")
                box.setText(f"Scale the look to {width} × {height}?")
                box.setInformativeText(
                    f"Sizes are in pixels, so at the new size the type would be "
                    f"{'larger' if factor < 1 else 'smaller'} in the frame unless it scales too.\n\n"
                    f"Scale look: fonts, spacing, logos and offsets × {factor:g} — the same picture at the new size.\n"
                    f"Canvas only: keep every size as it is and just re-centre the column.")
                scale = box.addButton("Scale look", QMessageBox.AcceptRole)
                canvas = box.addButton("Canvas only", QMessageBox.ActionRole)
                box.addButton(QMessageBox.Cancel)
                box.setDefaultButton(scale)
                box.exec()
                if box.clickedButton() not in (scale, canvas):
                    self.output_panel.sync_delivery()      # put the menu back
                    return
                scale_look = box.clickedButton() is scale
        self.project.set_resolution(width, height, scale_look)
        for panel in (self.look_panel, self.music_panel, self.timing_panel, self.output_panel):
            panel.load()
        label = self.preview.view.selected
        if label:
            self.preview.logo_bar.load(label, self.project.logo_settings.get(label, {}))
        self.sheet_editor.commit_undo()              # logo offsets and arrangement gaps moved
        self._panel_changed()

    def _panel_changed(self):
        """A panel says something changed. Panels also say so when a field merely
        loses focus, so compare: only a real difference dirties the project, and
        only a difference in the picture costs a re-layout."""
        state = self._panel_state()
        if state == self._panel_last:
            return
        picture_changed = state[0] != self._panel_last[0]
        self._panel_last = state
        self._unsaved = True
        self._sync_export_label()
        if picture_changed:
            self.schedule_rebuild()

    # ---- menus -------------------------------------------------------------

    def _menus(self):
        m = self.menuBar().addMenu("&File")
        self._act(m, "Open Sheet…", QKeySequence.Open, self.open_sheet)
        self._act(m, "Open Google Sheet…", "Ctrl+Shift+G", self.open_google_sheet).setToolTip(
            "Paste the link of a sheet shared as 'Anyone with the link can view'")
        self._act(m, "Open Project…", "Ctrl+Shift+O", self.open_project)
        self.recent_menu = m.addMenu("Open Recent")
        m.addSeparator()
        self._act(m, "Update from Revised Sheet…", "Ctrl+U", self.update_from_sheet).setToolTip(
            "Bring in a newer version of the credits without losing the work done here")
        self._act(m, "Import History…", None, self.show_import_history)
        self.refresh_action = self._act(m, "Refresh from Google Sheet", "Ctrl+Shift+U",
                                        lambda: self._fetch_google(manual=True))
        self.refresh_action.setToolTip("Download the sheet again and review what changed")
        self.watch_action = self._act(m, "Watch Google Sheet for Changes", None, self._sync_google)
        self.watch_action.setCheckable(True)
        self.watch_action.setChecked(self._settings().value("google/watch", True, type=bool))
        self.watch_action.setToolTip(f"Check the sheet every {WATCH_INTERVAL_MS // 1000} seconds "
                                     f"and say when it has changed")
        self.auto_apply_action = self._act(m, "Apply Google Sheet Changes Automatically", None, self._sync_google)
        self.auto_apply_action.setCheckable(True)
        self.auto_apply_action.setChecked(self._settings().value("google/auto_apply", False, type=bool))
        self.auto_apply_action.setToolTip("Bring changes straight in while watching. Rows you have also edited "
                                          "here are still held back for review.")
        self.import_options_action = self._act(m, "Import Options…", None, self.import_options)
        self.import_options_action.setToolTip("Which worksheet, columns and start row the credits are read from")
        self._act(m, "Reload Sheet (discard edits)", QKeySequence.Refresh,
                  lambda: self.load_sheet(self.project.source))
        m.addSeparator()
        self._act(m, "Save Project", QKeySequence.Save, self.save_project)
        self._act(m, "Save Project As…", QKeySequence.SaveAs, lambda: self.save_project(True))
        self.snapshots_action = self._act(m, "Version Snapshots…", None, self.version_snapshots)
        self.snapshots_action.setToolTip("Save, rename and restore named project milestones")
        self._act(m, "Collect Files into Project Folder", None, self.collect_files).setToolTip(
            "Copy the sheet and logo artwork next to the project so the folder can be moved or shared")
        m.addSeparator()
        self._act(m, "Relink Missing Files…", None, self.relink_files)
        m.addSeparator()
        self._act(m, "Save Look As…", None, self.save_look)
        self._act(m, "Load Look…", None, self.load_look)
        self._act(m, "Export Credits as CSV…", None, self.sheet_editor.export_csv)
        m.addSeparator()
        self._act(m, "Quit", QKeySequence.Quit, self.close)
        self._rebuild_recent_menu()

        e = self.menuBar().addMenu("&Edit")
        self.undo_action = self._act(e, "Undo", QKeySequence.Undo, self.undo)
        self.redo_action = self._act(e, "Redo", QKeySequence.Redo, self.redo)
        e.addSeparator()
        # No window-wide shortcuts for these: the sheet and text fields handle the keys themselves.
        self._act(e, "Cut", None, lambda: self._edit("cut")).setShortcutVisibleInContextMenu(True)
        self._act(e, "Copy", None, lambda: self._edit("copy"))
        self._act(e, "Paste", None, lambda: self._edit("paste"))
        e.addSeparator()
        self._act(e, "Insert Row Above", "Ctrl+Alt+Up", lambda: self._sheet(lambda s: s.insert_rows(above=True)))
        self._act(e, "Insert Row Below", "Ctrl+Alt+Down", lambda: self._sheet(lambda s: s.insert_rows(above=False)))
        self._act(e, "Insert Rows Above…", None, lambda: self._sheet(lambda s: s.insert_rows_dialog(above=True)))
        self._act(e, "Insert Rows Below…", None, lambda: self._sheet(lambda s: s.insert_rows_dialog(above=False)))
        self._act(e, "Delete Rows", "Ctrl+Alt+Backspace", lambda: self._sheet(lambda s: s.delete_rows()))
        e.addSeparator()
        self._act(e, "Dismiss Problem", "Ctrl+D", lambda: self._sheet(lambda s: s.dismiss(
            None if s.finding_index >= 0 else s._selected_finding_indices())))
        self._act(e, "Find…", QKeySequence.Find, self.find)

        v = self.menuBar().addMenu("&View")
        self._act(v, "Play / Pause", "Space", self.preview.toggle_play)
        self._act(v, "Previous Section", "Ctrl+Up", lambda: self.preview.slider.jump(-1))
        self._act(v, "Next Section", "Ctrl+Down", lambda: self.preview.slider.jump(1))
        v.addSeparator()
        for action in (self.preview.safe, self.preview.centre, self.preview.cuts):
            v.addAction(action)

        v.addSeparator()
        gpu = self._act(v, "GPU Preview (restart to apply)", None, lambda: None)
        gpu.setCheckable(True)
        gpu.setChecked(QSettings("easycrawl", "EasyCrawl").value("preview/gpu", True, type=bool))
        gpu.toggled.connect(lambda enabled: QSettings("easycrawl", "EasyCrawl").setValue("preview/gpu", enabled))

        r = self.menuBar().addMenu("E&xport")
        self._act(r, "Export Movie", "Ctrl+R", self.render)
        self._act(r, "Cancel Export", "Ctrl+.", self.cancel_export)
        self._act(r, "Export Settings…", None, lambda: self.tabs.setCurrentWidget(self.output_panel))
        r.addSeparator()
        self._act(r, "Check a Rendered Movie…", None, self.check_movie)

        help_menu = self.menuBar().addMenu("&Help")
        self._act(help_menu, "Update EasyCrawl…", None, self.update_app)

    def update_app(self):
        if getattr(sys, "frozen", False):
            QDesktopServices.openUrl(QUrl(getattr(self, "_installer_url", "https://github.com/RJ2320/easycrawl/releases/latest")))
            return
        updater = Path(__file__).resolve().parents[2] / "Update EasyCrawl.bat"
        if sys.platform != "win32" or getattr(sys, "frozen", False) or not updater.is_file():
            QMessageBox.information(self, "Update EasyCrawl",
                                    "This updater needs a Windows Git checkout with the Update EasyCrawl utility.")
            return
        if self._exporting():
            QMessageBox.information(self, "Update EasyCrawl", "Finish or cancel the export before updating.")
            return
        if QMessageBox.question(
                self, "Update EasyCrawl",
                "Close EasyCrawl and download the latest code?\n"
                "You will be asked to save any project changes. The updater stops if the code has local changes.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        # Launch only after closeEvent has accepted saving and completed worker shutdown.
        if not self.close():
            return
        started, _ = QProcess.startDetached(
            "cmd.exe", ["/c", str(updater), "-WaitForPid", str(os.getpid())], str(updater.parent))
        if not started:
            self.show()
            QMessageBox.warning(self, "Update EasyCrawl", "Could not start the updater. Try Update EasyCrawl.bat in the app folder.")

    def _act(self, menu, text, shortcut, fn):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(shortcut)
        a.triggered.connect(fn)
        menu.addAction(a)
        return a

    def show_import_history(self):
        from .import_history_dialog import ImportHistoryDialog
        ImportHistoryDialog(self.project, self).exec()

    def _title(self):
        name = Path(self.project_path).name if self.project_path else "Untitled"
        src = Path(self.project.source).name if self.project.source else ""
        if self.project.source_url:
            src = "Google Sheet" + (f" · {self.project.sheet}" if self.project.sheet else "")
        elif src and self.project.sheet and ingest.is_workbook(self.project.source):
            src = f"{src} · {self.project.sheet}"
        self.setWindowTitle(f"{name}[*] — EasyCrawl")
        self.title_label.setText(name.replace(proj.PROJECT_SUFFIX, ""))
        self.subtitle_label.setText(src)
        self.subtitle_label.setToolTip(self.project.source_url or self.project.source)
        from .import_history_dialog import latest_import_text
        self.sheet_editor.import_label.setText(latest_import_text(self.project))
        self.sheet_editor.import_label.setToolTip(self.project.source_url or self.project.source)
        if hasattr(self, "import_options_action"):
            self.import_options_action.setEnabled(bool(self.project.source))

    def _sheet(self, fn):
        """Run a sheet action from a menu: show the Credits tab first."""
        self.tabs.setCurrentWidget(self.sheet_editor)
        fn(self.sheet_editor)

    def _edit(self, op: str):
        """Cut / copy / paste go to whatever has focus: the sheet, or a text field."""
        from PySide6.QtWidgets import QApplication
        widget = QApplication.focusWidget()
        table = self.sheet_editor.table
        if widget is table or widget is table.viewport():
            getattr(self.sheet_editor, op)()
        elif widget is not None and hasattr(widget, op):
            getattr(widget, op)()

    def find(self):
        self.tabs.setCurrentWidget(self.sheet_editor)
        self.sheet_editor.focus_search()

    # ---- undo --------------------------------------------------------------

    def undo(self):
        self.sheet_editor.undo()

    def redo(self):
        self.sheet_editor.redo()

    def _sync_history(self):
        self.undo_action.setEnabled(self.sheet_editor.can_undo())
        self.redo_action.setEnabled(self.sheet_editor.can_redo())

    def _dismissed_changed(self):
        """Keep the build's findings (which gate export) in step with the dismissals."""
        self._unsaved = True
        if self.build is not None:
            hidden = set(self.project.dismissed)
            self.build.findings = [f for f in self.build.findings if not (f.key and f.key in hidden)]

    def _history_restored(self):
        """Undo/redo swapped logos, arrangements and rows back in: refresh what shows them."""
        label = self.preview.view.selected
        if label:
            self.preview.logo_bar.load(label, self.project.logo_settings.get(label, {}))

    # ---- recent files ------------------------------------------------------

    def _settings(self) -> QSettings:
        settings = QSettings("easycrawl", "Crawl")
        if not settings.contains("recent"):
            # Preferences used to live under the studio's name; carry the recent list over once.
            old = QSettings("Periscope", "Crawl")
            if old.contains("recent"):
                settings.setValue("recent", old.value("recent"))
        return settings

    def _recent(self):
        value = self._settings().value("recent", [])
        paths = [value] if isinstance(value, str) else list(value or [])
        return [p for p in paths if p and (gsheets.is_link(p) or Path(p).exists())]

    def _remember(self, path: str):
        path = gsheets.canonical(path) if gsheets.is_link(path) else str(Path(path).resolve())
        paths = [path] + [p for p in self._recent() if p != path]
        self._settings().setValue("recent", paths[:RECENT_LIMIT])
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self):
        self.recent_menu.clear()
        paths = self._recent()
        for path in paths:
            label = "Google Sheet " + gsheets.parse(path)[0][:8] + "…" if gsheets.is_link(path) else Path(path).name
            self.recent_menu.addAction(label, lambda p=path: self.open_path(p)).setToolTip(path)
        self.recent_menu.setToolTipsVisible(True)
        self.recent_menu.setEnabled(bool(paths))

    # ---- drag and drop -----------------------------------------------------

    def dragEnterEvent(self, event):
        data = event.mimeData()
        if data.hasUrls() or (data.hasText() and gsheets.is_link(data.text())):
            event.acceptProposedAction()

    def dropEvent(self, event):
        data = event.mimeData()
        links = [url.toString() for url in data.urls() if not url.isLocalFile() and gsheets.is_link(url.toString())]
        if not links and data.hasText() and gsheets.is_link(data.text()):
            links = [data.text().strip()]
        if links:
            self.open_google_sheet(links[0])
            event.acceptProposedAction()
            return
        paths = [url.toLocalFile() for url in data.urls() if url.isLocalFile()]
        images = [p for p in paths if p.lower().endswith(IMAGE_SUFFIXES)]
        others = [p for p in paths if p not in images]
        if others:
            self.open_path(others[0])
        if images and self.crawl is not None:
            self.tabs.setCurrentWidget(self.sheet_editor)
            self.sheet_editor.add_logo_paths(images)
        event.acceptProposedAction()

    # ---- files -------------------------------------------------------------

    def open_path(self, path: str):
        """Open whatever this is: a project, a sheet, or a Google Sheets link."""
        if gsheets.is_link(path):
            self.open_google_sheet(path)
        elif path.endswith(proj.PROJECT_SUFFIX):
            self.open_project(path)
        elif path.lower().endswith(SHEET_SUFFIXES):
            choice = self._update_or_replace(Path(path).name)
            if choice == "update":
                self.update_from_sheet(path)
            elif choice == "replace" and self.load_sheet(path):
                self._remember(path)
        else:
            QMessageBox.information(self, "Can't open that",
                                    "Open a credits sheet (.csv, .xlsx), a Google Sheets link, "
                                    "or a project (.crawl.json).")

    def _update_or_replace(self, name: str) -> str:
        """A crawl is already open: is this sheet a revision of it, or a different job?
        Returns 'update', 'replace' (edits already confirmed as discardable) or ''."""
        if self.crawl is None or not self.sheet_editor.table.rowCount():
            return "replace"
        box = QMessageBox(self)
        box.setWindowTitle("Open sheet")
        box.setText(f"Bring {name} into this crawl?")
        box.setInformativeText("Update keeps your layout, logos and edits and shows what changed. "
                               "Replace starts again from this sheet.")
        update = box.addButton("Update", QMessageBox.AcceptRole)
        replace = box.addButton("Replace", QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        if box.clickedButton() is update:
            return "update"
        if box.clickedButton() is replace:
            self.project.rows = None      # the choice was already confirmed
            return "replace"
        return ""

    def open_sheet(self):
        path, _ = QFileDialog.getOpenFileName(self, "Credits sheet", "", "Sheets (*.csv *.xlsx);;All files (*)")
        if path and self.load_sheet(path):
            self._remember(path)

    def new_blank(self):
        """Start typing with no source file."""
        self.project.rows = [["", "", ""] for _ in range(40)]
        self.project.arrangements[:] = []
        self.project.overrides[:] = []
        self.project.import_notes[:] = []
        self.project.base_rows = None
        self.load_sheet("", preserve_edits=True)
        self.sheet_editor.table.setCurrentCell(0, 0)
        self.sheet_editor.table.setFocus()

    def load_sheet(self, path: str, preserve_edits=False) -> bool:
        if not path and not (preserve_edits and self.project.rows is not None):
            return False
        if not preserve_edits and self.project.rows is not None:
            if QMessageBox.question(self, "Replace edited credits?",
                    "Loading the sheet replaces the credits edited in this project. Continue?") != QMessageBox.Yes:
                return False
        fresh = not (preserve_edits and self.project.rows is not None)
        if fresh and path and not self._prepare_import(path):
            return False
        try:
            rows, notes = proj.read_source(self.project, path) if fresh else (self.project.rows, [])
        except Exception as e:
            QMessageBox.critical(self, "Can't read sheet", str(e))
            return False
        self.project.source = str(Path(path).resolve()) if path else ""
        if fresh:
            self.project.source_url = self._pending_url
            self._pending_url = ""
        if not preserve_edits:
            self.project.rows = None
            self.project.arrangements[:] = []
            self.project.overrides[:] = []
        if fresh:
            # What the client sent, kept so a revised sheet can be merged in later.
            self.project.base_rows = [list(r) for r in rows]
            self.project.record_import(rows)
            self.project.import_notes[:] = notes
            self.project.dismissed[:] = [k for k in self.project.dismissed if not k.startswith("import|")]
        self.sheet_editor.load(rows)
        self.crawl = proj.crawl_from_rows(self.project, rows)
        if path and not self.project.output_dir:
            # A default, not an edit: don't let it read as an unsaved change.
            self.project.output_dir = str(Path(path).parent / "render")
            self.output_panel.load()
            self._panel_last = (self._panel_last[0], self._panel_state()[1])
        self.output_panel.set_logo_slots(self.crawl)
        self._title()
        if path:
            message = f"Loaded {Path(path).name}: {self.crawl.describe()}"
            if fresh and notes:
                message = (f"{Path(path).name} doesn't quite match the template: {len(notes)} "
                           f"row{'s' if len(notes) != 1 else ''} adjusted on import — see the warnings in Credits")
                self._sticky_message = message      # survive the "laid out" message that follows
            self.statusBar().showMessage(message)
        self.schedule_rebuild()
        return True

    def update_from_sheet(self, path: str = "", from_google: bool = False, silent: bool = False):
        """Merge a revised credits sheet into the crawl as it stands.

        `from_google`: the file is a fresh download of the project's Google Sheet.
        `silent`: apply the changes without asking, unless some collide with
        edits made here, in which case nothing is applied and None is returned
        so the caller can offer a review. Returns the changes found."""
        from .. import changes
        from .change_dialog import ChangeDialog
        if self.crawl is None:
            self.open_sheet()
            return
        if not path:
            start = str(Path(self.project.source).parent) if self.project.source else ""
            path, _ = QFileDialog.getOpenFileName(self, "Revised credits sheet", start,
                                                  "Sheets (*.csv *.xlsx);;All files (*)")
        if not path:
            return
        import_settings = (self.project.sheet, self.project.columns, self.project.start_row)
        def restore_import_settings():
            self.project.sheet, self.project.columns, self.project.start_row = import_settings
        if not self._prepare_import(path):
            restore_import_settings()
            return
        try:
            new_rows, notes = proj.read_source(self.project, path)
        except Exception as e:
            restore_import_settings()
            QMessageBox.critical(self, "Can't read sheet", str(e))
            return
        found = changes.diff(self.project.base_rows, self.sheet_editor.rows(), new_rows)
        name = "the Google Sheet" if from_google else Path(path).name
        if not found:
            # Still the new reference point: its rows match what is here.
            self.project.base_rows = [list(r) for r in new_rows]
            self.project.source = str(Path(path).resolve())
            if not from_google:
                self.project.source_url = ""
            if self.project.record_import(new_rows, "No changes", deduplicate=silent):
                self._unsaved = True
            self._title()
            if silent:
                self.statusBar().showMessage(f"{name[0].upper() + name[1:]} has no changes to bring in.")
            else:
                QMessageBox.information(self, "No changes", f"{name[0].upper() + name[1:]} has no changes to bring in.")
            return []
        if silent:
            if any(c.conflict for c in found):
                restore_import_settings()
                return None
            accepted = list(found)
        else:
            dialog = ChangeDialog(found, name, self, current_rows=self.sheet_editor.rows(), incoming_rows=new_rows)
            if dialog.exec() != ChangeDialog.Accepted:
                restore_import_settings()
                return
            accepted = dialog.accepted_changes()
        self.project.source = str(Path(path).resolve())
        if not from_google:
            self.project.source_url = ""
        self.project.record_import(new_rows, "Updated" if accepted else "Reviewed; kept current credits",
                                   applied=len(accepted), skipped=len(found)-len(accepted))
        self.tabs.setCurrentWidget(self.sheet_editor)
        self.sheet_editor.apply_update(new_rows, accepted, notes)
        self._unsaved = True
        self._title()
        self._remember(self.project.source_url if from_google else path)
        skipped = len(found) - len(accepted)
        self.statusBar().showMessage(f"Updated from {name}: {changes.summary(accepted)}" +
                                     (f"; {skipped} not applied" if skipped else ""))
        return found

    # ---- how the sheet is read ----------------------------------------------

    def _prepare_import(self, path: str, force: bool = False) -> bool:
        """Settle which worksheet, columns and start row `path` is read with,
        asking only when it isn't obvious. False if the user cancelled."""
        p = self.project
        reason = ""
        try:
            if ingest.is_workbook(path):
                infos = ingest.sheets(path)
                names = [info.name for info in infos if info.filled]
                if p.sheet not in names:
                    if len(names) == 1:
                        p.sheet = names[0]          # the only tab with anything on it
                    elif len(names) > 1:
                        reason = (f"{Path(path).name} has {len(names)} worksheets. Which one holds the credits?"
                                  if not p.sheet else
                                  f"{Path(path).name} has no worksheet called {p.sheet!r}. Which one holds the credits?")
                        p.sheet = ingest.guess_sheet(infos) or ""
            else:
                p.sheet = ""
            if not reason and not p.columns:
                detected = ingest.detect_columns(ingest.read_grid(path, p.sheet or None))
                if detected != ingest.TEMPLATE_COLUMNS:
                    first, _, last = detected.partition(",")
                    reason = (f"The credits in {Path(path).name} seem to be in columns {first}–{detected[-1]}, "
                              f"not B–D as in the template. Check which columns hold what.")
        except Exception as e:
            QMessageBox.critical(self, "Can't read sheet", str(e))
            return False
        if not reason and not force:
            return True
        dialog = ImportDialog(path, p.sheet, p.columns, p.start_row, reason, self)
        if dialog.exec() != ImportDialog.Accepted:
            return False
        p.sheet, p.columns, p.start_row = dialog.sheet, dialog.columns, dialog.start_row
        return True

    def import_options(self):
        """Re-read the current source with different import settings."""
        source = self.project.source
        if not source or not Path(source).is_file():
            QMessageBox.information(self, "Import options", "Open a sheet first.")
            return
        before = (self.project.sheet, self.project.columns, self.project.start_row)
        if not self._prepare_import(source, force=True):
            return
        if before == (self.project.sheet, self.project.columns, self.project.start_row):
            return
        self._unsaved = True
        untouched = self.project.base_rows is not None and self.sheet_editor.rows() == [list(r) for r in self.project.base_rows]
        if untouched or self.project.rows is None:
            # Nothing edited since the sheet came in: just read it again.
            self.project.rows = None
            url = self.project.source_url
            self._pending_url = url
            self.load_sheet(source)
        else:
            self.update_from_sheet(source, from_google=bool(self.project.source_url))

    # ---- Google Sheets ------------------------------------------------------

    def _sheet_folder(self) -> str:
        """Where a downloaded Google Sheet is kept: with the project's assets when it has a
        home, otherwise in the app's data folder."""
        if self.project_path:
            stem = Path(self.project_path).name
            stem = stem[:-len(proj.PROJECT_SUFFIX)] if stem.endswith(proj.PROJECT_SUFFIX) else Path(stem).stem
            return str(Path(self.project_path).parent / (stem + proj.ASSETS_SUFFIX))
        return str(Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)) / "sheets")

    def open_google_sheet(self, url: str = ""):
        """Download a shared Google Sheet and open it like a file."""
        if not url:
            url, ok = QInputDialog.getText(
                self, "Open Google Sheet",
                "Paste the sheet's link. It must be shared as \"Anyone with the link\" (Viewer is enough).\n"
                "The whole workbook is downloaded, so every tab is available.")
            if not ok or not url.strip():
                return
        try:
            url = gsheets.canonical(url.strip())
        except gsheets.GoogleSheetError as e:
            QMessageBox.critical(self, "Not a Google Sheets link", str(e))
            return
        if url == self.project.source_url and self.crawl is not None:
            self._fetch_google(manual=True)
            return
        choice = self._update_or_replace("the Google Sheet")
        if not choice:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.statusBar().showMessage("Downloading from Google Sheets…")
        try:
            path = gsheets.fetch(url, self._sheet_folder())
        except gsheets.GoogleSheetError as e:
            QMessageBox.critical(self, "Can't download the sheet", str(e))
            return
        finally:
            QApplication.restoreOverrideCursor()
        if choice == "update":
            previous_url = self.project.source_url
            self.project.source_url = url
            if self.update_from_sheet(path, from_google=True) is None:
                self.project.source_url = previous_url
                self._title()
                return
        else:
            self._pending_url = url
            if not self.load_sheet(path):
                self._pending_url = ""
                return
        self._remember(url)
        self._title()
        self._sync_google()

    def _sync_google(self):
        """Menu state and the watch timer follow whether the source is a Google Sheet."""
        linked = bool(self.project.source_url)
        settings = self._settings()
        settings.setValue("google/watch", self.watch_action.isChecked())
        settings.setValue("google/auto_apply", self.auto_apply_action.isChecked())
        self.refresh_action.setEnabled(linked)
        self.watch_action.setEnabled(linked)
        self.auto_apply_action.setEnabled(linked and self.watch_action.isChecked())
        if linked and self.watch_action.isChecked():
            if not self._watch_timer.isActive():
                self._watch_timer.start()
        else:
            self._watch_timer.stop()
        if not linked:
            self.banner.setVisible(False)
            self._offered_path = None

    def _fetch_google(self, manual: bool):
        """Download the Google Sheet in the background and compare it with what was brought in."""
        if not self.project.source_url or (self._fetch_worker and self._fetch_worker.isRunning()):
            return
        if self._exporting() and not manual:
            return
        self._fetch_manual = manual
        if manual:
            self.statusBar().showMessage("Checking the Google Sheet…")
        worker = SheetFetchWorker(self.project, self._sheet_folder(), self)
        worker.changed.connect(lambda path: self._fetch_changed(path) if self._fetch_worker is worker else None)
        worker.unchanged.connect(lambda path: self._fetch_unchanged(path) if self._fetch_worker is worker else None)
        worker.failed.connect(lambda message: self._fetch_failed(message) if self._fetch_worker is worker else None)
        self._fetch_worker = worker
        worker.start()

    def _fetch_changed(self, path: str):
        if self._fetch_manual:
            self.update_from_sheet(path, from_google=True)
            return
        if self.auto_apply_action.isChecked() and not self._modal_open():
            if self.update_from_sheet(path, from_google=True, silent=True) is not None:
                self.banner.setVisible(False)
                return
            held = True        # some changes touch rows edited here: those need a look
        else:
            held = False
        if path == self._offered_path and self.banner.isVisible():
            return
        self._offered_path = path
        self.banner_label.setText("The Google Sheet has changed since its credits were brought in."
                                  + (" Some changes touch rows edited here, so nothing was applied." if held else ""))
        self.banner.setVisible(True)

    def _fetch_unchanged(self, path: str):
        if self._fetch_manual:
            self.statusBar().showMessage("The Google Sheet has no changes to bring in.")
        self._offered_path = None
        self.banner.setVisible(False)

    def _fetch_failed(self, message: str):
        if self._fetch_manual:
            QMessageBox.critical(self, "Can't check the Google Sheet", message)
        else:
            self.statusBar().showMessage(f"Google Sheet check failed: {message}")

    def _review_offered(self):
        self.banner.setVisible(False)
        path = self._offered_path
        self._offered_path = None
        if path and Path(path).is_file():
            self.update_from_sheet(path, from_google=True)
        else:
            self._fetch_google(manual=True)

    def _modal_open(self) -> bool:
        return QApplication.activeModalWidget() is not None

    def open_project(self, path: str = ""):
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Project", "", f"Crawl project (*{proj.PROJECT_SUFFIX})")
        if not path:
            return
        if not self._save_pending_credits():
            return
        try:
            p = proj.Project.load(path)
        except Exception as e:
            QMessageBox.critical(self, "Cannot open project", str(e))
            return
        self.project_path = path
        # Swap in place so the panels keep their references.
        self.project.__dict__.update(p.__dict__)
        self.timing_panel.load()
        self.look_panel.load()
        self.music_panel.load()
        self.output_panel.load()
        self._panel_last = self._panel_state()
        self.preview.view.select_logo("")
        self._sync_export_label()
        self._title()
        self.load_sheet(self.project.source, preserve_edits=True)
        self._unsaved = False
        self._remember(path)
        if self.project.load_notes:
            # Files had moved or are missing: say what was done about it.
            self._sticky_message = self.project.load_notes[0]
            self.statusBar().showMessage(self._sticky_message)
            QMessageBox.information(self, "Project files", "\n\n".join(self.project.load_notes))

    def save_project(self, as_new: bool = False):
        if as_new or not self.project_path:
            start = self.project_path or (str(Path(self.project.source).with_suffix("")) + proj.PROJECT_SUFFIX
                                          if self.project.source else "")
            path, _ = QFileDialog.getSaveFileName(self, "Save project", start,
                                                  f"Crawl project (*{proj.PROJECT_SUFFIX})")
            if not path:
                return
            if not path.endswith(proj.PROJECT_SUFFIX):
                path += proj.PROJECT_SUFFIX
            self.project_path = path
            self._remember(path)
        self.project.save(self.project_path)
        self._unsaved = False
        self._title()
        self.statusBar().showMessage(f"Saved {self.project_path}")

    def version_snapshots(self):
        if self._exporting():
            self.statusBar().showMessage("Wait for the export to finish before managing snapshots.")
            return
        # Move focus out of the sheet editor so any in-progress cell is committed.
        self.tabs.setFocus()
        if self.crawl is not None:
            self.project.rows = self.sheet_editor.rows()
        dialog = SnapshotDialog(self.project, self)
        dialog.changed.connect(self._mark_unsaved)
        dialog.restore_requested.connect(self.restore_snapshot)
        dialog.exec()

    def restore_snapshot(self, snapshot_id: str):
        if self._exporting():
            return
        self.preview.play.setChecked(False)
        self._debounce.stop()
        self._watch_timer.stop()
        # Finish old work without allowing its results to replace the restored version.
        for worker, signals in ((self._worker, ("done", "failed", "finished")),
                                (self._fetch_worker, ("changed", "unchanged", "failed"))):
            if worker is not None:
                for name in signals:
                    try:
                        getattr(worker, name).disconnect()
                    except RuntimeError:
                        pass
                worker.wait()
        self._worker = None
        self._fetch_worker = None
        self._dirty = False
        try:
            self.project.restore_snapshot(snapshot_id)
        except Exception as error:
            QMessageBox.critical(self, "Can't restore snapshot", str(error))
            self._sync_google()
            return
        self.project.load_notes = self.project._repair(
            str(Path(self.project_path).parent) if self.project_path else os.getcwd())
        for panel in (self.timing_panel, self.look_panel, self.music_panel, self.output_panel):
            panel.load()
        self._panel_last = self._panel_state()
        self.preview.view.select_logo("")
        self.preview.clear()
        self._pending_finding_row = None
        self._offered_path = None
        self.banner.setVisible(False)
        self.watch_action.setChecked(False)
        self._sync_google()
        self.load_sheet(self.project.source, preserve_edits=True)
        self._sync_export_label()
        self._unsaved = True
        self._title()
        self.statusBar().showMessage("Snapshot restored. Your previous work is saved in Version Snapshots.")
        if self.project.load_notes:
            QMessageBox.information(self, "Snapshot files", "\n\n".join(self.project.load_notes))

    def relink_files(self):
        dialog = RelinkDialog(self.project, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.replacements:
            return
        relink.apply(self.project, dialog.items, dialog.replacements)
        self.sheet_editor.commit_undo()
        self._unsaved = True
        self._title()
        self.output_panel.set_logo_slots(self.crawl)
        if "source" in dialog.replacements and self.project.rows is None:
            self.load_sheet(self.project.source, preserve_edits=True)
        else:
            self.schedule_rebuild()
        self.statusBar().showMessage(f"Relinked {len(dialog.replacements)} files. Save the project to keep these paths.")

    def collect_files(self):
        """Make the project folder self-contained: copy outside files in, then save."""
        if not self.project_path:
            self.save_project()
            if not self.project_path:
                return
        try:
            copied = self.project.collect(self.project_path)
            self.project.save(self.project_path)
        except OSError as e:
            QMessageBox.critical(self, "Can't collect files", str(e))
            return
        self._unsaved = False
        self.output_panel.set_logo_slots(self.crawl)
        self._title()
        folder = Path(self.project_path).parent
        if copied:
            QMessageBox.information(
                self, "Files collected",
                f"Copied {len(copied)} file{'s' if len(copied) != 1 else ''} beside the project:\n" +
                "\n".join(copied[:12]) + ("\n…" if len(copied) > 12 else "") +
                f"\n\nEverything the project needs is now in {folder}. Fonts are not included: "
                f"they must be installed on the other machine.")
        else:
            QMessageBox.information(self, "Nothing to collect",
                                    f"Every file the project uses is already inside {folder}.")
        self.statusBar().showMessage(f"Project folder is self-contained: {folder}")

    def save_look(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save look", "look.json", "Look (*.json)")
        if path:
            self.project.look.save(path)

    def load_look(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load look", "", "Look (*.json)")
        if path:
            from ..look import Look
            self.project.look.__dict__.update(Look.load(path).__dict__)
            self.look_panel.load()
            self.music_panel.load()
            self._panel_changed()

    # ---- rebuild -----------------------------------------------------------

    def _credits_changed(self):
        self._unsaved = True
        self.crawl = proj.crawl_from_rows(self.project, self.sheet_editor.rows())
        self.output_panel.set_logo_slots(self.crawl)
        self.schedule_rebuild()

    def schedule_rebuild(self):
        # Reparse so artwork assignments and list-column changes reach the build.
        if self.crawl is not None:
            self.crawl = proj.crawl_from_rows(self.project, self.sheet_editor.rows())
        self.build = None
        self.logo_workspace.build = None
        self.logo_workspace.view.set_busy(True)
        self._sync_ready()
        if self.crawl is not None:
            self.preview.view.set_busy(True)
        if self._worker and self._worker.isRunning():
            self._dirty = True
        self._debounce.start()

    def _rebuild(self):
        if self.crawl is None:
            return
        if not self.crawl.groups:
            # Nothing typed yet: an empty frame, not an error.
            self.preview.clear()
            self.preview.view.set_busy(False)
            self._sync_ready()
            self._set_chips(["", "", ""])
            self.sheet_editor.clear_errors("")
            self.statusBar().showMessage("No credits yet")
            return
        if self._worker and self._worker.isRunning():
            self._dirty = True
            return
        self._dirty = False
        self.statusBar().showMessage("Laying out…")
        self._worker = RebuildWorker(self.project, self.crawl, self, logo_layers=self.logo_workspace._layer_cache)
        worker = self._worker
        worker.done.connect(lambda build, image: self._built(build, image) if self._worker is worker else None)
        worker.failed.connect(lambda message: self._build_failed(message) if self._worker is worker else None)
        worker.finished.connect(lambda: self._maybe_rerun() if self._worker is worker else None)
        self._worker.start()

    def _maybe_rerun(self):
        if self._dirty:
            self._rebuild()

    def _built(self, build: proj.Build, preview_img):
        if self._dirty or self._debounce.isActive():
            return
        self.build = build
        s, t, look = build.solution, self.project.timing, self.project.look
        self.timing_panel.show_result(build)
        self.sheet_editor.set_findings(build.findings)
        # The strip's own width says what scale it was drawn at (the look may have moved on since).
        self.preview.load(preview_img, preview_img.width / look.width, look.width, look.height, s.speed, t.head_hold,
                          s.total_frames, t.fps, build.layout.panels, lambda f: frames_to_tc(f, t.fps))
        self.preview.view.centre_x = look.center_x
        self.preview.view.set_logos(build.layout.logos)
        from ..layout_checks import regions
        self.preview.view.hit_regions = regions(build.layout, look)
        self.logo_workspace.set_build(build)
        self.preview.slider.set_markers(self._section_markers(build))
        self.preview.view.set_busy(False)
        self._seek_finding()
        self._sync_ready()
        self._set_chips([s.timecode, f"{s.speed} px/frame", f"spacing ×{s.flex:.2f}"])
        sticky, self._sticky_message = self._sticky_message, ""
        self.statusBar().showMessage(sticky or f"{s.timecode} · {s.speed} px/frame · spacing ×{s.flex:.3f} · "
                                               f"{len(build.layout.panels)} panels")

    def _select_preview_credit(self, row, target):
        from ..lint import Finding
        editor = self.sheet_editor
        if not self.build or not 1 <= row <= editor.table.rowCount():
            return
        self.preview.play.setChecked(False)
        self.tabs.setCurrentWidget(editor)
        r,c = editor._finding_cell(Finding('selection','info',row,'',target))
        editor.table.setRowHidden(r, False)
        editor.table.clearSelection()
        editor._select_cell(r,c)
        editor.table.scrollToItem(editor.table.item(r,c), QAbstractItemView.PositionAtCenter)

    def _row_frame(self, build: proj.Build, y: int) -> int:
        """The frame at which content row `y` is centred in the frame."""
        return round(self.project.timing.head_hold + (y + self.project.look.height / 2) / build.solution.speed)

    def _section_markers(self, build: proj.Build):
        from ..model import Header
        positions = build.layout.row_positions
        return [(self._row_frame(build, positions[b.row]), b.text)
                for b in build.crawl.blocks()
                if isinstance(b, Header) and b.level == 1 and b.row in positions]

    def _build_failed(self, msg: str):
        first = msg.splitlines()[0]
        self.preview.view.set_busy(False)
        self.timing_panel.show_result(None, first)
        self.sheet_editor.clear_errors("Can't check — see status")
        self.statusBar().showMessage(first)

    # ---- logos -------------------------------------------------------------

    def _workspace_changed(self, *_):
        active = self.tabs.currentWidget() is self.logo_workspace
        self.preview_stack.setCurrentIndex(1 if active else 0)
        if active:
            self.preview.play.setChecked(False)
            self.logo_workspace.refresh()

    def _show_logo_location(self, row):
        self.tabs.setCurrentWidget(self.sheet_editor)
        self.sheet_editor.table.setCurrentCell(row - 1, 0)
        self.sheet_editor.table.scrollToItem(self.sheet_editor.table.item(row - 1, 0), QAbstractItemView.PositionAtCenter)
        self.seek_row(row)

    def _logo_artwork_changed(self):
        self._unsaved = True
        self.sheet_editor.commit_undo()
        self.schedule_rebuild()

    def _logo_selected(self, label: str):
        if label:
            self.preview.play.setChecked(False)
        self.preview.logo_bar.load(label, self.project.logo_settings.get(label, {}))
        self.preview.view.place_inspector()

    def _logo_moved(self, label: str, dx: int, dy: int):
        cfg = self.project.logo_settings.get(label, {})
        self.set_logo_setting(label, {"dx": int(cfg.get("dx", 0)) + dx, "dy": int(cfg.get("dy", 0)) + dy})

    def auto_logo_levels(self, label: str):
        """Black point from the artwork's own background, so its box disappears."""
        from .. import logos
        cfg = self.project.logo_settings.get(label, {})
        level = logos.auto_black(self.project.logos.get(label), bool(cfg.get("invert")))
        if level <= 0:
            self.statusBar().showMessage(
                f"{label}: no dark background to remove — it is transparent, already black, or too bright "
                f"(try Invert first for a light background).")
            return
        self.set_logo_setting(label, {"black": int(round(level * 100))})
        self.statusBar().showMessage(f"{label}: black point set to {int(round(level * 100))} %")

    def set_logo_settings_batch(self, changes):
        for label, values in changes.items():
            cfg = {**LOGO_DEFAULTS, **self.project.logo_settings.get(label, {}), **values}
            if cfg == LOGO_DEFAULTS:
                self.project.logo_settings.pop(label, None)
            else:
                self.project.logo_settings[label] = cfg
        self._unsaved = True
        self.sheet_editor.commit_undo()
        self.schedule_rebuild()

    def set_logo_setting(self, label: str, values: dict):
        """Merge values into the logo's saved settings; all-default entries are dropped."""
        cfg = {**LOGO_DEFAULTS, **self.project.logo_settings.get(label, {}), **values}
        if cfg == LOGO_DEFAULTS:
            self.project.logo_settings.pop(label, None)
        else:
            self.project.logo_settings[label] = cfg
        if self.preview.view.selected == label:
            self.preview.logo_bar.load(label, cfg)
        self._unsaved = True
        self.output_panel.sync_logo_invert(label, bool(cfg["invert"]))
        if self.logo_workspace.inspector.label == label:
            self.logo_workspace.sync_selection(label)
        self.sheet_editor.commit_undo()
        self.schedule_rebuild()

    # ---- preview navigation ------------------------------------------------

    def seek_row(self, row: int):
        """Pause and centre the preview on a sheet row (or the nearest credit)."""
        if not 1 <= row <= self.sheet_editor.table.rowCount():
            return
        self.preview.play.setChecked(False)
        self._pending_finding_row = row
        self._seek_finding()

    def jump_to_finding(self, row: int, message: str = ""):
        if not 1 <= row <= self.sheet_editor.table.rowCount():
            return
        self.tabs.setCurrentWidget(self.sheet_editor)
        self.seek_row(row)

    def _seek_finding(self):
        row = self._pending_finding_row
        if row is None or self.build is None:
            return
        positions = self.build.layout.row_positions
        target = row if row in positions else min(positions, key=lambda r: (abs(r - row), r < row), default=None)
        y = positions.get(target)
        if y is not None:
            frame = self._row_frame(self.build, y)
            self.preview.slider.setValue(max(0, min(frame, self.preview.slider.maximum())))
        self._pending_finding_row = None

    # ---- render ------------------------------------------------------------

    def render(self):
        if not self.build:
            QMessageBox.information(self, "Not ready to export",
                                    "Wait for the preview to finish updating, or check the status bar for errors."
                                    if self.crawl is not None else "Open a sheet first.")
            return
        if self._render_worker and self._render_worker.isRunning():
            return
        if self.build.errors:
            r = QMessageBox.question(self, "Errors",
                                     f"The sheet has {self.build.errors} errors. Render anyway?")
            if r != QMessageBox.Yes:
                self.tabs.setCurrentWidget(self.sheet_editor)
                index = next((i for i, f in enumerate(self.sheet_editor.findings) if f.severity == "error"), 0)
                self.sheet_editor.focus_error(index)
                return
        if not self.project.output_dir:
            self.output_panel._browse()
            if not self.project.output_dir:
                return
        for bar in (self.output_panel.progress, self.header_progress):
            bar.setRange(0, self.build.solution.total_frames)
            bar.setValue(0)
            bar.setFormat("preparing…")
        self.output_panel.result.setText("")
        self._render_worker = RenderWorker(self.project, self.build, self)
        self._render_worker.progress.connect(self._render_progress)
        self._render_worker.done.connect(self._rendered)
        self._render_worker.failed.connect(self._render_failed)
        self._render_worker.cancelled.connect(self._render_cancelled)
        self._render_worker.start()
        self._set_exporting(True)          # after start(): the button now means Cancel

    def check_movie(self):
        """Measure the motion in an exported file: is every frame the same step?"""
        from ..verify import verify
        start = str(proj.output_dir(self.project)) if self.project.source or self.project.output_dir else ""
        path, _ = QFileDialog.getOpenFileName(self, "Rendered movie", start, "Movies (*.mov *.mp4 *.mxf);;All files (*)")
        if not path:
            return
        self.statusBar().showMessage(f"Measuring {Path(path).name}…")
        self.setCursor(Qt.WaitCursor)
        try:
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            text = verify(path).summary()
        except Exception as e:
            text = str(e)
        finally:
            self.unsetCursor()
            self.statusBar().clearMessage()
        box = QMessageBox(self)
        box.setWindowTitle("Motion check")
        box.setText(text.split("\n", 1)[0])
        box.setInformativeText(text.split("\n", 1)[1] if "\n" in text else "")
        box.exec()

    def _set_exporting(self, on: bool):
        self.output_panel.progress.setVisible(on)
        self.header_progress.setVisible(on)
        if on:
            self.export_btn.setText("Cancel export")
            self.export_btn.setToolTip("Stop the export and discard the partial file  (Ctrl+.)")
            self.export_btn.setEnabled(True)
        else:
            self.export_btn.setToolTip("Render the crawl to a movie  (Ctrl+R)\nCodec and folder are on the Export tab.")
            self._sync_export_label()
            self.export_btn.setEnabled(self.build is not None)

    def cancel_export(self):
        if self._exporting():
            self._render_worker.cancel()
            self.export_btn.setText("Cancelling…")
            self.export_btn.setEnabled(False)
            self.statusBar().showMessage("Cancelling export…")

    def _finish_export(self):
        """The worker's signal arrives just before its thread ends; wait for
        that so the button goes back to Export rather than staying on Cancel."""
        if self._render_worker:
            self._render_worker.wait()
        self._set_exporting(False)

    def _render_cancelled(self):
        self._finish_export()
        self.output_panel.result.setText("Export cancelled. The partial file was removed.")
        self.statusBar().showMessage("Export cancelled")

    def _render_progress(self, stage: str, i: int, n: int):
        label = f"encoding {i}/{n} frames" if stage == "encode" else \
            f"{'drawing' if stage == 'draw' else 'panels'} {i}/{n}"
        for bar in (self.output_panel.progress, self.header_progress):
            bar.setRange(0, n)
            bar.setValue(i)
            bar.setFormat(label)

    def _rendered(self, paths):
        self._finish_export()
        names = "<br>".join(Path(p).name for p in paths)
        self.output_panel.result.setText(f"Wrote to {Path(paths[0]).parent}:<br>{names}")
        self.statusBar().showMessage(f"Exported {Path(paths[0]).name} to {Path(paths[0]).parent}")

    def _render_failed(self, msg: str):
        self._finish_export()
        first = msg.splitlines()[0]
        self.output_panel.result.setText(f"<span style='color:{theme.ERROR}'>{first}</span>")
        self.statusBar().showMessage(f"Export failed: {first}")

    def closeEvent(self, event):
        if self._exporting():
            if QMessageBox.question(self, "Export running", "An export is running. Cancel it and close?") \
                    != QMessageBox.Yes:
                event.ignore()
                return
            self._render_worker.cancel()
            self._render_worker.wait()
        if not self._save_pending_credits():
            event.ignore()
            return
        if self._update_check_worker:
            self._update_check_worker.requestInterruption()
            self._update_check_worker.wait()
        self._debounce.stop()
        self._watch_timer.stop()
        self.preview.play.setChecked(False)
        if self._worker:
            self._worker.wait()
        if self._fetch_worker:
            self._fetch_worker.wait()
        event.accept()

    def _save_pending_credits(self):
        if not self._unsaved:
            return True
        choice = QMessageBox.question(self, "Unsaved changes", "Save your changes to the project?",
                                      QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if choice == QMessageBox.Cancel:
            return False
        if choice == QMessageBox.Save:
            self.save_project()
            return not self._unsaved
        return True
