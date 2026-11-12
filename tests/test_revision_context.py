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

def test_move_is_one_review_decision_in_either_direction():
    from PySide6.QtCore import Qt
    from crawl import changes
    app=QApplication.instance() or QApplication([])
    old=[('','','Ada'),('','','Bea'),('','','Cy'),('','','Dee')]
    for new in ([old[-1],*old[:-1]], [*old[1:],old[0]]):
        for found in (changes.diff(old,old,new),changes.source_diff(old,new)):
            dialog=ChangeDialog(found,'revision.xlsx',current_rows=old,incoming_rows=new)
            assert dialog.table.rowCount()==1
            assert dialog.table.item(0,0).text()=='Move credit'
            assert dialog.apply_button.text()=='Apply 1 change'
            assert [tuple(r) for r in changes.apply(old,dialog.accepted_changes())[0]]==new
            dialog.table.item(0,0).setCheckState(Qt.Unchecked)
            assert dialog.accepted_changes()==[]
            assert [tuple(r) for r in changes.apply(old,found)[0]]==old
            dialog.close()


def test_move_beside_new_credit_can_be_skipped_independently():
    from crawl import changes
    old=[('','','Ada'),('','','Bea'),('','','Cy'),('','','Dee')]
    extra=('','','Eli')
    new=[extra,old[-1],*old[:-1]]
    found=changes.diff(old,old,new)
    assert sorted(c.kind for c in found)==['add','move']
    assert [tuple(r) for r in changes.apply(old,found)[0]]==new
    next(c for c in found if c.kind=='move').accepted=False
    assert [tuple(r) for r in changes.apply(old,found)[0]]==[extra,*old]


def test_duplicate_move_is_not_paired():
    from crawl import changes
    old=[('','','Ada'),('','','Bea'),('','','Cy'),('','','Dee'),('','','Ada')]
    new=[*old[1:4],old[0],old[-1]]
    assert all(c.kind!='move' for c in changes.diff(old,old,new))

def test_moved_credit_keeps_manual_format_with_partial_acceptance():
    from crawl.project import Project
    from crawl.ui.sheet_editor import SheetEditor
    app=QApplication.instance() or QApplication([])
    rows=[('','','Ada'),('','','Bea'),('','','Cy'),('','','Dee')]
    new=[('','','Eli'),rows[-1],*rows[:-1]]
    p=Project();editor=SheetEditor(p);editor.load(rows)
    editor.apply_cell_format(dict(size=71),cells=[(3,2)])
    found=diff(rows,rows,new)
    editor.apply_update(new,[c for c in found if c.kind=='move'])
    assert editor.rows()[0][2]=='Dee'
    assert p.cell_formats==[dict(start=0,end=0,column=2,size=71)]
    editor.undo()
    assert editor.rows()[3][2]=='Dee' and p.cell_formats[0]['start']==3
    editor.close()
