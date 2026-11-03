import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from crawl import ingest, music, changes
from crawl.model import Header,RolePair,Legal,ListBlock
from crawl.project import Project,load_crawl,prepare
from crawl.layout import layout
from crawl.ui.sheet_editor import SheetEditor

ROWS=[['','MUSIC',''],['First song','',''],['Written by','','Example Writer'],['Performed by','','Example Artist'],['','',''],['','Second song',''],['Courtesy of','','Example Label'],['','',''],['Normal role','','Example Person']]


def test_explicit_songs_need_no_quotes_and_grid_renders():
    p=Project(rows=ROWS);e=SheetEditor(p);e.load(ROWS)
    blocks=music.blocks_from_selection(ROWS,list(range(7)))
    e.apply_music_blocks(blocks,columns=2,alignment='left',song_gap=80,title_gap=20)
    crawl=load_crawl(p)
    assert [b.text for b in crawl.blocks() if isinstance(b,Header) and b.level==2]==['First song','Second song']
    pairs=[b for b in crawl.blocks() if isinstance(b,RolePair)]
    assert [b.music for b in pairs]==[True,True,True,False]
    rendered=layout(crawl,p.look)
    assert rendered.row_positions[2]==rendered.row_positions[6]
    assert all(line.anchor=='ls' for line in rendered.lines if line.row in (2,3,4,6,7))
    e.close()


def test_music_roundtrip_undo_and_row_insertion(tmp_path):
    p=Project();e=SheetEditor(p);e.load(ROWS)
    blocks=music.blocks_from_selection(ROWS,list(range(7)))
    e.apply_music_blocks(blocks,columns=1)
    assert e.rows()==ROWS
    e.undo();assert p.music_blocks==[] and p.arrangements==[]
    e.redo();assert len(p.music_blocks)==2
    path=tmp_path/'example.crawl.json';p.save(str(path))
    restored=Project.load(str(path));assert restored.music_blocks==p.music_blocks
    e.table.setCurrentCell(0,0);e.insert_rows(above=True,count=15)
    assert p.music_blocks[0]['start']==16
    e.undo();assert e.rows()==ROWS and p.music_blocks[0]['start']==1
    e.remove_music(list(range(7)));assert not p.music_blocks and not p.arrangements
    assert e.rows()==ROWS
    e.close()


def test_music_blocks_follow_revision_row_shifts():
    p=Project();e=SheetEditor(p);e.load(ROWS)
    e.apply_music_blocks(music.blocks_from_selection(ROWS,list(range(7))))
    revised=[['New row','','']]+ROWS
    found=changes.diff(ROWS,ROWS,revised)
    e.apply_update(revised,found)
    assert p.music_blocks[0]['start']==2
    assert e.rows()==revised
    e.close()


def test_mark_short_legal_text_in_any_column_and_clear():
    p=Project();e=SheetEditor(p);rows=[['Short legal note','',''],['','Legal heading','']];e.load(rows)
    e.apply_layout([0,1],'legal')
    assert all(isinstance(b,Legal) for b in load_crawl(p).blocks())
    assert e.rows()==rows
    e.undo();assert not p.overrides
    e.redo();assert len([b for b in load_crawl(p).blocks() if isinstance(b,Legal)])==2
    e.apply_layout([0,1],'auto');assert not any(isinstance(b,Legal) for b in load_crawl(p).blocks())
    e.close()


def test_multiple_thanks_sections_keep_independent_columns(tmp_path):
    rows=[['Special thanks','',''],['Example One','',''],['Example Two','',''],['Additional thanks','',''],['Example Three','',''],['Example Four','','']]
    p=Project();e=SheetEditor(p);e.load(rows)
    e.apply_layout([0,1,2],'thanks',title=True,columns=2)
    e.apply_layout([3,4,5],'thanks',title=True,columns=3)
    crawl=load_crawl(p);lists=[b for b in crawl.blocks() if isinstance(b,ListBlock)]
    assert [b.columns for b in lists]==[2,3]
    assert [b.text for b in crawl.blocks() if isinstance(b,Header)]==['Special thanks','Additional thanks']
    assert len(p.overrides)==2 and e.rows()==rows
    p.timing.mode='manual';assert prepare(p).layout.lines
    path=tmp_path/'thanks.crawl.json';p.save(str(path));assert Project.load(str(path)).overrides==p.overrides
    e.close()


