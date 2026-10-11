"""Reusable widgets: font picker, text-style editor, crawl preview."""

from __future__ import annotations

import os
import time
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image
from PySide6.QtCore import QPointF, QRect, QRectF, QSize, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap, QOpenGLContext, QOffscreenSurface
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
                               QGroupBox, QHBoxLayout, QLabel, QMenu, QPushButton, QSlider, QSpinBox,
                               QToolButton, QToolTip, QVBoxLayout, QWidget)

from .. import fonts
from . import theme
from ..look import TextStyle


# --------------------------------------------------------------------------- #
# Font picker
# --------------------------------------------------------------------------- #

class FontPicker(QWidget):
    """Family + style combos backed by the installed-font scan, or a file."""

    changed = Signal(str)   # "Family:Style" or a path

    _families: Optional[Dict[str, List[fonts.FontFace]]] = None

    def __init__(self, parent=None):
        super().__init__(parent)
        if FontPicker._families is None:
            FontPicker._families = fonts.families()
        self.family = QComboBox()
        self.family.setEditable(True)
        self.family.setInsertPolicy(QComboBox.NoInsert)
        self.family.addItems(sorted(self._families.keys(), key=str.lower))
        self.style = QComboBox()
        # Otherwise each combo is as wide as its longest font name and the row overflows.
        for combo, chars in ((self.family, 12), (self.style, 7)):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(chars)
        self.browse = QToolButton()
        self.browse.setText("…")
        self.browse.setToolTip("Choose a font file")
        self._path: Optional[str] = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.family, 3)
        lay.addWidget(self.style, 2)
        lay.addWidget(self.browse)

        self.family.currentTextChanged.connect(self._family_changed)
        self.style.currentTextChanged.connect(lambda _: self._emit())
        self.browse.clicked.connect(self._browse)

    def _family_changed(self, fam: str):
        self.style.blockSignals(True)
        self.style.clear()
        faces = self._families.get(fam) or []
        self.style.addItems([f.style for f in faces])
        # Prefer a book weight when switching family.
        for pref in ("Regular", "Medium", "Book", "Roman"):
            i = self.style.findText(pref)
            if i >= 0:
                self.style.setCurrentIndex(i)
                break
        self.style.blockSignals(False)
        self._path = None
        self._emit()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Font file", "", "Fonts (*.ttf *.otf *.ttc)")
        if path:
            self.set_value(path)
            self._emit()

    def _emit(self):
        self.changed.emit(self.value())

    def value(self) -> str:
        if self._path:
            return self._path
        return f"{self.family.currentText()}:{self.style.currentText()}"

    def set_value(self, spec: str):
        self.blockSignals(True)
        self.family.blockSignals(True)
        self.style.blockSignals(True)
        if os.path.isfile(spec):
            self._path = spec
            self.family.setEditText(os.path.basename(spec))
            self.style.clear()
        else:
            self._path = None
            fam, _, sty = spec.partition(":")
            face = fonts.resolve(spec)
            if face:
                fam, sty = face.family, face.style
            i = self.family.findText(fam, Qt.MatchFixedString)
            if i >= 0:
                self.family.setCurrentIndex(i)
            else:
                self.family.setEditText(fam)
            self.style.clear()
            self.style.addItems([f.style for f in self._families.get(self.family.currentText(), [])])
            j = self.style.findText(sty, Qt.MatchFixedString)
            self.style.setCurrentIndex(j if j >= 0 else 0)
        self.style.blockSignals(False)
        self.family.blockSignals(False)
        self.blockSignals(False)


# --------------------------------------------------------------------------- #
# Text style editor
# --------------------------------------------------------------------------- #

