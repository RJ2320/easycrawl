from pathlib import Path
import pytest
from PIL import Image
from PySide6.QtWidgets import QDialog,QDialogButtonBox,QLineEdit
from crawl.project import Project,load_crawl
from crawl.model import LogoRow,ListBlock
from crawl.ui.sheet_editor import SheetEditor


def editor(rows):
    project=Project()
    sheet=SheetEditor(project);sheet.load(rows)
    return project,sheet


def test_convert_selected_header_cell_in_place_and_undo():
    rows=[['','Example Studio',''],['Next role','','Example Person']]
    p,e=editor(rows)
    e.apply_logo_cells([(0,1)])
    assert e.rows()==[['[Logo: Example Studio]','',''],rows[1]]
    assert isinstance(next(load_crawl(p).blocks()),LogoRow)
    e.undo();assert e.rows()==rows
    e.redo();assert e.rows()[0][0]=='[Logo: Example Studio]'
    e.close()


def test_convert_name_column_and_assign_artwork_roundtrip(tmp_path):
    image=tmp_path/'Studio.png';Image.new('RGBA',(100,50),'white').save(image)
    p,e=editor([['','','Example Studio']])
    e.apply_logo_cells([(0,2)],path=str(image))
    assert p.logos['Example Studio']==str(image.resolve())
    path=tmp_path/'project.crawl.json';p.save(str(path))
    restored=Project.load(str(path))
    assert next(load_crawl(restored).logos()).path==str(image.resolve())
    e.undo();assert not p.logos and e.rows()==[['','','Example Studio']]
    e.close()


def test_multi_cell_logo_row_has_correct_labels_without_extra_rows():
    p,e=editor([['First Studio','','Second Studio'],['Third Studio','','']])
    e.apply_logo_cells([(0,0),(0,2),(1,0)])
    assert len(e.rows())==2
    assert [logo.label for logo in load_crawl(p).logos()]==['First Studio','Second Studio','Third Studio']
    e.close()


def test_partial_row_conversion_does_not_destroy_neighboring_names():
    p,e=editor([['Example role','','Example Person']])
    before=e._state()
    with pytest.raises(ValueError,match='other credit text'):
        e.apply_logo_cells([(0,0)])
    assert e._state()==before
    e.close()


def test_logo_conversion_overrides_thanks_or_legal_without_absorbing_neighbors():
    p,e=editor([['Example Studio','',''],['Example Person','',''],['Another Person','','']])
    e.apply_layout([0,1,2],'thanks',title=True,columns=2)
    e.apply_logo_cells([(0,0)])
    blocks=list(load_crawl(p).blocks())
    assert isinstance(blocks[0],LogoRow)
    assert isinstance(blocks[1],ListBlock) and blocks[1].names==['Example Person','Another Person']
    assert p.overrides[0]['title'] is False
    e.undo();assert p.overrides[0]['start']==0 and p.overrides[0]['title']
    e.close()


def test_conversion_never_changes_other_logo_assignments(tmp_path):
    image=tmp_path/'Studio.png';Image.new('RGBA',(100,50),'white').save(image)
    p,e=editor([['[Logo: Studio]','',''],['','Studio','']])
    p.logos['Studio']='original.png';e.commit_undo()
    e.apply_logo_cells([(1,1)],path=str(image))
    assert p.logos['Studio']=='original.png' and p.logos['Studio 2']==str(image.resolve())
    e.close()


def test_logo_dialog_uses_cell_text_and_applies_once(monkeypatch):
    p,e=editor([['','Example Studio','']])
    e.table.setCurrentCell(0,1)
    def accept(dialog):
        field=dialog.findChild(QLineEdit)
        assert field.text()=='Example Studio'
        field.setText('New Studio')
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
        return QDialog.Accepted
    monkeypatch.setattr(QDialog,'exec',accept)
    e._apply_layout_to_selection('logo')
    assert e.rows()[0][0]=='[Logo: New Studio]'
    e.undo();assert e.rows()==[['','Example Studio','']]
    e.close()


def test_empty_cell_can_become_named_logo_placeholder():
    p,e=editor([['','','']])
    e.apply_logo_cells([(0,2)],name='My Studio')
    assert next(load_crawl(p).logos()).label=='My Studio'
    assert len(e.rows())==1
    e.close()