def test_removing_title_row_does_not_promote_credit_to_song_title():
    p=Project();e=SheetEditor(p);e.load(ROWS)
    e.apply_music_blocks(music.blocks_from_selection(ROWS,list(range(7))))
    e.table.clearSelection();e.table.setCurrentCell(1,0);e.delete_rows()
    assert p.music_blocks[0]['title'] is False
    assert any(isinstance(b,RolePair) and b.role=='Written by' and b.music for b in load_crawl(p).blocks())
    e.close()


def test_music_dialog_opens_and_cancel_does_not_change_data(monkeypatch):
    from PySide6.QtWidgets import QDialog,QTableWidget
    p=Project();e=SheetEditor(p);e.load(ROWS)
    from PySide6.QtWidgets import QTableWidgetSelectionRange
    e.table.setRangeSelected(QTableWidgetSelectionRange(0,0,6,2),True)
    def reject(dialog):
        table=dialog.findChild(QTableWidget)
        assert table.rowCount()==2
        return QDialog.Rejected
    monkeypatch.setattr(QDialog,'exec',reject)
    e.music_dialog();assert p.music_blocks==[] and e.rows()==ROWS
    e.close()


def test_music_dialog_apply_selects_side_by_side_and_undoes(monkeypatch):
    from PySide6.QtWidgets import QDialog,QComboBox,QDialogButtonBox,QTableWidgetSelectionRange
    p=Project();e=SheetEditor(p);e.load(ROWS)
    e.table.setRangeSelected(QTableWidgetSelectionRange(0,0,6,2),True)
    def apply(dialog):
        layout=dialog.findChildren(QComboBox)[0]
        layout.setCurrentIndex(1)
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
        return QDialog.Accepted
    monkeypatch.setattr(QDialog,'exec',apply)
    e.music_dialog()
    assert len(p.music_blocks)==2 and p.arrangements[0]['columns']==2
    assert e.table.columnSpan(1,0)==3
    e.undo();assert p.music_blocks==[] and p.arrangements==[]
    assert e.rows()==ROWS
    e.close()


def test_thanks_columns_and_heading_survive_legal_override():
    rows=[['Thanks','',''],['Example One','',''],['Example Two','','']]
    p=Project();e=SheetEditor(p);e.load(rows)
    e.apply_layout([0,1,2],'thanks',title=True,columns=2)
    e.apply_layout([1],'legal')
    assert any(isinstance(b,Legal) and b.text=='Example One' for b in load_crawl(p).blocks())
    assert [b.names for b in load_crawl(p).blocks() if isinstance(b,ListBlock)]==[['Example Two']]
    assert next(o for o in p.overrides if o['start']==2)['title'] is False
    e.close()


def test_invalid_music_layout_does_not_change_project():
    p=Project();e=SheetEditor(p);e.load(ROWS)
    original=e._state()
    with pytest.raises(ValueError,match='overlap'):
        e.apply_music_blocks([dict(start=1,end=3,title=True),dict(start=3,end=6,title=True)])
    assert e._state()==original
    e.close()


def test_thanks_wraps_long_and_multiline_entries_without_row_overlap():
    from crawl import text
    p=Project()
    p.look.list_width=900
    p.look.list_column_gap=100
    rows=[['','SPECIAL THANKS',''],['Example Community Arts Partnership','',''],
          ['First Person\nSecond Person','',''],['Next Person','',''],
          ['Another Community Organisation','',''],['Other Person','',''],['Final Person','','']]
    e=SheetEditor(p);e.load(rows)
    e.apply_layout(list(range(7)),'thanks',title=True,columns=2)
    result=layout(load_crawl(p),p.look)
    names=[line for line in result.lines if line.style=='list']
    assert len([line for line in names if line.row==2])>1
    assert len([line for line in names if line.row==3])==2
    assert all('\n' not in line.text for line in names)
    assert all(text.width(p.look.list,line.text)<=400 for line in names)
    for col in {line.x for line in names}:
        lines=[line for line in names if line.x==col]
        assert all(b.y-a.y>=p.look.list.leading for a,b in zip(lines,lines[1:]))
    assert result.row_positions[3]==result.row_positions[6]
    assert result.row_positions[4]>max(line.y for line in names if line.row==3)
    e.close()