class StyleEditor(QGroupBox):
    changed = Signal()

    def __init__(self, title: str, style: TextStyle, parent=None):
        super().__init__(title, parent)
        self.style = style
        self.font = FontPicker()
        self.size = _spin(8, 400, " px")
        self.leading = _spin(0, 600, " px")
        self.tracking = _dspin(-20, 60, 0.5, " px")
        self.upper = QCheckBox("Uppercase")
        self.italic = QCheckBox("Italic")

        # One line of metrics and flags under the font, sized to fit a narrow panel.
        for widget, width in ((self.size, 80), (self.leading, 80), (self.tracking, 94)):
            widget.setFixedWidth(width)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 6, 0, 2)
        column.setSpacing(6)
        column.addWidget(self.font)
        row = QHBoxLayout()
        row.setSpacing(6)
        for caption, widget in (("Size", self.size), ("Leading", self.leading), ("Track", self.tracking)):
            label = QLabel(caption)
            label.setProperty("role", "caption")
            row.addWidget(label)
            row.addWidget(widget)
            row.addSpacing(4)
        row.addStretch(1)
        column.addLayout(row)
        flags = QHBoxLayout()
        flags.setSpacing(14)
        flags.addWidget(self.upper)
        flags.addWidget(self.italic)
        flags.addStretch(1)
        column.addLayout(flags)

        self.load(style)
        self.font.changed.connect(self._apply)
        self.size.valueChanged.connect(self._apply)
        self.leading.valueChanged.connect(self._apply)
        self.tracking.valueChanged.connect(self._apply)
        self.upper.toggled.connect(self._apply)
        self.italic.toggled.connect(self._apply)

    def load(self, style: TextStyle):
        self.style = style
        for w in (self.size, self.leading, self.tracking, self.upper, self.italic):
            w.blockSignals(True)
        self.font.set_value(style.font)
        self.size.setValue(style.size)
        self.leading.setValue(style.leading)
        self.tracking.setValue(style.tracking)
        self.upper.setChecked(style.uppercase)
        self.italic.setChecked(style.italic)
        for w in (self.size, self.leading, self.tracking, self.upper, self.italic):
            w.blockSignals(False)

    def _apply(self, *_):
        self.style.font = self.font.value()
        self.style.size = self.size.value()
        self.style.leading = self.leading.value()
        self.style.tracking = self.tracking.value()
        self.style.uppercase = self.upper.isChecked()
        self.style.italic = self.italic.isChecked()
        self.changed.emit()


def _spin(lo: int, hi: int, suffix: str = "") -> QSpinBox:
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    return s


def _dspin(lo: float, hi: float, step: float, suffix: str = "") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(2)
    s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    return s


# --------------------------------------------------------------------------- #
# Preview
# --------------------------------------------------------------------------- #

def pil_to_qimage(img: Image.Image) -> QImage:
    if img.mode == "L":
        data = img.tobytes()
        return QImage(data, img.width, img.height, img.width, QImage.Format_Grayscale8).copy()
    img = img.convert("RGB")
    data = img.tobytes()
    return QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888).copy()


