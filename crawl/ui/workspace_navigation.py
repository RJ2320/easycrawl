"""Section navigation and a contextual inspector for the Credits workspace."""
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QIcon,QPixmap,QPainter,QPen,QColor
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,
                               QPushButton,QGroupBox,QAbstractItemView,QToolButton,QStyle,QDialog,QDialogButtonBox)
from ..model import Header,LogoRow


class WorkspaceNavigation(QWidget):
    def __init__(self,window):
        super().__init__()
        self.window=window
        self.editor=window.sheet_editor
        layout=QVBoxLayout(self);layout.setContentsMargins(10,8,10,4)
        buttons=QHBoxLayout()
        self.format=QPushButton('Text formatting…')
        self.logos=QPushButton('Edit logo block…')
        buttons.addWidget(self.format);buttons.addWidget(self.logos)
        self.text_tools=[]
        bold=QToolButton();bold.setText('B');bold.setCheckable(True)
        font=bold.font();font.setBold(True);bold.setFont(font)
        bold.setToolTip('Bold selected text');bold.setAccessibleName('Bold selected text')
        bold.clicked.connect(lambda checked:self.editor.apply_bold(checked))
        self.bold=bold;buttons.addWidget(bold);self.text_tools.append(bold)
        self.no_wrap=QToolButton()
        self.no_wrap.setText("No wrap")
        self.no_wrap.setCheckable(True)
        self.no_wrap.setAccessibleName("No wrap for selected text")
        self.no_wrap.setToolTip("Keep selected text on one line in the crawl, even past title safe. Manual line breaks are preserved. Click again to use the section default.")
        self.no_wrap.clicked.connect(lambda checked:self.editor.apply_cell_format({'wrap':False if checked else None}))
        buttons.addWidget(self.no_wrap);self.text_tools.append(self.no_wrap)
        self.line_breaks=QToolButton()
        self.line_breaks.setText("Line breaks…")
        self.line_breaks.setToolTip("Choose where the selected credit starts a new line")
        self.line_breaks.clicked.connect(self.editor.edit_line_breaks)
        buttons.addWidget(self.line_breaks)
        for alignment in ('left','center','right'):
            pixmap=QPixmap(24,24);pixmap.fill(Qt.transparent)
            painter=QPainter(pixmap);painter.setPen(QPen(QColor('#dce4ef'),2))
            for y,width in ((5,18),(10,12),(15,18),(20,12)):
                x=3 if alignment=='left' else 21-width if alignment=='right' else (24-width)//2
                painter.drawLine(x,y,x+width,y)
            painter.end()
            tool=QToolButton();tool.setIcon(QIcon(pixmap));tool.setIconSize(QSize(20,20))
            tool.setToolTip(f'Align selected text {alignment}');tool.setAccessibleName(f'Align selected text {alignment}')
            tool.clicked.connect(lambda checked=False,value=alignment:self.editor.apply_cell_format({'alignment':value}))
            buttons.addWidget(tool);self.text_tools.append(tool)
        self.reset_style=QToolButton()
        self.reset_style.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.reset_style.setToolTip('Use section style\nClear manual text formatting from the selected cells; keep their content and layout.')
        self.reset_style.setAccessibleName('Use section style')
        self.reset_style.clicked.connect(lambda:self.editor.apply_cell_format({},reset=True))
        buttons.addWidget(self.reset_style);self.text_tools.append(self.reset_style)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.sections=QComboBox(self);self.sections.setEditable(True)
        self.sections.setInsertPolicy(QComboBox.NoInsert)
        self.sections.setPlaceholderText('Find a heading or logo block…')
        self.sections.setMinimumContentsLength(12)
        self.sections.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.sections.completer().setFilterMode(Qt.MatchContains)
        self.sections.hide()
        self.jump_dialog=None
        self.sections.activated.connect(self._activate_section)
        self.format.clicked.connect(lambda:self.editor.format_dialog())
        self.logos.clicked.connect(lambda:window._show_logo_layout(self.editor.table.currentRow()+1))
        self.editor.table.itemSelectionChanged.connect(self.refresh_selection)
        self.editor.table.currentCellChanged.connect(lambda *_:self.refresh_selection())

    def open_section_dialog(self):
        if self.jump_dialog is None:
            self.jump_dialog=QDialog(self.window)
            self.jump_dialog.setWindowTitle('Jump to section')
            self.jump_dialog.resize(540,130)
            layout=QVBoxLayout(self.jump_dialog)
            layout.addWidget(QLabel('Find a section heading or logo block:'))
            layout.addWidget(self.sections);self.sections.show()
            buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
            buttons.button(QDialogButtonBox.Ok).setText('Jump')
            buttons.accepted.connect(lambda:self._activate_section(self.sections.currentIndex()))
            buttons.rejected.connect(self.jump_dialog.reject)
            layout.addWidget(buttons)
        self.sections.setFocus()
        self.sections.lineEdit().selectAll()
        self.jump_dialog.exec()

    def _activate_section(self,index):
        if self.sections.itemData(index) is None:return
        self.window._restore_panel_layout()
        self.window.tabs.setCurrentWidget(self.editor)
        self.jump(index)
        if self.jump_dialog:self.jump_dialog.accept()

    def refresh(self,crawl):
        if crawl is None:return
        previous=self.sections.currentData()
        self.sections.blockSignals(True);self.sections.clear()
        for block in crawl.blocks():
            if isinstance(block,Header):label=block.text.replace('\n',' ')
            elif isinstance(block,LogoRow):label='Logos · '+', '.join(logo.label for logo in block.logos)
            else:continue
            self.sections.addItem(f'{label}  ·  row {block.row}',block.row)
        index=self.sections.findData(previous)
        self.sections.setCurrentIndex(index)
        self.sections.blockSignals(False)
        self.refresh_selection()

    def jump(self,index):
        row=self.sections.itemData(index)
        if not row:return
        table=self.editor.table
        table.setCurrentCell(row-1,1)
        table.scrollToItem(table.item(row-1,1),QAbstractItemView.PositionAtCenter)
        self.window.seek_row(row)

    def refresh_selection(self):
        table=self.editor.table;row=table.currentRow()
        info=getattr(self.editor,'_row_types',[])
        # Row categories are exposed by the table's accessible header labels.
        kind=info[row]['label'] if 0<=row<len(info) else ''
        label=f'Row {row+1} · {kind}' if row>=0 else 'No selection'
        selected=table.selectedIndexes()
        cells=self.editor._text_cells()
        styled=any(item['start']<=r<=item['end'] and item['column']==c
                   for item in self.window.project.cell_formats for r,c in cells)
        self.format.setToolTip(f'{label} · {len(selected)} selected cells\n'+
            ('Custom text formatting is applied. Other settings inherit the project style.' if styled else
             'Using project text styles. Formatting changes apply to the selected cells.'))
        logo='Logos' in label
        self.format.setVisible(not logo);self.logos.setVisible(logo)
        self.format.setEnabled(bool(selected))
        for tool in self.text_tools:tool.setEnabled(bool(cells) and not logo)
        self.line_breaks.setEnabled(len(cells)==1 and not logo)
        self.no_wrap.setChecked(bool(cells) and all(any(item['start']<=r<=item['end'] and item['column']==c and item.get('wrap') is False
            for item in self.window.project.cell_formats) for r,c in cells))
        self.bold.setChecked(bool(cells) and all(any(item['start']<=r<=item['end'] and item['column']==c and item.get('bold')
            for item in self.window.project.cell_formats) for r,c in cells))

class StyleDisclosure(QWidget):
    def __init__(self,editor):
        super().__init__();self.editor=editor
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.button=QPushButton();self.button.setCheckable(True)
        self.button.setStyleSheet('text-align: left; padding: 12px;')
        self.button.toggled.connect(editor.setVisible)
        layout.addWidget(self.button);layout.addWidget(editor)
        editor.hide();editor.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        style=self.editor.style
        self.button.setText(f'{self.editor.title()}\n{style.font} · {style.size} px')
        self.button.setAccessibleName('Edit '+self.editor.title())