@pytest.mark.parametrize('blank_count',[1,3])
def test_ignore_blank_rows_below_heading_preserves_rows_and_normalizes_gap(blank_count,tmp_path):
    rows=[['','SECTION ONE','']]+[['','','']]*blank_count+[['Role','','Person'],['','',''],['','SECTION TWO',''],['Role','','Person']]
    p=Project(rows=rows)
    result=layout(load_crawl(p),p.look)
    first_gap=result.row_positions[blank_count+2]-result.row_positions[1]
    second_gap=result.row_positions[blank_count+5]-result.row_positions[blank_count+4]
    assert first_gap==second_gap
    assert len(load_crawl(p).groups)==2  # blank after credits still separates sections
    assert p.rows==rows
    p.look.ignore_blank_after_header=False
    legacy=layout(load_crawl(p),p.look)
    assert legacy.row_positions[blank_count+2]-legacy.row_positions[1]==first_gap+p.look.group_gap
    path=tmp_path/'spacing.crawl.json';p.save(str(path))
    assert Project.load(str(path)).look.ignore_blank_after_header is False


def test_ignore_heading_blanks_does_not_change_song_title_spacing():
    rows=[['','MUSIC',''],['','"Example song"',''],['','',''],['Written by','','Example Writer']]
    a=Project(rows=rows);b=Project(rows=rows)
    b.look.ignore_blank_after_header=False
    assert layout(load_crawl(a),a.look).row_positions==layout(load_crawl(b),b.look).row_positions


def test_thanks_widths_are_independent_saved_undoable_and_resolution_relative(tmp_path):
    rows=[['','FIRST THANKS',''],['Example One','',''],['Example Two','',''],
          ['','SECOND THANKS',''],['Example Three','',''],['Example Four','','']]
    p=Project();e=SheetEditor(p);e.load(rows)
    e.apply_layout([0,1,2],'thanks',title=True,columns=2,width_percent=55)
    e.apply_layout([3,4,5],'thanks',title=True,columns=2,width_percent=80)
    rendered=layout(load_crawl(p),p.look)
    def distance(result,first,last):
        xs=[line.x for line in result.lines if line.style=='list' and first<=line.row<=last]
        return max(xs)-min(xs)
    assert distance(rendered,2,3)<distance(rendered,5,6)
    e.undo();assert len(p.overrides)==1 and p.overrides[0]['width_percent']==55
    e.redo();assert p.overrides[1]['width_percent']==80
    path=tmp_path/'widths.crawl.json';p.save(str(path));restored=Project.load(str(path))
    assert restored.overrides==p.overrides
    restored.set_resolution(1920,1080)
    assert [item['width_percent'] for item in restored.overrides]==[55,80]
    small=layout(load_crawl(restored),restored.look)
    assert abs(distance(small,2,3)*2-distance(rendered,2,3))<=2
    assert e.rows()==rows
    e.close()


def test_thanks_dialog_applies_and_reopens_section_width(monkeypatch):
    from PySide6.QtWidgets import QDialog,QSpinBox,QDialogButtonBox
    p=Project();e=SheetEditor(p);e.load([['','THANKS',''],['Example One','',''],['Example Two','','']])
    from PySide6.QtWidgets import QTableWidgetSelectionRange
    e.table.setRangeSelected(QTableWidgetSelectionRange(0,0,2,2),True)
    def accept(dialog):
        width=next(control for control in dialog.findChildren(QSpinBox) if control.suffix()==' % of frame')
        assert width.value()==55
        width.setValue(63)
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
        return QDialog.Accepted
    monkeypatch.setattr(QDialog,'exec',accept)
    e.thanks_dialog();assert p.overrides[0]['width_percent']==63
    def reopen(dialog):
        width=next(control for control in dialog.findChildren(QSpinBox) if control.suffix()==' % of frame')
        assert width.value()==63
        width.reset_button.click();assert width.value()==55
        dialog.reject();return QDialog.Rejected
    monkeypatch.setattr(QDialog,'exec',reopen)
    e.thanks_dialog();assert p.overrides[0]['width_percent']==63
    e.close()