class _FrameViewMixin:
    """Shows the delivery frame at a given frame number, scaled to fit.

    Logos are live objects: click one to select it, drag to move it. The view
    only reports what happened (logo_selected / logo_moved, in delivery px);
    the owner stores the offset and rebuilds.
    """

    credit_selected = Signal(int, str)
    logo_selected = Signal(str)          # label, or "" when the selection is cleared
    logo_moved = Signal(str, int, int)   # label, dx, dy to add to its offset
    nudge = Signal(int)                  # arrow keys: frames to step
    section = Signal(int)                # up/down: previous (-1) / next (+1) section

    MARGIN = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 180)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)
        self.hit_regions = []
        self.logos: list = []            # layout.LogoItem, in content px
        self.selected = ""
        self.inspector: Optional[QWidget] = None   # floats beside the selected logo
        self._press: Optional[QPointF] = None
        self._drag = (0, 0)              # delivery px, shown until the rebuild lands
        self._guides: list = []          # ("v", x) / ("h", content y) snap lines, delivery px
        self.strip: Optional[QImage] = None   # whole crawl at preview scale
        self.scale = 0.25
        self.frame = 0
        self.speed = 10
        self.head = 0
        self.width_px = 3840
        self.height_px = 2160
        self.panels: List[Tuple[int, int]] = []
        self.show_cuts = False
        self.show_safe = False           # 90% action-safe box
        self.show_centre = False         # the column centre line
        self.centre_x = 1920
        self.busy = False                # a rebuild is pending: what's shown is stale

    def set_strip(self, strip: Optional[QImage], scale: float, width_px: int, height_px: int,
                  speed: int, head: int, panels: List[Tuple[int, int]]):
        self.strip, self.scale = strip, scale
        self.width_px, self.height_px = width_px, height_px
        self.speed, self.head, self.panels = speed, head, panels
        self.update()

    def set_frame(self, f: int):
        self.frame = f
        self.place_inspector()
        self.update()

    def set_busy(self, on: bool):
        if on != self.busy:
            self.busy = on
            self.update()

    def set_logos(self, logos):
        """New layout: positions are authoritative again, so drop any drag ghost."""
        self.logos = list(logos)
        self._drag = (0, 0)
        if self.selected and not any(lg.label == self.selected for lg in self.logos):
            self.selected = ""
            self.logo_selected.emit("")
        self.place_inspector()
        self.update()

    def select_logo(self, label: str):
        if label != self.selected:
            self.selected = label
            self._drag = (0, 0)
            self.logo_selected.emit(label)
            self.place_inspector()
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(960, 540)

    # ---- geometry ----------------------------------------------------------

    def _geom(self):
        """(ox, oy, w, h, k, content_top): frame rect on screen, display px per
        delivery px, and the content's top in delivery px from the frame top."""
        aspect = self.width_px / self.height_px
        m = self.MARGIN
        w = max(1, self.width() - 2 * m)
        h = int(w / aspect)
        if h > self.height() - 2 * m:
            h = max(1, self.height() - 2 * m)
            w = int(h * aspect)
        ox, oy = (self.width() - w) // 2, (self.height() - h) // 2
        k = h / self.height_px
        content_top = self.height_px - (self.frame - self.head) * self.speed
        return ox, oy, w, h, k, content_top

    def logo_rect(self, lg, offset=(0, 0)) -> QRectF:
        ox, oy, _, _, k, content_top = self._geom()
        return QRectF(ox + (lg.x + offset[0]) * k, oy + (content_top + lg.y + offset[1]) * k, lg.w * k, lg.h * k)

    def logo_at(self, pos):
        for lg in reversed(self.logos):
            if self.logo_rect(lg).contains(pos):
                return lg
        return None

    def _selected_item(self):
        return next((lg for lg in self.logos if lg.label == self.selected), None)

    def place_inspector(self):
        """Float the inspector just under (or over) the selected logo, inside the view."""
        ins = self.inspector
        if ins is None:
            return
        sel = self._selected_item()
        ox, oy, w, h, _, _ = self._geom()
        if sel is None or self._press is not None:
            ins.hide()
            return
        r = self.logo_rect(sel, self._drag)
        if r.bottom() < oy or r.top() > oy + h:
            ins.hide()
            return
        ins.adjustSize()
        iw, ih = ins.width(), ins.height()
        x = min(max(8, r.center().x() - iw / 2), max(8, self.width() - iw - 8))
        y = r.bottom() + 10
        if y + ih > self.height() - 8:
            y = r.top() - ih - 10
        ins.move(int(x), int(max(8, y)))
        ins.show()
        ins.raise_()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.place_inspector()

    # ---- keyboard ----------------------------------------------------------

    def keyPressEvent(self, ev):
        big = 10 if ev.modifiers() & Qt.ShiftModifier else 1
        key = ev.key()
        if key == Qt.Key_Left:
            self.nudge.emit(-big)
        elif key == Qt.Key_Right:
            self.nudge.emit(big)
        elif key == Qt.Key_Up:
            self.section.emit(-1)
        elif key == Qt.Key_Down:
            self.section.emit(1)
        elif key == Qt.Key_Escape and self.selected:
            self.select_logo("")
        else:
            super().keyPressEvent(ev)

    # ---- mouse -------------------------------------------------------------

    def credit_at(self, pos):
        if self.busy or self.strip is None:
            return None
        ox,oy,w,h,k,top = self._geom()
        if not (ox <= pos.x() <= ox+w and oy <= pos.y() <= oy+h):
            return None
        x,y = (pos.x()-ox)/k, (pos.y()-oy)/k-top
        return next((r for r in reversed(self.hit_regions) if r.contains(x,y)), None)

    def mousePressEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        self.setFocus()
        region = self.credit_at(ev.position())
        if region and region.row > 0:
            self.credit_selected.emit(region.row, region.target)
        lg = self.logo_at(ev.position())
        self._drag = (0, 0)
        self.select_logo(lg.label if lg else "")
        self._press = ev.position() if lg else None

    def mouseMoveEvent(self, ev):
        if self._press is None:
            self.setCursor(Qt.OpenHandCursor if self.logo_at(ev.position()) else
                           Qt.PointingHandCursor if self.credit_at(ev.position()) else Qt.ArrowCursor)
            return
        k = self._geom()[4]
        d = ev.position() - self._press
        dx, dy = int(round(d.x() / k)), int(round(d.y() / k))
        if ev.modifiers() & Qt.ShiftModifier:   # constrain to one axis
            dx, dy = (dx, 0) if abs(dx) >= abs(dy) else (0, dy)
        self._guides = []
        if not ev.modifiers() & Qt.AltModifier:  # Alt: place freely
            dx, dy = self._snap(dx, dy, SNAP_PX / k)
        self._drag = (dx, dy)
        self.setCursor(Qt.ClosedHandCursor)
        self.place_inspector()          # hidden while dragging
        self.update()

    def _snap(self, dx: int, dy: int, reach: float):
        """Pull the dragged logo onto nearby alignments and record guide lines.

        Per axis, the closest of: its automatic position, the frame's centre
        line, and the centres/edges of the other logos.
        """
        sel = self._selected_item()
        if sel is None:
            return dx, dy
        others = [lg for lg in self.logos if lg is not sel]
        cx, cy = sel.x + sel.w / 2, sel.y + sel.h / 2

        # (offset that achieves the alignment, guide position)
        xs = [(-sel.dx, cx - sel.dx), (self.width_px / 2 - cx, self.width_px / 2)]
        ys = [(-sel.dy, cy - sel.dy)]
        for o in others:
            xs += [(o.x + o.w / 2 - cx, o.x + o.w / 2), (o.x - sel.x, o.x), (o.x + o.w - sel.x - sel.w, o.x + o.w)]
            ys += [(o.y + o.h / 2 - cy, o.y + o.h / 2), (o.y - sel.y, o.y), (o.y + o.h - sel.y - sel.h, o.y + o.h)]

        def nearest(value, options):
            target, guide = min(options, key=lambda t: abs(t[0] - value))
            return (int(round(target)), guide) if abs(target - value) <= reach else (value, None)

        dx, gx = nearest(dx, xs)
        dy, gy = nearest(dy, ys)
        if gx is not None:
            self._guides.append(("v", gx))
        if gy is not None:
            self._guides.append(("h", gy))
        return dx, dy

    def mouseReleaseEvent(self, ev):
        if self._press is None:
            return
        self._press = None
        self._guides = []
        self.setCursor(Qt.OpenHandCursor)
        self.place_inspector()
        self.update()
        if self._drag != (0, 0) and self.selected:
            # Keep showing the ghost until set_logos() delivers the new layout.
            self.logo_moved.emit(self.selected, *self._drag)

    # ---- paint -------------------------------------------------------------

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG))
        ox, oy, w, h, k, content_top = self._geom()
        target = QRect(ox, oy, w, h)
        p.fillRect(target, Qt.black)
        if self.strip is None:
            self._paint_empty(p, target)
        else:
            # Keep the translation fractional at display scale. Rounding here
            # alternated 2/3-pixel steps for a 10px/frame quarter-size preview.
            p.save()
            p.setClipRect(target)
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            dst = QRectF(ox, oy + content_top * k, w,
                         self.strip.height() / self.scale * k)
            self._draw_strip(p, dst, target)
            sel = self._selected_item()
            if sel is not None:
                here = self.logo_rect(sel)
                moved = self.logo_rect(sel, self._drag)
                if self._drag != (0, 0):
                    # Lift the logo out of the strip and show it where it is being dropped.
                    s = self.scale
                    p.fillRect(here, Qt.black)
                    p.drawImage(moved, self.strip, QRectF(sel.x * s, sel.y * s, sel.w * s, sel.h * s))
                p.setRenderHint(QPainter.Antialiasing, False)
                p.setPen(QPen(QColor(theme.ACCENT), 1.5))
                p.setBrush(Qt.NoBrush)
                p.drawRect(moved.adjusted(-2, -2, 2, 2))
                p.setPen(QPen(theme.color(theme.ACCENT, 170), 1, Qt.DashLine))
                for axis, at in self._guides:
                    if axis == "v":
                        p.drawLine(QPointF(ox + at * k, oy), QPointF(ox + at * k, oy + h))
                    else:
                        yy = oy + (content_top + at) * k
                        p.drawLine(QPointF(ox, yy), QPointF(ox + w, yy))
            overlay = QPen(theme.color("#ffffff", 46), 1)
            if self.show_safe:
                p.setPen(overlay)
                p.setBrush(Qt.NoBrush)
                p.drawRect(QRectF(ox + w * 0.05, oy + h * 0.05, w * 0.9, h * 0.9))
            if self.show_centre:
                p.setPen(overlay)
                x = ox + self.centre_x * k
                p.drawLine(QPointF(x, oy), QPointF(x, oy + h))
            p.restore()
            if self.show_cuts:
                p.setPen(QPen(theme.color(theme.WARNING, 170), 1, Qt.DashLine))
                for top, _ in self.panels[1:]:
                    y = content_top + top
                    if 0 <= y < self.height_px:
                        yy = oy + int(y * h / self.height_px)
                        p.drawLine(ox, yy, ox + w, yy)
        p.setPen(QPen(QColor(theme.BORDER)))
        p.setBrush(Qt.NoBrush)
        p.drawRect(target.adjusted(0, 0, -1, -1))
        if self.hasFocus():
            p.setPen(QPen(theme.color(theme.ACCENT, 120)))
            p.drawRect(target.adjusted(0, 0, -1, -1))
        if self.busy and self.strip is not None:
            self._paint_pill(p, target, "Updating…")
        p.end()

    def _draw_strip(self, painter, destination, viewport):
        painter.drawImage(destination, self.strip, QRectF(self.strip.rect()))

    def _paint_empty(self, p: QPainter, target: QRect):
        p.setPen(QColor(theme.TEXT))
        f = QFont(p.font())
        f.setPixelSize(17)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        title = "Updating…" if self.busy else "Drop a credits sheet here"
        p.drawText(target.adjusted(0, -14, 0, -14), Qt.AlignCenter, title)
        if not self.busy:
            f.setPixelSize(13)
            f.setWeight(QFont.Normal)
            p.setFont(f)
            p.setPen(QColor(theme.MUTED))
            p.drawText(target.adjusted(0, 16, 0, 16), Qt.AlignCenter,
                       ".csv or .xlsx — or a .crawl.json project")

    def _paint_pill(self, p: QPainter, target: QRect, label: str):
        p.setRenderHint(QPainter.Antialiasing, True)
        f = QFont(p.font())
        f.setPixelSize(11)
        p.setFont(f)
        tw = p.fontMetrics().horizontalAdvance(label)
        r = QRectF(target.right() - tw - 30, target.top() + 10, tw + 20, 22)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color(theme.RAISED, 230))
        p.drawRoundedRect(r, 11, 11)
        p.setPen(QColor(theme.MUTED))
        p.drawText(r, Qt.AlignCenter, label)


