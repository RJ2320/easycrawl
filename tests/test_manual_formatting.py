import pytest
from crawl import text
from crawl.project import Project, load_crawl
from crawl.layout import layout
from crawl.lint import lint
from crawl.ui.sheet_editor import SheetEditor


@pytest.mark.parametrize('alignment,anchor', [('left','ls'), ('center','ms'), ('right','rs')])
def test_paired_names_share_name_typography_and_baseline(alignment, anchor, tmp_path):
    rows = [['','CAMERA TEAM',''], ['Avery Morgan','','Robin Chen'], ['Alex Taylor','Jamie Reed','']]
    p = Project(); e = SheetEditor(p); e.load(rows)
    e.apply_layout([1,2], 'names_' + alignment)
    p.look.role.size = 30; p.look.name.size = 60; p.look.name.leading = 90
    result = layout(load_crawl(p), p.look)
    first = [line for line in result.lines if line.row == 2]
    second = [line for line in result.lines if line.row == 3]
    assert [line.text for line in first] == ['Avery Morgan', 'Robin Chen']
    assert all(line.style == 'name' and line.anchor == anchor for line in first + second)
    assert first[0].y == first[1].y and second[0].y - first[0].y == 90
    assert first[0].x < first[1].x
    assert not any(f.check == 'empty' for f in lint(load_crawl(p)))
    assert e.rows() == rows
    path = tmp_path/'names.crawl.json'; p.save(str(path))
    assert Project.load(str(path)).overrides == p.overrides
    e.undo(); assert not p.overrides
    e.redo(); assert p.overrides[0]['kind'] == 'names_' + alignment
    e.close()


def test_names_wrap_independently_and_next_row_clears_longest_cell():
    p = Project(); e = SheetEditor(p)
    e.load([['Avery Morgan\nAlex Taylor','','Robin Chen'],['Jamie Reed','','Casey Miller']])
    e.apply_layout([0,1], 'names_center')
    result = layout(load_crawl(p), p.look)
    lines = {line.text: line for line in result.lines}
    assert lines['Avery Morgan'].y == lines['Robin Chen'].y
    assert lines['Jamie Reed'].y - lines['Avery Morgan'].y == p.look.name.leading * 2
    e.close()


def test_bold_is_saved_separately_and_follows_rows_and_sheet_updates(tmp_path):
    rows = [['Role','','Avery Morgan'], ['Other','','Robin Chen']]
    p = Project(); e = SheetEditor(p); e.load(rows)
    e.table.setCurrentCell(0,2); e.apply_bold()
    assert e.rows() == rows and p.rows == rows
    result = layout(load_crawl(p),p.look)
    name = next(line for line in result.lines if line.row == 1 and line.style == 'name')
    assert name.text_style.bold
    assert '**' not in ''.join(value for _,value in text.runs(p.look.name,name.text))
    path = tmp_path/'format.crawl.json'; p.save(str(path))
    assert Project.load(str(path)).cell_formats == p.cell_formats
    e.undo(); assert not p.cell_formats
    e.redo(); assert p.cell_formats
    e.table.setCurrentCell(0,0); e.insert_rows(above=True,count=2)
    assert p.cell_formats[0]['start'] == 2
    from crawl.changes import source_diff
    new = [['','','']] + e.rows()
    e.apply_update(new,source_diff(e.rows(),new))
    assert p.cell_formats[0]['start'] == 3
    e.table.setCurrentCell(3,2); e.apply_bold(False)
    assert not p.cell_formats
    e.close()


def test_bold_applies_only_selected_name_cell_in_pair_and_skips_logos():
    p = Project(); e = SheetEditor(p); e.load([['Avery Morgan','','Robin Chen'],['[Logo: Example]','','']])
    e.apply_layout([0],'names_left')
    e.table.setCurrentCell(0,0); e.apply_bold()
    lines = layout(load_crawl(p), p.look).lines
    assert lines[0].text_style.bold
    assert lines[1].text_style is None
    e.table.setCurrentCell(1,0); e.apply_bold()
    assert len(p.cell_formats) == 1
    e.close()


