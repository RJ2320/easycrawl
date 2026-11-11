import pytest
from PIL import Image
from crawl.project import Project, load_crawl
from crawl.layout import layout, _vertical_bounds


@pytest.mark.parametrize('flex',[.8,1,1.3])
@pytest.mark.parametrize('marked',[0,1,2])
def test_logo_boundaries_use_one_ink_gap_and_preserve_marked_spaces(tmp_path,flex,marked):
    path=tmp_path/'logo.png'
    Image.new('RGBA',(240,100),'white').save(path)
    p=Project(rows=[['','FIRST SECTION',''],['Role','','Avery Morgan'],
                    ['','',''],['','',''],['[Logo: A]','',''],
                    ['','',''],['','',''],['','NEXT SECTION','']],logos={'A':str(path)})
    if marked:
        p.spacer_rows=[dict(start=4-marked,end=3),dict(start=5,end=4+marked)]
    p.look.header_gap_before=300;p.look.header_gap_after=170;p.look.group_gap=123
    result=layout(load_crawl(p),p.look,flex)
    logo=result.logos[0]
    before=_vertical_bounds([line for line in result.lines if line.row==2],[],p.look)[1]
    after=_vertical_bounds([line for line in result.lines if line.row==8],[],p.look)[0]
    expected=(p.look.logo_gap+marked*p.look.group_gap)*flex
    assert logo.y-before==pytest.approx(expected,abs=1)
    assert after-(logo.y+logo.h)==pytest.approx(expected,abs=1)


def test_grid_spacing_rows_break_the_grid_and_add_space(tmp_path):
    path=tmp_path/'logo.png';Image.new('RGBA',(240,100),'white').save(path)
    p=Project(rows=[['[Logo: A]','',''],['','',''],['[Logo: B]','','']],
              logos={'A':str(path),'B':str(path)},
              arrangements=[dict(start=0,end=2,columns=2,gap=120,logo_grid=True)])
    p.spacer_rows=[dict(start=1,end=1)]
    result=layout(load_crawl(p),p.look)
    a,b=result.logos
    assert b.y-a.y-a.h==pytest.approx(p.look.logo_gap+p.look.group_gap,abs=1)


def test_logo_spacing_moves_all_following_text_together(tmp_path,monkeypatch):
    from crawl import layout as engine
    from crawl.look import Look
    from crawl.model import Crawl,Group,LogoRow,Logo,Header,RolePair,Legal
    path=tmp_path/'logo.png';Image.new('RGBA',(240,100),'white').save(path)
    crawl=Crawl(groups=[Group([Header('FIRST',row=1)]),
        Group([LogoRow([Logo('A',str(path))],row=2)]),
        Group([Header('SPECIAL THANKS',row=3)]),
        Group([RolePair('',[],row=4,name_cells=['Avery Morgan','Robin Chen'],name_alignment='inward'),
               RolePair('',['Jamie Reed'],row=5,center_names=True),
               RolePair('Performed by',['Taylor Quinn'],row=6,music=True)]),
        Group([Legal('Copyright Example Company',row=7)])])
    look=Look();result=engine.layout(crawl,look,.93)
    monkeypatch.setattr(engine,'_normalize_logo_spacing',lambda *args:None)
    original=engine.layout(crawl,look,.93)
    shifts=[new.y-old.y for new,old in zip(result.lines,original.lines) if new.row>=3]
    assert max(shifts)-min(shifts)<=1
    assert min(x.y for x in result.lines if x.row==7)>max(x.y for x in result.lines if x.row==6)
