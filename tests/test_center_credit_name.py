import pytest
from crawl.project import Project,load_crawl
from crawl.layout import layout
from crawl.ui.sheet_editor import SheetEditor


ROWS=[['','FAMILY',''],['Parent One','','Avery Morgan'],['Parent Two','','Robin Chen'],['','','Alex Taylor']]


def test_selected_final_name_centers_without_changing_text_style_or_spacing(tmp_path):
    p=Project(rows=ROWS);e=SheetEditor(p);e.load(ROWS)
    before=layout(load_crawl(p),p.look)
    e.apply_layout([3],'center_name')
    result=layout(load_crawl(p),p.look)
    final=next(line for line in result.lines if line.row==4 and line.style=='name')
    assert final.x==p.look.center_x and final.anchor=='ms'
    assert final.y==before.row_positions[4]
    assert result.row_positions[4]-result.row_positions[3]==p.look.name.leading
    assert [(line.text,line.x,line.y,line.style,line.anchor) for line in result.lines if line.row<4]==[(line.text,line.x,line.y,line.style,line.anchor) for line in before.lines if line.row<4]
    assert e.rows()==ROWS
    path=tmp_path/'family.crawl.json';p.save(str(path))
    restored=Project.load(str(path))
    assert next(block for block in load_crawl(restored).blocks() if block.row==4).center_names
    e.undo();assert not p.overrides
    e.redo();assert p.overrides[0]['kind']=='center_name'
    e.apply_layout([3],'auto')
    assert not next(block for block in load_crawl(p).blocks() if block.row==4).center_names
    e.close()


def test_centering_rejects_role_name_pair_without_losing_text():
    p=Project();e=SheetEditor(p);e.load(ROWS)
    before=e._state()
    with pytest.raises(ValueError,match='name-only'):
        e.apply_layout([1],'center_name')
    assert e._state()==before
    e.close()


def test_centered_name_follows_inserted_rows_and_hidden_rows():
    p=Project(hidden_rows=[dict(start=2,end=2)])
    e=SheetEditor(p);e.load([ROWS[0],ROWS[1],['','',''],ROWS[3]])
    e.apply_layout([3],'center_name')
    e.table.setCurrentCell(0,0);e.insert_rows(above=True,count=2)
    result=layout(load_crawl(p),p.look)
    final=next(line for line in result.lines if line.row==6 and line.style=='name')
    assert final.anchor=='ms' and final.x==p.look.center_x
    assert result.row_positions[6]-result.row_positions[4]==p.look.name.leading
    e.close()


def test_centered_name_stays_name_style_when_master_moves_it_into_column_c():
    p=Project(rows=[['','AVERY MORGAN','']],overrides=[dict(start=0,end=0,kind='center_name')])
    result=layout(load_crawl(p),p.look)
    assert len(result.lines)==1 and result.lines[0].style=='name'
    assert result.lines[0].anchor=='ms' and result.lines[0].x==p.look.center_x
