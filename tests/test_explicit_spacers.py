from PySide6.QtWidgets import QTableWidgetSelectionRange
from crawl.model import Spacer
from crawl.project import Project,load_crawl
from crawl.layout import layout
from crawl.ui.sheet_editor import SheetEditor
from crawl.changes import source_diff


ROWS=[['First role','','Avery Morgan'],['','',''],['','',''],['Next role','','Robin Chen']]


def test_consecutive_marked_empty_rows_each_add_space_and_can_be_cleared(tmp_path):
    p=Project(rows=ROWS);e=SheetEditor(p);e.load(ROWS)
    original=layout(load_crawl(p),p.look)
    e.table.setRangeSelected(QTableWidgetSelectionRange(1,0,2,2),True)
    e.set_spacer_rows(True)
    result=layout(load_crawl(p),p.look)
    assert result.row_positions[4]-result.row_positions[1]==p.look.name.leading+2*p.look.group_gap
    assert len([block for block in load_crawl(p).blocks() if isinstance(block,Spacer)])==2
    assert e.rows()==ROWS and e.table.spacer_rows=={1,2}
    assert 'Spacing' in e.table.verticalHeaderItem(1).text()
    path=tmp_path/'spacing.crawl.json';p.save(str(path))
    assert Project.load(str(path)).spacer_rows==[dict(start=1,end=2)]
    e.undo();assert not p.spacer_rows
    e.redo();assert p.spacer_rows
    e.table.setRangeSelected(QTableWidgetSelectionRange(1,0,2,2),True)
    e.set_spacer_rows(False)
    assert layout(load_crawl(p),p.look).row_positions==original.row_positions
    e.close()


def test_explicit_spacing_overrides_hidden_rows_and_heading_blank_suppression():
    p=Project(rows=[['','HEADING',''],['','',''],['Role','','Avery Morgan']],hidden_rows=[dict(start=1,end=1)])
    e=SheetEditor(p);e.load(p.rows)
    before=layout(load_crawl(p),p.look)
    assert e.table.isRowHidden(1)
    e.table.setCurrentCell(1,0);e.set_spacer_rows(True)
    result=layout(load_crawl(p),p.look)
    assert not e.table.isRowHidden(1)
    assert result.row_positions[3]-before.row_positions[3]==p.look.group_gap
    assert next(block for block in load_crawl(p).blocks() if isinstance(block,Spacer)).row==2
    e.close()


def test_spacer_marks_follow_insert_and_source_updates_without_marking_new_rows():
    p=Project(rows=ROWS);e=SheetEditor(p);e.load(ROWS)
    e.table.setCurrentCell(1,0);e.set_spacer_rows(True)
    e.insert_rows(above=True,count=1)
    assert p.spacer_rows==[dict(start=2,end=2)]
    incoming=[['New role','','Jamie Reed']]+e.rows()
    e.apply_update(incoming,source_diff(e.rows(),incoming))
    assert p.spacer_rows==[dict(start=3,end=3)]
    assert [block.row for block in load_crawl(p).blocks() if isinstance(block,Spacer)]==[4]
    e.close()


def test_spacer_mark_does_not_hide_or_replace_credit_text():
    p=Project(rows=ROWS);e=SheetEditor(p);e.load(ROWS)
    e.table.setRangeSelected(QTableWidgetSelectionRange(0,0,1,2),True)
    e.set_spacer_rows(True)
    assert p.spacer_rows==[dict(start=1,end=1)] and p.rows==ROWS
    e.table.item(1,2).setText('Jamie Reed')
    assert 1 not in e.table.spacer_rows
    assert not any(isinstance(block,Spacer) for block in load_crawl(p).blocks())
    assert any(line.text=='Jamie Reed' for line in layout(load_crawl(p),p.look).lines)
    e.close()


def test_trailing_explicit_spacing_is_reserved_in_content_height():
    p=Project(rows=[['Role','','Avery Morgan'],['','',''],['','','']],spacer_rows=[dict(start=1,end=2)])
    result=layout(load_crawl(p),p.look)
    assert result.content_height>=p.look.name.leading+2*p.look.group_gap


def test_spacing_inside_thanks_keeps_left_and_right_column_slots():
    p=Project();e=SheetEditor(p)
    e.load([['','Special Thanks',''],['Avery Morgan','',''],['','',''],['','','Robin Chen']])
    e.apply_layout([0,1,2,3],'thanks',title=True,columns=2,flow='sheet',column_gap=120,left_alignment='right',right_alignment='left')
    e.table.setCurrentCell(2,0);e.set_spacer_rows(True)
    result=layout(load_crawl(p),p.look)
    left=next(line for line in result.lines if line.row==2)
    right=next(line for line in result.lines if line.row==4)
    assert (left.anchor,left.x)==('rs',p.look.center_x-60)
    assert (right.anchor,right.x)==('ls',p.look.center_x+60)
    e.close()