def test_bold_wrap_and_italics_keep_formatting_and_use_real_bold_face():
    p = Project()
    runs = list(text.runs(p.look.name, '***Avery Morgan***'))
    assert runs[0][0].bold and runs[0][0].italic and runs[0][1] == 'Avery Morgan'
    assert text.font_for(runs[0][0]) is not None
    wrapped = text.wrap(p.look.name, '**Avery Morgan Robin Chen**', text.width(p.look.name,'**Avery Morgan**') + 1)
    assert len(wrapped) >= 2
    assert all(style.bold for line in wrapped for style,value in text.runs(p.look.name,line) if value.strip())


def test_alignment_override_inside_thanks_section_is_not_swallowed():
    p = Project(); e = SheetEditor(p)
    e.load([['','SPECIAL THANKS',''],['Avery Morgan','','Robin Chen'],['Alex Taylor','','Jamie Reed']])
    e.apply_layout([0,1,2], 'thanks', flow='sheet', title=True, columns=2)
    e.apply_layout([2], 'names_right')
    lines = [line for line in layout(load_crawl(p),p.look).lines if line.row == 3]
    assert len(lines) == 2 and all(line.style == 'name' and line.anchor == 'rs' for line in lines)
    e.close()


def test_bold_toggle_and_default_do_not_change_neighboring_cells():
    from types import SimpleNamespace
    from crawl.ui.workspace_navigation import WorkspaceNavigation
    p = Project(); e = SheetEditor(p); e.load([['Role','','Avery Morgan']])
    e.table.setCurrentCell(0,2)
    toolbar=WorkspaceNavigation(SimpleNamespace(project=p,sheet_editor=e))
    toolbar.refresh_selection()
    toolbar.bold.click(); assert p.cell_formats == [dict(start=0,end=0,column=2,bold=True)]
    toolbar.bold.click(); assert not p.cell_formats
    toolbar.close()
    e.close()


def test_bold_does_not_suppress_placeholder_warning():
    p = Project(rows=[['Role','','Name 3']], cell_formats=[dict(start=0,end=0,column=2,bold=True)])
    assert any(f.check == 'placeholder' for f in lint(load_crawl(p)))


def test_thanks_heading_font_override_is_independent_and_renders(tmp_path):
    from crawl.render import render_panel
    p = Project(); e = SheetEditor(p)
    e.load([['','Special Thanks',''],['Avery Morgan','','Robin Chen'],['','',''],['','OTHER HEADING','']])
    e.apply_layout([0,1],'thanks',title=True,flow='sheet',columns=2)
    shared = p.look.to_dict()
    e.apply_cell_format(dict(font=p.look.name.font,size=88,leading=112,bold=False,uppercase=False,alignment='left'),cells=[(0,1)])
    result = layout(load_crawl(p),p.look)
    heading = next(line for line in result.lines if line.row==1)
    other = next(line for line in result.lines if line.row==4)
    assert heading.style=='header' and heading.text=='Special Thanks' and heading.anchor=='ls'
    assert heading.text_style.size==88 and heading.text_style.leading==112
    assert 'bold' not in (text.fonts.resolve(heading.text_style.font) or text.fonts.resolve_default(heading.text_style.font)).style.lower()
    assert other.text_style is None and p.look.to_dict()==shared
    assert render_panel(result,p.look,0,result.content_height).getchannel('A').getbbox()
    path=tmp_path/'thanks.crawl.json';p.save(str(path))
    restored=layout(load_crawl(Project.load(str(path))),p.look)
    assert restored.lines[0].text_style==heading.text_style
    e.apply_cell_format({},cells=[(0,1)],reset=True)
    assert next(line for line in layout(load_crawl(p),p.look).lines if line.row==1).text_style is None
    e.close()


def test_name_pair_mixed_sizes_align_baselines_and_reserve_spacing():
    p=Project();e=SheetEditor(p)
    e.load([['Avery Morgan','','Robin Chen'],['Alex Taylor','','Jamie Reed']])
    e.apply_layout([0,1],'names_center')
    e.apply_cell_format(dict(size=100,bold=True),cells=[(0,0)])
    result=layout(load_crawl(p),p.look)
    first=[line for line in result.lines if line.row==1]
    second=[line for line in result.lines if line.row==2]
    assert first[0].y==first[1].y
    assert first[0].text_style.size==100 and first[0].text_style.leading==round(p.look.name.leading*100/p.look.name.size)
    assert second[0].y>first[0].y+p.look.name.leading
    assert first[1].text_style is None
    e.close()