LOGO_DEFAULTS = {"invert": False, "scale": 1.0, "dx": 0, "dy": 0, "black": 0, "white": 100, "mode": "original"}
SNAP_PX = 7   # display px within which a dragged logo snaps to an alignment


class FrameView(_FrameViewMixin, QWidget):
    pass


class LogoBar(QFrame):
    """Exact values for the logo selected in the preview. Floats beside it."""

    changed = Signal(str, dict)   # label, {invert, scale, dx, dy, black, white}
    auto_requested = Signal(str)  # label: pick the black point from the artwork's background

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("inspector")
        self.label = ""
        self.name = QLabel()
        self.name.setProperty("role", "caption")
        self.dx = _spin(-8192, 8192, " px")
        self.dy = _spin(-8192, 8192, " px")
        self.scale = _spin(5, 1000, " %")
        for widget in (self.dx, self.dy, self.scale):
            widget.setFixedWidth(84)
        self.greyscale = QCheckBox("Greyscale")
        self.greyscale.setToolTip("Remove color from this logo in the preview and final export, preserving transparency.")
        self.invert = QCheckBox("Invert")
        self.invert.setToolTip("Flip the artwork's colours — for a dark logo on the black crawl.")
        self.reset = QToolButton()
        self.reset.setText("Reset")
        self.reset.setProperty("flat", True)
        self.reset.setToolTip("Back to the automatic position, size and colours.")
        # Levels, applied after Invert: anything darker than Black becomes black
        # (so a not-quite-black background disappears), anything brighter than
        # White becomes full brightness.
        self.black = _spin(0, 95, " %")
        self.white = _spin(5, 100, " %")
        self.black.setToolTip("Black point. Raise it until a dark background box disappears.")
        self.white.setToolTip("White point. Lower it to brighten a dull or grey logo.")
        self.auto = QToolButton()
        self.auto.setText("Auto")
        self.auto.setProperty("flat", True)
        self.auto.setToolTip("Set the black point from the artwork's background (its corners).")
        for widget in (self.black, self.white):
            widget.setFixedWidth(76)

        def captioned(row, text_, widget):
            caption = QLabel(text_)
            caption.setProperty("role", "caption")
            row.addWidget(caption)
            row.addWidget(widget)

        place = QHBoxLayout()
        place.setSpacing(6)
        place.addWidget(self.name)
        place.addStretch(1)
        for text_, widget in (("X", self.dx), ("Y", self.dy), ("Size", self.scale)):
            captioned(place, text_, widget)
        tone = QHBoxLayout()
        tone.setSpacing(6)
        tone.addWidget(self.invert)
        tone.addWidget(self.greyscale)
        tone.addSpacing(6)
        captioned(tone, "Black", self.black)
        captioned(tone, "White", self.white)
        tone.addWidget(self.auto)
        tone.addStretch(1)
        tone.addWidget(self.reset)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 8, 6)
        lay.setSpacing(4)
        lay.addLayout(place)
        lay.addLayout(tone)
        for widget in (self.dx, self.dy, self.scale, self.black, self.white):
            widget.valueChanged.connect(self._emit)
        self.invert.toggled.connect(self._emit)
        self.greyscale.toggled.connect(self._emit)
        self.reset.clicked.connect(lambda: (self.load(self.label, {}), self._emit()))
        self.auto.clicked.connect(lambda: self.label and self.auto_requested.emit(self.label))
        self._controls = (self.dx, self.dy, self.scale, self.invert, self.greyscale, self.black, self.white, self.auto, self.reset)
        self.load("", {})
        self.hide()

    def load(self, label: str, cfg: dict):
        self.label = label
        cfg = {**LOGO_DEFAULTS, **(cfg or {})}
        widgets = (self.dx, self.dy, self.scale, self.invert, self.greyscale, self.black, self.white)
        for widget in widgets:
            widget.blockSignals(True)
        self.name.setText(label)
        self.black.setValue(int(cfg["black"]))
        self.white.setValue(int(cfg["white"]))
        self.dx.setValue(int(cfg["dx"]))
        self.dy.setValue(int(cfg["dy"]))
        self.scale.setValue(int(round(float(cfg["scale"]) * 100)))
        self.invert.setChecked(bool(cfg["invert"]))
        self.greyscale.setChecked(cfg["mode"] == "grayscale")
        for widget in widgets:
            widget.blockSignals(False)
        for widget in self._controls:
            widget.setEnabled(bool(label))

    def values(self) -> dict:
        # The white point stays above the black point, or the logo would vanish.
        black = self.black.value()
        return {"invert": self.invert.isChecked(), "mode": "grayscale" if self.greyscale.isChecked() else "original",
                "scale": self.scale.value() / 100,
                "dx": self.dx.value(), "dy": self.dy.value(),
                "black": black, "white": max(self.white.value(), black + 2)}

    def _emit(self, *_):
        if self.label:
            self.changed.emit(self.label, self.values())


