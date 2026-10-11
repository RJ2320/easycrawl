import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from crawl.changes import diff
from crawl.ui.change_dialog import ChangeDialog


def test_revision_displays_section_and_unchanged_neighbors():
    app = QApplication.instance() or QApplication([])
    old = [['','CAMERA',''], ['Director of Photography','','Alice'], ['Camera Operator','','Bob'], ['Assistant','','Carol'], ['','SOUND',''], ['Mixer','','Dan']]
    new = [r[:] for r in old]; new[2][2] = 'Robert'
    found = diff(old, old, new)
    dialog = ChangeDialog(found, 'revision.xlsx', current_rows=old, incoming_rows=new)
    assert 'CAMERA' in dialog.detail_title.text()
    assert dialog.current_cells.rowCount() == 4
    assert dialog.current_cells.item(0,1).text() == 'CAMERA'
    assert dialog.current_cells.item(1,2).text() == 'Alice'
    assert dialog.incoming_cells.item(2,2).text() == 'Robert'
    assert dialog.current_cells.verticalHeaderItem(2).text() == '3'
    assert dialog.accepted_changes() == found
    dialog.close()


def test_revision_additions_and_removals_show_context():
    app = QApplication.instance() or QApplication([])
    old = [['','CAMERA',''], ['Operator','','Bob'], ['Assistant','','Carol']]
    for new in (old[:2], old[:2]+[['Focus Puller','','Alice']]+old[2:]):
        found = diff(old, old, new)
        dialog = ChangeDialog(found, 'revision.xlsx', current_rows=old, incoming_rows=new)
        assert 'CAMERA' in dialog.detail_title.text()
        assert dialog.current_cells.item(0,1).text() == 'CAMERA'
        assert dialog.incoming_cells.item(1,2).text() == 'Bob'
        assert dialog.current_cells.rowCount() == max(len(old),len(new))
        dialog.close()
