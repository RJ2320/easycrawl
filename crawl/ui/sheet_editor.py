"""The Credits tab: the sheet's B/C/D cells, edited like a spreadsheet.

Edits live in the project (not the source file). Everything that changes the
credits funnels through `_changed()`, which records an undo step.
"""
import csv
import io
import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
                               QStackedLayout, QTableWidgetItem, QTableWidgetSelectionRange, QToolButton,
                               QVBoxLayout, QWidget)

from .. import arrangements, ingest
from .arrangement_table import ArrangementTable
from .widgets import _spin

LAYOUT_LABELS = {
    'auto': 'Automatic (6+ rows become a list, fewer are roles)',
    'roles': 'Roles — left column, names to come',
    'list': 'List in columns',
    'center': 'Centred lines',
}
LAYOUT_SHORT = {'auto': 'Automatic', 'roles': 'Roles (names to come)', 'list': 'List in columns',
                'center': 'Centred lines'}
UNDO_LIMIT = 200


def _tool(text, tip='', menu=None):
    button = QToolButton()
    button.setText(text)
    button.setToolTip(tip)
    button.setProperty('flat', True)
    if menu is not None:
        button.setMenu(menu)
        button.setPopupMode(QToolButton.InstantPopup)
        button.setProperty('menu', True)
    return button


