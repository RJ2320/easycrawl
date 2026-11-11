import pytest
from crawl.project import Project,load_crawl
from crawl.layout import layout
from crawl.ui.sheet_editor import SheetEditor
from PySide6.QtWidgets import QDialog,QComboBox,QDialogButtonBox,QSpinBox

ROWS=[['','SPECIAL THANKS',''],['Avery Morgan','','Robin Chen'],['Casey Reed','','Alex Taylor'],['','','Final Person']]


def rendered(rows=ROWS,hidden=None):
    p=Project(hidden_rows=hidden or []);e=SheetEditor(p);e.load(rows)
    e.apply_layout(list(range(len(rows))),'thanks',title=True,columns=2,flow='sheet')
    return p,e,layout(load_crawl(p),p.look)


def test_match_sheet_keeps_left_right_names_and_missing_cells_on_original_rows():
    p,e,result=rendered()
    lines={line.text:line for line in result.lines if line.style=='list'}
    assert lines['Avery Morgan'].y==lines['Robin Chen'].y
    assert lines['Casey Reed'].y==lines['Alex Taylor'].y
    assert lines['Avery Morgan'].x==lines['Casey Reed'].x
    assert lines['Robin Chen'].x==lines['Alex Taylor'].x==lines['Final Person'].x
    assert lines['Avery Morgan'].x<lines['Robin Chen'].x
    assert lines['Final Person'].y>lines['Alex Taylor'].y
    assert [(name,line.row) for name,line in lines.items()]==[('Avery Morgan',2),('Robin Chen',2),('Casey Reed',3),('Alex Taylor',3),('Final Person',4)]
    assert e.rows()==ROWS;e.close()


def test_lone_middle_column_name_centers_without_creating_a_third_column():
    rows=ROWS[:-1]+[['','Final Person','']]
    p,e,result=rendered(rows)
    lines={line.text:line for line in result.lines if line.style=='list'}
    assert lines['Final Person'].x==p.look.center_x
    assert lines['Avery Morgan'].x<p.look.center_x<lines['Robin Chen'].x
    assert lines['Final Person'].y>lines['Alex Taylor'].y
    e.close()


def test_wraps_one_cell_without_separating_its_paired_name():
    rows=[ROWS[0],['Example Community Arts Partnership','','Robin Chen'],['Casey Reed','','Alex Taylor']]
    p=Project();p.look.list_width=900
    e=SheetEditor(p);e.load(rows);e.apply_layout([0,1,2],'thanks',title=True,flow='sheet',columns=2)
    result=layout(load_crawl(p),p.look)
    long=[line for line in result.lines if line.row==2 and line.text!='Robin Chen']
    assert len(long)>1
    right=next(line for line in result.lines if line.text=='Robin Chen')
    assert right.y==long[0].y
    assert min(line.y for line in result.lines if line.row==3)>max(line.y for line in long)
    e.close()


def test_hidden_rows_do_not_break_paired_names_or_source_coordinates():
    rows=[ROWS[0],ROWS[1],['','',''],ROWS[2]]
    p,e,result=rendered(rows,[dict(start=2,end=2)])
    assert [line.row for line in result.lines if line.style=='list']==[2,2,4,4]
    assert result.row_positions[4]-result.row_positions[2]==p.look.list.leading
    e.close()


def test_match_sheet_mode_saves_and_supports_undo(tmp_path):
    p,e,result=rendered()
    path=tmp_path/'thanks.crawl.json';p.save(str(path))
    restored=Project.load(str(path))
    assert restored.overrides[0]['flow']=='sheet'
    assert [(line.text,line.x,line.y) for line in layout(load_crawl(restored),restored.look).lines]==[(line.text,line.x,line.y) for line in result.lines]
    e.undo();assert not p.overrides
    e.redo();assert p.overrides[0]['flow']=='sheet'
    e.close()


def test_new_paired_section_defaults_to_match_sheet_dialog(monkeypatch):
    p=Project();e=SheetEditor(p);e.load(ROWS)
    from PySide6.QtWidgets import QTableWidgetSelectionRange
    e.table.setRangeSelected(QTableWidgetSelectionRange(0,0,3,2),True)
    def accept(dialog):
        flow=next(combo for combo in dialog.findChildren(QComboBox) if combo.findData('sheet')>=0)
        assert flow.currentData()=='sheet'
        columns=next(spin for spin in dialog.findChildren(QSpinBox) if spin.maximum()==6)
        assert not columns.isEnabled() and columns.value()==2
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
        return QDialog.Accepted
    monkeypatch.setattr(QDialog,'exec',accept)
    e.thanks_dialog();assert p.overrides[0]['flow']=='sheet'
    e.close()
