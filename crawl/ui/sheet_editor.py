"""The Credits tab: the sheet's B/C/D cells, edited like a spreadsheet.

Edits live in the project (not the source file). Everything that changes the
credits funnels through `_changed()`, which records an undo step.
"""
import csv
import io
import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QItemSelectionModel
from PySide6.QtGui import QAction, QColor, QFontMetrics, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
                               QStackedLayout, QTableWidget, QTableWidgetItem, QTableWidgetSelectionRange, QToolButton,
                               QVBoxLayout, QWidget)

from .. import arrangements, ingest
from .arrangement_table import ArrangementTable
from .widgets import _spin, panel_expand_icon, resettable, default_look, FontPicker, ColorPicker

LAYOUT_LABELS = {
    'auto': 'Automatic (6+ rows become a list, fewer are roles)',
    'roles': 'Roles and names — two columns',
    'list': 'List in columns',
    'center': 'Centred lines',
    'center_name': 'Centered credit name',
    'legal': 'Legal text',
    'thanks': 'Special thanks',
    'heading': 'Section heading',
    'names_left': 'Names only — left aligned',
    'names_center': 'Names only — centered',
    'names_right': 'Names only — right aligned',
    'names_inward': 'Names only — facing the center gap',
}
LAYOUT_SHORT = {'auto': 'Automatic', 'roles': 'Roles / names (two columns)', 'list': 'List in columns',
                'heading': 'Section heading', 'center': 'Centred lines', 'legal': 'Legal text', 'thanks': 'Special thanks…', 'logo': 'Logo block…'}
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
    music_style_requested = Signal()
    logo_layout_requested = Signal(int)
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
        self._show_row_types = True
        self._row_types = []
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
        self.table.setHorizontalHeaderLabels(['B · Role / Text', 'C · Heading', 'D · Name'])
        for column,tip in enumerate([
            'Source column B: role / job title, names-only lists, general text, and logo blocks. Layout markings determine how it appears in the crawl.',
            'Source column C: section headings and song titles. Can also hold centered text or logo blocks, depending on the selected layout.',
            'Source column D: credit names, usually paired with a role in B. In names-only layouts, B and D both use the name style.',
        ]):
            self.table.horizontalHeaderItem(column).setToolTip(tip)
        self.table.tooltip_for = self.cell_tooltip

        # ---- row 1: things you do to the sheet -----------------------------
        insert_menu = QMenu(self)
        self._populate_rows_menu(insert_menu)
        layout_menu = QMenu(self)
        self._populate_layout_menu(layout_menu)
        more_menu = QMenu('Review', self)
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

        insert_menu.addSeparator()
        insert_menu.addMenu(more_menu)
        self.arrange_button = _tool('Side by side…', 'Set the selected groups next to each other in columns.\n'
                                    'Select rows across two or more groups (blank rows separate groups).')
        actions = QHBoxLayout()
        actions.setSpacing(4)
        actions.addWidget(_tool('Rows', 'Insert or delete rows', insert_menu))
        actions.addWidget(_tool('Layout', 'Choose section types, name-column layouts, music or logos', layout_menu))
        actions.addWidget(self.arrange_button)
        actions.addStretch(1)
        self.expand_button = _tool('', 'Expand spreadsheet')
        self.expand_button.setIcon(panel_expand_icon())
        self.expand_button.setAccessibleName('Expand spreadsheet')
        self.expand_button.setFocusPolicy(Qt.NoFocus)
        actions.addWidget(self.expand_button)

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
                                    'It comes back if the text changes; restore dismissed problems under Rows → Review.')
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
        self.import_label.setWordWrap(False)
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
        hint = QLabel('Import a credits sheet (.csv or .xlsx), drop it or a Google Sheets link on the window,\n'
                      'or start from a blank sheet and type or paste.')
        hint.setProperty('role', 'caption')
        hint.setAlignment(Qt.AlignCenter)
        open_button = QPushButton('Import Excel / CSV…')
        open_button.setProperty('primary', True)
        open_button.clicked.connect(self.open_requested)
        link_button = QPushButton('Import Google Sheet…')
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
        self.arrange_button.clicked.connect(self._edit_current_arrangement)
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
        self.refresh_row_types()

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
        self.refresh_row_types()
        self.table.sync_centered_rows()
        self._sync_empty()
        self.commit_undo()
        self.table.viewport().update()
        self._selection_changed()
        self.changed.emit()

    # ---- undo ----------------------------------------------------------------

    def _ranges(self):
        """Every list of {start, end} row ranges that must follow inserted and deleted rows."""
        return (self.project.arrangements, self.project.overrides, self.project.cell_formats, self.project.spacer_rows, self.project.import_notes, self.project.music_blocks, self.project.hidden_rows,
                self.table.change_marks)

    def _state(self):
        p = self.project
        return json.dumps([self.rows(), p.arrangements, p.overrides, p.logos, p.logo_settings,
                           p.dismissed, p.import_notes, p.base_rows, self.table.change_marks, p.music_blocks, p.hidden_rows, p.base_hidden_rows, p.cell_formats, p.spacer_rows])

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
        rows, arrangements_, overrides, logos, logo_settings, dismissed, notes, base_rows, marks, music_blocks, hidden_rows, base_hidden_rows, cell_formats, spacer_rows = json.loads(state)
        current = (self.table.currentRow(), self.table.currentColumn())
        p = self.project
        p.arrangements[:] = arrangements_
        p.overrides[:] = overrides
        p.cell_formats[:] = cell_formats
        p.spacer_rows[:] = spacer_rows
        p.music_blocks[:] = music_blocks
        p.hidden_rows[:] = hidden_rows
        p.base_hidden_rows[:] = base_hidden_rows
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
                if ranges is self.project.hidden_rows or ranges is self.project.spacer_rows:
                    ingest.insert_hidden_row(ranges, at)
                else:
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

    def add_logo_paths(self, paths, names=None):
        """Append to a selected logo row, otherwise insert a new row after selection."""
        if not paths:
            return
        from ..logo_import import prepare_logo
        original_paths=list(paths)
        paths=[prepare_logo(path) for path in original_paths]
        names=names or [Path(path).stem for path in original_paths]
        rows = self.rows()
        row = self.table.currentRow()
        labels = ingest.logo_labels(rows[row][0] or rows[row][1]) if row >= 0 and not rows[row][2] else []
        if not labels:
            row = row + 1 if row >= 0 else len(rows)
            for ranges in self._ranges():
                if ranges is self.project.hidden_rows or ranges is self.project.spacer_rows:
                    ingest.insert_hidden_row(ranges, row)
                else:
                    arrangements.insert_row(ranges, row)
            rows.insert(row, ['', '', ''])
        used = {label for b, c, d in rows for label in ingest.logo_labels(b or c)} | set(self.project.logos)
        for index, path in enumerate(paths):
            name = names[index] if names and index < len(names) else Path(path).stem
            base = name.replace('|', '-').replace('[', '').replace(']', '') or 'Logo'
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

    def remove_logo_labels(self, labels, start, end):
        """Remove selected slots, including placeholders, within one logo section."""
        labels = set(labels)
        rows = self.rows()
        if not labels or not (0 <= start <= end < len(rows)):
            return
        changed = False
        for row in range(start, end + 1):
            if rows[row][2]:
                continue
            current = ingest.logo_labels(rows[row][0] or rows[row][1])
            if not current or not labels.intersection(current):
                continue
            kept = [label for label in current if label not in labels]
            column = 0 if rows[row][0] else 1
            rows[row][column] = ' | '.join(f'[Logo: {label}]' for label in kept)
            changed = True
        if not changed:
            return
        remaining = {label for b,c,d in rows if not d for label in ingest.logo_labels(b or c)}
        for label in labels - remaining:
            self.project.logos.pop(label, None)
            self.project.logo_settings.pop(label, None)
        arrangements_ = []
        for item in self.project.arrangements:
            present = {label for r in range(max(0,item['start']),min(len(rows),item['end']+1))
                       if not rows[r][2] for label in ingest.logo_labels(rows[r][0] or rows[r][1])}
            if item.get('logo_grid') and not present:
                continue
            if 'logo_order' in item:
                item['logo_order'] = [label for label in item['logo_order'] if label in present]
            arrangements_.append(item)
        self.project.arrangements[:] = arrangements_
        self._fill(rows)
        self._select_cell(start,0)
        self._changed()

    def apply_logo_cells(self, cells, name=None, path=None):
        """Convert selected entries in place, without consuming neighboring text."""
        from ..music import without_rows
        rows = self.rows()
        cells = sorted(set(cells))
        if not cells or any(not (0 <= r < len(rows) and 0 <= c < 3) for r,c in cells):
            raise ValueError('Select the cell or cells to turn into logos first.')
        populated = [(r,c) for r,c in cells if rows[r][c].strip()]
        cells = populated or (cells if len(cells)==1 else [])
        if not cells:
            raise ValueError('Select text entries, or one empty cell for a new logo placeholder.')
        if (name is not None or path is not None) and len(cells)!=1:
            raise ValueError('Select one cell to choose a custom name or assign artwork.')
        selected = set(cells)
        chosen = {r for r,c in cells}
        for r in chosen:
            if any(rows[r][c].strip() and (r,c) not in selected for c in range(3)):
                raise ValueError('This row has other credit text. Select all entries on that row to turn them into logos, or move the logo to its own row first.')
        if any(block['start']<=r<=block['end'] for block in self.project.music_blocks for r in chosen):
            raise ValueError('Return this music block to automatic before turning its cells into logos.')
        if path and not Path(path).is_file():
            raise ValueError('The selected artwork file is no longer available.')
        if path:
            from ..logo_import import prepare_logo
            path=prepare_logo(path)
        outside = {label for r,row in enumerate(rows) if r not in chosen
                   for label in ingest.logo_labels(row[0] or row[1])}
        old = {label for r,c in cells for label in ingest.logo_labels(rows[r][c])}
        used = outside | (set(self.project.logos) - (old - outside))
        assigned = dict(self.project.logos)
        converted = {}
        for r,c in cells:
            existing = ingest.logo_labels(rows[r][c])
            if len(existing)>1 and (name is not None or path):
                raise ValueError('This cell already contains several logos. Edit them in the Logos tab.')
            values = [name] if name is not None else existing or [rows[r][c]]
            for value in values:
                base = str(value).replace('|','-').replace('[','').replace(']','').strip() or 'Logo'
                label = base
                n = 2
                while label in used:
                    label = f'{base} {n}'
                    n += 1
                used.add(label)
                converted.setdefault(r,[]).append(label)
                if path:
                    assigned[label] = str(Path(path).resolve())
                elif existing and value in self.project.logos:
                    assigned[label] = self.project.logos[value]
        for r,labels in converted.items():
            rows[r] = [' | '.join(f'[Logo: {label}]' for label in labels),'','']
        overrides = []
        for item in self.project.overrides:
            for piece in without_rows([item], chosen):
                if item['kind']=='thanks' and piece['start']!=item['start']:
                    piece['title']=False
                overrides.append(piece)
        self.project.overrides[:] = overrides
        self.project.logos.clear()
        self.project.logos.update(assigned)
        self._fill(rows)
        self._select_cell(min(chosen),0)
        self._changed()

    def logo_block_dialog(self):
        cells = sorted({(index.row(),index.column()) for index in self.table.selectedIndexes()})
        if not cells and self.table.currentRow()>=0:
            cells=[(self.table.currentRow(),max(0,self.table.currentColumn()))]
        rows=self.rows()
        populated=[(r,c) for r,c in cells if rows[r][c].strip()]
        cells=populated or cells
        if len(cells)>1 and not populated:
            QMessageBox.information(self,'Select a cell','Select one empty cell, or populated entries to turn into logos.')
            return
        if not cells:
            QMessageBox.information(self,'Select a cell','Select the cell to turn into a logo block first.')
            return
        single=len(cells)==1
        if single and len(ingest.logo_labels(rows[cells[0][0]][cells[0][1]]))>1:
            QMessageBox.information(self,'Multiple logos','This cell already contains multiple logos. Use the Logos tab to edit their artwork.')
            return
        dialog=QDialog(self)
        dialog.setWindowTitle('Convert to logo block')
        dialog.resize(490,230)
        layout=QVBoxLayout(dialog)
        note=QLabel('The selected entries become logo placeholders in their existing rows. No new rows are inserted. You can assign artwork now or later in Logos.')
        note.setWordWrap(True);layout.addWidget(note)
        name=QLineEdit()
        if single:
            value=rows[cells[0][0]][cells[0][1]]
            labels=ingest.logo_labels(value)
            name.setText(labels[0] if labels else value or 'Logo')
            form=QFormLayout();form.addRow('Logo name',name);layout.addLayout(form)
        artwork={'path':None}
        status=QLabel('No new artwork selected — keep a placeholder or existing artwork.')
        status.setWordWrap(True);layout.addWidget(status)
        if single:
            actions=QHBoxLayout()
            browse=QPushButton('Choose file…')
            library=QPushButton('Choose from logo library…')
            def choose_file():
                from ..logo_import import LOGO_FILTER
                from .logo_import import prepare_logo_files
                path,_=QFileDialog.getOpenFileName(dialog,'Logo artwork','',LOGO_FILTER)
                if path:
                    converted=prepare_logo_files(dialog,[path])
                    if converted:
                        artwork['path']=converted[0];status.setText(Path(path).name+(' → PNG' if Path(path).suffix.lower()=='.eps' else ''))
            def choose_library():
                from .logo_library_dialog import LogoLibraryDialog
                try:
                    picker=LogoLibraryDialog(self.project.logos,dialog)
                    if picker.exec()==QDialog.Accepted:
                        artwork['path']=picker.selected_paths[0]
                        status.setText(picker.selected_names[0])
                except (OSError,ValueError) as error:
                    QMessageBox.information(dialog,'Cannot open library',str(error))
            browse.clicked.connect(choose_file);library.clicked.connect(choose_library)
            actions.addWidget(browse);actions.addWidget(library);layout.addLayout(actions)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        def accept():
            try:
                self.apply_logo_cells(cells,name=name.text() if single else None,path=artwork['path'])
            except ValueError as error:
                QMessageBox.information(dialog,'Cannot convert to logos',str(error))
                return
            dialog.accept()
        buttons.accepted.connect(accept);buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons);dialog.exec()

    def add_logos(self):
        from .logo_library_dialog import LogoLibraryDialog
        try:
            dialog = LogoLibraryDialog(self.project.logos, self)
            if dialog.exec() == QDialog.Accepted:
                self.add_logo_paths(dialog.selected_paths, dialog.selected_names)
        except (OSError, ValueError) as error:
            QMessageBox.information(self, 'Cannot open logo library', str(error))

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

    def _populate_rows_menu(self, menu):
        above=menu.addAction('Insert row above',lambda:self.insert_rows(above=True))
        below=menu.addAction('Insert row below',lambda:self.insert_rows(above=False))
        menu.addAction('Insert rows above…',lambda:self.insert_rows_dialog(above=True))
        menu.addAction('Insert rows below…',lambda:self.insert_rows_dialog(above=False))
        menu.addSeparator()
        spacing=menu.addAction('Make empty rows visible as spacing',lambda:self.set_spacer_rows(True))
        clear_spacing=menu.addAction('Clear explicit spacing',lambda:self.set_spacer_rows(False))
        menu.addSeparator()
        delete=menu.addAction('Delete row',self.delete_rows)
        def update():
            count=max(1,len(self._selected_rows()))
            label='row' if count==1 else f'{count} rows'
            above.setText(f'Insert {label} above')
            below.setText(f'Insert {label} below')
            delete.setText(f'Delete {label}')
            rows=self.rows();selected=self._selected_rows();marked=ingest.hidden_indices(self.project.spacer_rows)
            spacing.setEnabled(any(not any(rows[row]) and row not in marked for row in selected))
            clear_spacing.setEnabled(bool(marked.intersection(selected)))
        menu.aboutToShow.connect(update)

    def set_spacer_rows(self, enabled):
        marked=ingest.hidden_indices(self.project.spacer_rows)
        selected=self._selected_rows();rows=self.rows()
        if enabled:
            marked.update(row for row in selected if not any(rows[row]))
        else:
            marked.difference_update(selected)
        self.project.spacer_rows[:]=ingest.hidden_ranges(ingest.SheetRows(hidden_rows=marked))
        self._changed()
        self._apply_filter()

    def _populate_layout_menu(self, menu, context=False):
        show_types=menu.addAction('Show row types')
        show_types.setVisible(not context)
        show_types.setCheckable(True);show_types.setChecked(self._show_row_types)
        show_types.setToolTip('Labels beside row numbers show how each row is interpreted. ✓ = manually marked; * = local text styling. Hover a row label for details.')
        show_types.toggled.connect(self.set_row_types_visible)
        menu.addSeparator()
        for kind,label in LAYOUT_SHORT.items():
            if kind=='list':
                continue
            action=menu.addAction(label,lambda checked=False,k=kind:self._apply_layout_to_selection(k))
            action.setCheckable(True);action.setData(kind)
        names = menu.addMenu('Name column layout')
        for alignment, label in [('left', 'Left'), ('center', 'Center'), ('right', 'Right'),('inward','Face center (like roles / names)')]:
            kind = 'names_' + alignment
            action = names.addAction(label, lambda checked=False, k=kind: self._apply_layout_to_selection(k))
            action.setCheckable(True); action.setData(kind)
            action.setToolTip('Treat each populated cell as a name, using the shared name font, size and line spacing')
        formatting = menu.addMenu('Text formatting')
        formatting.addAction('Format selected cells…', self.format_dialog)
        bold = formatting.addAction('Bold selected cells')
        bold.setCheckable(True)
        bold.triggered.connect(lambda checked=False: self.apply_bold(checked))
        formatting.addAction('Use section default', lambda: self.apply_cell_format({}, reset=True))
        def update_formatting():
            cells = [(i.row(), i.column()) for i in self.table.selectedIndexes() if i.data()]
            bold.setChecked(bool(cells) and all(any(f['start'] <= row <= f['end'] and f['column'] == column
                                                    and f.get('bold') for f in self.project.cell_formats)
                                                for row, column in cells))
        formatting.aboutToShow.connect(update_formatting)
        menu.addSeparator()
        music=menu.addAction('Music…',self.music_dialog)
        music.setCheckable(True);music.setData('music')
        library=menu.addAction('Logo library…',self.add_logos)
        library.setVisible(not context)
        menu.addSeparator()
        advanced=menu.addMenu('More layouts')
        action=advanced.addAction(LAYOUT_SHORT['list'],lambda:self._apply_layout_to_selection('list'))
        action.setCheckable(True);action.setData('list')
        def update():
            row=self.table.currentRow()
            current=self.override_at(row)
            data=self.rows()
            logo=0<=row<len(data) and not data[row][2] and ingest.logo_labels(data[row][0] or data[row][1])
            music=any(item['start']<=row<=item['end'] for item in self.project.music_blocks)
            kind='logo' if logo else current['kind'] if current else 'music' if music else 'auto'
            if kind == 'center_name':
                kind = 'names_center'
            for action in menu.actions()+advanced.actions()+names.actions():
                if action.isCheckable() and action.data() is not None:
                    action.setChecked(action.data()==kind)
                    if context:
                        value=action.data()
                        if value=='logo':
                            selected={(i.row(),i.column()) for i in self.table.selectedIndexes()}
                            chosen={row for row,col in selected}
                            valid=bool(selected) and all(not text or (row,col) in selected for row in chosen for col,text in enumerate(data[row]))
                            valid=valid and not any(block['start']<=row<=block['end'] for block in self.project.music_blocks for row in chosen)
                        elif value=='music':
                            valid=bool(self._selected_rows()) and not any(ingest.logo_labels(cell) for row in self._selected_rows() for cell in data[row] if cell)
                        else:
                            try:
                                self._validate_layout(self._selected_rows(),value)
                                valid=True
                            except ValueError:
                                valid=False
                        action.setVisible(valid)
            if context:
                names.menuAction().setVisible(any(action.isVisible() for action in names.actions()))
                advanced.menuAction().setVisible(False)
                formatting.menuAction().setVisible(False)
            show_types.blockSignals(True);show_types.setChecked(self._show_row_types);show_types.blockSignals(False)
        menu.aboutToShow.connect(update)
        update()

    def set_row_types_visible(self, visible):
        self._show_row_types = visible
        self.refresh_row_types()

    def refresh_row_types(self, crawl=None):
        from ..project import crawl_from_rows
        from .row_types import describe_rows
        from . import theme
        rows=self.rows()
        if crawl is None:
            crawl=crawl_from_rows(self.project,rows)
        self._row_types=describe_rows(crawl,self.project,self.table.rowCount())
        self.table.row_kinds={row:kind['label'].removesuffix(' *') for row,kind in enumerate(self._row_types)}
        self.table.spacer_rows={row for row in ingest.hidden_indices(self.project.spacer_rows) if 0<=row<len(rows) and not any(rows[row])}
        header=self.table.verticalHeader()
        width=QFontMetrics(header.font()).horizontalAdvance('9999 · Role / name * ✓')+18 if self._show_row_types else QFontMetrics(header.font()).horizontalAdvance(str(max(1,self.table.rowCount())))+18
        header.setFixedWidth(width)
        for row,kind in enumerate(self._row_types):
            label=f'{row+1} · {kind["label"]}' if self._show_row_types and kind['label'] else str(row+1)
            if self._show_row_types and kind['manual']:
                label+=' ✓'
            item=self.table.verticalHeaderItem(row)
            if item is None:
                item=QTableWidgetItem();self.table.setVerticalHeaderItem(row,item)
            if item.text()!=label:item.setText(label)
            item.setToolTip(kind['description']+'\nChange the category under Layout; edit local styling under Text formatting.')
            item.setForeground(QColor(theme.ACCENT if kind['manual'] and self._show_row_types else theme.MUTED))

    def apply_bold(self, enabled=True):
        from ..text import FontError
        try:
            self.apply_cell_format({'bold': True if enabled else None})
        except FontError as error:
            QMessageBox.information(self,'Cannot apply bold',str(error))

    def _text_cells(self):
        cells = {(index.row(), index.column()) for index in self.table.selectedIndexes()}
        if not cells and self.table.currentRow() >= 0:
            cells.add((self.table.currentRow(), self.table.currentColumn()))
        rows = self.rows()
        return {(row,column) for row,column in cells if rows[row][column] and not ingest.logo_labels(rows[row][column])}

    def apply_cell_format(self, options, *, cells=None, reset=False):
        from .. import text
        allowed = {'font','size','leading','tracking','bold','italic','uppercase','alignment','color','wrap'}
        if set(options) - allowed:
            raise ValueError('Unknown text formatting option.')
        for key in ('size','leading'):
            if options.get(key) is not None and not 1 <= options[key] <= 2000:
                raise ValueError('Font size and line spacing must be between 1 and 2000 pixels.')
        if options.get('alignment') not in (None,'left','center','right'):
            raise ValueError('Choose left, center or right alignment.')
        if options.get('wrap') is not None and not isinstance(options['wrap'],bool):
            raise ValueError('Choose On, Off or the section default for text wrapping.')
        if options.get('color') is not None:
            import math
            color = options['color']
            if (not isinstance(color,(list,tuple)) or len(color)!=3
                    or any(not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=1 for value in color)):
                raise ValueError('Choose a valid RGB font color.')
            options = dict(options,color=list(color))
        cells = self._text_cells() if cells is None else set(cells)
        rows = self.rows()
        cells = {(row,col) for row,col in cells if 0<=row<len(rows) and 0<=col<3
                 and rows[row][col] and not ingest.logo_labels(rows[row][col])}
        pieces = []
        existing = {}
        from ..project import crawl_from_rows
        style_crawl = crawl_from_rows(self.project,rows)
        for item in self.project.cell_formats:
            for row in range(item['start'], item['end'] + 1):
                if (row, item['column']) in cells:
                    existing[(row,item['column'])] = dict(item, start=row, end=row)
                else:
                    pieces.append(dict(item, start=row, end=row))
        for row,column in sorted(cells):
            item = dict(start=row,end=row,column=column) if reset else existing.get((row,column),dict(start=row,end=row,column=column))
            for key,value in options.items():
                if value is None:
                    item.pop(key,None)
                else:
                    item[key] = value
            if len(item)>3:
                # Resolve the actual font before accepting an override, so missing
                # bold/italic faces are explained in the dialog instead of failing export.
                base = self._cell_style(row,column,crawl=style_crawl)
                text.font_for(text.override_style(base,item))
                pieces.append(item)
        self.project.cell_formats[:] = pieces
        self._changed()
        self.table.viewport().update()

    def _cell_style(self, row, column, *, crawl=None):
        from ..project import crawl_from_rows
        from ..model import Header, ListBlock, Legal, RolePair
        for block in (crawl if crawl is not None else crawl_from_rows(self.project,self.rows())).blocks():
            if isinstance(block,ListBlock) and row+1 in [block.name_row(i) for i in range(len(block.names))]:
                return self.project.look.list
            if block.row != row+1:
                continue
            if isinstance(block,Header):
                return self.project.look.header if block.level==1 else self.project.look.song
            if isinstance(block,Legal):
                return self.project.look.legal
            if isinstance(block,RolePair):
                name = block.name_cells is not None or block.center_names or column!=0 or not block.role
                return self.project.look.styles()[('music_' if block.music else '')+('name' if name else 'role')]
        return self.project.look.name

    def format_dialog(self, *, cells=None, default_style=None):
        from ..text import FontError
        cells = sorted(self._text_cells() if cells is None else cells)
        if not cells:
            QMessageBox.information(self,'Select text','Select one or more text cells to format.')
            return
        base = default_style or self._cell_style(*cells[0])
        current = [next((item for item in self.project.cell_formats if item['start']<=row<=item['end'] and item['column']==column),{})
                   for row,column in cells]
        dialog=QDialog(self);dialog.setWindowTitle('Format selected cells')
        layout=QVBoxLayout(dialog)
        note=QLabel(f'{len(cells)} text cell(s). Checked options override the section style.\n'
                    'Unchecked options follow the section defaults. Credit text and Google Sheets stay unchanged.')
        note.setWordWrap(True);layout.addWidget(note)
        form=QFormLayout(); controls={}
        font=FontPicker();font.set_value(current[0].get('font',base.font))
        size=_spin(1,2000,' px');size.setValue(current[0].get('size',base.size))
        leading=_spin(1,2000,' px');leading.setValue(current[0].get('leading',base.leading))
        color=ColorPicker();color.set_value(current[0].get('color',base.color))
        alignment=QComboBox()
        for label,value in [('Left','left'),('Center','center'),('Right','right')]:alignment.addItem(label,value)
        alignment.setCurrentIndex(alignment.findData(current[0].get('alignment','center')))
        for key,label,widget in [('font','Font',font),('size','Font size',size),('color','Font color',color),('leading','Line spacing',leading),('alignment','Alignment',alignment)]:
            widget.setObjectName('format_' + key)
            enabled=QCheckBox(label)
            enabled.setChecked(all(key in item and item[key]==current[0].get(key) for item in current))
            widget.setEnabled(enabled.isChecked());enabled.toggled.connect(widget.setEnabled)
            form.addRow(enabled,widget);controls[key]=(enabled,widget)
        for key,label in [('bold','Bold'),('italic','Italic'),('uppercase','Uppercase'),('wrap','Wrap text')]:
            value=QComboBox();value.addItem('Use section default',None);value.addItem('On',True);value.addItem('Off',False)
            value.setObjectName('format_' + key)
            if all(key in item and item[key]==current[0].get(key) for item in current):
                value.setCurrentIndex(1 if current[0][key] else 2)
            form.addRow(label,value);controls[key]=(None,value)
        layout.addLayout(form)
        hint=QLabel('Wrap text fits long entries inside their column. For an exact line break, edit the cell and press Alt+Enter.\n'
                    'Font size scales line spacing unless you override line spacing too. Alignment stays within the credit’s column.')
        hint.setWordWrap(True);layout.addWidget(hint)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        reset=buttons.addButton('Use section defaults',QDialogButtonBox.ResetRole)
        reset.clicked.connect(lambda:(self.apply_cell_format({},cells=cells,reset=True),dialog.accept()))
        def accept():
            options={}
            for key,(enabled,widget) in controls.items():
                options[key] = (widget.value() if key in ('font','size','leading','color') else widget.currentData()) if enabled is None or enabled.isChecked() else None
            try:
                self.apply_cell_format(options,cells=cells)
            except (ValueError,FontError) as error:
                QMessageBox.information(dialog,'Cannot apply formatting',str(error));return
            dialog.accept()
        buttons.accepted.connect(accept);buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons);dialog.exec()

    def _build_context_menu(self):
        menu=QMenu(self)
        menu.addAction('Cut',self.cut,QKeySequence.Cut)
        menu.addAction('Copy',self.copy,QKeySequence.Copy)
        menu.addAction('Paste',self.paste,QKeySequence.Paste)
        menu.addAction('Clear',self.clear_cells)
        flagged=self._selected_finding_indices()
        if flagged:
            menu.addSeparator()
            label='Dismiss problem' if len(flagged)==1 else f'Dismiss {len(flagged)} problems'
            menu.addAction(label,lambda:self.dismiss(flagged))
        menu.addSeparator()
        self._populate_rows_menu(menu.addMenu('Rows'))
        self._populate_layout_menu(menu.addMenu('Layout'),context=True)
        arrangement=menu.addAction(self._arrangement_action_text(),self._edit_current_arrangement)
        if self.current_arrangement() is None and not self._current_logo_labels():
            try:
                arrangements.selection_range(self.rows(),self._selected_rows(),self.arrangement_boundaries())
            except ValueError:
                arrangement.setVisible(False)
        if self.current_arrangement() is not None:
            action=menu.addAction('Remove column arrangement',self.remove_arrangement)
            action.setToolTip('Remove the grid layout while keeping the credit text and section markings')
        menu.addSeparator()
        menu.addAction(self.show_in_preview)
        return menu

    def _context_menu(self, global_pos):
        if self.table.rowCount():
            index=self.table.indexAt(self.table.viewport().mapFromGlobal(global_pos))
            if index.isValid():
                flags=QItemSelectionModel.NoUpdate if index in self.table.selectedIndexes() else QItemSelectionModel.ClearAndSelect
                self.table.setCurrentCell(index.row(),index.column(),flags)
            else:
                header=self.table.verticalHeader()
                point=header.mapFromGlobal(global_pos)
                row=header.logicalIndexAt(point.y()) if header.rect().contains(point) else -1
                if row>=0:
                    if row not in self._selected_rows():
                        self.table.selectRow(row)
                    self.table.setCurrentCell(row,max(0,self.table.currentColumn()),QItemSelectionModel.NoUpdate)
            self._build_context_menu().exec(global_pos)

    def cell_tooltip(self, row, col):
        tips = []
        if row<len(self._row_types):
            tips.append(self._row_types[row]['description'])
        current = self.table.arrangement_at(row)
        if current:
            tips.append(f"{current.get('label', 'Side by side')} · {current['columns']} columns")
        if any(block['start'] <= row <= block['end'] for block in self.project.music_blocks):
            tips.append('Music song block — use Music… to edit its layout')
        override = self.override_at(row)
        if override:
            tips.append(f"Layout: {LAYOUT_LABELS[override['kind']]}")
        if any(item['start'] <= row <= item['end'] and item['column'] == col for item in self.project.cell_formats):
            tips.append('Manual styling — edit or reset under Layout → Text formatting')
        mark = next((m for m in self.table.change_marks if m['start'] <= row <= m['end']), None)
        if mark:
            tips.append('Changed by the last sheet update' + (f" — was: {mark['was']}" if mark.get('was') else ''))
        tips += [self.findings[i].message for i in self._error_cells.get((row, col), [])]
        return '\n'.join(tips)

    # ---- layout overrides ----------------------------------------------------------

    def override_at(self, row):
        return next((o for o in self.project.overrides if o['start'] <= row <= o['end']), None)

    def _apply_layout_to_selection(self, kind):
        if kind == 'logo':
            self.logo_block_dialog()
            return
        if kind == 'thanks':
            self.thanks_dialog()
            return
        try:
            self.apply_layout(self._selected_rows(), kind)
        except ValueError as error:
            QMessageBox.information(self, 'Cannot set layout', str(error))

    def _validate_layout(self, selected_rows, kind, **options):
        """Validate without changing the project, also for context-menu choices."""
        selected = sorted(set(selected_rows))
        if not selected:
            raise ValueError('Select the rows to change first.')
        if kind not in ('auto',) + ingest.LAYOUT_KINDS:
            raise ValueError(f'Unknown layout {kind!r}.')
        rows = self.rows()
        occupied=[rows[r] for r in selected if 0<=r<len(rows) and any(rows[r])]
        if kind in ('legal','thanks') and any(ingest.logo_labels(value) for row in occupied for value in row if value):
            raise ValueError('Logo rows keep their own layout. Choose text rows instead.')
        if kind == 'thanks':
            if any(options.get(key,'center') not in ('left','center','right') for key in ('left_alignment','right_alignment')):
                raise ValueError('Choose left, center or right alignment for each thanks column.')
            if options.get('flow','across') not in ('across','down','sheet'):
                raise ValueError('Choose across rows or down columns for name order.')
            columns = options.get('columns', 3)
            if not 1 <= columns <= 6:
                raise ValueError('Choose 1–6 name columns.')
            width = options.get('width_percent')
            if width is not None and not 1 <= width <= 100:
                raise ValueError('Choose a section width between 1% and 100% of the frame.')
            pixels = self.project.look.list_width if width is None else self.project.look.width * width / 100
            gap = options.get('column_gap', self.project.look.list_column_gap)
            if gap < 0:
                raise ValueError('Column gap cannot be negative.')
            if pixels <= (columns - 1) * gap:
                raise ValueError('The columns have no room for text. Increase the section width or reduce the column gap.')
        if kind == 'center_name':
            occupied = [rows[r] for r in selected if 0 <= r < len(rows) and any(rows[r])]
            if not occupied or any(sum(bool(value) for value in row)!=1 for row in occupied):
                raise ValueError('Select a name-only row with just one populated cell. Role/name pairs stay together.')
        if kind == 'heading':
            occupied = [rows[r] for r in selected if 0 <= r < len(rows) and any(rows[r])]
            if not occupied or any(sum(bool(value) for value in row)!=1 or any(ingest.logo_labels(value) for value in row if value) for row in occupied):
                raise ValueError('Select heading rows containing one text cell, without names or logos beside it.')
        if kind.startswith('names_'):
            occupied = [rows[r] for r in selected if 0 <= r < len(rows) and any(rows[r])]
            if not occupied or any(ingest.logo_labels(value) for row in occupied for value in row if value):
                raise ValueError('Select cells containing names. Logo rows keep their own layout.')
            if kind=='names_inward' and any(sum(bool(value) for value in row)>2 for row in occupied):
                raise ValueError('Face center supports one centered name or two names on opposite sides of the gap.')
        if kind == 'roles':
            occupied = [rows[r] for r in selected if 0 <= r < len(rows) and any(rows[r])]
            if (not occupied or any(ingest.logo_labels(b or c) or (c and d)
                    or (not b and c) for b,c,d in occupied)):
                raise ValueError('Select role/name rows: roles in column B, names in C or D. Keep section headings and logo rows outside this selection.')
        if not kind.startswith('names_') and kind not in ('auto', 'legal', 'thanks', 'center_name', 'roles', 'heading') and not any(rows[r][0] and not rows[r][1] and not rows[r][2] and not ingest.logo_labels(rows[r][0])
                                      for r in selected if r < len(rows)):
            raise ValueError('Layout overrides apply to rows with only column B filled '
                             '(roles or names with nothing in C or D).')
        return selected

    def apply_layout(self, selected_rows, kind, **options):
        """Apply an explicit layout in one undo step, preserving unaffected ranges."""
        selected=self._validate_layout(selected_rows,kind,**options)
        chosen = set(selected)
        pieces = []
        for item in self.project.overrides:
            run = []
            for r in range(item['start'], item['end'] + 1):
                if r in chosen:
                    if run:
                        pieces.append(dict(item, start=run[0], end=run[-1], **({'title': False} if item['kind']=='thanks' and run[0]!=item['start'] else {})))
                        run = []
                else:
                    run.append(r)
            if run:
                pieces.append(dict(item, start=run[0], end=run[-1], **({'title': False} if item['kind']=='thanks' and run[0]!=item['start'] else {})))
        if kind != 'auto':
            start = selected[0]
            for a, b in zip(selected, selected[1:] + [None]):
                if b != a + 1:
                    pieces.append(dict(start=start, end=a, kind=kind, **options))
                    start = b
        pieces.sort(key=lambda o: o['start'])
        merged = []
        for piece in pieces:
            if merged and piece['kind'] != 'thanks' and merged[-1]['kind'] == piece['kind'] and merged[-1]['end'] + 1 >= piece['start']:
                merged[-1]['end'] = max(merged[-1]['end'], piece['end'])
            else:
                merged.append(piece)
        self.project.overrides[:] = merged
        self._changed()

    # ---- side-by-side arrangements -------------------------------------------------

    def current_arrangement(self):
        row = self.table.currentRow()
        return next((a for a in self.project.arrangements if a['start'] <= row <= a['end']), None)

    def _arrangement_action_text(self):
        current=self.current_arrangement()
        if self._current_logo_labels() and not (current and current.get('logo_grid')):
            return 'Edit logo block…'
        if current and current.get('music'):
            return 'Edit music layout…'
        if current and current.get('logo_grid'):
            return 'Edit logo grid…'
        return 'Edit side by side…' if current is not None else 'Side by side…'

    def _current_logo_labels(self):
        row=self.table.currentRow()
        if row<0:
            return []
        values=[self.table.item(row,col).text() if self.table.item(row,col) else '' for col in range(3)]
        return ingest.logo_labels(values[0] or values[1]) if not values[2] else []

    def _edit_current_arrangement(self):
        current=self.current_arrangement()
        if self._current_logo_labels() or (current and current.get('logo_grid')):
            self.logo_layout_requested.emit(self.table.currentRow()+1)
        elif current and current.get('music'):
            self.music_dialog()
        else:
            self.arrange_dialog(edit=current is not None)

    def _selection_changed(self):
        self.arrange_button.setText(self._arrangement_action_text())
        current=self.current_arrangement()
        self.arrange_button.setToolTip('Open the Logos page and select the logos on this row' if self._current_logo_labels() else
                                      'Open this section in the Music editor' if current and current.get('music') else
                                      'Open this section in the Logos editor' if current and current.get('logo_grid') else
                                      'Arrange whole credit groups next to each other in columns')

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
        if current and (current.get('music') or current.get('logo_grid')):
            self._edit_current_arrangement()
            return
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

    def thanks_dialog(self):
        selected=self._selected_rows()
        row=self.table.currentRow()
        current=self.override_at(row if row>=0 else (selected[0] if selected else -1))
        # Names-only overrides can split the names away from their thanks heading.
        # Recover that adjacent section when opening its editor from either part.
        names=current if current and current['kind'].startswith('names_') else None
        if names and len(selected)<=1:
            heading=next((item for item in self.project.overrides if item['kind']=='thanks'
                          and item.get('title',True) and item['end']+1==names['start']),None)
            if heading:
                current=dict(heading,end=names['end'])
        current=current if current and current['kind']=='thanks' else None
        if current and len(selected)<=1:
            tail=next((item for item in self.project.overrides if item['start']==current['end']+1
                       and item['kind'].startswith('names_')),None)
            if tail:
                current=dict(current,end=tail['end'])
            related_names=names or tail
            if related_names:
                alignment=related_names['kind'].removeprefix('names_')
                if alignment=='inward':
                    current=dict(current,left_alignment='right',right_alignment='left',column_gap=self.project.look.gutter)
                elif alignment in ('left','center','right'):
                    current=dict(current,left_alignment=alignment,right_alignment=alignment)
            selected=list(range(current['start'],current['end']+1))
        if not selected or selected!=list(range(selected[0],selected[-1]+1)):
            QMessageBox.information(self,'Select a thanks section','Select one continuous range containing the heading and names, or just the names.')
            return
        dialog=QDialog(self);dialog.setWindowTitle('Special thanks section')
        layout=QVBoxLayout(dialog)
        note=QLabel(f'Rows {selected[0]+1}–{selected[-1]+1}. This section has its own heading, columns and width.\n'
                    'Match spreadsheet columns keeps left/right pairs together; a lone middle-column entry stays centered.')
        note.setWordWrap(True);layout.addWidget(note)
        title=QCheckBox('First selected row is the section heading');title.setChecked(current.get('title',True) if current else True)
        columns=_spin(1,6,'');columns.setValue(current.get('columns',3) if current else 3)
        width=_spin(1,100,' % of frame')
        inherited=round(100*self.project.look.list_width/self.project.look.width)
        width.setValue(current.get('width_percent',inherited) if current else 55)
        width.setToolTip('Maximum width before names wrap. Columns fit their text and stay together instead of filling unused width.')
        gap=_spin(0,1000,' px')
        gap.setValue(current.get('column_gap',self.project.look.list_column_gap) if current else self.project.look.list_column_gap)
        left_alignment=QComboBox();right_alignment=QComboBox()
        left_alignment.setObjectName('thanks_left_alignment');right_alignment.setObjectName('thanks_right_alignment')
        for widget,key in ((left_alignment,'left_alignment'),(right_alignment,'right_alignment')):
            for label,value in [('Left','left'),('Center','center'),('Right','right')]:widget.addItem(label,value)
            widget.setCurrentIndex(widget.findData(current.get(key,'center') if current else 'center'))
        left_alignment.setToolTip('Alignment within the leftmost names column. Choose Right to align toward the middle gap.')
        right_alignment.setToolTip('Alignment within the rightmost names column. Choose Left to align toward the middle gap.')
        flow=QComboBox()
        flow.addItem('Match spreadsheet columns','sheet')
        flow.addItem('Across rows — one entry per source row','across')
        flow.addItem('Down each column','down')
        def source_column_count():
            data=self.rows()
            body=selected[1:] if title.isChecked() else selected
            active={column for row in body for column,value in enumerate(data[row]) if value}
            if 0 in active and 2 in active and all(not data[row][1] or not (data[row][0] or data[row][2]) for row in body):
                return 2
            return max(1,len(active))
        paired=any(self.rows()[row][0] and self.rows()[row][2] for row in selected[1:])
        flow.setCurrentIndex(flow.findData(current.get('flow','across') if current else ('sheet' if paired else 'across')))
        def sync_columns(*_):
            match=flow.currentData()=='sheet'
            columns.setEnabled(not match)
            if match:columns.setValue(source_column_count())
            left_alignment.setEnabled(columns.value()>1);right_alignment.setEnabled(columns.value()>1)
        flow.currentIndexChanged.connect(sync_columns)
        title.toggled.connect(sync_columns)
        columns.valueChanged.connect(lambda *_:(left_alignment.setEnabled(columns.value()>1),right_alignment.setEnabled(columns.value()>1)))
        sync_columns()
        form=QFormLayout();form.addRow('',title);form.addRow('Name columns',columns)
        form.addRow('Name order',flow)
        form.addRow('Maximum section width',resettable(width,lambda:55,'thanks section width'))
        form.addRow('Space between columns',resettable(gap,lambda:default_look(self.project).list_column_gap,'thanks column gap'))
        form.addRow('Left name column alignment',left_alignment)
        form.addRow('Right name column alignment',right_alignment)
        face_center=QPushButton('Use role / name alignment')
        face_center.setToolTip('Right-align the left names and left-align the right names using the same center gap as ordinary credits.')
        def use_role_alignment():
            left_alignment.setCurrentIndex(left_alignment.findData('right'))
            right_alignment.setCurrentIndex(right_alignment.findData('left'))
            gap.setValue(self.project.look.gutter)
        face_center.clicked.connect(use_role_alignment)
        form.addRow('',face_center)
        heading_format=QPushButton('Heading font and styling…')
        heading_format.setEnabled(title.isChecked());title.toggled.connect(heading_format.setEnabled)
        def format_heading():
            values=self.rows()[selected[0]]
            column=next((column for column,value in enumerate(values) if value),1)
            self.format_dialog(cells=[(selected[0],column)],default_style=self.project.look.header)
        heading_format.clicked.connect(format_heading)
        form.addRow('Heading appearance',heading_format)
        layout.addLayout(form)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        def accept():
            try:
                self.apply_layout(selected,'thanks',title=title.isChecked(),columns=columns.value(),width_percent=width.value(),column_gap=gap.value(),flow=flow.currentData(),
                                  left_alignment=left_alignment.currentData(),right_alignment=right_alignment.currentData())
            except ValueError as error:
                QMessageBox.information(dialog,'Cannot set thanks layout',str(error))
                return
            dialog.accept()
        buttons.accepted.connect(accept);buttons.rejected.connect(dialog.reject)
        if current:
            remove=buttons.addButton('Return to automatic',QDialogButtonBox.DestructiveRole)
            remove.clicked.connect(lambda:(self.apply_layout(selected,'auto'),dialog.accept()))
        layout.addWidget(buttons);dialog.exec()

    # ---- explicit music sections -------------------------------------------

    def apply_music_blocks(self, blocks, columns=1, gap=120, alignment='center',
                           song_gap=96, title_gap=12, inline_gap=16):
        from ..music import without_rows
        rows=self.rows()
        blocks=sorted((dict(block) for block in blocks),key=lambda b:b['start'])
        if not blocks:
            raise ValueError('Define at least one song block.')
        if not 1<=columns<=6 or alignment not in ('center','left') or min(gap,song_gap,title_gap,inline_gap)<0:
            raise ValueError('Choose 1–6 columns and non-negative spacing.')
        for index,block in enumerate(blocks):
            if not 0<=block['start']<=block['end']<len(rows):
                raise ValueError('Each song needs valid first and last rows.')
            if index and blocks[index-1]['end']>=block['start']:
                raise ValueError('Song blocks cannot overlap.')
            if not any(rows[block['start']]) or not any(rows[block['end']]):
                raise ValueError('Start and end each song on a row containing text.')
            if any(ingest.logo_labels(rows[r][0] or rows[r][1]) for r in range(block['start'],block['end']+1)):
                raise ValueError('Keep logo rows outside the music section.')
        start,end=blocks[0]['start'],blocks[-1]['end']
        for old in self.project.music_blocks:
            if not (end<old['start'] or start>old['end']) and not (start<=old['start'] and old['end']<=end):
                raise ValueError('Include the complete existing song when changing its boundaries.')
        for item in self.project.arrangements:
            if not (end<item['start'] or start>item['end']):
                if not (item.get('music') and start<=item['start'] and item['end']<=end):
                    raise ValueError('This range overlaps an existing layout. Select the complete music section or remove that layout first.')
        width=min(self.project.look.width*.9,2*min(self.project.look.center_x,self.project.look.width-self.project.look.center_x))
        if (width-(columns-1)*gap)/columns<200:
            raise ValueError('The song columns are too narrow. Choose fewer columns or a smaller gap.')
        # Unassigned gaps between song blocks must not introduce unrelated text.
        covered={r for block in blocks for r in range(block['start'],block['end']+1)}
        if any(any(rows[r]) for r in range(start,end+1) if r not in covered):
            raise ValueError('Each populated row inside this section must belong to a song block.')
        self.project.music_blocks[:]=[b for b in self.project.music_blocks if b['end']<start or b['start']>end]+blocks
        self.project.music_blocks.sort(key=lambda b:b['start'])
        self.project.overrides[:]=without_rows(self.project.overrides,covered)
        self.project.arrangements[:]=[a for a in self.project.arrangements if a['end']<start or a['start']>end]
        self.project.arrangements.append(dict(start=start,end=end,columns=columns,gap=gap,alignment=alignment,
                                             label='Music',music=True,song_gap=song_gap,title_gap=title_gap,inline_gap=inline_gap))
        self.project.arrangements.sort(key=lambda a:a['start'])
        self._changed()
        self.refresh_arrangements()

    def remove_music(self, selected):
        selected=set(selected)
        self.project.music_blocks[:]=[b for b in self.project.music_blocks
                                     if not selected.intersection(range(b['start'],b['end']+1))]
        self.project.arrangements[:]=[a for a in self.project.arrangements
                                     if not (a.get('music') and selected.intersection(range(a['start'],a['end']+1)))]
        self._changed()
        self.refresh_arrangements()

    def music_dialog(self):
        from ..music import blocks_from_selection
        selected=self._selected_rows()
        current=self.current_arrangement()
        current=current if current and current.get('music') else None
        if current and selected and (len(selected)<=1 or all(current['start']<=r<=current['end'] for r in selected)):
            selected=list(range(current['start'],current['end']+1))
        elif current:
            current=None
        try:
            proposed=([dict(b) for b in self.project.music_blocks
                       if b['start']>=selected[0] and b['end']<=selected[-1]] if current else
                      blocks_from_selection(self.rows(),selected))
        except (ValueError,IndexError) as error:
            QMessageBox.information(self,'Select music credits',str(error) or 'Select music rows first.')
            return
        dialog=QDialog(self);dialog.setWindowTitle('Music blocks');dialog.resize(780,620)
        layout=QVBoxLayout(dialog)
        hint=QLabel('Each row below defines one song block. Edit its first/last sheet rows and whether its first row is the title.\n'
                    'Credit text stays in its original cells. Typography is shared under Look → Music.')
        hint.setWordWrap(True);layout.addWidget(hint)
        table=QTableWidget(0,4);table.setHorizontalHeaderLabels(['Song / first line','First row','Last row','First row is title'])
        table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        def populate(blocks):
            table.setRowCount(0)
            for block in blocks:
                row=table.rowCount();table.insertRow(row)
                text=' / '.join(v for v in self.rows()[block['start']] if v)
                label=QTableWidgetItem(text);label.setFlags(label.flags() & ~Qt.ItemIsEditable);table.setItem(row,0,label)
                for column,key in ((1,'start'),(2,'end')):
                    control=_spin(1,self.table.rowCount(),'');control.setValue(block[key]+1);table.setCellWidget(row,column,control)
                title=QTableWidgetItem('Song title');title.setFlags((title.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
                title.setCheckState(Qt.Checked if block.get('title',True) else Qt.Unchecked);table.setItem(row,3,title)
        def definitions():
            return [dict(start=table.cellWidget(r,1).value()-1,end=table.cellWidget(r,2).value()-1,
                         title=table.item(r,3).checkState()==Qt.Checked) for r in range(table.rowCount())]
        populate(proposed);layout.addWidget(table,1)
        tools=QHBoxLayout()
        def split_song():
            blocks=definitions();row=table.currentRow()
            if not 0<=row<len(blocks) or blocks[row]['start']>=blocks[row]['end']:
                return
            block=blocks[row]
            position,ok=QInputDialog.getInt(dialog,'Split song block','First sheet row of the next song:',
                                          block['start']+2,block['start']+2,block['end']+1)
            if ok:
                old_end=block['end'];block['end']=position-2
                blocks.insert(row+1,dict(start=position-1,end=old_end,title=True));populate(blocks)
        def merge_song():
            blocks=definitions();row=table.currentRow()
            if 0<=row<len(blocks)-1:
                blocks[row]['end']=blocks[row+1]['end'];blocks.pop(row+1);populate(blocks)
        for label,callback in (('Split at blank rows',lambda:populate(blocks_from_selection(self.rows(),selected))),
                               ('Use one song',lambda:populate(blocks_from_selection(self.rows(),selected,split=False))),
                               ('Split selected song…',split_song),
                               ('Merge with next song',merge_song)):
            button=QPushButton(label);button.clicked.connect(callback);tools.addWidget(button)
        layout.addLayout(tools)
        form=QFormLayout()
        columns=QComboBox();columns.addItem('Stacked',1)
        for count in range(2,7):
            columns.addItem(f'Side by side — {count} columns',count)
        columns.setCurrentIndex(current['columns']-1 if current else 0)
        gap=_spin(0,1000,' px');gap.setValue(current.get('gap',120) if current else 120)
        alignment=QComboBox();alignment.addItem('Centered','center');alignment.addItem('Left aligned','left')
        alignment.setCurrentIndex(1 if current and current['alignment']=='left' else 0)
        spacing=[]
        for key,label,default in (('song_gap','Between song groups',self.project.look.music_group_gap),
                                  ('title_gap','Below song titles',self.project.look.music_title_gap),
                                  ('inline_gap','Between label and name',self.project.look.music_inline_gap)):
            control=_spin(0,1000,' px');control.setValue(current.get(key,default) if current else default)
            spacing.append(control);form.addRow(label,control)
        form.insertRow(0,'Song layout',columns)
        form.insertRow(1,'Column gap',gap);form.insertRow(2,'Title / credit alignment',alignment);layout.addLayout(form)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        style=buttons.addButton('Music typography…',QDialogButtonBox.ActionRole)
        if current:
            remove=buttons.addButton('Return to automatic',QDialogButtonBox.DestructiveRole)
            remove.clicked.connect(lambda:(self.remove_music(selected),dialog.accept()))
        def accept(open_style=False):
            try:
                self.apply_music_blocks(definitions(),columns.currentData(),gap.value(),alignment.currentData(),
                                        *(control.value() for control in spacing))
            except ValueError as error:
                QMessageBox.information(dialog,'Cannot apply music layout',str(error));return
            dialog.accept()
            if open_style:self.music_style_requested.emit()
        buttons.accepted.connect(lambda:accept());buttons.rejected.connect(dialog.reject)
        style.clicked.connect(lambda:accept(True));layout.addWidget(buttons);dialog.exec()

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
        source_hidden = ingest.hidden_indices(self.project.hidden_rows)
        explicit_spacing=ingest.hidden_indices(self.project.spacer_rows)
        for row in range(self.table.rowCount()):
            hidden = (row in source_hidden and row not in explicit_spacing and not any(self.table.item(row,c) and self.table.item(row,c).text() for c in range(3))) or \
                     (only_problems and row not in problem_rows) or \
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
        for ranges in (self.project.arrangements, self.project.overrides, self.project.cell_formats, self.project.import_notes, self.project.music_blocks):
            changes.replay(ranges, shifts)
        for shift in shifts:
            arrangements.delete_rows(self.project.spacer_rows,shift.removed)
            for k in range(shift.inserted):
                ingest.insert_hidden_row(self.project.spacer_rows,shift.inserted_at+k)
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
        self.project.hidden_rows[:] = ingest.map_hidden_rows(new_rows, rows)
        self.project.base_hidden_rows[:] = ingest.hidden_ranges(new_rows)
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
