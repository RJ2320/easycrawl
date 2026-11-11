"""Searchable official logo downloads and a private, reusable personal collection."""
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QSize
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox,
    QListWidget, QListWidgetItem, QLabel, QPushButton, QFileDialog, QMessageBox,
    QInputDialog, QDialogButtonBox)

from ..logo_library import LogoLibrary
from .widgets import pil_to_qimage


class DownloadWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, root, entry_id, parent=None):
        super().__init__(parent)
        self.root, self.entry_id = root, entry_id

    def run(self):
        try:
            self.completed.emit(LogoLibrary(self.root).fetch(self.entry_id))
        except Exception as error:
            self.failed.emit(str(error))


class LogoLibraryDialog(QDialog):
    def __init__(self, project_logos=None, parent=None, library=None):
        super().__init__(parent)
        self.setWindowTitle('Logo library')
        self.resize(880, 640)
        self.library = library or LogoLibrary()
        self.project_logos = dict(project_logos or {})
        self.selected_paths = []
        self.selected_names = []
        self.worker = None
        self._thumbnails = {}
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search names, companies or tags…')
        self.scope = QComboBox()
        for label, key in [('All logos','all'),('Official sources','official'),('My logos','personal')]:
            self.scope.addItem(label,key)
        self.results = QListWidget()
        self.results.setIconSize(QSize(96,60))
        self.preview = QLabel('Choose a logo')
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(260,150)
        self.preview.setStyleSheet('background: #686b73; border: 1px solid #444;')
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.variant = QComboBox()
        self.variant.setMinimumContentsLength(15)
        self.variant.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.download = QPushButton('Download from official source')
        self.source = QPushButton('Open official source / guidelines')
        self.import_button = QPushButton('Import my logos…')
        self.project_button = QPushButton('Save project logos to My logos')
        self.edit_button = QPushButton('Edit name / tags…')
        self.remove_button = QPushButton('Remove from My logos')
        self.status = QLabel('Personal logos stay on this computer. Downloaded artwork works offline.')
        self.status.setWordWrap(True)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.use = self.buttons.addButton('Add to credits', QDialogButtonBox.AcceptRole)
        self.buttons.rejected.connect(self.reject)
        self.use.clicked.connect(self.use_logo)
        layout=QVBoxLayout(self)
        filters=QHBoxLayout();filters.addWidget(self.search,1);filters.addWidget(self.scope)
        layout.addLayout(filters)
        body=QHBoxLayout();body.addWidget(self.results,1)
        info=QVBoxLayout();info.addWidget(self.preview);info.addWidget(self.detail)
        info.addWidget(self.variant);info.addWidget(self.download);info.addWidget(self.source)
        info.addWidget(self.edit_button);info.addWidget(self.remove_button);info.addStretch()
        body.addLayout(info,1);layout.addLayout(body,1)
        imports=QHBoxLayout();imports.addWidget(self.import_button);imports.addWidget(self.project_button)
        layout.addLayout(imports);layout.addWidget(self.status);layout.addWidget(self.buttons)
        self.search.textChanged.connect(self.refresh)
        self.scope.currentIndexChanged.connect(self.refresh)
        self.results.currentItemChanged.connect(self.selection_changed)
        self.results.itemDoubleClicked.connect(lambda *_: self.use_logo())
        self.variant.currentIndexChanged.connect(self.show_preview)
        self.download.clicked.connect(self.download_logo)
        self.source.clicked.connect(self.open_source)
        self.import_button.clicked.connect(self.import_files)
        self.project_button.clicked.connect(self.save_project_logos)
        self.edit_button.clicked.connect(self.edit_entry)
        self.remove_button.clicked.connect(self.remove_entry)
        self.project_button.setEnabled(bool(self.project_logos))
        self.refresh()

    def current(self):
        item=self.results.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _pixmap(self, asset):
        try:
            from .. import logos
            path=self.library.asset_path(asset)
            if str(path) in self._thumbnails and path.exists():
                return self._thumbnails[str(path)]
            with Image.open(path) as image:
                box=logos.ink_box(str(path))
                if box:
                    image=image.crop(box)
                image.thumbnail((400,180))
                pixmap=QPixmap.fromImage(pil_to_qimage(image.convert('RGBA')))
            if len(self._thumbnails)>=128:
                self._thumbnails.clear()
            self._thumbnails[str(path)]=pixmap
            return pixmap
        except (OSError, ValueError):
            return QPixmap()

    def refresh(self, *_):
        previous=self.current()
        self.results.clear()
        for entry in self.library.entries(self.search.text(),self.scope.currentData()):
            cached=bool(entry.get('assets'))
            item=QListWidgetItem(entry['name']+('  ·  My logos' if entry['kind']=='personal'
                else '  ·  Offline' if cached else '  ·  Official source'))
            item.setData(Qt.UserRole,entry)
            if cached:
                item.setIcon(QIcon(self._pixmap(entry['assets'][0])))
            self.results.addItem(item)
            if previous and previous['id']==entry['id']:
                self.results.setCurrentItem(item)
        if self.results.currentRow()<0 and self.results.count():
            self.results.setCurrentRow(0)
        self.selection_changed()

    def selection_changed(self, *_):
        entry=self.current()
        self.variant.blockSignals(True)
        self.variant.clear()
        if entry:
            for asset in entry.get('assets',[]):
                self.variant.addItem(asset['name'],asset)
            self.detail.setText(entry['name']+'\n\n'+entry['usage']+
                ('\n\nOfficial source checked: '+entry['checked'] if entry['kind']=='official' else '')+
                ('\nTags: '+entry['tags'] if entry.get('tags') else ''))
            if entry.get('original',{}).get('format')=='EPS':
                self.detail.setText(self.detail.text()+'\n\nEPS converted to a high-resolution PNG. Original EPS retained locally.')
        else:
            self.detail.setText('No matching logos. Try a different search or import your own.')
        self.variant.blockSignals(False)
        personal=bool(entry and entry['kind']=='personal')
        busy=bool(self.worker and self.worker.isRunning())
        self.edit_button.setEnabled(personal and not busy)
        self.remove_button.setEnabled(personal and not busy)
        self.source.setEnabled(bool(entry and entry.get('source')))
        self.download.setEnabled(bool(entry and entry.get('download')) and not (self.worker and self.worker.isRunning()))
        self.download.setText('Check / download latest artwork' if entry and entry.get('assets') else 'Download from official source')
        self.show_preview()

    def show_preview(self, *_):
        asset=self.variant.currentData()
        pixmap=self._pixmap(asset) if asset else QPixmap()
        self.preview.setPixmap(pixmap)
        if pixmap.isNull():
            self.preview.setText('Download to preview' if self.current() and self.current().get('download')
                                 else 'Import artwork from the official source' if self.current() else 'Choose a logo')
        self.use.setEnabled(bool(asset and not pixmap.isNull()))

    def open_source(self):
        entry=self.current()
        if entry and entry.get('source'):
            QDesktopServices.openUrl(QUrl(entry['source']))

    def download_logo(self):
        entry=self.current()
        if not entry or not entry.get('download') or (self.worker and self.worker.isRunning()):
            return
        self.status.setText('Downloading official artwork… Your current project logos will not change.')
        self.worker=DownloadWorker(self.library.root,entry['id'],self)
        self.worker.completed.connect(self.downloaded)
        self.worker.failed.connect(self.download_failed)
        self.worker.finished.connect(self.download_finished)
        for control in (self.download,self.import_button,self.project_button,self.remove_button,self.edit_button):
            control.setEnabled(False)
        self.worker.start()

    def downloaded(self, assets):
        self.library=LogoLibrary(self.library.root)
        self.refresh()
        self.status.setText(f'{len(assets)} artwork variant(s) saved for offline use. Choose a variant, then Add to credits.')

    def download_failed(self, error):
        self.status.setText('Download failed. You can open the official source and import its artwork instead.')
        QMessageBox.information(self,'Could not download logo',error)

    def download_finished(self):
        self.import_button.setEnabled(True)
        self.project_button.setEnabled(bool(self.project_logos))
        self.selection_changed()

    def import_files(self):
        from ..logo_import import LOGO_FILTER
        paths,_=QFileDialog.getOpenFileNames(self,'Save logos for future projects','',
            LOGO_FILTER)
        self.import_paths(paths)

    def import_paths(self, paths):
        from .logo_import import prepare_logo_files
        paths=list(paths)
        prepared=prepare_logo_files(self,paths)
        if prepared is None:
            return
        failures=[];count=0
        for original,path in zip(paths,prepared):
            try:
                self.library.import_file(path,name=Path(original).stem)
                count+=1
            except (OSError,ValueError,Image.DecompressionBombError) as error:
                failures.append(Path(path).name+': '+str(error))
        self.search.clear();self.scope.setCurrentIndex(self.scope.findData('personal'));self.refresh()
        self.status.setText(f'{count} logo(s) saved to My logos. Original files can be moved without losing these copies.')
        if failures:
            QMessageBox.information(self,'Some logos could not be saved','\n'.join(failures))

    def save_project_logos(self):
        failures=[];count=0
        for name,path in self.project_logos.items():
            try:
                self.library.import_file(path,name=name);count+=1
            except (OSError,ValueError,Image.DecompressionBombError) as error:
                failures.append(name+': '+str(error))
        self.search.clear();self.scope.setCurrentIndex(self.scope.findData('personal'));self.refresh()
        self.status.setText(f'{count} project logo(s) saved for future projects.')
        if failures:
            QMessageBox.information(self,'Some logos could not be saved','\n'.join(failures))

    def edit_entry(self):
        entry=self.current()
        if not entry or entry['kind']!='personal':
            return
        name,ok=QInputDialog.getText(self,'Logo name','Name',text=entry['name'])
        if not ok or not name.strip():
            return
        tags,ok=QInputDialog.getText(self,'Search tags','Tags (company, department, etc.)',text=entry.get('tags',''))
        if not ok:
            return
        stored=next(item for item in self.library.data['personal'] if item['id']==entry['id'])
        stored.update(name=name.strip(),tags=tags.strip());self.library.save();self.refresh()

    def remove_entry(self):
        entry=self.current()
        if entry and entry['kind']=='personal':
            self.library.remove_personal(entry['id']);self.refresh()
            self.status.setText('Removed from My logos. Existing project artwork is retained.')

    def use_logo(self):
        asset=self.variant.currentData()
        if asset and self.use.isEnabled():
            self.selected_paths=[str(self.library.asset_path(asset))]
            entry=self.current()
            self.selected_names=[entry['name'] if entry and entry['kind']=='personal' else asset['name']]
            self.accept()

    def done(self, result):
        if self.worker and self.worker.isRunning():
            self.status.setText('The download is still running. You can close this window when it finishes.')
            return
        super().done(result)
