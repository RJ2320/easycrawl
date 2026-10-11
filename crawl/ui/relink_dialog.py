"""Review folder matches and relink several missing files in one action."""
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QDialog, QLabel, QVBoxLayout, QHBoxLayout, QTableWidget,
                               QTableWidgetItem, QPushButton, QComboBox, QFileDialog, QHeaderView)
from .. import relink


class SearchWorker(QThread):
    done = Signal(object)

    def __init__(self, folder, items, parent):
        super().__init__(parent)
        self.folder, self.items = folder, items

    def run(self):
        self.done.emit(relink.search(self.folder, self.items))


class RelinkDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.items = relink.missing(project)
        self.replacements = {}
        self.worker = None
        self.setWindowTitle('Relink missing files')
        self.resize(1000, 460)
        layout = QVBoxLayout(self)
        self.note = QLabel('Search a folder and its subfolders, then review the matches. '
                           'Multiple matches need your choice. Logo placement and tone settings are preserved.')
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.search_button = QPushButton('Search folder…')
        self.search_button.clicked.connect(self.search_folder)
        layout.addWidget(self.search_button)
        self.table = QTableWidget(len(self.items), 4)
        self.table.setHorizontalHeaderLabels(['Slot', 'Missing file', 'Replacement', ''])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.choices = []
        for row, item in enumerate(self.items):
            self.table.setItem(row, 0, QTableWidgetItem(item['label']))
            name = QTableWidgetItem(Path(item['path']).name)
            name.setToolTip(item['path'])
            self.table.setItem(row, 1, name)
            combo = QComboBox()
            combo.addItem('Unresolved — leave unchanged', '')
            self.choices.append(combo)
            self.table.setCellWidget(row, 2, combo)
            button = QPushButton('Choose…')
            button.clicked.connect(lambda checked=False, r=row: self.choose(r))
            self.table.setCellWidget(row, 3, button)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        cancel = QPushButton('Cancel')
        cancel.clicked.connect(self.reject)
        self.apply_button = QPushButton('Apply relinks')
        self.apply_button.setProperty('primary', True)
        self.apply_button.clicked.connect(self.apply)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(self.apply_button)
        layout.addLayout(buttons)
        if not self.items:
            self.note.setText('All source and logo files are available. Nothing needs relinking.')
            self.search_button.setEnabled(False)
            self.apply_button.setEnabled(False)

    def search_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Search for missing files')
        if not folder:
            return
        self.search_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.note.setText('Searching the folder and its subfolders…')
        self.worker = SearchWorker(folder, self.items, self)
        self.worker.done.connect(self.show_matches)
        self.worker.start()

    def show_matches(self, matches):
        for item, combo in zip(self.items, self.choices):
            paths = matches.get(item['key'], [])
            combo.clear()
            combo.addItem('Choose a match…' if len(paths) > 1 else 'Unresolved — leave unchanged', '')
            for path in paths:
                combo.addItem(path, path)
            if len(paths) == 1:
                combo.setCurrentIndex(1)
        self.search_button.setEnabled(True)
        self.apply_button.setEnabled(True)
        self.note.setText('Review the replacements. Unique filenames are selected; choose among any duplicate matches.')

    def choose(self, row):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose replacement', '',
                                             'Sheets (*.csv *.xlsx *.xlsm)' if self.items[row]['key'] == 'source'
                                             else 'Images (*.png *.jpg *.jpeg *.tif *.tiff)')
        if path:
            combo = self.choices[row]
            combo.addItem(path, path)
            combo.setCurrentIndex(combo.count() - 1)

    def apply(self):
        self.replacements = {item['key']: combo.currentData() for item, combo in zip(self.items, self.choices)
                             if combo.currentData()}
        self.accept()

    def done(self, result):
        if self.worker:
            self.worker.wait()
        super().done(result)
