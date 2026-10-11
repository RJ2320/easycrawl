"""Named project milestones, stored with the project."""
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QInputDialog, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QVBoxLayout)


class SnapshotDialog(QDialog):
    changed = Signal()
    restore_requested = Signal(str)

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Version snapshots")
        self.resize(650, 440)
        layout = QVBoxLayout(self)
        hint = QLabel("Keep named milestones of your credits, look, timing and logo placement. "
                      "Snapshots are stored inside the project when you save it.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._selection_changed)
        layout.addWidget(self.list, 1)
        self.details = QLabel()
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        buttons = QHBoxLayout()
        self.save_button = QPushButton("Save snapshot…")
        self.save_button.setProperty("primary", True)
        self.save_button.clicked.connect(self.save_snapshot)
        buttons.addWidget(self.save_button)
        self.rename_button = QPushButton("Rename…")
        self.rename_button.clicked.connect(self.rename_snapshot)
        buttons.addWidget(self.rename_button)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.delete_snapshot)
        buttons.addWidget(self.delete_button)
        buttons.addStretch()
        self.restore_button = QPushButton("Restore…")
        self.restore_button.clicked.connect(self.restore_snapshot)
        buttons.addWidget(self.restore_button)
        layout.addLayout(buttons)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        layout.addWidget(close, alignment=Qt.AlignRight)
        self.refresh()

    def selected(self):
        item = self.list.currentItem()
        if item is None:
            return None
        return next((s for s in self.project.snapshots if s["id"] == item.data(Qt.UserRole)), None)

    def refresh(self, selected_id=None):
        self.list.clear()
        for snapshot in reversed(self.project.snapshots):
            date = datetime.fromisoformat(snapshot["created_at"]).astimezone().strftime("%b %d, %Y · %I:%M %p")
            item = QListWidgetItem(f'{snapshot["name"]}\n{date}')
            item.setData(Qt.UserRole, snapshot["id"])
            self.list.addItem(item)
            if snapshot["id"] == selected_id:
                self.list.setCurrentItem(item)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        self._selection_changed()

    def _selection_changed(self, *_):
        snapshot = self.selected()
        for button in (self.rename_button, self.delete_button, self.restore_button):
            button.setEnabled(snapshot is not None)
        if snapshot:
            state = snapshot["state"]
            look, timing = state["look"], state["timing"]
            self.details.setText(f'{len(state.get("rows") or [])} rows · '
                                 f'{look["width"]} × {look["height"]} · {timing["fps"]:g} fps')
        else:
            self.details.setText("No snapshots yet. Save one before sending a review or trying a new look.")

    def save_snapshot(self):
        name, accepted = QInputDialog.getText(self, "Save snapshot", "Name", text="Client review 1")
        if not accepted or not name.strip():
            return
        try:
            snapshot = self.project.create_snapshot(name)
        except Exception as error:
            QMessageBox.critical(self, "Can't save snapshot", str(error))
            return
        self.changed.emit()
        self.refresh(snapshot["id"])

    def rename_snapshot(self):
        snapshot = self.selected()
        if snapshot is None:
            return
        name, accepted = QInputDialog.getText(self, "Rename snapshot", "Name", text=snapshot["name"])
        if accepted and name.strip():
            snapshot["name"] = name.strip()
            self.changed.emit()
            self.refresh(snapshot["id"])

    def delete_snapshot(self):
        snapshot = self.selected()
        if snapshot is None:
            return
        if QMessageBox.question(self, "Delete snapshot", f'Delete “{snapshot["name"]}”?',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.project.snapshots.remove(snapshot)
        self.changed.emit()
        self.refresh()

    def restore_snapshot(self):
        snapshot = self.selected()
        if snapshot is None:
            return
        if QMessageBox.question(self, "Restore snapshot",
                                f'Restore “{snapshot["name"]}”?\n\nYour current work will be saved as a '
                                '“Before restoring…” snapshot. Google Sheet watching will pause so you '
                                'can review the restored version.',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.restore_requested.emit(snapshot["id"])
        self.refresh(snapshot["id"])
