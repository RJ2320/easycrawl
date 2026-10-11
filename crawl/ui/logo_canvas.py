"""Cached artwork layers and multi-selection for the logo workspace."""
from dataclasses import replace
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QPainter, QColor, QPen
from .widgets import FrameView
from . import theme


class LogoCanvas(FrameView):
    selection_changed = Signal(object)
    group_moved = Signal(object, int, int)

    def __init__(self):
        super().__init__()
        self.selection = set()
        self.layers = {}

    def set_selection(self, labels):
        self.selection = set(labels)
        self.selected = next((logo.label for logo in self.logos if logo.label in self.selection), '')
        self.update()

    def select_logo(self, label):
        self.set_selection([label] if label else [])
        self.selection_changed.emit(set(self.selection))

    def _selected_item(self):
        selected = [logo for logo in self.logos if logo.label in self.selection]
        if not selected:
            return None
        if len(selected) == 1:
            return selected[0]
        left, top = min(l.x for l in selected), min(l.y for l in selected)
        return replace(selected[0], x=left, y=top,
                       w=max(l.x+l.w for l in selected)-left,
                       h=max(l.y+l.h for l in selected)-top, dx=0, dy=0)

    def _snap(self, dx, dy, reach):
        # Snap the group's bounds against only the unselected artwork.
        original = self.logos
        selected = self._selected_item()
        if selected is None:
            return dx, dy
        self.logos = [logo for logo in original if logo.label not in self.selection] + [selected]
        try:
            return super()._snap(dx, dy, reach)
        finally:
            self.logos = original

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self.busy:
            return
        self.setFocus()
        logo = self.logo_at(event.position())
        toggle = bool(event.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier | Qt.MetaModifier))
        if logo:
            if toggle:
                self.selection.symmetric_difference_update({logo.label})
            elif logo.label not in self.selection:
                self.selection = {logo.label}
        elif not toggle:
            self.selection.clear()
        self.set_selection(self.selection)
        self.selection_changed.emit(set(self.selection))
        self._drag = (0, 0)
        self._press = event.position() if logo and logo.label in self.selection else None

    def mouseReleaseEvent(self, event):
        if self._press is None:
            return
        self._press = None
        self._guides = []
        self.setCursor(Qt.OpenHandCursor)
        if self._drag != (0, 0):
            self.group_moved.emit(set(self.selection), *self._drag)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme.BG))
        ox, oy, w, h, k, content_top = self._geom()
        target = QRectF(ox, oy, w, h)
        painter.fillRect(target, Qt.black)
        painter.setClipRect(target)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        for logo in self.logos:
            offset = self._drag if logo.label in self.selection else (0, 0)
            rect = self.logo_rect(logo, offset)
            layer = self.layers.get(logo.label)
            if layer is not None:
                painter.drawImage(rect, layer)
            if logo.label in self.selection:
                painter.setPen(QPen(QColor(theme.ACCENT), 1.5))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(rect.adjusted(-2, -2, 2, 2))
        painter.setPen(QPen(QColor(theme.ACCENT), 1, Qt.DashLine))
        for axis, value in self._guides:
            if axis == 'v':
                painter.drawLine(QPointF(ox+value*k, oy), QPointF(ox+value*k, oy+h))
            else:
                y = oy+(content_top+value)*k
                painter.drawLine(QPointF(ox, y), QPointF(ox+w, y))
        painter.end()