class Timeline(QSlider):
    """The scrub bar: a QSlider that draws itself, with a tick per section.

    Click anywhere to jump there (a click near a tick lands on it); hover a
    tick to see its section name.
    """

    PAD = 8
    SNAP = 6      # px within which a click lands on a marker

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.markers: List[Tuple[int, str]] = []   # (frame, section name), ascending
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedHeight(28)
        self.setCursor(Qt.PointingHandCursor)

    def set_markers(self, markers):
        self.markers = sorted((int(f), str(t)) for f, t in markers)
        self.update()

    def _x(self, value: int) -> float:
        span = max(1, self.maximum() - self.minimum())
        return self.PAD + (self.width() - 2 * self.PAD) * (value - self.minimum()) / span

    def _value(self, x: float) -> int:
        span = self.maximum() - self.minimum()
        frac = (x - self.PAD) / max(1, self.width() - 2 * self.PAD)
        return int(round(self.minimum() + span * min(1.0, max(0.0, frac))))

    def _marker_near(self, x: float):
        best = min(self.markers, key=lambda m: abs(self._x(m[0]) - x), default=None)
        return best if best and abs(self._x(best[0]) - x) <= self.SNAP else None

    def jump(self, direction: int):
        """Go to the previous (-1) or next (+1) section marker."""
        v = self.value()
        if direction > 0:
            target = next((f for f, _ in self.markers if f > v), None)
        else:
            target = next((f for f, _ in reversed(self.markers) if f < v), None)
        if target is not None:
            self.setValue(target)

    def mousePressEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        marker = self._marker_near(ev.position().x())
        self.setSliderDown(True)
        self.setValue(marker[0] if marker else self._value(ev.position().x()))

    def mouseMoveEvent(self, ev):
        if self.isSliderDown():
            self.setValue(self._value(ev.position().x()))
            return
        marker = self._marker_near(ev.position().x())
        if marker:
            QToolTip.showText(ev.globalPosition().toPoint(), marker[1], self)
        else:
            QToolTip.hideText()

    def mouseReleaseEvent(self, ev):
        self.setSliderDown(False)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        mid = self.height() / 2 + 3
        left, right = self.PAD, self.width() - self.PAD
        x = self._x(self.value())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.BORDER))
        p.drawRoundedRect(QRectF(left, mid - 2, right - left, 4), 2, 2)
        p.setBrush(QColor(theme.ACCENT if self.isEnabled() else theme.FAINT))
        p.drawRoundedRect(QRectF(left, mid - 2, max(0.0, x - left), 4), 2, 2)
        p.setPen(QPen(QColor(theme.MUTED), 1.2))
        for frame, _ in self.markers:
            mx = self._x(frame)
            p.drawLine(QPointF(mx, mid - 11), QPointF(mx, mid - 5))
        p.setPen(QPen(QColor(theme.BG), 2))
        p.setBrush(QColor(theme.TEXT))
        p.drawEllipse(QPointF(x, mid), 6, 6)
        p.end()


