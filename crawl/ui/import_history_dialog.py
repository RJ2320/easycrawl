"""Project-local spreadsheet provenance, newest first."""
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QTableWidget,
                              QTableWidgetItem, QVBoxLayout, QHeaderView, QAbstractItemView)


def import_time(value):
    try:
        return datetime.fromisoformat(value).astimezone().strftime('%b %d, %Y · %I:%M %p')
    except (ValueError,TypeError):
        return 'Time unavailable'


def source_name(entry):
    return 'Google Sheet' if entry.get('source_url') else Path(entry.get('source','')).name or 'Spreadsheet'


def latest_import_text(project):
    if not project.import_history:
        return 'Import date not recorded for this source' if project.source else 'No spreadsheet imported'
    last=project.import_history[-1]
    sheet=f" · {last['sheet']}" if last.get('sheet') else ''
    return f"Last brought in: {source_name(last)}{sheet}\n{import_time(last.get('imported_at'))} · {last['action']}"


class ImportHistoryDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Import history')
        self.resize(1050,540)
        layout=QVBoxLayout(self)
        title=QLabel(latest_import_text(project));title.setWordWrap(True)
        layout.addWidget(title)
        note=QLabel('Newest first. Counts are review decisions, which can cover several rows. '
                    'This records what was brought in; credits may have been edited, undone, or restored from a snapshot afterwards. '
                    'Earlier imports made before history was available cannot be recovered.')
        note.setWordWrap(True);note.setProperty('role','caption');layout.addWidget(note)
        self.table=QTableWidget(len(project.import_history),6)
        self.table.setHorizontalHeaderLabels(['Imported / reviewed','Spreadsheet','Worksheet','Result','Applied','Skipped'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch)
        for row,entry in enumerate(reversed(project.import_history)):
            values=[import_time(entry.get('imported_at')),source_name(entry),entry.get('sheet') or '—',
                    entry['action'],str(entry.get('applied',0)),str(entry.get('skipped',0))]
            tip=(f"{entry.get('source_url') or entry.get('source','')}\n"
                 f"Columns: {entry.get('columns') or 'Automatic'} · Start row: {entry.get('start_row',1)}\n"
                 f"{entry.get('row_count',0)} source rows")
            for col,value in enumerate(values):
                item=QTableWidgetItem(value);item.setToolTip(tip);self.table.setItem(row,col,item)
        self.table.resizeRowsToContents();layout.addWidget(self.table,1)
        buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
