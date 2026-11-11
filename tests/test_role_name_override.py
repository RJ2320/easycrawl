import pytest
from crawl.project import Project,load_crawl
from crawl.model import RolePair
from crawl.layout import layout
from crawl.ui.sheet_editor import SheetEditor


ROWS=[['','MUSIC',''],['','"Example score"',''],['Conductor','','Example Musician']]


def test_role_name_override_accepts_populated_pair_and_overrides_music(tmp_path):
    p=Project();e=SheetEditor(p);e.load(ROWS)
    e.apply_layout([2],'roles')
    block=next(b for b in load_crawl(p).blocks() if b.row==3)
    assert isinstance(block,RolePair) and not block.music and block.two_column
    assert block.role=='Conductor' and block.names==['Example Musician']
    result=layout(load_crawl(p),p.look)
    role,name=[line for line in result.lines if line.row==3]
    assert (role.style,role.anchor,role.x)==('role','rs',p.look.center_x-p.look.gutter//2)
    assert (name.style,name.anchor,name.x)==('name','ls',p.look.center_x+p.look.gutter//2)
    assert role.y==name.y and e.rows()==ROWS
    path=tmp_path/'score.crawl.json';p.save(str(path))
    assert next(b for b in load_crawl(Project.load(str(path))).blocks() if b.row==3).two_column
    e.undo();assert not p.overrides
    e.redo();assert p.overrides[0]['kind']=='roles'
    e.close()


def test_two_column_override_also_wins_inside_explicit_music_block():
    p=Project();e=SheetEditor(p);e.load([['Example title','',''],['Conductor','','Example Musician']])
    e.apply_music_blocks([dict(start=0,end=1,title=True)],columns=1)
    e.apply_layout([1],'roles')
    result=layout(load_crawl(p),p.look)
    lines=[line for line in result.lines if line.row==2]
    assert [line.anchor for line in lines]==['rs','ls']
    assert [line.style for line in lines]==['role','name']
    e.close()


def test_roles_accept_b_only_pending_and_name_continuations():
    p=Project();e=SheetEditor(p);e.load([['Conductor','',''],['','','Example Musician']])
    e.apply_layout([0,1],'roles')
    blocks=list(load_crawl(p).blocks())
    assert blocks[0].names_pending and blocks[1].names==['Example Musician']
    e.close()


def test_roles_reject_heading_without_changing_project():
    p=Project();e=SheetEditor(p);e.load([['','SECTION HEADING','']])
    before=e._state()
    with pytest.raises(ValueError,match='section headings'):
        e.apply_layout([0],'roles')
    assert e._state()==before
    e.close()