def _transport_icon(kind: str) -> QIcon:
    pm = QPixmap(32, 32)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(theme.TEXT))
    if kind == "play":
        path = QPainterPath()
        path.moveTo(5, 3)
        path.lineTo(13.5, 8)
        path.lineTo(5, 13)
        path.closeSubpath()
        p.drawPath(path)
    else:
        p.drawRoundedRect(QRectF(4, 3, 3, 10), 1, 1)
        p.drawRoundedRect(QRectF(9, 3, 3, 10), 1, 1)
    p.end()
    return QIcon(pm)


class GpuFrameView(_FrameViewMixin, QOpenGLWidget):
    """Same preview and interactions, with cached tiles drawn through OpenGL.

    Tiling avoids GPU texture-height limits on very long credits. Only visible
    tiles are drawn; the CPU-rendered strip remains the source of truth.
    """
    TILE_HEIGHT = 1024

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tiles = []

    def set_strip(self, strip, *args):
        self._tiles = []
        if strip is not None:
            for top in range(0, strip.height(), self.TILE_HEIGHT):
                # One overlapping pixel at each edge keeps filtered tile joins seamless.
                start = max(0, top - 1)
                end = min(strip.height(), top + self.TILE_HEIGHT + 1)
                self._tiles.append((top, QPixmap.fromImage(strip.copy(0, start, strip.width(), end-start)), start))
        super().set_strip(strip, *args)

    def paintEvent(self, event):
        QOpenGLWidget.paintEvent(self, event)

    def paintGL(self):
        _FrameViewMixin.paintEvent(self, None)

    def _draw_strip(self, painter, destination, viewport):
        ratio = destination.height() / self.strip.height()
        for top, pixmap, start in self._tiles:
            height = min(self.TILE_HEIGHT, self.strip.height() - top)
            tile = QRectF(destination.x(), destination.y() + top * ratio,
                          destination.width(), height * ratio)
            if not tile.intersects(QRectF(viewport)):
                continue
            painter.save()
            painter.setClipRect(tile, Qt.IntersectClip)
            expanded = QRectF(destination.x(), destination.y() + start * ratio,
                              destination.width(), pixmap.height() * ratio)
            painter.drawPixmap(expanded, pixmap, QRectF(pixmap.rect()))
            painter.restore()


