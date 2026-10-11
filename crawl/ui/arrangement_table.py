"""The credits grid: a QTableWidget that behaves like a spreadsheet.

  type            replaces the cell          Enter / F2 / double-click  edit in place
  Enter           commit, move down          Shift+Enter                commit, move up
  Tab             commit, move right         Alt/Cmd+Enter              new line in the cell
  Delete          clear the selection        Cmd+C / X / V              ranges, Excel/Sheets-compatible

Decorations (error cells, side-by-side arrangements, layout overrides) are
painted by the delegate from lookups, not stored on the items, so an edit never
has to walk the whole table to refresh them.
"""
from PySide6.QtCore import QEvent, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QPen, QTextCursor
from PySide6.QtWidgets import (QAbstractItemDelegate, QAbstractItemView, QHeaderView, QPlainTextEdit,
                               QStyledItemDelegate, QStyleOptionViewItem, QTableWidget, QToolTip)

from .. import ingest
from . import theme

BAND = 24          # height of an arrangement's label strip above its first row
ROW_HEIGHT = 27


class CellEditor(QPlainTextEdit):
    """In-place editor that grows with its text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cellEditor")
        self.setFrameShape(QPlainTextEdit.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTabChangesFocus(False)
        self.document().setDocumentMargin(3)
        self.min_height = ROW_HEIGHT
        self.textChanged.connect(self.fit)

    def fit(self):
        lines = sum(max(1, block.layout().lineCount()) for block in self._blocks())
        needed = int(lines * self.fontMetrics().lineSpacing() + 2 * self.document().documentMargin() + 4)
        self.setFixedHeight(max(self.min_height, needed))

    def _blocks(self):
        block = self.document().begin()
        while block.isValid():
            yield block
            block = block.next()

    def toggle_italic(self):
        """Wrap the selection in *asterisks* (the crawl's italic mark), or unwrap it."""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return
        selected = cursor.selectedText().replace(" ", "\n")
        lines = selected.split("\n")
        if all(len(l) >= 2 and l.startswith("*") and l.endswith("*") for l in lines if l):
            lines = [l[1:-1] if l else l for l in lines]
        else:
            lines = [f"*{l}*" if l else l for l in lines]
        cursor.insertText("\n".join(lines))


class ArrangementDelegate(QStyledItemDelegate):
    def table(self) -> "ArrangementTable":
        return self.parent()

    # ---- painting ----------------------------------------------------------

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        text = index.data() or ""
        if index.column() == 0 and self.table().centered_at(index.row()):
            option.displayAlignment = Qt.AlignCenter
            if text.isupper():
                option.font.setWeight(QFont.DemiBold)
        elif index.column() == 1 and text:
            option.font.setWeight(QFont.DemiBold)          # section headers and song titles
        elif index.column() == 0 and text.startswith("[") and ingest.logo_labels(text):
            option.palette.setColor(option.palette.ColorRole.Text, QColor(theme.ACCENT))

    def paint(self, painter, option, index):
        table = self.table()
        row, col = index.row(), index.column()
        opt = QStyleOptionViewItem(option)
        if table.starts_at(row):
            opt.rect = opt.rect.adjusted(0, BAND, 0, 0)
        severity = table.error_severity.get((row, col))
        tint = None
        if severity:
            tint = theme.color(theme.SEVERITY[severity], 62 if severity == "error" else 38)
        elif table.arrangement_at(row):
            tint = theme.color(theme.ACCENT, 20)
        elif table.override_at(row):
            tint = theme.color("#ffffff", 14)
        if tint is not None:
            painter.fillRect(opt.rect, tint)
        super().paint(painter, opt, index)
        if severity:
            painter.save()
            painter.setPen(QPen(QColor(theme.SEVERITY[severity]), 1.5))
            painter.drawRect(opt.rect.adjusted(1, 1, -2, -2))
            painter.restore()
        if col == 0 and table.changed_at(row):
            # Changed by the last update from a revised sheet.
            painter.fillRect(QRect(opt.rect.left(), opt.rect.top(), 3, opt.rect.height()), QColor(theme.ACCENT))
        elif col == 0 and table.override_at(row):
            painter.fillRect(QRect(opt.rect.left(), opt.rect.top(), 2, opt.rect.height()), QColor(theme.MUTED))

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        height = max(ROW_HEIGHT, size.height() + 6)
        return QSize(size.width(), height + (BAND if self.table().starts_at(index.row()) else 0))

    def helpEvent(self, event, view, option, index):
        if event.type() == QEvent.ToolTip and index.isValid():
            tip = self.table().tooltip_for(index.row(), index.column())
            if tip:
                QToolTip.showText(event.globalPos(), tip, view)
                return True
            QToolTip.hideText()
        return super().helpEvent(event, view, option, index)

    # ---- editing -----------------------------------------------------------

    def createEditor(self, parent, option, index):
        editor = CellEditor(parent)
        editor.setFont(option.font)
        return editor

    def setEditorData(self, editor, index):
        editor.setPlainText(index.data(Qt.EditRole) or "")
        if self.table().typed_edit:
            editor.selectAll()                      # the key that started the edit replaces the cell
        else:
            editor.moveCursor(QTextCursor.End)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.toPlainText(), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        rect = option.rect
        if self.table().starts_at(index.row()):
            rect = rect.adjusted(0, BAND, 0, 0)
        editor.min_height = rect.height()
        editor.setGeometry(rect)
        editor.fit()

    def eventFilter(self, editor, event):
        if event.type() == QEvent.KeyPress and isinstance(editor, CellEditor):
            key, mods = event.key(), event.modifiers()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if mods & (Qt.AltModifier | Qt.ControlModifier | Qt.MetaModifier):
                    editor.insertPlainText("\n")
                    return True
                self._finish(editor, -1 if mods & Qt.ShiftModifier else 1, 0)
                return True
            if key in (Qt.Key_Tab, Qt.Key_Backtab):
                self._finish(editor, 0, -1 if key == Qt.Key_Backtab else 1)
                return True
            if key == Qt.Key_I and mods & Qt.ControlModifier:
                editor.toggle_italic()
                return True
        return super().eventFilter(editor, event)

    def _finish(self, editor, d_row: int, d_col: int):
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QAbstractItemDelegate.NoHint)
        self.table().move_current(d_row, d_col)


