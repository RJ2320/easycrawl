import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from crawl.project import Project
from crawl.ui.sheet_editor import SheetEditor


def test_custom_insertion_shifts_centering_and_undoes_as_one_step():
    app=QApplication.instance() or QApplication([])
    p=Project(); editor=SheetEditor(p)
    original=[['SECTION','',''],['Role','','Name']]
    editor.load(original);editor.apply_layout([0],'center')
    editor.table.setCurrentCell(0,0)
    with patch('crawl.ui.sheet_editor.QInputDialog.getInt',return_value=(15,True)):
        editor.insert_rows_dialog(above=True)
    assert editor.rows()==[['','',''] for _ in range(15)]+original
    assert p.overrides[0]['start']==15
    assert editor.table.columnSpan(15,0)==3
    editor.undo();assert editor.rows()==original
    editor.redo();assert editor.table.rowCount()==17
    editor.close()


def test_custom_insert_below_and_cancel():
    app=QApplication.instance() or QApplication([])
    editor=SheetEditor(Project());original=[['First','',''],['Last','','']]
    editor.load(original);editor.table.setCurrentCell(0,0)
    with patch('crawl.ui.sheet_editor.QInputDialog.getInt',return_value=(15,False)):
        editor.insert_rows_dialog(above=False)
    assert editor.rows()==original and not editor.can_undo()
    editor.insert_rows(above=False,count=3)
    assert editor.rows()==[original[0]]+[['','','']]*3+[original[1]]
    editor.undo();assert editor.rows()==original
    editor.close()
