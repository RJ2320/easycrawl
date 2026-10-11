"""Choose how a sheet is read: which worksheet, which columns, which row it starts on.

Shown when a workbook has several tabs or the credits aren't in the template's
columns, and on demand from File → Import Options. The preview shows the
cells as they are in the file with the chosen columns tinted, and says what
the crawl would read from them.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QFormLayout, QHBoxLayout, QHeaderView,
                               QLabel, QListWidget, QListWidgetItem, QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from .. import ingest
from . import theme

PREVIEW_ROWS = 80
ROLE_TINT, HEADER_TINT, NAMES_TINT = "#2a3a52", "#2f3f33", "#3c3550"


class ImportDialog(QDialog):
    """After exec(): `.sheet`, `.columns` ("" when they are the ones that would be found
    anyway) and `.start_row` are what the project should read with."""

    def __init__(self, path: str, sheet: str = "", columns: str = "", start_row: int = 1,
                 reason: str = "", parent=None):
        super().__init__(parent)
        self.path = path
        self.setWindowTitle("Import options")
        self.resize(1040, 640)
        self._grids: Dict[str, List[List[str]]] = {}
        self.infos = ingest.sheets(path)
        names = [info.name for info in self.infos]
        wanted = sheet if sheet in names else (ingest.guess_sheet(self.infos) or (names[0] if names else ""))

        title = QLabel(reason or "How should this sheet be read?")
        title.setObjectName("emptyTitle")
        title.setWordWrap(True)
        hint = QLabel("The template keeps the role in column B, centred headings in C and names in D. "
                      "If this sheet is laid out differently, say which columns hold what; names spread "
                      "across several columns are stacked. Rows above the start row are skipped.")
        hint.setProperty("role", "caption")
        hint.setWordWrap(True)

        # ---- worksheets ------------------------------------------------------
        self.sheet_list = QListWidget()
        self.sheet_list.setFixedWidth(230)
        for info in self.infos:
            label = info.name or "Sheet"
            item = QListWidgetItem(f"{label}\n{info.filled} row{'s' if info.filled != 1 else ''}"
                                   + (f" · {info.preview[0]}" if info.preview else ""))
            item.setData(Qt.UserRole, info.name)
            item.setToolTip("\n".join(info.preview) or "Empty")
            if not info.filled:
                item.setForeground(QColor(theme.FAINT))
            self.sheet_list.addItem(item)
            if info.name == wanted:
                self.sheet_list.setCurrentItem(item)
        self.sheet_list.currentItemChanged.connect(lambda *_: self._sheet_changed())

        # ---- columns ---------------------------------------------------------
        letters = [chr(ord("A") + i) for i in range(ingest.MAX_COLS)]
        self.role_box, self.header_box, self.first_box, self.last_box = (QComboBox() for _ in range(4))
        for box in (self.role_box, self.header_box, self.first_box, self.last_box):
            box.addItems(letters)
            box.currentIndexChanged.connect(lambda *_: self._mapping_changed())
        self.start_spin = QSpinBox()
        self.start_spin.setRange(1, 9999)
        self.start_spin.setValue(max(1, int(start_row)))
        self.start_spin.valueChanged.connect(lambda *_: self._mapping_changed())
        self.auto_button = QPushButton("Find columns")
        self.auto_button.setToolTip("Use the three adjacent columns with the most text")
        self.auto_button.clicked.connect(self._auto)

        names_row = QHBoxLayout()
        names_row.setSpacing(6)
        names_row.addWidget(self.first_box)
        names_row.addWidget(QLabel("to"))
        names_row.addWidget(self.last_box)
        names_row.addStretch(1)
        form = QFormLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)
        form.addRow("Role", self.role_box)
        form.addRow("Heading", self.header_box)
        form.addRow("Names", names_row)
        form.addRow("Start row", self.start_spin)
        form.addRow("", self.auto_button)
        mapping = QWidget()
        mapping.setLayout(form)
        mapping.setFixedWidth(230)

        # ---- preview ---------------------------------------------------------
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setDefaultSectionSize(150)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.summary = QLabel()
        self.summary.setProperty("role", "caption")
        self.summary.setWordWrap(True)

        side = QVBoxLayout()
        side.setSpacing(8)
        if len(self.infos) > 1:
            sheets_label = QLabel("Worksheet")
            sheets_label.setProperty("role", "caption")
            side.addWidget(sheets_label)
            side.addWidget(self.sheet_list, 1)
        columns_label = QLabel("Columns")
        columns_label.setProperty("role", "caption")
        side.addWidget(columns_label)
        side.addWidget(mapping)
        side.addStretch(0 if len(self.infos) > 1 else 1)
        body = QHBoxLayout()
        body.setSpacing(14)
        body.addLayout(side)
        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(self.table, 1)
        right.addWidget(self.summary)
        body.addLayout(right, 1)

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.ok_button = QPushButton("Import")
        self.ok_button.setProperty("primary", True)
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(self.ok_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addLayout(body, 1)
        layout.addLayout(buttons)

        self._setting = False
        self._set_mapping(columns or ingest.detect_columns(self._grid()))
        self._refresh()

    # ---- state -----------------------------------------------------------------

    @property
    def sheet(self) -> str:
        item = self.sheet_list.currentItem()
        return item.data(Qt.UserRole) if item else (self.infos[0].name if self.infos else "")

    @property
    def columns(self) -> str:
        """The spec, or "" for the template's columns (which is what reading
        without a spec falls back to, so the revised sheets still auto-detect)."""
        spec = self._mapping()
        return "" if spec == ingest.TEMPLATE_COLUMNS else spec

    @property
    def start_row(self) -> int:
        return self.start_spin.value()

    def _grid(self) -> List[List[str]]:
        name = self.sheet
        if name not in self._grids:
            try:
                self._grids[name] = ingest.read_grid(self.path, name or None)
            except Exception:
                self._grids[name] = []
        return self._grids[name]

    def _mapping(self) -> str:
        return ingest.format_columns(self.role_box.currentIndex(), self.header_box.currentIndex(),
                                     self.first_box.currentIndex(), self.last_box.currentIndex())

    def _set_mapping(self, spec: str):
        role, header, first, last = ingest.parse_columns(spec)
        self._setting = True
        for box, index in ((self.role_box, role), (self.header_box, header),
                           (self.first_box, first), (self.last_box, last)):
            box.setCurrentIndex(min(index, box.count() - 1))
        self._setting = False

    # ---- reactions -------------------------------------------------------------

    def _sheet_changed(self):
        self._set_mapping(ingest.detect_columns(self._grid()))
        self._refresh()

    def _auto(self):
        self._set_mapping(ingest.detect_columns(self._grid()))
        self._refresh()

    def _mapping_changed(self):
        if self._setting:
            return
        if self.last_box.currentIndex() < self.first_box.currentIndex():
            self._setting = True
            self.last_box.setCurrentIndex(self.first_box.currentIndex())
            self._setting = False
        self._refresh()

    def _refresh(self):
        grid = self._grid()
        spec = self._mapping()
        try:
            role, header, first, last = ingest.parse_columns(spec)
            problem = ""
        except ValueError as e:
            role = header = first = last = -1
            problem = str(e)
        self.ok_button.setEnabled(not problem)

        width = max(max((len(r) for r in grid), default=0), 4)
        width = min(width, ingest.MAX_COLS)
        shown = grid[:PREVIEW_ROWS]
        self.table.clear()
        self.table.setColumnCount(width)
        self.table.setRowCount(len(shown))
        self.table.setHorizontalHeaderLabels([chr(ord("A") + c) for c in range(width)])
        self.table.setVerticalHeaderLabels([str(i + 1) for i in range(len(shown))])
        tints = {role: ROLE_TINT, header: HEADER_TINT}
        tints.update({c: NAMES_TINT for c in range(first, last + 1)})
        skip = self.start_spin.value() - 1
        for r, row in enumerate(shown):
            for c in range(width):
                value = row[c] if c < len(row) else ""
                item = QTableWidgetItem(value.replace("\n", " ⏎ "))
                item.setToolTip(value)
                if r < skip:
                    item.setForeground(QColor(theme.FAINT))
                elif c in tints:
                    item.setBackground(QColor(tints[c]))
                self.table.setItem(r, c, item)
        for c in range(width):
            self.table.setColumnWidth(c, 160 if c in tints else 90)

        if problem:
            self.summary.setText(problem)
            return
        rows, notes = ingest.normalize_grid(grid, spec, self.start_spin.value())
        found = ingest.parse(rows).describe()
        more = f" · {len(grid) - len(shown)} more rows not shown" if len(grid) > len(shown) else ""
        warnings = f" · {len(notes)} row{'s' if len(notes) != 1 else ''} will be flagged" if notes else ""
        self.summary.setText(f"Reads as {found}{warnings}{more}")