class ArrangementTable(QTableWidget):
    clear_requested = Signal()
    copy_requested = Signal()
    cut_requested = Signal()
    paste_requested = Signal()

    def __init__(self, project, parent=None):
        super().__init__(0, 3, parent)
        self.project = project
        self.error_cells = set()             # (row, col) with a finding
        self.error_severity = {}             # (row, col) → "error" | "warning" | "info"
        self.tooltip_for = lambda row, col: ""
        self.change_marks = []               # {start, end}: rows changed by the last sheet update
        self.typed_edit = False              # the current edit was started by typing a character
        self.setItemDelegate(ArrangementDelegate(self))
        self.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed |
                             QAbstractItemView.AnyKeyPressed)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setTabKeyNavigation(True)
        self.setWordWrap(True)
        self.setTextElideMode(Qt.ElideNone)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.verticalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.verticalHeader().setMinimumSectionSize(ROW_HEIGHT)
        self.verticalHeader().setDefaultAlignment(Qt.AlignCenter)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setMinimumSectionSize(80)
        self._sized = False
        # Wrapping depends on column width, so row heights are re-measured after
        # the columns settle (not on every pixel of a drag).
        self._remeasure = QTimer(self)
        self._remeasure.setSingleShot(True)
        self._remeasure.setInterval(120)
        self._remeasure.timeout.connect(self._remeasure_rows)
        header.sectionResized.connect(lambda *_: self._remeasure.start())

    # ---- lookups the delegate paints from ----------------------------------

    def centered_at(self, row):
        override = self.override_at(row)
        if not override or override['kind'] != 'center':
            return False
        cells = [self.item(row, c).text() if self.item(row, c) else '' for c in range(3)]
        return bool(cells[0] and not cells[1] and not cells[2]
                    and not ingest.logo_labels(cells[0]))

    def sync_centered_rows(self):
        # Spans are presentation only: all three underlying cells remain intact.
        wanted = {row for row in range(self.rowCount()) if self.centered_at(row)}
        current = {row for row in range(self.rowCount()) if self.columnSpan(row, 0) > 1}
        if wanted == current:
            return
        self.clearSpans()
        for row in wanted:
            self.setSpan(row, 0, 1, 3)
        for row in wanted | current:
            self.resizeRowToContents(row)

    def starts_at(self, row):
        return any(a['start'] == row for a in self.project.arrangements)

    def arrangement_at(self, row):
        return next((a for a in self.project.arrangements if a['start'] <= row <= a['end']), None)

    def changed_at(self, row):
        return any(m['start'] <= row <= m['end'] for m in self.change_marks)

    def override_at(self, row):
        return next((o for o in self.project.overrides if o['start'] <= row <= o['end']), None)

    # ---- behaviour ---------------------------------------------------------

    def scroll_anchor(self):
        row = self.rowAt(0)
        return (row, self.rowViewportPosition(row), self.horizontalScrollBar().value()) if row >= 0 else None

    def restore_scroll_anchor(self, anchor):
        if anchor is None:
            return
        row, offset, horizontal = anchor
        if row < self.rowCount() and not self.isRowHidden(row):
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() + self.rowViewportPosition(row) - offset)
        self.horizontalScrollBar().setValue(horizontal)

    def _remeasure_rows(self):
        # Changing wrapped row heights must not move the credit being read.
        anchor = self.scroll_anchor()
        self.setUpdatesEnabled(False)
        try:
            self.resizeRowsToContents()
            self.restore_scroll_anchor(anchor)
        finally:
            self.setUpdatesEnabled(True)
        # Scrollbar visibility can resize the stretched column during measurement.
        # Its final geometry has already been measured; avoid a second full pass.
        self._remeasure.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._sized and self.viewport().width() > 200:
            # First layout: roles and names wide, the header column narrower.
            width = self.viewport().width()
            self.setColumnWidth(0, int(width * 0.40))
            self.setColumnWidth(1, int(width * 0.24))
            self._sized = True

    def move_current(self, d_row: int, d_col: int):
        row = min(max(0, self.currentRow() + d_row), self.rowCount() - 1)
        col = min(max(0, self.currentColumn() + d_col), self.columnCount() - 1)
        self.setCurrentCell(row, col)
        self.setFocus()

    def keyPressEvent(self, event):
        key = event.key()
        if self.state() != QAbstractItemView.EditingState:
            if event.matches(QKeySequence.Copy):
                self.copy_requested.emit()
                return
            if event.matches(QKeySequence.Cut):
                self.cut_requested.emit()
                return
            if event.matches(QKeySequence.Paste):
                self.paste_requested.emit()
                return
            if key in (Qt.Key_Delete, Qt.Key_Backspace):
                self.clear_requested.emit()
                return
            if key in (Qt.Key_Return, Qt.Key_Enter) and self.currentIndex().isValid():
                self.typed_edit = False
                self.edit(self.currentIndex())
                return
        # A printable key starts an edit that replaces the cell, as in a spreadsheet.
        self.typed_edit = bool(event.text()) and event.text().isprintable() and \
            not event.modifiers() & (Qt.ControlModifier | Qt.MetaModifier)
        try:
            super().keyPressEvent(event)
        finally:
            self.typed_edit = False

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.project.arrangements:
            return
        painter = QPainter(self.viewport())
        painter.setClipRect(event.rect())
        left = self.columnViewportPosition(0) + 1
        right = self.columnViewportPosition(2) + self.columnWidth(2) - 2
        for item in self.project.arrangements:
            if item['start'] >= self.rowCount():
                continue
            end = min(item['end'], self.rowCount() - 1)
            top = self.rowViewportPosition(item['start'])
            bottom = self.rowViewportPosition(end) + self.rowHeight(end) - 1
            if bottom < 0 or top > self.viewport().height():
                continue
            painter.setPen(QPen(QColor(theme.ACCENT), 1.5))
            painter.drawRect(QRect(left, top + 1, right - left, bottom - top - 1))
            band = QRect(left + 1, top + 2, right - left - 1, BAND - 2)
            painter.fillRect(band, QColor(theme.ACCENT_DIM))
            painter.setPen(QColor(theme.TEXT))
            label = f"{item.get('label', 'Side by side')} · {item['columns']} columns · rows {item['start'] + 1}–{item['end'] + 1}"
            label = painter.fontMetrics().elidedText(label, Qt.ElideRight, max(0, band.width() - 16))
            painter.drawText(band.adjusted(8, 0, -8, 0), Qt.AlignVCenter | Qt.AlignLeft, label)
        painter.end()
