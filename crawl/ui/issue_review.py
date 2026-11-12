"""A focused issue list with source context and opt-in encoding corrections."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QComboBox,QLabel,QTableWidget,
    QTableWidgetItem,QHeaderView,QAbstractItemView,QPlainTextEdit,QPushButton)
from ..encoding_checks import suggest_correction

LABELS={'encoding':'Text encoding','placeholder':'Template text','empty':'Missing credit',
        'duplicate':'Repeated credit','near-dup':'Similar names','logo':'Logo artwork','import':'Import note'}


class IssueReview(QDialog):
    def __init__(self,editor):
        super().__init__(editor)
        self.editor=editor;self.visible_findings=[];self.setWindowTitle('Review issues')
        self.resize(900,570)
        layout=QVBoxLayout(self);filters=QHBoxLayout()
        self.summary=QLabel();filters.addWidget(self.summary,1)
        self.severity=QComboBox()
        for label,value in [('All issues',''),('Errors','error'),('Warnings','warning'),('Notes','info')]:
            self.severity.addItem(label,value)
        self.category=QComboBox();self.category.addItem('All types','')
        filters.addWidget(self.severity);filters.addWidget(self.category);layout.addLayout(filters)
        self.table=QTableWidget(0,4)
        self.table.setHorizontalHeaderLabels(['Level','Issue','Section','Cell'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch)
        layout.addWidget(self.table,1)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);self.details.setMaximumHeight(170)
        layout.addWidget(self.details)
        actions=QHBoxLayout()
        self.show_credit=QPushButton('Show in credits')
        self.correct=QPushButton('Apply suggested correction')
        self.dismiss=QPushButton('Dismiss selected issue')
        close=QPushButton('Close')
        for button in (self.show_credit,self.correct,self.dismiss):actions.addWidget(button)
        actions.addStretch(1);actions.addWidget(close);layout.addLayout(actions)
        close.clicked.connect(self.close)
        self.show_credit.clicked.connect(self.show_selected)
        self.correct.clicked.connect(self.apply_correction)
        self.dismiss.clicked.connect(self.dismiss_selected)
        self.table.currentCellChanged.connect(lambda *_:self.describe())
        self.severity.currentIndexChanged.connect(self.refresh)
        self.category.currentIndexChanged.connect(self.refresh)
        editor.findings_changed.connect(self.refresh)
        self.refresh()

    def selected(self):
        row=self.table.currentRow()
        return self.visible_findings[row] if 0<=row<len(self.visible_findings) else None

    def refresh(self,*_):
        previous=self.selected();findings=self.editor.findings
        counts={level:sum(f.severity==level for f in findings) for level in ('error','warning','info')}
        self.summary.setText(' · '.join(f'{counts[key]} {label}'+('s' if counts[key]!=1 else '')
                            for key,label in [('error','error'),('warning','warning'),('info','note')]))
        category=self.category.currentData()
        self.category.blockSignals(True);self.category.clear();self.category.addItem('All types','')
        for key in sorted({f.check for f in findings}):self.category.addItem(LABELS.get(key,key.replace('-',' ').capitalize()),key)
        self.category.setCurrentIndex(max(0,self.category.findData(category)));self.category.blockSignals(False)
        self.visible_findings=[f for f in findings if (not self.severity.currentData() or f.severity==self.severity.currentData())
                              and (not self.category.currentData() or f.check==self.category.currentData())]
        rows=self.editor.rows();section='Opening credits';sections={}
        for index,values in enumerate(rows):
            if index<len(self.editor._row_types) and self.editor._row_types[index]['label'].startswith('Heading'):
                section=' '.join(' '.join(values).split())
            sections[index+1]=section
        self.table.blockSignals(True);self.table.setRowCount(len(self.visible_findings))
        for index,finding in enumerate(self.visible_findings):
            row,column=self.editor._finding_cell(finding)
            values=[{'error':'Error','warning':'Warning','info':'Note'}.get(finding.severity,finding.severity),
                    LABELS.get(finding.check,finding.check.replace('-',' ').capitalize()),sections.get(finding.row,''),
                    f'{"BCD"[column]}{row+1}']
            for col,value in enumerate(values):
                item=QTableWidgetItem(value);item.setToolTip(finding.message);self.table.setItem(index,col,item)
        choice=next((i for i,f in enumerate(self.visible_findings) if f==previous),0)
        if self.visible_findings:self.table.setCurrentCell(choice,0)
        self.table.blockSignals(False);self.describe()

    def describe(self):
        finding=self.selected()
        self.show_credit.setEnabled(finding is not None)
        self.correct.setVisible(bool(finding and finding.suggestion))
        self.dismiss.setEnabled(bool(finding and finding.key))
        if not finding:self.details.setPlainText('No issues in this view.');return
        row,col=self.editor._finding_cell(finding)
        current=self.editor.rows()[row][col]
        self.details.setPlainText(f'{finding.message}\n\nCurrent text:\n{current}'+
                                  (f'\n\nSuggested correction:\n{finding.suggestion}' if finding.suggestion else ''))

    def show_selected(self):
        finding=self.selected()
        if finding in self.editor.findings:self.editor.focus_error(self.editor.findings.index(finding))

    def apply_correction(self):
        finding=self.selected()
        if not finding or not finding.suggestion:return
        row,col=self.editor._finding_cell(finding)
        if suggest_correction(self.editor.rows()[row][col])!=finding.suggestion:
            self.details.setPlainText('This cell changed. Wait for the issue list to refresh before applying a correction.');return
        self.editor._set_cells({(row,col):finding.suggestion})
        self.refresh()

    def dismiss_selected(self):
        finding=self.selected()
        if finding in self.editor.findings:self.editor.dismiss([self.editor.findings.index(finding)])