class SheetEditor(QWidget):
    import_history_requested = Signal()
    changed = Signal()
    finding_selected = Signal(int, str)
    preview_requested = Signal(int)
    history_changed = Signal()       # undo/redo availability moved
    restored = Signal()              # undo/redo replaced project state (logos, arrangements…)
    open_requested = Signal()        # empty state: open a sheet
    link_requested = Signal()        # empty state: paste a Google Sheets link
    blank_requested = Signal()       # empty state: start from blank rows
    dismissed_changed = Signal()     # a finding was dismissed or dismissals were restored

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.findings = []
        self.finding_index = -1
        self._resume_error_row = None
        self._error_cells = {}
        self._navigating_error = False
        self._loading = False
        self._band_rows = set()
        self._undo, self._redo = [], []
        self._last_state = None

        self.table = ArrangementTable(project)
        self.table.setHorizontalHeaderLabels(['B · Role / list / logo', 'C · Header / song', 'D · Names'])
        self.table.tooltip_for = self.cell_tooltip

        # ---- row 1: things you do to the sheet -----------------------------
        insert_menu = QMenu(self)
        insert_menu.addAction('Row above', lambda: self.insert_rows(above=True))
        insert_menu.addAction('Row below', lambda: self.insert_rows(above=False))
        insert_menu.addAction('Insert rows above…', lambda: self.insert_rows_dialog(above=True))
        insert_menu.addAction('Insert rows below…', lambda: self.insert_rows_dialog(above=False))
        insert_menu.addSeparator()
        insert_menu.addAction('Delete rows', self.delete_rows)
        layout_menu = QMenu(self)
        for kind, label in LAYOUT_SHORT.items():
            layout_menu.addAction(label, lambda k=kind: self._apply_layout_to_selection(k))
        more_menu = QMenu(self)
        self.show_in_preview = QAction('Show in preview', self)
        self.show_in_preview.setEnabled(False)
        self.show_in_preview.triggered.connect(self.request_preview)
        self.follow_selection = QAction('Preview follows selection', self, checkable=True)
        self.follow_selection.setChecked(True)
        self.follow_selection.toggled.connect(lambda on: self.request_preview() if on else None)
        more_menu.addAction(self.follow_selection)
        more_menu.addAction(self.show_in_preview)
        more_menu.addSeparator()
        self.restore_action = more_menu.addAction('Restore dismissed problems', self.restore_dismissed)
        self.clear_marks_action = more_menu.addAction('Clear change marks', self.clear_change_marks)
        more_menu.aboutToShow.connect(self._sync_more_menu)
        more_menu.addSeparator()
        more_menu.addAction('Export CSV…', self.export_csv)

        logos_button = _tool('Logos…', 'Add logo artwork as a new row, or append to the selected logo row')
        logos_button.clicked.connect(self.add_logos)
        self.arrange_button = _tool('Side by side…', 'Set the selected groups next to each other in columns.\n'
                                    'Select rows across two or more groups (blank rows separate groups).')
        actions = QHBoxLayout()
        actions.setSpacing(4)
        actions.addWidget(_tool('Rows', 'Insert or delete rows', insert_menu))
        actions.addWidget(logos_button)
        actions.addWidget(_tool('Layout', 'How rows with only column B filled are set', layout_menu))
        actions.addWidget(self.arrange_button)
        actions.addStretch(1)
        self.expand_button = _tool('Expand', 'Show the spreadsheet full screen')
        actions.addWidget(self.expand_button)
        actions.addWidget(_tool('···', 'More', more_menu))

        # ---- row 2: find and review ----------------------------------------
        self.search = QLineEdit()
        self.search.setPlaceholderText('Find')
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(lambda: self.find_next(self.search.text()))
        self.search.setToolTip('Find text in the credits — Enter for the next match')
        self.errors_chip = _tool('', 'Show only rows with problems')
        self.errors_chip.setCheckable(True)
        self.errors_chip.toggled.connect(self._apply_filter)
        self.previous_error = _tool('‹', 'Previous problem')
        self.next_error = _tool('›', 'Next problem')
        self.previous_error.clicked.connect(lambda: self.step_error(-1))
        self.next_error.clicked.connect(lambda: self.step_error(1))
        review = QHBoxLayout()
        review.setSpacing(4)
        self.changes_chip = _tool('', 'Show only the rows changed by the last update from a revised sheet')
        self.changes_chip.setCheckable(True)
        self.changes_chip.setVisible(False)
        self.changes_chip.toggled.connect(self._apply_filter)
        review.addWidget(self.search, 1)
        review.addWidget(self.changes_chip)
        review.addWidget(self.errors_chip)
        review.addWidget(self.previous_error)
        review.addWidget(self.next_error)

        self.finding_note = QLabel()
        self.finding_note.setWordWrap(True)
        self.dismiss_button = _tool('Dismiss', "I've checked this — stop flagging it.\n"
                                    'It comes back if the text changes; restore dismissed problems under ···.')
        self.dismiss_button.clicked.connect(lambda: self.dismiss())
        self._finding_bar = QWidget()
        self._finding_bar.setObjectName('findingNote')
        self._finding_bar.setAttribute(Qt.WA_StyledBackground, True)
        note_row = QHBoxLayout(self._finding_bar)
        note_row.setContentsMargins(9, 3, 3, 3)
        note_row.addWidget(self.finding_note, 1)
        note_row.addWidget(self.dismiss_button)
        self._finding_bar.setVisible(False)

        toolbar = QWidget()
        toolbar.setObjectName('toolbar')
        toolbar.setAttribute(Qt.WA_StyledBackground, True)
        bar = QVBoxLayout(toolbar)
        bar.setContentsMargins(8, 8, 8, 8)
        bar.setSpacing(6)
        self.import_label = QLabel()
        self.import_label.setWordWrap(True)
        self.import_label.setProperty('role', 'caption')
        history_button = _tool('Import history…', 'See which spreadsheets were brought into this project and when')
        history_button.clicked.connect(self.import_history_requested)
        source_row = QHBoxLayout()
        source_row.addWidget(self.import_label, 1)
        source_row.addWidget(history_button)
        bar.addLayout(source_row)
        bar.addLayout(actions)
        bar.addLayout(review)
        bar.addWidget(self._finding_bar)
        self._toolbar = toolbar

        # ---- empty state -----------------------------------------------------
        empty = QWidget()
        box = QVBoxLayout(empty)
        box.addStretch(2)
        title = QLabel('No credits yet')
        title.setObjectName('emptyTitle')
        title.setAlignment(Qt.AlignCenter)
        hint = QLabel('Open the credits sheet (.csv or .xlsx), drop it or a Google Sheets link on the window,\n'
                      'or start from a blank sheet and type or paste.')
        hint.setProperty('role', 'caption')
        hint.setAlignment(Qt.AlignCenter)
        open_button = QPushButton('Open sheet…')
        open_button.setProperty('primary', True)
        open_button.clicked.connect(self.open_requested)
        link_button = QPushButton('Google Sheet…')
        link_button.setToolTip('Paste the link of a sheet shared as "Anyone with the link can view"')
        link_button.clicked.connect(self.link_requested)
        blank_button = QPushButton('Start blank')
        blank_button.clicked.connect(self.blank_requested)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(open_button)
        buttons.addWidget(link_button)
        buttons.addWidget(blank_button)
        buttons.addStretch(1)
        box.addWidget(title)
        box.addWidget(hint)
        box.addSpacing(8)
        box.addLayout(buttons)
        box.addStretch(3)

        self._stack = QStackedLayout()
        self._stack.addWidget(empty)
        self._stack.addWidget(self.table)
        body = QWidget()
        body.setLayout(self._stack)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(toolbar)
        layout.addWidget(body, 1)

        self.table.currentCellChanged.connect(self._preview_selection_changed)
        self.arrange_button.clicked.connect(lambda: self.arrange_dialog())
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.cellChanged.connect(self._cell_changed)
        self.table.cellClicked.connect(self._cell_clicked)
        self.table.customContextMenuRequested.connect(
            lambda pos: self._context_menu(self.table.viewport().mapToGlobal(pos)))
        self.table.verticalHeader().customContextMenuRequested.connect(
            lambda pos: self._context_menu(self.table.verticalHeader().mapToGlobal(pos)))
        self.table.clear_requested.connect(self.clear_cells)
        self.table.copy_requested.connect(self.copy)
        self.table.cut_requested.connect(self.cut)
        self.table.paste_requested.connect(self.paste)
        self.clear_errors('')
        self._sync_empty()

    # ---- rows in and out -----------------------------------------------------

    def load(self, rows):
        """Replace the sheet (a new file or project): history starts over."""
        self.table.change_marks[:] = []
        self._fill(rows)
        self._sync_changes_chip()
        self._undo, self._redo = [], []
        self._last_state = self._state()
        self.history_changed.emit()

    def _fill(self, rows):
        self._resume_error_row = None
        self.clear_errors()
        self._loading = True
        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.clearSpans()
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c in range(3):
                self.table.setItem(r, c, QTableWidgetItem(row[c] if c < len(row) else ''))
        self.table.resizeRowsToContents()
        self.table.blockSignals(False)
        self._loading = False
        self._band_rows = {a['start'] for a in self.project.arrangements}
        self._sync_empty()
        self.refresh_arrangements()

    def rows(self):
        return [[self.table.item(r, c).text() if self.table.item(r, c) else ''
                 for c in range(3)] for r in range(self.table.rowCount())]

    def _sync_empty(self):
        has_rows = self.table.rowCount() > 0
        self._stack.setCurrentIndex(1 if has_rows else 0)
        self._toolbar.setEnabled(has_rows)

    def _cell_changed(self, row, col):
        """One cell was edited in place: findings elsewhere are still valid."""
        self.table.resizeRowToContents(row)
        self._changed(touched_rows={row})

    def _changed(self, *_, touched_rows=None):
        """The credits changed. `touched_rows` set = content only (row numbers
        still line up, so other findings stay); None = structure changed."""
        if touched_rows is None:
            self.clear_errors()
        else:
            self._drop_findings(touched_rows)
        self.project.rows = self.rows()
        self.table.sync_centered_rows()
        self._sync_empty()
        self.commit_undo()
        self.table.viewport().update()
        self._selection_changed()
        self.changed.emit()

    # ---- undo ----------------------------------------------------------------

    def _ranges(self):
        """Every list of {start, end} row ranges that must follow inserted and deleted rows."""
        return (self.project.arrangements, self.project.overrides, self.project.import_notes,
                self.table.change_marks)

    def _state(self):
        p = self.project
        return json.dumps([self.rows(), p.arrangements, p.overrides, p.logos, p.logo_settings,
                           p.dismissed, p.import_notes, p.base_rows, self.table.change_marks])

    def commit_undo(self):
        """Record a step if anything undoable changed since the last one."""
        state = self._state()
        if self._last_state is None:
            self._last_state = state
        elif state != self._last_state:
            self._undo.append(self._last_state)
            del self._undo[:-UNDO_LIMIT]
            self._redo.clear()
            self._last_state = state
            self.history_changed.emit()

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def undo(self):
        if self._undo:
            self._redo.append(self._last_state)
            self._restore(self._undo.pop())

    def redo(self):
        if self._redo:
            self._undo.append(self._last_state)
            self._restore(self._redo.pop())

    def _restore(self, state):
        rows, arrangements_, overrides, logos, logo_settings, dismissed, notes, base_rows, marks = json.loads(state)
        current = (self.table.currentRow(), self.table.currentColumn())
        p = self.project
        p.arrangements[:] = arrangements_
        p.overrides[:] = overrides
        p.dismissed[:] = dismissed
        p.import_notes[:] = notes
        p.base_rows = base_rows
        self.table.change_marks[:] = marks
        p.logos.clear()
        p.logos.update(logos)
        p.logo_settings.clear()
        p.logo_settings.update(logo_settings)
        self._fill(rows)
        p.rows = rows
        self._last_state = state
        if rows:
            self._loading = True
            self.table.setCurrentCell(min(max(0, current[0]), len(rows) - 1), max(0, current[1]))
            self._loading = False
        self._sync_changes_chip()
        self.history_changed.emit()
        self.restored.emit()
        self.changed.emit()

    # ---- clipboard -------------------------------------------------------------

    def _selection_bounds(self):
        """(top, left, bottom, right) of everything selected, or the current cell."""
        indexes = self.table.selectedIndexes()
        if not indexes:
            row, col = self.table.currentRow(), self.table.currentColumn()
            return (row, col, row, col) if row >= 0 else None
        rows = [i.row() for i in indexes]
        cols = [i.column() for i in indexes]
        return min(rows), min(cols), max(rows), max(cols)

    def copy(self):
        bounds = self._selection_bounds()
        if bounds is None:
            return
        top, left, bottom, right = bounds
        data = self.rows()
        out = io.StringIO()
        # excel-tab quotes cells that contain line breaks, which is what Sheets and Excel expect.
        csv.writer(out, dialect='excel-tab', lineterminator='\n').writerows(
            [data[r][left:right + 1] for r in range(top, bottom + 1)])
        QGuiApplication.clipboard().setText(out.getvalue().rstrip('\n'))

    def cut(self):
        self.copy()
        self.clear_cells()

    def clear_cells(self):
        cells = [(i.row(), i.column()) for i in self.table.selectedIndexes()]
        cells = [(r, c) for r, c in cells if self.table.item(r, c) and self.table.item(r, c).text()]
        self._set_cells({cell: '' for cell in cells})

    def paste(self, text=None):
        text = QGuiApplication.clipboard().text() if text is None else text
        bounds = self._selection_bounds()
        if not text or bounds is None:
            return
        data = list(csv.reader(io.StringIO(text), dialect='excel-tab'))
        while data and not any(data[-1]):
            data.pop()
        if not data:
            return
        top, left, _, _ = bounds
        values = {}
        if len(data) == 1 and len(data[0]) == 1:
            # One value into a selection fills it, as in a spreadsheet.
            for index in self.table.selectedIndexes() or [self.table.currentIndex()]:
                values[(index.row(), index.column())] = data[0][0]
        else:
            for r, line in enumerate(data):
                for c, value in enumerate(line):
                    if left + c < 3:
                        values[(top + r, left + c)] = value
        if not values:
            return
        self._set_cells(values)
        rows = [r for r, _ in values]
        cols = [c for _, c in values]
        self.table.clearSelection()
        self.table.setRangeSelected(QTableWidgetSelectionRange(min(rows), min(cols), max(rows), max(cols)), True)

    def _set_cells(self, values):
        """Write many cells as one edit (one undo step, one rebuild)."""
        if not values:
            return
        last = max(r for r, _ in values)
        grew = last >= self.table.rowCount()
        self.table.blockSignals(True)
        if grew:
            old = self.table.rowCount()
            self.table.setRowCount(last + 1)
            for r in range(old, last + 1):
                for c in range(3):
                    self.table.setItem(r, c, QTableWidgetItem(''))
        for (r, c), value in values.items():
            item = self.table.item(r, c)
            if item is None:
                item = QTableWidgetItem('')
                self.table.setItem(r, c, item)
            item.setText(ingest._cell(value))
        rows = {r for r, _ in values}
        for r in rows:
            self.table.resizeRowToContents(r)
        self.table.blockSignals(False)
        self._changed(touched_rows=None if grew else rows)

    # ---- rows ----------------------------------------------------------------

    def _selected_rows(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows and self.table.currentRow() >= 0:
            rows = [self.table.currentRow()]
        return rows

    def _select_cell(self, row, col):
        """Move the cursor without the preview chasing it."""
        self._loading = True
        self.table.setCurrentCell(row, col)
        self._loading = False

    def insert_rows_dialog(self, above=False):
        direction = 'above' if above else 'below'
        count, accepted = QInputDialog.getInt(
            self, f'Insert rows {direction}', 'Number of blank rows:',
            max(1, len(self._selected_rows())), 1, 10000, 1)
        if accepted:
            self.insert_rows(above=above, count=count)

    def insert_rows(self, above=False, count=None):
        """Insert a custom count, or as many rows as selected, in one undo step."""
        rows = self._selected_rows()
        count = max(1, len(rows)) if count is None else count
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError('The row count must be a positive whole number.')
        at = (rows[0] if above else rows[-1] + 1) if rows else self.table.rowCount()
        col = max(0, self.table.currentColumn())
        self.table.blockSignals(True)
        for _ in range(count):
            for ranges in self._ranges():
                arrangements.insert_row(ranges, at)
            self.table.insertRow(at)
            for c in range(3):
                self.table.setItem(at, c, QTableWidgetItem(''))
        self.table.blockSignals(False)
        self._select_cell(at, col)
        self._changed()

    def insert_row(self):
        self.insert_rows(above=False)

    def delete_rows(self):
        rows = sorted(self._selected_rows(), reverse=True)
        if not rows:
            return
        col = max(0, self.table.currentColumn())
        for ranges in self._ranges():
            arrangements.delete_rows(ranges, rows)
        self.table.blockSignals(True)
        for row in rows:
            self.table.removeRow(row)
        self.table.blockSignals(False)
        if self.table.rowCount():
            self._select_cell(min(rows[-1], self.table.rowCount() - 1), col)
        self._changed()

    # ---- logos -----------------------------------------------------------------

    def add_logo_paths(self, paths):
        """Append to a selected logo row, otherwise insert a new row after selection."""
        if not paths:
            return
        rows = self.rows()
        row = self.table.currentRow()
        labels = ingest.logo_labels(rows[row][0] or rows[row][1]) if row >= 0 and not rows[row][2] else []
        if not labels:
            row = row + 1 if row >= 0 else len(rows)
            for ranges in self._ranges():
                arrangements.insert_row(ranges, row)
            rows.insert(row, ['', '', ''])
        used = {label for b, c, d in rows for label in ingest.logo_labels(b or c)} | set(self.project.logos)
        for path in paths:
            base = Path(path).stem.replace('|', '-').replace('[', '').replace(']', '') or 'Logo'
            label, n = base, 2
            while label in used:
                label = f'{base} {n}'
                n += 1
            used.add(label)
            labels.append(label)
            self.project.logos[label] = str(Path(path).resolve())
        rows[row] = [' | '.join(f'[Logo: {label}]' for label in labels), '', '']
        self._fill(rows)
        self._select_cell(row, 0)
        self._changed()

    def add_logos(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Add logos side by side', '',
                                               'Images (*.png *.tif *.tiff *.jpg *.jpeg)')
        self.add_logo_paths(paths)

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export edited credits', 'credits-edited.csv', 'CSV (*.csv)')
        if not path:
            return
        if not path.lower().endswith('.csv'):
            path += '.csv'
        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                csv.writer(f).writerows([[''] + row for row in self.rows()])
        except OSError as e:
            QMessageBox.critical(self, 'Cannot export credits', str(e))

    # ---- find --------------------------------------------------------------------

    def focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def find_next(self, text, direction=1):
        """Select the next cell containing `text` (case-insensitive), wrapping around."""
        needle = text.strip().lower()
        total = self.table.rowCount() * 3
        if not needle or not total:
            return False
        start = max(0, self.table.currentRow()) * 3 + max(0, self.table.currentColumn())
        data = self.rows()
        for step in range(1, total + 1):
            index = (start + direction * step) % total
            row, col = divmod(index, 3)
            if needle in data[row][col].lower():
                self.table.setRowHidden(row, False)
                self.table.clearSelection()
                self._select_cell(row, col)
                self.table.scrollToItem(self.table.item(row, col), QAbstractItemView.PositionAtCenter)
                self.preview_requested.emit(row + 1)
                return True
        return False

    # ---- context menu ------------------------------------------------------------

    def _context_menu(self, global_pos):
        if not self.table.rowCount():
            return
        menu = QMenu(self)
        menu.addAction('Cut', self.cut, QKeySequence.Cut)
        menu.addAction('Copy', self.copy, QKeySequence.Copy)
        menu.addAction('Paste', self.paste, QKeySequence.Paste)
        menu.addAction('Clear', self.clear_cells)
        flagged = self._selected_finding_indices()
        if flagged:
            menu.addSeparator()
            label = 'Dismiss problem' if len(flagged) == 1 else f'Dismiss {len(flagged)} problems'
            menu.addAction(label, lambda: self.dismiss(flagged))
        menu.addSeparator()
        count = max(1, len(self._selected_rows()))
        plural = f'{count} rows' if count > 1 else 'row'
        menu.addAction(f'Insert {plural} above', lambda: self.insert_rows(above=True))
        menu.addAction(f'Insert {plural} below', lambda: self.insert_rows(above=False))
        menu.addAction('Insert rows above…', lambda: self.insert_rows_dialog(above=True))
        menu.addAction('Insert rows below…', lambda: self.insert_rows_dialog(above=False))
        menu.addAction(f'Delete {plural}', self.delete_rows)
        menu.addSeparator()
        layout = menu.addMenu('Layout')
        current = self.override_at(self.table.currentRow())
        for kind, label in LAYOUT_SHORT.items():
            action = layout.addAction(label, lambda k=kind: self._apply_layout_to_selection(k))
            action.setCheckable(True)
            action.setChecked((current['kind'] if current else 'auto') == kind)
        if self.current_arrangement() is not None:
            menu.addAction('Edit side-by-side arrangement…', lambda: self.arrange_dialog(edit=True))
            menu.addAction('Remove arrangement', self.remove_arrangement)
        else:
            menu.addAction('Arrange side by side…', lambda: self.arrange_dialog())
        menu.addAction('Add logos…', self.add_logos)
        menu.addSeparator()
        menu.addAction(self.show_in_preview)
        menu.exec(global_pos)

    def cell_tooltip(self, row, col):
        tips = []
        current = self.table.arrangement_at(row)
        if current:
            tips.append(f"{current.get('label', 'Side by side')} · {current['columns']} columns")
        override = self.override_at(row)
        if override:
            tips.append(f"Layout: {LAYOUT_LABELS[override['kind']]}")
        mark = next((m for m in self.table.change_marks if m['start'] <= row <= m['end']), None)
        if mark:
            tips.append('Changed by the last sheet update' + (f" — was: {mark['was']}" if mark.get('was') else ''))
        tips += [self.findings[i].message for i in self._error_cells.get((row, col), [])]
        return '\n'.join(tips)

    # ---- layout overrides ----------------------------------------------------------

    def override_at(self, row):
        return next((o for o in self.project.overrides if o['start'] <= row <= o['end']), None)

    def _apply_layout_to_selection(self, kind):
        try:
            self.apply_layout(self._selected_rows(), kind)
        except ValueError as error:
            QMessageBox.information(self, 'Cannot set layout', str(error))

    def apply_layout(self, selected_rows, kind):
        """Mark rows as roles / list / center, or 'auto' to clear. Existing
        overrides are cut around the selection; adjacent same-kind runs merge."""
        selected = sorted(set(selected_rows))
        if not selected:
            raise ValueError('Select the rows to change first.')
        if kind not in ('auto',) + ingest.LAYOUT_KINDS:
            raise ValueError(f'Unknown layout {kind!r}.')
        rows = self.rows()
        if kind != 'auto' and not any(rows[r][0] and not rows[r][1] and not rows[r][2]
                                      for r in selected if r < len(rows)):
            raise ValueError('Layout overrides apply to rows with only column B filled '
                             '(roles or names with nothing in C or D).')
        chosen = set(selected)
        pieces = []
        for item in self.project.overrides:
            run = []
            for r in range(item['start'], item['end'] + 1):
                if r in chosen:
                    if run:
                        pieces.append(dict(start=run[0], end=run[-1], kind=item['kind']))
                        run = []
                else:
                    run.append(r)
            if run:
                pieces.append(dict(start=run[0], end=run[-1], kind=item['kind']))
        if kind != 'auto':
            start = selected[0]
            for a, b in zip(selected, selected[1:] + [None]):
                if b != a + 1:
                    pieces.append(dict(start=start, end=a, kind=kind))
                    start = b
        pieces.sort(key=lambda o: o['start'])
        merged = []
        for piece in pieces:
            if merged and merged[-1]['kind'] == piece['kind'] and merged[-1]['end'] + 1 >= piece['start']:
                merged[-1]['end'] = max(merged[-1]['end'], piece['end'])
            else:
                merged.append(piece)
        self.project.overrides[:] = merged
        self._changed()

    # ---- side-by-side arrangements -------------------------------------------------

    def current_arrangement(self):
        row = self.table.currentRow()
        return next((a for a in self.project.arrangements if a['start'] <= row <= a['end']), None)

    def _selection_changed(self):
        current = self.current_arrangement()
        self.arrange_button.setText('Edit side by side…' if current is not None else 'Side by side…')

    def refresh_arrangements(self):
        """Arrangements, overrides or findings changed: repaint, and re-measure
        the rows whose height depends on an arrangement's label band."""
        self.table.sync_centered_rows()
        self.table.error_cells = set(self._error_cells)
        self.table.error_severity = {
            cell: ('error' if any(self.findings[i].severity == 'error' for i in indices)
                   else self.findings[indices[0]].severity)
            for cell, indices in self._error_cells.items()}
        starts = {a['start'] for a in self.project.arrangements}
        if starts != self._band_rows:
            for row in starts | self._band_rows:
                if row < self.table.rowCount():
                    self.table.resizeRowToContents(row)
            self._band_rows = starts
        self.table.viewport().update()
        self._selection_changed()

    def arrangement_boundaries(self):
        return {row for item in self.project.arrangements for row in (item["start"], item["end"] + 1)}

    def apply_arrangement(self, selected_rows, columns=2, gap=120, alignment='center', label='Side by side', existing=None):
        start, end, count = arrangements.selection_range(self.rows(), selected_rows, self.arrangement_boundaries())
        for item in self.project.arrangements:
            if item is not existing and not (end < item['start'] or start > item['end']):
                raise ValueError('This selection overlaps an existing arrangement. Edit or remove that arrangement first.')
        if not 2 <= columns <= 6 or gap < 0 or alignment not in ('center', 'left'):
            raise ValueError('Choose 2–6 columns, a non-negative gap, and left or center alignment.')
        width = min(self.project.look.width * .9,
                    2 * min(self.project.look.center_x, self.project.look.width - self.project.look.center_x))
        if (width - (columns - 1) * gap) / columns < 200:
            raise ValueError('The columns would be too narrow. Use fewer columns or a smaller gap.')
        value = dict(start=start, end=end, columns=columns, gap=gap, alignment=alignment,
                     label=label.strip() or 'Side by side')
        if existing is not None:
            existing.update(value)
        else:
            self.project.arrangements.append(value)
        self.project.arrangements.sort(key=lambda a: a['start'])
        self._changed()
        return value

    def arrange_dialog(self, edit=False):
        current = self.current_arrangement()
        edit = edit or current is not None
        selected = (list(range(current['start'], current['end'] + 1)) if current is not None
                    else sorted({index.row() for index in self.table.selectedIndexes()}))
        try:
            start, end, count = arrangements.selection_range(self.rows(), selected, self.arrangement_boundaries())
        except ValueError as error:
            QMessageBox.information(self, 'Select credit groups', str(error))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Edit arrangement' if edit else 'Arrange side by side')
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f'{count} complete blocks · rows {start + 1}–{end + 1}\n'
                                'Blocks fill left to right, then continue on the next row.'))
        form = QFormLayout()
        name = QLineEdit(current.get('label', 'Side by side') if current else 'Side by side')
        columns = _spin(2, 6, '')
        columns.setValue(current['columns'] if current else 2)
        gap = _spin(0, 1000, ' px')
        gap.setValue(current['gap'] if current else 120)
        alignment = QComboBox()
        alignment.addItem('Centered text', 'center')
        alignment.addItem('Left-aligned text', 'left')
        alignment.setCurrentIndex(1 if current and current['alignment'] == 'left' else 0)
        for label, widget in [('Label', name), ('Columns', columns), ('Column gap', gap), ('Text alignment', alignment)]:
            form.addRow(label, widget)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        if current is not None:
            remove = buttons.addButton('Remove', QDialogButtonBox.DestructiveRole)
            remove.clicked.connect(lambda: (self.remove_arrangement(), dialog.reject()))
        def accept():
            try:
                self.apply_arrangement(selected, columns.value(), gap.value(), alignment.currentData(), name.text(), current)
            except ValueError as error:
                QMessageBox.information(dialog, 'Cannot arrange these rows', str(error))
                return
            dialog.accept()
        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def remove_arrangement(self):
        current = self.current_arrangement()
        if current is not None:
            self.project.arrangements.remove(current)
            self._changed()

    # ---- findings -----------------------------------------------------------------

    def clear_errors(self, message='Checking…'):
        self.findings = []
        self.finding_index = -1
        self._error_cells = {}
        self.table.error_cells = set()
        self.table.error_severity = {}
        self._set_chip(message, '')
        self.previous_error.setEnabled(False)
        self.next_error.setEnabled(False)
        self._finding_bar.setVisible(False)
        self._apply_filter()
        self.refresh_arrangements()

    def _drop_findings(self, rows):
        """Forget findings on edited rows; the rest still point at the right cells."""
        sheet_rows = {r + 1 for r in rows}
        if any(f.row in sheet_rows for f in self.findings):
            self.set_findings([f for f in self.findings if f.row not in sheet_rows])

    def _set_chip(self, text, level):
        self.errors_chip.setText(text)
        self.errors_chip.setVisible(bool(text))
        if self.errors_chip.property('chip') != level:
            self.errors_chip.setProperty('chip', level)
            self.errors_chip.style().unpolish(self.errors_chip)
            self.errors_chip.style().polish(self.errors_chip)

    def _apply_filter(self, *_):
        """Hide rows that fail the active chips: problems only, changed rows only, or both."""
        only_problems = self.errors_chip.isChecked() and bool(self.findings)
        only_changed = self.changes_chip.isChecked() and bool(self.table.change_marks)
        problem_rows = {f.row - 1 for f in self.findings}
        for row in range(self.table.rowCount()):
            hidden = (only_problems and row not in problem_rows) or \
                     (only_changed and not self.table.changed_at(row))
            if self.table.isRowHidden(row) != hidden:
                self.table.setRowHidden(row, hidden)

    # ---- dismissing ----------------------------------------------------------------

    def _selected_finding_indices(self):
        cells = {(i.row(), i.column()) for i in self.table.selectedIndexes()}
        if self.table.currentRow() >= 0:
            cells.add((self.table.currentRow(), self.table.currentColumn()))
        return sorted({i for cell in cells for i in self._error_cells.get(cell, []) if self.findings[i].key})

    def dismiss(self, indices=None):
        """Stop flagging these findings (default: the one being shown). Stored by
        what the finding is about, so it holds as rows move and lapses if the
        text changes. Steps on to the next problem."""
        if indices is None:
            indices = [self.finding_index] if 0 <= self.finding_index < len(self.findings) else []
        keys = {self.findings[i].key for i in indices if self.findings[i].key}
        if not keys:
            return
        position = min(indices)
        self.project.dismissed.extend(k for k in sorted(keys) if k not in self.project.dismissed)
        self.finding_index = -1
        self.set_findings([f for f in self.findings if f.key not in keys])
        self.commit_undo()
        self.dismissed_changed.emit()
        if self.findings:
            self.focus_error(min(position, len(self.findings) - 1))

    def restore_dismissed(self):
        if self.project.dismissed:
            self.project.dismissed[:] = []
            self.commit_undo()
            self.dismissed_changed.emit()
            self.changed.emit()          # re-check so they come back

    def _sync_more_menu(self):
        n = len(self.project.dismissed)
        self.restore_action.setText(f'Restore {n} dismissed problem{"s" if n != 1 else ""}' if n
                                    else 'Restore dismissed problems')
        self.restore_action.setEnabled(bool(n))
        self.clear_marks_action.setEnabled(bool(self.table.change_marks))

    # ---- updating from a revised sheet -----------------------------------------------

    def apply_update(self, new_rows, accepted, notes=()):
        """Merge the client's accepted changes in as one undoable step.

        Row ranges (arrangements, layout overrides, import notes) follow the
        rows; the changed rows are marked for review; `new_rows` becomes the
        snapshot the next revision is compared against.
        """
        from .. import changes
        rows, shifts, marks = changes.apply(self.rows(), accepted)
        self.table.change_marks[:] = []
        for ranges in (self.project.arrangements, self.project.overrides, self.project.import_notes):
            changes.replay(ranges, shifts)
        # What each marked row used to say, for its tooltip.
        ordered = sorted(accepted, key=lambda c: (c.start, c.end))
        with_new = [c for c in ordered if c.new]
        self.table.change_marks[:] = [
            dict(start=a, end=b, was=' / '.join(changes.row_text(r) for r in c.old) if c.old else '')
            for (a, b), c in zip(marks, with_new)]
        # Import notes from the revised sheet apply to the rows that came from it.
        for note in notes:
            for (a, b), c in zip(marks, with_new):
                if c.sheet_row - 1 <= note['start'] < c.sheet_row - 1 + len(c.new):
                    at = a + note['start'] - (c.sheet_row - 1)
                    self.project.import_notes.append(dict(start=at, end=at, message=note['message']))
        self.project.base_rows = [list(r) for r in new_rows]
        self._fill(rows)
        self._sync_changes_chip()
        self._changed()

    def clear_change_marks(self):
        if self.table.change_marks:
            self.table.change_marks[:] = []
            self.changes_chip.setChecked(False)
            self._sync_changes_chip()
            self.commit_undo()

    def _sync_changes_chip(self):
        n = sum(m['end'] - m['start'] + 1 for m in self.table.change_marks)
        self.changes_chip.setText(f"{n} changed row{'s' if n != 1 else ''}")
        self.changes_chip.setVisible(bool(n))
        if not n:
            self.changes_chip.setChecked(False)
        self._apply_filter()
        self.table.viewport().update()

    def _finding_cell(self, finding):
        row = finding.row - 1
        values = [self.table.item(row, col).text() if self.table.item(row, col) else '' for col in range(3)]
        target = finding.target
        if target in ('role', 'list'):
            col = 0
        elif target == 'header':
            col = 1
        elif target == 'logo':
            col = 0 if values[0] else 1
        elif target == 'name':
            col = 2 if values[2] or not values[1] else 1
        else:
            col = next((i for i, value in enumerate(values) if value), 0)
        # Music templates put names in C, including empty Produced by cells.
        if target == 'name' and not values[1] and not values[2]:
            for offset in (-1, 1):
                neighbor = row + offset
                if 0 <= neighbor < self.table.rowCount():
                    name = self.table.item(neighbor, 1)
                    role = self.table.item(neighbor, 0)
                    if name and name.text() and role and role.text():
                        col = 1
                        break
        return row, col

    def set_findings(self, findings):
        old = self.findings[self.finding_index] if 0 <= self.finding_index < len(self.findings) else None
        self.findings = [f for f in findings if 1 <= f.row <= self.table.rowCount()]
        self._error_cells = {}
        for index, finding in enumerate(self.findings):
            self._error_cells.setdefault(self._finding_cell(finding), []).append(index)
        self.finding_index = next((i for i, f in enumerate(self.findings) if f == old), -1)
        self.previous_error.setEnabled(bool(self.findings))
        self.next_error.setEnabled(bool(self.findings))
        self._finding_bar.setVisible(False)
        self._error_summary()
        self.refresh_arrangements()
        self._apply_filter()
        if self.finding_index >= 0:
            self._show_error_message()

    def _error_summary(self):
        if not self.findings:
            self._set_chip('No problems', '')
            return
        errors = sum(f.severity == 'error' for f in self.findings)
        possible = len(self.findings) - errors
        parts = []
        if errors:
            parts.append(f"{errors} error{'s' if errors != 1 else ''}")
        if possible:
            parts.append(f"{possible} warning{'s' if possible != 1 else ''}")
        position = f'   {self.finding_index + 1}/{len(self.findings)}' if self.finding_index >= 0 else ''
        self._set_chip(' · '.join(parts) + position, 'error' if errors else 'warning')

    def _show_error_message(self):
        finding = self.findings[self.finding_index]
        label = 'Error' if finding.severity == 'error' else 'Possible problem'
        self.finding_note.setText(f'{label} · Row {finding.row}: {finding.message}')
        self.dismiss_button.setVisible(bool(finding.key))
        self._finding_bar.setVisible(True)
        self._error_summary()

    def step_error(self, direction):
        if not self.findings:
            return
        if self.finding_index >= 0:
            index = (self.finding_index + direction) % len(self.findings)
        elif self._resume_error_row is not None:
            candidates = [i for i, finding in enumerate(self.findings)
                          if (finding.row >= self._resume_error_row if direction > 0
                              else finding.row <= self._resume_error_row)]
            index = (candidates[0] if direction > 0 else candidates[-1]) if candidates else (0 if direction > 0 else len(self.findings)-1)
        else:
            index = 0 if direction > 0 else len(self.findings)-1
        self.focus_error(index)

    def focus_error(self, index):
        if not 0 <= index < len(self.findings):
            return
        self.finding_index = index
        self._resume_error_row = self.findings[index].row
        row, col = self._finding_cell(self.findings[index])
        self._navigating_error = True
        self.table.setRowHidden(row, False)
        self.table.clearSelection()
        self.table.setCurrentCell(row, col)
        self.table.scrollToItem(self.table.item(row, col), QAbstractItemView.PositionAtCenter)
        self._navigating_error = False
        self._show_error_message()
        finding = self.findings[index]
        self.finding_selected.emit(finding.row, finding.message)

    def _error_clicked(self, row, col):
        if self._navigating_error:
            return False
        indices = self._error_cells.get((row, col), [])
        if indices:
            self.focus_error(indices[0])
        return bool(indices)

    def _cell_clicked(self, row, col):
        """A click snaps the preview to that row; on an error cell the finding
        drives the jump so its message shows as well."""
        if not self._error_clicked(row, col):
            self.preview_requested.emit(row + 1)

    def request_preview(self):
        row = self.table.currentRow()
        if row >= 0:
            self.preview_requested.emit(row + 1)

    def _preview_selection_changed(self, row, column, previous_row, previous_column):
        self.show_in_preview.setEnabled(row >= 0)
        if self._loading or self._navigating_error:
            return
        if self.follow_selection.isChecked() and row != previous_row:
            self.request_preview()
