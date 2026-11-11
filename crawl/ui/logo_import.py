"""Responsive one-time artwork conversion shared by logo file pickers."""
from PySide6.QtCore import QThread, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QProgressDialog, QMessageBox
from pathlib import Path

from ..logo_import import prepare_logo, MissingGhostscript, GHOSTSCRIPT_URL


class LogoConversionWorker(QThread):
    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.paths=paths;self.result=None;self.error=None

    def run(self):
        try:
            self.result=[prepare_logo(path) for path in self.paths]
        except Exception as error:
            self.error=error


def prepare_logo_files(parent, paths):
    paths=list(paths)
    if not any(Path(path).suffix.lower()=='.eps' for path in paths):
        return paths
    dialog=QProgressDialog('Converting EPS artwork to high-resolution PNG…','',0,0,parent)
    dialog.setWindowTitle('Import logo artwork')
    dialog.setWindowModality(Qt.WindowModal)
    dialog.setCancelButton(None)
    dialog.setWindowFlag(Qt.WindowCloseButtonHint,False)
    worker=LogoConversionWorker(paths,dialog)
    worker.finished.connect(dialog.accept)
    worker.start();dialog.exec();worker.wait()
    result=worker.result;error=worker.error
    dialog.deleteLater()
    if error:
        if isinstance(error,MissingGhostscript):
            box=QMessageBox(QMessageBox.Information,'Set up EPS import',
                'EPS artwork needs Ghostscript for the initial conversion. Install it once, then retry the import.',
                QMessageBox.Ok,parent)
            button=box.addButton('Get EPS support…',QMessageBox.ActionRole)
            box.exec()
            if box.clickedButton() is button:
                QDesktopServices.openUrl(QUrl(GHOSTSCRIPT_URL))
        else:
            QMessageBox.information(parent,'Cannot import logo',str(error))
        return None
    return result
