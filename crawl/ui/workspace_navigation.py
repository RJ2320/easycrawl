"""Section navigation and a contextual inspector for the experimental workspace."""
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QIcon,QPixmap,QPainter,QPen,QColor
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,
                               QPushButton,QGroupBox,QAbstractItemView,QToolButton)
from ..model import Header,LogoRow


class WorkspaceNavigation(QWidget):
    def __init__(self,window):
        super().__init__()
        self.window=window
        self.editor=window.sheet_editor
        layout=QVBoxLayout(self);layout.setContentsMargins(10,8,10,4)
        self.setToolTip('Experimental workspace · local preview')
        buttons=QHBoxLayout()
        self.format=QPushButton('Text formatting…')
        self.logos=QPushButton('Edit logo block…')
        self.shared=QPushButton('Project style…')
        buttons.addWidget(self.format);buttons.addWidget(self.logos);buttons.addWidget(self.shared)
        self.text_tools=[]
        bold=QToolButton();bold.setText('B');bold.setCheckable(True)
        font=bold.font();font.setBold(True);bold.setFont(font)
        bold.setToolTip('Bold selected text');bold.setAccessibleName('Bold selected text')
        bold.clicked.connect(lambda checked:self.editor.apply_bold(checked))
        self.bold=bold;buttons.addWidget(bold);self.text_tools.append(bold)
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
        buttons.addStretch(1)
        layout.addLayout(buttons)
        row=QHBoxLayout();row.addWidget(QLabel('Jump to section'))
        self.sections=QComboBox();self.sections.setEditable(True)
        self.sections.setInsertPolicy(QComboBox.NoInsert)
        self.sections.setPlaceholderText('Find a heading or logo block…')
        self.sections.setMinimumContentsLength(12)
        self.sections.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.sections.completer().setFilterMode(Qt.MatchContains)
        row.addWidget(self.sections,1);layout.addLayout(row)
        self.sections.activated.connect(self.jump)
        self.format.clicked.connect(lambda:self.editor.format_dialog())
        self.logos.clicked.connect(lambda:window._show_logo_layout(self.editor.table.currentRow()+1))
        self.shared.clicked.connect(self.show_style)
        self.editor.table.itemSelectionChanged.connect(self.refresh_selection)
        self.editor.table.currentCellChanged.connect(lambda *_:self.refresh_selection())

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
        rows={index.row() for index in selected}
        styled=any(item['start']<=r<=item['end'] for item in self.window.project.cell_formats for r in rows)
        self.format.setToolTip(f'{label} · {len(selected)} selected cells\n'+
            ('Custom text formatting is applied. Other settings inherit the project style.' if styled else
             'Using project text styles. Formatting changes apply to the selected cells.'))
        logo='Logos' in label
        self.format.setVisible(not logo);self.logos.setVisible(logo)
        self.format.setEnabled(bool(selected));self.shared.setEnabled(row>=0)
        for tool in self.text_tools:tool.setEnabled(bool(self.editor._text_cells()) and not logo)
        cells=self.editor._text_cells()
        self.bold.setChecked(bool(cells) and all(any(item['start']<=r<=item['end'] and item['column']==c and item.get('bold')
            for item in self.window.project.cell_formats) for r,c in cells))

    def show_style(self):
        self.window.tabs.setCurrentWidget(self.window.look_tabs)
        self.window.look_tabs.setCurrentWidget(self.window.look_panel)


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
