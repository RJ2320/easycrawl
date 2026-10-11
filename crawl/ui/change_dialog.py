"""Review the client's changes before they go into the crawl."""
from difflib import SequenceMatcher

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QSplitter, QWidget)

from .. import changes as changes_mod
from . import theme

KIND_LABELS = {"change": "Changed", "add": "Added", "remove": "Removed"}


def _lines(rows) -> str:
    return "\n".join(changes_mod.row_text(r) for r in rows)


def _heading(row):
    b, c, d = (list(row) + ["", "", ""])[:3]
    return bool((c.strip() and c.strip().isupper() and not b.strip() and not d.strip())
                or (b.strip() and b.strip().isupper() and not c.strip() and not d.strip()))


def _section(rows, start, count):
    """Include the enclosing heading and section, or nearby rows without a heading."""
    start = min(max(start, 0), len(rows))
    end = min(len(rows), start + count)
    anchor = min(start, max(0, len(rows)-1))
    heading = next((i for i in range(anchor, -1, -1) if _heading(rows[i])), None)
    left = heading if heading is not None else max(0, start-3)
    right = next((i for i in range(max(end, anchor+1), len(rows)) if _heading(rows[i])), len(rows))
    if heading is None:
        right = min(right, max(end, start)+3)
    return left, right, changes_mod.row_text(rows[heading]) if heading is not None else "Nearby credits"


def _incoming_boundary(current, incoming, position):
    for tag, a, b, c, d in SequenceMatcher(None, current, incoming, autojunk=False).get_opcodes():
        if a <= position <= b:
            return c + position-a if tag == "equal" else c
    return len(incoming)


