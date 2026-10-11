import csv
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from crawl.project import Project
from crawl.changes import diff, apply


@pytest.fixture(scope='module')
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def write_sheet(tmp_path,name,rows):
    path=tmp_path/name
    with path.open('w',newline='') as f:
        csv.writer(f).writerows([['']+r for r in rows])
    return str(path)


def test_history_save_reload_and_legacy(tmp_path):
    rows=[['Director','','Alice']]
    p=Project(source=write_sheet(tmp_path,'first.csv',rows), rows=rows, base_rows=rows)
    assert p.record_import(rows)
    first=p.import_history[0]
    assert first['imported_at'] and first['row_count']==1
    assert not p.record_import(rows,'No changes',deduplicate=True)
    p.record_import(rows,'No changes')
    path=tmp_path/'test.crawl.json';p.save(str(path))
    loaded=Project.load(str(path))
    assert loaded.import_history==p.import_history
    assert Project.from_dict({'rows':rows}).import_history==[]
    snap=p.create_snapshot('Before revision')
    p.record_import([['Director','','Bob']],'Updated',applied=1)
    p.restore_snapshot(snap['id'])
    assert len(p.import_history)==3  # Restoring credits does not erase import history.


def test_real_import_update_cancel_and_no_changes(app,tmp_path,monkeypatch):
    from crawl.ui.main_window import MainWindow
    from crawl.ui.change_dialog import ChangeDialog
    from crawl.ui.import_history_dialog import ImportHistoryDialog
    from PySide6.QtWidgets import QMessageBox
    rows=[['Director','','Alice'],['Producer','','Bob']]
    first=write_sheet(tmp_path,'first.csv',rows)
    revised=write_sheet(tmp_path,'revised.csv',[['Director','','Ada'],rows[1]])
    win=MainWindow(Project(source=first));win._debounce.stop()
    p=win.project
    assert len(p.import_history)==1
    assert 'first.csv' in win.sheet_editor.import_label.text()
    p.source_url='https://example.com/original'
    monkeypatch.setattr(ChangeDialog,'exec',lambda self: ChangeDialog.Rejected)
    assert win.update_from_sheet(revised) is None
    assert len(p.import_history)==1 and p.source==first
    assert p.source_url=='https://example.com/original'
    monkeypatch.setattr(ChangeDialog,'exec',lambda self: ChangeDialog.Accepted)
    win.update_from_sheet(revised);win._debounce.stop()
    assert len(p.import_history)==2
    assert p.import_history[-1]['applied']==1
    assert p.import_history[-1]['source']==revised and p.source_url==''
    assert p.rows[0][2]=='Ada'
    assert 'revised.csv' in win.sheet_editor.import_label.text()
    monkeypatch.setattr(QMessageBox,'information',lambda *args: None)
    win.update_from_sheet(revised)
    assert len(p.import_history)==3 and p.import_history[-1]['action']=='No changes'
    win.update_from_sheet(revised,silent=True)
    assert len(p.import_history)==3
    dialog=ImportHistoryDialog(p)
    assert dialog.table.item(0,1).text()=='revised.csv'
    assert dialog.table.item(2,1).text()=='first.csv'
    win._unsaved=False
    win.close()


def test_compare_details_conflict_defaults_and_decisions(app):
    from crawl.ui.change_dialog import ChangeDialog
    base=[['Director','','Alice'],['Producer','','Bob']]
    current=[['Director','','Alice Smith'],base[1]]
    incoming=[['Directed by','','Alice'],base[1],['Editor','','Cleo']]
    found=diff(base,current,incoming)
    dialog=ChangeDialog(found,'revision.xlsx')
    assert found[0].conflict and not found[0].accepted
    assert dialog.current_cells.item(0,2).text()=='Alice Smith'
    assert dialog.incoming_cells.item(0,0).text()=='Directed by'
    assert 'Keep current' in dialog.detail_title.text()
    dialog._toggle_current()
    assert found[0].accepted and 'Replace' in dialog.detail_title.text()
    dialog._step(1)
    assert dialog.current_cells.item(0,2).text()=='—'
    assert dialog.incoming_cells.item(0,2).text()=='Cleo'
    assert dialog.incoming_cells.verticalHeaderItem(0).text()=='3'
    dialog._set_all(False)
    assert dialog.accepted_changes()==[]
    assert 'keep current' in dialog.apply_button.text()
    assert 'including skipped changes' in dialog.decision_summary.text()


def test_list_additions_preserve_original_and_local_names():
    base=[[name,'',''] for name in ('Alice','Bob','Cleo','Dara')]
    current=base[:2]+[['Local name','','']]+base[2:]
    incoming=base[:2]+[['Incoming name','','']]+base[2:]
    found=diff(base,current,incoming)
    assert len(found)==1 and found[0].kind=='add' and not found[0].conflict
    result,_,_=apply(current,found)
    assert [r[0] for r in result]==['Alice','Bob','Local name','Incoming name','Cleo','Dara']
    # Multiple names inside a single cell are a conflicting row replacement,
    # not a union that silently preserves all names.
    base=[['Thanks','','Alice\nBob']]
    current=[['Thanks','','Alice\nBob\nLocal name']]
    incoming=[['Thanks','','Alice\nBob\nIncoming name']]
    found=diff(base,current,incoming)
    assert found[0].conflict
    assert apply(current,found)[0]==incoming