def create_frame_view():
    settings = QSettings("easycrawl", "EasyCrawl")
    enabled = settings.value("preview/gpu", True, type=bool)
    if not enabled or QApplication.platformName() in ("offscreen", "minimal"):
        return FrameView()
    # Check the platform's context before choosing the accelerated widget.
    context = QOpenGLContext()
    surface = QOffscreenSurface()
    surface.create()
    if not context.create() or not context.makeCurrent(surface):
        return FrameView()
    context.doneCurrent()
    return GpuFrameView()


class PreviewPanel(QWidget):
    """The frame, the logo inspector that floats over it, and the transport."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = create_frame_view()
        self.logo_bar = LogoBar(self.view)
        self.view.inspector = self.logo_bar

        self.slider = Timeline()
        self.slider.setRange(0, 0)
        self.slider.setToolTip("Click to jump · ticks are sections")
        self._icons = {False: _transport_icon("play"), True: _transport_icon("pause")}
        self.play = QToolButton()
        self.play.setProperty("flat", True)
        self.play.setIcon(self._icons[False])
        self.play.setCheckable(True)
        self.play.setToolTip("Play / pause  (Space)\n← → step a frame, Shift for 10 · ↑ ↓ previous / next section")
        mono = QFont("Menlo")
        mono.setStyleHint(QFont.Monospace)
        mono.setPixelSize(12)
        self.readout = QLabel("—")
        self.readout.setFont(mono)
        self.readout.setMinimumWidth(92)
        self.duration = QLabel("")
        self.duration.setFont(mono)
        self.duration.setProperty("role", "caption")

        self.guides = QToolButton()
        self.guides.setText("Guides")
        self.guides.setProperty("flat", True)
        self.guides.setProperty("menu", True)
        self.guides.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.guides)
        self.safe = QAction("Action-safe (90%)", self, checkable=True)
        self.centre = QAction("Column centre line", self, checkable=True)
        self.cuts = QAction("Panel cuts", self, checkable=True)
        for action in (self.safe, self.centre, self.cuts):
            menu.addAction(action)
            action.toggled.connect(self._overlays_changed)
        self.guides.setMenu(menu)

        transport = QWidget()
        transport.setObjectName("transport")
        transport.setAttribute(Qt.WA_StyledBackground, True)
        bar = QHBoxLayout(transport)
        bar.setContentsMargins(8, 4, 8, 4)
        bar.setSpacing(8)
        bar.addWidget(self.play)
        bar.addWidget(self.readout)
        bar.addWidget(self.slider, 1)
        bar.addWidget(self.duration)
        bar.addWidget(self.guides)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        preview_header = QHBoxLayout()
        preview_header.setContentsMargins(8, 4, 8, 4)
        preview_header.addWidget(QLabel("Crawl preview"))
        preview_header.addStretch(1)
        self.expand_button = QToolButton()
        self.expand_button.setText("Expand")
        self.expand_button.setToolTip("Show the crawl preview full screen")
        self.expand_button.setProperty("flat", True)
        preview_header.addWidget(self.expand_button)
        lay.addLayout(preview_header)
        lay.addWidget(self.view, 1)
        lay.addWidget(transport)

        self.fps = 24.0
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self._clock = time.monotonic
        self._started = 0.0
        self._start_frame = 0
        self._advancing = False
        self.timer.timeout.connect(self._tick)
        self.slider.valueChanged.connect(self._frame_changed)
        self.play.toggled.connect(self._toggle_play)
        self.view.nudge.connect(self.step)
        self.view.section.connect(self.slider.jump)
        self._tc: Callable[[int], str] = lambda f: str(f)

    def load(self, strip: Image.Image, scale: float, width_px: int, height_px: int,
             speed: int, head: int, total_frames: int, fps: float,
             panels: List[Tuple[int, int]], tc: Callable[[int], str]):
        self.fps = fps
        self._tc = tc
        self.view.set_strip(pil_to_qimage(strip), scale, width_px, height_px, speed, head, panels)
        keep = min(self.slider.value(), total_frames - 1)
        self.slider.setRange(0, max(0, total_frames - 1))
        self.slider.setValue(keep)
        self.duration.setText(tc(total_frames))
        self._frame_changed(keep)

    def clear(self):
        """Back to the empty state (no sheet loaded)."""
        self.play.setChecked(False)
        self.view.set_strip(None, self.view.scale, self.view.width_px, self.view.height_px, 1, 0, [])
        self.view.set_logos([])
        self.view.hit_regions = []
        self.slider.set_markers([])
        self.slider.setRange(0, 0)
        self.readout.setText("—")
        self.duration.setText("")

    def toggle_play(self):
        if self.slider.maximum() > 0:
            self.play.toggle()

    def step(self, frames: int):
        self.play.setChecked(False)
        self.slider.setValue(max(0, min(self.slider.maximum(), self.slider.value() + frames)))

    def _frame_changed(self, f: int):
        if self.play.isChecked() and not self._advancing:
            self._started = self._clock()
            self._start_frame = f
        self.view.set_frame(f)
        self.readout.setText(self._tc(f))
        self.readout.setToolTip(f"Frame {f}")

    def _toggle_play(self, on: bool):
        self.play.setIcon(self._icons[on])
        if on:
            self._started = self._clock()
            self._start_frame = self.slider.value()
            self.timer.start(8)
        else:
            self.timer.stop()

    def _overlays_changed(self, *_):
        self.view.show_safe = self.safe.isChecked()
        self.view.show_centre = self.centre.isChecked()
        self.view.show_cuts = self.cuts.isChecked()
        self.view.update()

    def _tick(self):
        elapsed = max(0.0, self._clock() - self._started)
        f = (self._start_frame + int(elapsed * self.fps)) % (self.slider.maximum() + 1)
        self._advancing = True
        try:
            self.slider.setValue(f)
        finally:
            self._advancing = False