class ChangeDialog(QDialog):
    """A checklist of changes. `accepted_changes()` after exec() gives the ticked ones."""

    def __init__(self, changes, sheet_name: str, parent=None, current_rows=None, incoming_rows=None):
        super().__init__(parent)
        self.changes = list(changes)
        self.current_rows = [tuple(r) for r in current_rows] if current_rows is not None else None
        self.incoming_rows = [tuple(r) for r in incoming_rows] if incoming_rows is not None else None
        self.setWindowTitle("Update from revised sheet")
        self.resize(1200, 780)

        title = QLabel(f"{sheet_name}: {changes_mod.summary(self.changes)}")
        title.setObjectName("emptyTitle")
        hint = QLabel("Choose which changes to bring in. Checked = use the incoming spreadsheet; unchecked = keep your current credits. "
                      "Select a change to compare it within its surrounding section below.\n"
                      "Changes that also replace an edit made here start unchecked. Layout, logos, look and timing are kept.")
        hint.setProperty("role", "caption")
        hint.setWordWrap(True)

        self.table = QTableWidget(len(self.changes), 4)
        self.table.setHorizontalHeaderLabels(["Use incoming", "Current location", "Current credits", "Incoming spreadsheet"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setWordWrap(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        for i, change in enumerate(self.changes):
            if change.conflict:
                change.accepted = False
            kind = QTableWidgetItem(KIND_LABELS[change.kind] + ("  · review your edit" if change.conflict else ""))
            kind.setFlags(kind.flags() | Qt.ItemIsUserCheckable)
            kind.setCheckState(Qt.Checked if change.accepted else Qt.Unchecked)
            if change.conflict:
                kind.setForeground(QColor(theme.WARNING))
                kind.setToolTip("These rows were also edited in the app. Applying replaces that edit "
                                "with the client's version; untick to keep yours.")
            where = str(change.start + 1) if change.end - change.start <= 1 else f"{change.start + 1}–{change.end}"
            row_item = QTableWidgetItem(where if change.kind != "add" else (f"after row {change.start}" if change.start else "at beginning"))
            old = QTableWidgetItem(_lines(change.old) if change.old else "—")
            new = QTableWidgetItem(_lines(change.new) if change.new else "—")
            if change.kind == "remove":
                old.setForeground(QColor(theme.ERROR))
            if change.kind == "add":
                new.setForeground(QColor(theme.ACCENT))
            for col, item in enumerate((kind, row_item, old, new)):
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
                self.table.setItem(i, col, item)
        self.table.resizeRowsToContents()
        self.table.itemChanged.connect(self._sync)
        self.table.currentCellChanged.connect(lambda *_: self._show_detail())

        self.detail_title = QLabel()
        self.detail_title.setWordWrap(True)
        self.detail_note = QLabel()
        self.detail_note.setWordWrap(True)
        self.detail_note.setProperty("role", "caption")
        detail_panels = QSplitter(Qt.Horizontal)
        self.current_cells, self.incoming_cells = QTableWidget(), QTableWidget()
        for title_text, table in (("Current credits in this project", self.current_cells),
                                  ("Incoming spreadsheet: " + sheet_name, self.incoming_cells)):
            panel = QWidget()
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0,0,0,0)
            label = QLabel(title_text); label.setWordWrap(True)
            panel_layout.addWidget(label)
            table.setColumnCount(3)
            table.setHorizontalHeaderLabels(["Role / list / logo", "Header / song", "Names"])
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.setWordWrap(True)
            panel_layout.addWidget(table)
            detail_panels.addWidget(panel)
        self.current_cells.verticalScrollBar().valueChanged.connect(self.incoming_cells.verticalScrollBar().setValue)
        self.incoming_cells.verticalScrollBar().valueChanged.connect(self.current_cells.verticalScrollBar().setValue)
        self.previous_button = QPushButton("Previous change")
        self.next_button = QPushButton("Next change")
        self.previous_button.clicked.connect(lambda: self._step(-1))
        self.next_button.clicked.connect(lambda: self._step(1))
        self.choice_button = QPushButton()
        self.choice_button.clicked.connect(self._toggle_current)
        navigation = QHBoxLayout()
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.next_button)
        navigation.addStretch(1)
        navigation.addWidget(self.choice_button)
        self.decision_summary = QLabel()
        self.decision_summary.setWordWrap(True)

        all_button = QPushButton("Select all")
        none_button = QPushButton("Select none")
        copy_button = QPushButton("Copy change list")
        copy_button.setToolTip("Copy a plain-text list of these changes, e.g. to confirm them with the client.")
        all_button.clicked.connect(lambda: self._set_all(True))
        none_button.clicked.connect(lambda: self._set_all(False))
        copy_button.clicked.connect(self._copy)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.apply_button = QPushButton()
        self.apply_button.setProperty("primary", True)
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        for button in (all_button, none_button, copy_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(self.apply_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.table, 2)
        layout.addWidget(self.detail_title)
        layout.addWidget(self.detail_note)
        layout.addWidget(detail_panels, 3)
        layout.addLayout(navigation)
        layout.addWidget(self.decision_summary)
        layout.addLayout(buttons)
        self._sheet_name = sheet_name
        self._sync()
        if self.changes:
            self.table.setCurrentCell(0,0)

    def _sync(self, *_):
        for i, change in enumerate(self.changes):
            change.accepted = self.table.item(i, 0).checkState() == Qt.Checked
        n = sum(c.accepted for c in self.changes)
        self.apply_button.setText(f"Apply {n} change{'s' if n != 1 else ''}")
        if not n:
            self.apply_button.setText("Finish review — keep current credits")
        self.decision_summary.setText(
            f"{n} selected · {len(self.changes)-n} skipped. Finishing makes this spreadsheet the reference for future comparisons, "
            "including skipped changes. Cancel leaves the reference unchanged.")
        self._show_detail()
        # Applying nothing still records that this revision was reviewed.
        self.apply_button.setToolTip("" if n else "Nothing ticked: the crawl stays as it is, and these "
                                                  "differences won't be offered again.")

    def _step(self, direction):
        if self.changes:
            self.table.setCurrentCell((self.table.currentRow()+direction) % len(self.changes),0)

    def _toggle_current(self):
        row = self.table.currentRow()
        if row >= 0:
            item = self.table.item(row,0)
            item.setCheckState(Qt.Unchecked if item.checkState()==Qt.Checked else Qt.Checked)

    def _show_detail(self):
        row = self.table.currentRow()
        if not 0 <= row < len(self.changes):
            return
        change = self.changes[row]
        outcome = ({"add":"Add these rows", "remove":"Remove these rows", "change":"Replace with incoming cells"}[change.kind]
                   if change.accepted else "Keep current credits; skip this change")
        self.detail_title.setText(f"Change {row+1} of {len(self.changes)} · {KIND_LABELS[change.kind]} · {outcome}")
        self.choice_button.setText("Keep current instead" if change.accepted else "Use incoming change")
        self.detail_note.setText(("Both versions changed these rows. Using incoming will replace your local edit. " if change.conflict else "") +
                                "Highlighted cells differ. Row numbers refer to each version separately; — means no row or an empty cell.")
        if self.current_rows is not None and self.incoming_rows is not None:
            self._show_context(change)
            return
        count = max(len(change.old),len(change.new))
        for table, values, start, other in ((self.current_cells,change.old,change.start+1,change.new),
                                           (self.incoming_cells,change.new,change.sheet_row,change.old)):
            table.setRowCount(count)
            for r in range(count):
                present = r < len(values)
                table.setVerticalHeaderItem(r,QTableWidgetItem(str(start+r) if present else "—"))
                for c in range(3):
                    value = values[r][c] if present else ""
                    item = QTableWidgetItem(value or "—")
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
                    differs = not present or r >= len(other) or value != other[r][c]
                    if differs:
                        color = QColor(theme.WARNING if change.conflict else theme.ACCENT)
                        color.setAlpha(45)
                        item.setBackground(color)
                        item.setToolTip("Different between versions" if present else "No row in this version")
                    table.setItem(r,c,item)
            table.resizeRowsToContents()
        for r in range(count):
            height = max(self.current_cells.rowHeight(r),self.incoming_cells.rowHeight(r))
            self.current_cells.setRowHeight(r,height)
            self.incoming_cells.setRowHeight(r,height)

    def _show_context(self, change):
        current, incoming = self.current_rows, self.incoming_rows
        new_start = change.sheet_row-1 if change.sheet_row else _incoming_boundary(current, incoming, change.start)
        a, b, current_label = _section(current, change.start, len(change.old))
        c, d, incoming_label = _section(incoming, new_start, len(change.new))
        self.detail_title.setText(self.detail_title.text() + "\n" + current_label +
                                  (" → " + incoming_label if current_label != incoming_label else ""))
        self.detail_note.setText(self.detail_note.text() + " Unhighlighted rows provide section context; only the selected change is applied.")
        pairs = []
        for tag, i, j, k, l in SequenceMatcher(None, current[a:b], incoming[c:d], autojunk=False).get_opcodes():
            for offset in range(max(j-i, l-k)):
                pairs.append((a+i+offset if offset < j-i else None,
                              c+k+offset if offset < l-k else None))
        focus = []
        for table in (self.current_cells, self.incoming_cells):
            table.setRowCount(len(pairs))
        for row, (old_index, new_index) in enumerate(pairs):
            selected = ((old_index is not None and change.start <= old_index < change.end) or
                        (new_index is not None and new_start <= new_index < new_start+len(change.new)))
            if selected:
                focus.append(row)
            for table, rows, index, other_rows, other_index in (
                    (self.current_cells, current, old_index, incoming, new_index),
                    (self.incoming_cells, incoming, new_index, current, old_index)):
                table.setVerticalHeaderItem(row, QTableWidgetItem(str(index+1) if index is not None else "—"))
                for column in range(3):
                    value = rows[index][column] if index is not None else ""
                    item = QTableWidgetItem(value or "—")
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
                    if index is not None and _heading(rows[index]):
                        font = item.font(); font.setBold(True); item.setFont(font)
                    differs = index is None or other_index is None or value != other_rows[other_index][column]
                    if selected and differs:
                        color = QColor(theme.WARNING if change.conflict else theme.ACCENT)
                        color.setAlpha(45); item.setBackground(color)
                        item.setToolTip("Selected change" if index is not None else "No row in this version")
                    table.setItem(row, column, item)
        for table in (self.current_cells, self.incoming_cells):
            table.resizeRowsToContents()
        for row in range(len(pairs)):
            height = max(self.current_cells.rowHeight(row), self.incoming_cells.rowHeight(row))
            self.current_cells.setRowHeight(row, height); self.incoming_cells.setRowHeight(row, height)
        if focus:
            for table in (self.current_cells, self.incoming_cells):
                table.scrollToItem(table.item(focus[0], 0), QAbstractItemView.PositionAtCenter)

    def _set_all(self, on: bool):
        self.table.blockSignals(True)
        for i in range(self.table.rowCount()):
            self.table.item(i, 0).setCheckState(Qt.Checked if on else Qt.Unchecked)
        self.table.blockSignals(False)
        self._sync()

    def _copy(self):
        QGuiApplication.clipboard().setText(changes_mod.report(self.changes, f"Credit changes — {self._sheet_name}"))

    def accepted_changes(self):
        return [c for c in self.changes if c.accepted]
