import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
from crawl.project import Project
from crawl.ui.sheet_editor import SheetEditor


def test_centered_title_spans_without_changing_cells_and_undoes(tmp_path):
    app = QApplication.instance() or QApplication([])
    rows = [['THANK YOU TO OUR BRAND PARTNERS', '', ''], ['Director', '', 'Alice']]
    project = Project()
    editor = SheetEditor(project)
    editor.load(rows)
    editor.apply_layout([0], 'center')
    assert editor.table.columnSpan(0, 0) == 3
    assert editor.table.columnSpan(1, 0) == 1
    assert editor.rows() == rows
    option = QStyleOptionViewItem()
    editor.table.itemDelegate().initStyleOption(option, editor.table.model().index(0, 0))
    assert option.displayAlignment == Qt.AlignCenter
    editor.undo()
    assert editor.table.columnSpan(0, 0) == 1
    editor.redo()
    assert editor.table.columnSpan(0, 0) == 3
    path = tmp_path / 'centered.crawl.json'
    project.save(str(path))
    restored = Project.load(str(path))
    other = SheetEditor(restored)
    other.load(restored.rows)
    assert other.table.columnSpan(0, 0) == 3
    assert other.rows() == rows
    editor.apply_layout([0], 'roles')
    assert editor.table.columnSpan(0, 0) == 1
    assert editor.rows() == rows
    editor.close()
    other.close()


def test_centered_rows_keep_other_columns_visible_when_edited():
    app = QApplication.instance() or QApplication([])
    editor = SheetEditor(Project())
    editor.load([['THANK YOU', '', ''], ['Director', '', 'Alice'], ['[Logo: Studio]', '', '']])
    editor.apply_layout([0, 1, 2], 'center')
    assert [editor.table.columnSpan(r, 0) for r in range(3)] == [3, 1, 3]
    editor.table.item(0, 0).setText('SPECIAL THANKS')
    assert editor.rows()[0][0] == 'SPECIAL THANKS'
    editor.table.item(0, 2).setText('Bob')
    assert editor.table.columnSpan(0, 0) == 1
    assert editor.rows()[0][2] == 'Bob'
    editor.undo()
    assert editor.table.columnSpan(0, 0) == 3
    editor.apply_layout([0], 'auto')
    assert editor.table.columnSpan(0, 0) == 1
    editor.close()


def test_section_heading_spans_keep_source_column_and_formatting():
    from PySide6.QtWidgets import QStyleOptionViewItem
    from PySide6.QtGui import QGuiApplication
    editor=SheetEditor(Project())
    editor.load([['','CAMERA DEPARTMENT',''],['Role','','Avery Morgan']])
    table=editor.table
    assert table.columnSpan(0,0)==3 and table.columnSpan(1,0)==1
    table.setCurrentCell(0,0)
    assert editor._text_cells()=={(0,1)}
    editor.apply_cell_format({'bold':True})
    assert editor.project.cell_formats[0]['column']==1
    delegate=table.itemDelegate();index=table.model().index(0,0)
    option=QStyleOptionViewItem();delegate.initStyleOption(option,index)
    assert option.text=='CAMERA DEPARTMENT'
    cell=delegate.createEditor(table.viewport(),option,index)
    delegate.setEditorData(cell,index);cell.setPlainText('POST PRODUCTION')
    delegate.setModelData(cell,table.model(),index)
    assert editor.rows()[0]==['','POST PRODUCTION','']
    editor.copy();assert 'POST PRODUCTION' in QGuiApplication.clipboard().text()
    editor.clear_cells();assert editor.rows()[0]==['','','']
    editor.undo();assert editor.rows()[0]==['','POST PRODUCTION','']
    assert table.columnSpan(0,0)==3
    cell.deleteLater();editor.close()
