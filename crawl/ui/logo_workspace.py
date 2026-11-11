"""Dedicated logo layout surface, linked to logo sections in the credits sheet."""
from dataclasses import replace
from collections import Counter

from PySide6.QtCore import Qt, Signal, QItemSelectionModel
from .logo_canvas import LogoCanvas
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
                              QPushButton, QComboBox, QListWidget, QFileDialog, QMessageBox, QAbstractItemView)
from .. import ingest
from .widgets import LogoBar, _spin


class LogoOrderList(QListWidget):
    order_dropped = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)

    def dropEvent(self, event):
        before = [self.item(i).text() for i in range(self.count())]
        super().dropEvent(event)
        after = [self.item(i).text() for i in range(self.count())]
        if before != after:
            self.order_dropped.emit()


class LogoWorkspace(QWidget):
    changed = Signal()
    setting_changed = Signal(str, dict)
    auto_requested = Signal(str)
    moved = Signal(str, int, int)
    show_row = Signal(int)
    batch_settings = Signal(dict)

    def __init__(self, project, sheet_editor, parent=None):
        super().__init__(parent)
        self.project, self.editor = project, sheet_editor
        self.sections = []
        self.build = None
        self._bounds = None
        self._bounds_section = None
        self._layer_cache = {}
        self.section = QComboBox()
        self.artwork = LogoOrderList()
        self.artwork.setToolTip("Drag logos up or down to change their order in the credits.")
        self.artwork.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.color_mode = QComboBox()
        self.color_mode.addItem("Original color", "original")
        self.color_mode.addItem("Greyscale", "grayscale")
        self.columns = _spin(1, 6, '')
        self.columns.setValue(3)
        self.gap = _spin(0, 1000, ' px')
        self.gap.setValue(120)
        self.note = QLabel('Choose a logo section, or add artwork at the selected spreadsheet row.')
        self.note.setWordWrap(True)
        form = QFormLayout()
        form.addRow('Credits location', self.section)
        form.addRow('Columns', self.columns)
        form.addRow('Column spacing', self.gap)
        apply = QPushButton('Apply logo grid')
        apply.clicked.connect(self.apply_grid)
        library = QPushButton('Logo library…')
        library.clicked.connect(self.open_library)
        add = QPushButton('Add logo…')
        add.clicked.connect(self.add_artwork)
        replace_button = QPushButton('Replace selected logo…')
        self.replace_button = replace_button
        self.remove_button = QPushButton('Remove logo')
        self.remove_button.clicked.connect(self.remove_artwork)
        self.replace_button.setEnabled(False)
        self.remove_button.setEnabled(False)
        replace_button.clicked.connect(self.replace_artwork)
        show = QPushButton('Show locations')
        show.setToolTip('Show this logo section in the Credits spreadsheet')
        show.clicked.connect(lambda: self.current() and self.show_row.emit(self.current()['start'] + 1))
        buttons = QHBoxLayout()
        self.move_buttons = {}
        for label, direction in [('Move earlier', -1), ('Move later', 1)]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, d=direction: self.reorder(d))
            button.setEnabled(False)
            self.move_buttons[direction] = button
            buttons.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.note)
        layout.addLayout(form)
        layout.addWidget(apply)
        layout.addWidget(self.artwork, 1)
        layout.addLayout(buttons)
        layout.addWidget(self.color_mode)
        self.color_mode.currentIndexChanged.connect(self._color_changed)
        layout.addWidget(replace_button)
        layout.addWidget(add)
        layout.addWidget(self.remove_button)
        layout.addWidget(library)
        layout.addWidget(show)
        self.canvas = QWidget()
        canvas_layout = QVBoxLayout(self.canvas)
        caption = QLabel('Logo layout · drag artwork to position it; select a logo to adjust size and tone.')
        caption.setWordWrap(True)
        self.view = LogoCanvas()
        self.inspector = LogoBar()
        self.inspector.show()
        caption.setText('Shift/Cmd-click logos to select several, or select them in the list. Drag together; Option bypasses snapping.')
        canvas_layout.addWidget(caption)
        tools = QHBoxLayout()
        self.align_mode = QComboBox()
        for label, key in [('Left edges', 'left'), ('Horizontal centers', 'center_x'), ('Right edges', 'right'),
                           ('Top edges', 'top'), ('Vertical centers', 'center_y'), ('Bottom edges', 'bottom'),
                           ('Equal horizontal gaps', 'distribute_x'), ('Equal vertical gaps', 'distribute_y')]:
            self.align_mode.addItem(label, key)
        self.align_button = QPushButton('Apply to selection')
        self.align_button.setEnabled(False)
        self.align_button.clicked.connect(lambda: self.align_selected(self.align_mode.currentData()))
        tools.addWidget(self.align_mode)
        tools.addWidget(self.align_button)
        self.selection_count = QLabel('Select logos to align')
        tools.addWidget(self.selection_count)
        canvas_layout.addLayout(tools)
        canvas_layout.addWidget(self.view, 1)
        canvas_layout.addWidget(self.inspector)
        self.section.currentIndexChanged.connect(self._section_changed)
        self.artwork.itemSelectionChanged.connect(self._list_selection)
        self.artwork.order_dropped.connect(self._order_dropped)
        self.view.selection_changed.connect(self._canvas_selection)
        self.view.group_moved.connect(self.move_selected)
        self.inspector.changed.connect(self.setting_changed)
        self.inspector.auto_requested.connect(self.auto_requested)

    def current(self):
        index = self.section.currentIndex()
        return self.sections[index] if 0 <= index < len(self.sections) else None

    def select_source_row(self, row):
        """Focus the matching section and artwork for a zero-based credits row."""
        index=next((i for i,section in enumerate(self.sections) if section['start']<=row<=section['end']),None)
        if index is None:
            return
        self.section.setCurrentIndex(index)
        values=self.editor.rows()[row]
        labels=set(ingest.logo_labels(values[0] or values[1])) if not values[2] else set()
        if labels:
            self._canvas_selection(labels)
            if self.artwork.currentItem():
                self.artwork.scrollToItem(self.artwork.currentItem())

    def refresh(self):
        previous = self.current()
        selected = {item.text() for item in self.artwork.selectedItems()}
        sections, current = [], None
        for index, row in enumerate(self.editor.rows()):
            labels = ingest.logo_labels(row[0] or row[1]) if not row[2] else []
            if labels:
                if current is None:
                    current = dict(start=index, end=index, labels=[])
                    sections.append(current)
                current['end'] = index
                current['labels'].extend(labels)
            elif any(row):
                current = None
        self.sections = sections
        self.section.blockSignals(True)
        self.section.clear()
        for item in sections:
            self.section.addItem(f"Rows {item['start'] + 1}–{item['end'] + 1} · {len(item['labels'])} logos")
        choice = next((i for i, item in enumerate(sections)
                       if previous and set(item['labels']) & set(previous['labels'])), 0)
        self.section.setCurrentIndex(choice if sections else -1)
        self.section.blockSignals(False)
        self._section_changed()
        self._canvas_selection(selected)

    def arrangement(self):
        section = self.current()
        return next((item for item in self.project.arrangements if section and
                     item['start'] == section['start'] and item['end'] == section['end']), None)

    def _section_changed(self, *_):
        section = self.current()
        cfg = self.arrangement() or {}
        labels = section['labels'] if section else []
        order = cfg.get('logo_order', [])
        labels = sorted(labels, key=lambda label: order.index(label) if label in order else len(order))
        self.artwork.blockSignals(True)
        self.artwork.clear()
        self.artwork.addItems(labels)
        self.artwork.blockSignals(False)
        self.columns.setValue(cfg.get('columns', 3))
        self.gap.setValue(cfg.get('gap', 120))
        self.note.setText('Drag logos in the list to reorder them, or use Move earlier / Move later. Changes appear in the credits.'
                          if section else 'No logo section yet. Add artwork at the selected spreadsheet row.')
        self._draw()
        self.inspector.load('', {})

    def _select(self, label):
        self.view.select_logo(label)
        self.sync_selection(label)

    def _select_from_canvas(self, label):
        matches = self.artwork.findItems(label, Qt.MatchExactly)
        if matches:
            self.artwork.setCurrentItem(matches[0])
        self.sync_selection(label)

    def sync_selection(self, label):
        cfg = self.project.logo_settings.get(label, {})
        self.inspector.load(label, cfg)
        self.color_mode.blockSignals(True)
        self.color_mode.setCurrentIndex(1 if cfg.get('mode') == 'grayscale' else 0)
        self.color_mode.setEnabled(bool(label))
        self.color_mode.blockSignals(False)

    def _color_changed(self, *_):
        if self.inspector.label:
            self.setting_changed.emit(self.inspector.label, {'mode': self.color_mode.currentData()})

    def set_build(self, build):
        self.build = build
        self.refresh()

    def _draw(self):
        section = self.current()
        if not self.build or not section:
            self.view.set_strip(None, 1, self.project.look.width, self.project.look.height, 1, 0, [])
            self.view.set_logos([])
            return
        items = [item for item in self.build.layout.logos if item.label in section['labels']]
        if not items:
            self.view.set_strip(None, 1, self.project.look.width, self.project.look.height, 1, 0, [])
            self.view.set_logos([])
            return
        key = tuple(section['labels'])
        top = min(item.y for item in items) - 160
        bottom = max(item.y + item.h for item in items) + 160
        if self._bounds_section == key and self._bounds:
            top = min(top, self._bounds[0])
            bottom = max(bottom, self._bounds[1])
        self._bounds_section, self._bounds = key, (top, bottom)
        local = [replace(item, y=item.y-top) for item in items]
        height = max(360, bottom-top)
        look = self.project.look
        scale = min(1, 960 / look.width)
        layers = {}
        prepared = getattr(self.build, 'logo_layers', {})
        for item in local:
            cached = prepared.get(item.label)
            if cached:
                self._layer_cache[item.label] = cached
                layers[item.label] = cached[1]
            else:
                # For builds supplied directly (outside the background rebuild).
                from .logo_layers import key, prepare
                cache_key = key(item, scale)
                cached = self._layer_cache.get(item.label)
                if not cached or cached[0] != cache_key:
                    cached = (cache_key, prepare(item, scale))
                    self._layer_cache[item.label] = cached
                layers[item.label] = cached[1]
        self.view.layers = layers
        self.view.set_strip(None, scale, look.width, height, 1, 0, [])
        self.view.set_frame(height)
        self.view.centre_x = look.center_x
        self.view.set_logos(local)
        self.view.set_busy(False)

    def apply_grid(self, checked=False, *, commit=True, order=None):
        section = self.current()
        if not section:
            return
        old = self.arrangement()
        overlaps = [a for a in self.project.arrangements if a is not old and
                    a['start'] <= section['end'] and a['end'] >= section['start']]
        if overlaps:
            QMessageBox.information(self, 'Overlapping arrangement',
                                    'Remove or resize the overlapping spreadsheet arrangement before applying this logo grid.')
            return
        columns, gap = self.columns.value(), self.gap.value()
        width = min(self.project.look.width * .9, 2 * min(self.project.look.center_x,
                     self.project.look.width-self.project.look.center_x))
        if (width-(columns-1)*gap)/columns < 200:
            QMessageBox.information(self, 'Columns too narrow', 'Reduce the column count or spacing.')
            return
        cfg = dict(old or {}, start=section['start'], end=section['end'], columns=columns,
                   gap=gap, alignment='center', label='Logo layout', logo_grid=True)
        if order is not None:
            cfg['logo_order'] = list(order)
        if old is None:
            self.project.arrangements.append(cfg)
        else:
            old.update(cfg)
        if commit:
            self.editor._changed()
        return old if old is not None else cfg

    def _apply_order(self, labels):
        section = self.current()
        if not section or Counter(labels) != Counter(section['labels']):
            self.refresh()
            return
        selected = {item.text() for item in self.artwork.selectedItems()}
        cfg = self.arrangement()
        if cfg and cfg.get('logo_grid'):
            if cfg.get('logo_order') == labels:
                return
            cfg['logo_order'] = list(labels)
        elif self.apply_grid(commit=False, order=labels) is None:
            self.refresh()
            return
        # Update the visible list now; the main window rebuilds the preview.
        self._section_changed()
        self._canvas_selection(selected)
        self.editor._changed()

    def _order_dropped(self):
        self._apply_order([self.artwork.item(i).text() for i in range(self.artwork.count())])

    def reorder(self, direction):
        selected = {item.text() for item in self.artwork.selectedItems()}
        if not selected or direction not in (-1, 1):
            return
        labels = [self.artwork.item(i).text() for i in range(self.artwork.count())]
        original = list(labels)
        indices = range(1,len(labels)) if direction == -1 else range(len(labels)-2,-1,-1)
        for index in indices:
            neighbor = index + direction
            if labels[index] in selected and labels[neighbor] not in selected:
                labels[index],labels[neighbor] = labels[neighbor],labels[index]
        if labels != original:
            self._apply_order(labels)

    def open_library(self):
        section = self.current()
        if section:
            self.editor.table.setCurrentCell(section['end'], 0)
        self.editor.add_logos()
        self.refresh()

    def add_artwork(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Add logo', '', 'Images (*.png *.tif *.tiff *.jpg *.jpeg)')
        if not paths:
            return
        section = self.current()
        if section:
            self.editor.table.setCurrentCell(section['end'], 0)
        self.editor.add_logo_paths(paths)
        self.refresh()

    def replace_artwork(self):
        selected = self.artwork.selectedItems()
        if len(selected) != 1:
            return
        current = selected[0]
        path, _ = QFileDialog.getOpenFileName(self, 'Replace selected logo', '', 'Images (*.png *.tif *.tiff *.jpg *.jpeg)')
        if path:
            self.project.logos[current.text()] = path
            self.editor._changed()
            self.refresh()

    def remove_artwork(self):
        section = self.current()
        labels = {item.text() for item in self.artwork.selectedItems()}
        if not section or not labels:
            return
        self.editor.remove_logo_labels(labels, section['start'], section['end'])
        self.refresh()

    def _list_selection(self):
        labels = {item.text() for item in self.artwork.selectedItems()}
        self.view.set_selection(labels)
        self.selection_count.setText(f'{len(labels)} selected')
        self.replace_button.setEnabled(len(labels) == 1)
        self.remove_button.setEnabled(bool(labels))
        order = [self.artwork.item(i).text() for i in range(self.artwork.count())]
        for direction,button in self.move_buttons.items():
            button.setEnabled(any(label in labels and 0 <= i+direction < len(order)
                                  and order[i+direction] not in labels for i,label in enumerate(order)))
        self.align_button.setEnabled(len(labels) >= 2)
        self.sync_selection(next(iter(labels)) if len(labels) == 1 else '')

    def _canvas_selection(self, labels):
        current = self.artwork.currentItem()
        current_label = current.text() if current else None
        self.artwork.blockSignals(True)
        selected_items = []
        for index in range(self.artwork.count()):
            item = self.artwork.item(index)
            item.setSelected(item.text() in labels)
            if item.text() in labels:
                selected_items.append(item)
        if selected_items:
            active = next((item for item in selected_items if item.text()==current_label),selected_items[0])
            self.artwork.setCurrentItem(active,QItemSelectionModel.NoUpdate)
        self.artwork.blockSignals(False)
        self._list_selection()

    def move_selected(self, labels, dx, dy):
        changes = {}
        for label in labels:
            cfg = self.project.logo_settings.get(label, {})
            changes[label] = dict(dx=int(cfg.get('dx', 0))+dx, dy=int(cfg.get('dy', 0))+dy)
        if changes:
            self.batch_settings.emit(changes)

    def align_selected(self, mode):
        if self.view.busy:
            return
        items = [item for item in self.view.logos if item.label in self.view.selection]
        if len(items) < 2:
            return
        horizontal = mode in ('left', 'right', 'center_x', 'distribute_x')
        axis, size, offset = ('x','w','dx') if horizontal else ('y','h','dy')
        positions = {}
        if mode.startswith('distribute'):
            if len(items) < 3:
                QMessageBox.information(self, 'Distribute logos', 'Select at least three logos. The outer two stay in place.')
                return
            items.sort(key=lambda item: getattr(item, axis))
            first = getattr(items[0],axis)
            end = getattr(items[-1],axis)+getattr(items[-1],size)
            gap = (end-first-sum(getattr(item,size) for item in items))/(len(items)-1)
            if gap < 0:
                QMessageBox.information(self, 'Not enough space', 'Move the outer logos farther apart before distributing.')
                return
            at = first
            for item in items:
                positions[item.label] = round(at)
                at += getattr(item,size)+gap
        else:
            first = min(getattr(item,axis) for item in items)
            end = max(getattr(item,axis)+getattr(item,size) for item in items)
            for item in items:
                positions[item.label] = round(first if mode in ('left','top') else
                     end-getattr(item,size) if mode in ('right','bottom') else
                     (first+end-getattr(item,size))/2)
        changes = {item.label: {offset:int(self.project.logo_settings.get(item.label,{}).get(offset,0))
                               +positions[item.label]-getattr(item,axis)} for item in items}
        self.batch_settings.emit(changes)