def test_bold_toggle_preserves_other_manual_styling():
    p=Project();e=SheetEditor(p);e.load([['Role','','Avery Morgan']]);e.table.setCurrentCell(0,2)
    e.apply_cell_format(dict(size=84,alignment='right'))
    e.apply_bold(True);e.apply_bold(False)
    assert p.cell_formats==[dict(start=0,end=0,column=2,size=84,alignment='right')]
    e.close()


def test_manual_style_survives_arrangement_and_resolution_change():
    p=Project();e=SheetEditor(p)
    e.load([['','FIRST',''],['Role','','Avery Morgan'],['','',''],['','SECOND',''],['Role','','Robin Chen']])
    e.apply_arrangement([0,1,2,3,4],columns=2)
    e.apply_cell_format(dict(size=80,leading=120),cells=[(0,1)])
    line=next(line for line in layout(load_crawl(p),p.look).lines if line.row==1)
    assert line.text_style.size==80
    p.set_resolution(1920,1080)
    assert p.cell_formats[0]['size']==40 and p.cell_formats[0]['leading']==60
    e.close()


def test_format_dialog_applies_heading_font_and_size(monkeypatch):
    from PySide6.QtWidgets import QDialog, QComboBox, QDialogButtonBox, QSpinBox
    from crawl.ui.widgets import FontPicker
    p=Project();e=SheetEditor(p);e.load([['','SPECIAL THANKS','']]);e.table.setCurrentCell(0,1)
    def edit(dialog):
        for key in ('font','size'):
            dialog.findChild(QComboBox,'mode_'+key).setCurrentText('Custom')
        dialog.findChild(FontPicker,'format_font').set_value(p.look.name.font)
        dialog.findChild(QSpinBox,'format_size').setValue(90)
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
        return 1
    monkeypatch.setattr(QDialog,'exec',edit)
    e.format_dialog()
    heading=layout(load_crawl(p),p.look).lines[0]
    assert heading.text_style.size==90
    assert p.cell_formats[0]['font'] and p.rows==[['','SPECIAL THANKS','']]
    e.close()


def test_custom_font_file_is_collected_and_saved_portably(tmp_path):
    import json
    from pathlib import Path
    font=tmp_path/'example.ttf';font.write_bytes(b'font asset')
    folder=tmp_path/'project';folder.mkdir();path=folder/'example.crawl.json'
    p=Project(rows=[['','HEADING','']],cell_formats=[dict(start=0,end=0,column=1,font=str(font))])
    p.create_snapshot('Custom heading')
    assert p.collect(str(path))==['example.ttf']
    p.save(str(path));data=json.loads(path.read_text())
    assert not Path(data['cell_formats'][0]['font']).is_absolute()
    loaded=Project.load(str(path))
    assert Path(loaded.cell_formats[0]['font']).read_bytes()==b'font asset'
    assert loaded.snapshots[0]['state']['cell_formats']==loaded.cell_formats


def test_font_color_saves_undoes_and_renders_rgb_without_changing_text(tmp_path):
    import numpy as np
    from crawl.render import render_panel
    rows=[['','SPECIAL THANKS',''],['','','Avery Morgan']]
    p=Project();e=SheetEditor(p);e.load(rows)
    e.table.setCurrentCell(0,1);e.apply_cell_format(dict(color=(1.0,0.0,0.0)))
    result=layout(load_crawl(p),p.look)
    heading=result.lines[0]
    assert heading.text_style.color==(1.0,0.0,0.0)
    assert result.lines[1].text_style is None and e.rows()==rows and p.rows==rows
    pixels=np.array(render_panel(result,p.look,0,heading.y+20))
    ink=pixels[:,:,3]>0
    assert pixels[:,:,0][ink].max()>0
    assert pixels[:,:,1][ink].max()==0 and pixels[:,:,2][ink].max()==0
    path=tmp_path/'color.crawl.json';p.save(str(path))
    assert layout(load_crawl(Project.load(str(path))),p.look).lines[0].text_style.color==(1.0,0.0,0.0)
    e.undo();assert not p.cell_formats
    e.redo();assert p.cell_formats[0]['color']==[1.0,0.0,0.0]
    e.apply_cell_format(dict(color=None))
    assert not p.cell_formats
    e.close()


