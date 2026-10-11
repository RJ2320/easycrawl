"""Music-specific typography and spacing controls."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QLabel, QScrollArea
from .widgets import StyleEditor, _spin


class MusicPanel(QWidget):
    changed = Signal()

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(14, 10, 14, 14)
        note = QLabel('Music credits use compact, centered label-and-name lines.\n'
                      'To italicise words, edit the cell in Credits, select them and press Ctrl+I.\n'
                      'Fit runtime also scales vertical spacing to meet the chosen duration.')
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.controls = {}
        for key, label, lo, hi in [
            ('music_title_gap', 'Gap below song title', 0, 600),
            ('music_group_gap', 'Gap between song groups', 0, 1000),
            ('music_inline_gap', 'Gap between label and name', 0, 600),
            ('music_width', 'Maximum line width', 200, 8192),
        ]:
            control = _spin(lo, hi, ' px')
            self.controls[key] = control
            form.addRow(label, control)
            control.valueChanged.connect(self._apply)
        layout.addLayout(form)
        self.editors = {}
        for key, label in [('song', 'Song title'), ('music_role', 'Labels — Written by, Performed by…'),
                           ('music_name', 'Names — leading sets line spacing')]:
            editor = StyleEditor(label, getattr(project.look, key))
            self.editors[key] = editor
            layout.addWidget(editor)
            editor.changed.connect(self.changed)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.load()

    def load(self):
        for key, control in self.controls.items():
            control.blockSignals(True)
            control.setValue(getattr(self.project.look, key))
            control.blockSignals(False)
        for key, editor in self.editors.items():
            editor.load(getattr(self.project.look, key))

    def _apply(self, *_):
        for key, control in self.controls.items():
            setattr(self.project.look, key, control.value())
        self.changed.emit()
