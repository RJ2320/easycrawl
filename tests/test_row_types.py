from crawl.ingest import parse
from crawl.layout import layout
from crawl.model import Header
from crawl.project import Project, load_crawl
from crawl.ui.sheet_editor import SheetEditor


def test_mixed_case_sections_follow_header_style_and_music_stays_separate():
    p=Project(rows=[['','Additional visual effects provided by Example Studio',''],
                    ['','',''],['','Music',''],['','"Example Song"',''],['Written by','','Avery Morgan']])
    crawl=load_crawl(p)
    headers=[b for b in crawl.blocks() if isinstance(b,Header)]
    assert [b.level for b in headers]==[1,1,2]
    result=layout(crawl,p.look)
    assert result.lines[0].style=='header'
    assert next(line for line in result.lines if line.row==4).style=='song'


def test_row_labels_follow_markings_undo_and_manual_styling():
    p=Project();e=SheetEditor(p)
    rows=[['','Additional photography',''],['Avery Morgan','','Robin Chen'],['','',''],['[Logo: Example]','','']]
    e.load(rows)
    assert 'Heading' in e.table.verticalHeaderItem(0).text()
    assert 'automatic' in e.table.verticalHeaderItem(0).toolTip()
    e.apply_layout([1],'names_center')
    assert 'Names only' in e.table.verticalHeaderItem(1).text()
    assert '✓' in e.table.verticalHeaderItem(1).text()
    assert 'marked manually' in e.table.verticalHeaderItem(1).toolTip()
    e.table.setCurrentCell(1,0);e.apply_bold()
    assert '*' in e.table.verticalHeaderItem(1).text()
    e.undo();assert '*' not in e.table.verticalHeaderItem(1).text()
    e.undo();assert 'Role / name' in e.table.verticalHeaderItem(1).text()
    assert e.rows()==rows
    assert 'Logos' in e.table.verticalHeaderItem(3).text()
    e.close()


def test_type_labels_are_a_view_option_and_do_not_modify_project_or_scroll():
    p=Project();e=SheetEditor(p);e.load([['','HEADING','']]+[['Role','','Avery Morgan']]*150)
    e.resize(700,350);e.show()
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()
    e.table.verticalScrollBar().setValue(300)
    scroll=e.table.verticalScrollBar().value();before=e._state()
    e.refresh_row_types()
    assert e.table.verticalScrollBar().value()==scroll
    e.set_row_types_visible(False)
    assert e.table.verticalHeaderItem(0).text()=='1' and e._state()==before
    e.set_row_types_visible(True)
    assert 'Heading' in e.table.verticalHeaderItem(0).text() and e._state()==before
    e.close()


def test_manual_heading_can_be_marked_in_any_single_cell():
    p=Project();e=SheetEditor(p);e.load([['Mixed case section','','']])
    e.apply_layout([0],'heading')
    assert next(load_crawl(p).blocks()).level==1
    assert 'marked manually' in e.table.verticalHeaderItem(0).toolTip()
    e.close()