def test_font_color_picker_applies_selected_color(monkeypatch):
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QDialog,QComboBox,QColorDialog,QDialogButtonBox
    from crawl.ui.widgets import ColorPicker
    p=Project();e=SheetEditor(p);e.load([['','HEADING','']]);e.table.setCurrentCell(0,1)
    monkeypatch.setattr(QColorDialog,'getColor',lambda *args:QColor('#2878C8'))
    def edit(dialog):
        dialog.findChild(QComboBox,'mode_color').setCurrentText('Custom')
        picker=dialog.findChild(ColorPicker,'format_color');picker.click()
        assert picker.text()=='#2878C8'
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
        return 1
    monkeypatch.setattr(QDialog,'exec',edit)
    e.format_dialog()
    assert p.cell_formats[0]['color']==pytest.approx([40/255,120/255,200/255],abs=0.0001)
    e.close()


@pytest.mark.parametrize('color',[(1,0),(2,0,0),(float('nan'),0,0),'red'])
def test_invalid_font_color_does_not_change_project(color):
    p=Project();e=SheetEditor(p);e.load([['','HEADING','']]);e.table.setCurrentCell(0,1)
    before=e._state()
    with pytest.raises(ValueError,match='RGB'):
        e.apply_cell_format(dict(color=color))
    assert e._state()==before
    e.close()

def test_reset_one_setting_preserves_mixed_values(monkeypatch):
    from PySide6.QtWidgets import QDialog,QComboBox,QDialogButtonBox
    p=Project();e=SheetEditor(p);e.load([['','','First'],['','','Second']])
    cells=[(0,2),(1,2)]
    e.apply_cell_format(dict(size=80,bold=False,alignment='right'),cells=[cells[0]])
    e.apply_cell_format(dict(size=95,bold=True,alignment='right'),cells=[cells[1]])
    assert 'bold: off' in e.cell_tooltip(0,2)
    assert 'font size: 95 px' in e.cell_tooltip(1,2)
    def edit(dialog):
        assert dialog.findChild(QComboBox,'mode_size').currentText()=='Keep mixed values'
        dialog.findChild(QComboBox,'mode_alignment').setCurrentText('Use section default')
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
    monkeypatch.setattr(QDialog,'exec',edit)
    e.format_dialog(cells=cells)
    assert [(v['size'],v['bold']) for v in p.cell_formats]==[(80,False),(95,True)]
    assert all('alignment' not in v for v in p.cell_formats)
    e.undo()
    assert all(v['alignment']=='right' for v in p.cell_formats)
    e.close()

def test_no_wrap_toolbar_and_explicit_break_in_paired_names(monkeypatch):
    from PySide6.QtWidgets import QDialog,QPlainTextEdit,QPushButton
    from crawl.ui.main_window import MainWindow
    value="One unusually long full credit with several words"
    p=Project(rows=[[value,'','Second name']],overrides=[dict(start=0,end=0,kind='names_inward')])
    p.look.list_width=400
    win=MainWindow(p);win._debounce.stop()
    e=win.sheet_editor;e.table.setCurrentCell(0,0)
    nav=win.workspace_navigation
    nav.no_wrap.click()
    def rendered():
        return [line.text for line in layout(load_crawl(p),p.look).lines if line.column==0]
    assert rendered()==[value]
    def edit(dialog):
        entry=dialog.findChild(QPlainTextEdit)
        cursor=entry.textCursor();cursor.setPosition(3);entry.setTextCursor(cursor)
        next(b for b in dialog.findChildren(QPushButton) if b.text()=='Insert line break').click()
        return QDialog.Accepted
    monkeypatch.setattr(QDialog,'exec',edit)
    nav.line_breaks.click()
    assert [s.strip() for s in rendered()]==['One',value[4:]]
    e.undo();assert rendered()==[value]
    nav.no_wrap.click();assert len(rendered())>1
    win._debounce.stop();win._unsaved=False;win.close()
