import pytest
from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QMenu,QTableWidgetSelectionRange,QApplication

from crawl.project import Project,load_crawl
from crawl.layout import layout
from crawl.ui.sheet_editor import SheetEditor


def test_manual_breaks_in_heading_and_role_render_as_lines_and_reserve_height():
    p=Project(rows=[['','Additional\nPhotography',''],['Assistant\nEditor','','Avery Morgan'],['Next role','','Robin Chen']])
    result=layout(load_crawl(p),p.look)
    heading=[line for line in result.lines if line.row==1]
    role=[line for line in result.lines if line.row==2 and line.style=='role']
    assert len(heading)==2 and len(role)==2
    assert all('\n' not in line.text for line in result.lines)
    next_name=next(line for line in result.lines if line.row==3 and line.style=='name')
    first_name=next(line for line in result.lines if line.row==2 and line.style=='name')
    assert next_name.y-first_name.y>=2*p.look.name.leading


def test_wrap_is_local_and_persists_without_editing_source(tmp_path):
    rows=[['A sufficiently long role title with several words','','A sufficiently long full credit name with several words'],['Next','','Robin Chen']]
    p=Project(rows=rows);e=SheetEditor(p);e.load(rows)
    p.look.list_width=1100
    before=layout(load_crawl(p),p.look)
    e.apply_cell_format(dict(wrap=True),cells=[(0,0),(0,2)])
    result=layout(load_crawl(p),p.look)
    assert len([line for line in result.lines if line.row==1 and line.style=='role'])>1
    assert len([line for line in result.lines if line.row==1 and line.style=='name'])>1
    assert result.row_positions[2]>before.row_positions[2]
    assert e.rows()==rows
    path=tmp_path/'wrap.crawl.json';p.save(str(path))
    assert Project.load(str(path)).cell_formats==p.cell_formats
    e.undo();assert not p.cell_formats
    e.close()


def test_context_click_targets_clicked_cell_and_preserves_existing_selection(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    def unexpected(*args):raise AssertionError(str(args[1:]))
    monkeypatch.setattr(QMessageBox,'information',unexpected)
    p=Project();e=SheetEditor(p);e.load([['First','',''],['Second','',''],['Third','','']]);e.resize(800,400);e.show();QApplication.processEvents()
    class Menu:
        def exec(self,*args):pass
    monkeypatch.setattr(e,'_build_context_menu',lambda:Menu())
    e.table.setCurrentCell(0,0)
    point=e.table.viewport().mapToGlobal(e.table.visualItemRect(e.table.item(2,0)).center())
    e._context_menu(point)
    assert e._selected_rows()==[2]
    e._apply_layout_to_selection('center')
    assert p.overrides==[dict(start=2,end=2,kind='center')]
    e.table.clearSelection();e.table.setRangeSelected(QTableWidgetSelectionRange(0,0,1,0),True)
    point=e.table.viewport().mapToGlobal(e.table.visualItemRect(e.table.item(1,0)).center())
    e._context_menu(point)
    assert e._selected_rows()==[0,1]
    e.close()


def test_context_hides_inapplicable_layouts():
    p=Project();e=SheetEditor(p);e.load([['','HEADING','']]);e.table.setCurrentCell(0,1)
    menu=e._build_context_menu();layouts=next(a.menu() for a in menu.actions() if a.text()=='Layout')
    choices={a.data():a for a in layouts.actions() if a.data()}
    assert not choices['center'].isVisible() and not choices['roles'].isVisible()
    assert choices['heading'].isVisible()
    e.close()


def test_thanks_columns_can_face_middle_gap_and_keep_centered_exceptions(tmp_path):
    p=Project();e=SheetEditor(p)
    e.load([['','Special Thanks',''],['Avery Morgan','','Robin Chen'],['','Jamie Reed',''],['Alex Taylor','','Casey Miller']])
    e.apply_layout([0,1,2,3],'thanks',title=True,columns=2,flow='sheet',column_gap=160,left_alignment='right',right_alignment='left')
    lines=layout(load_crawl(p),p.look).lines
    left,right=[line for line in lines if line.row==2]
    assert (left.anchor,left.x)==('rs',p.look.center_x-80)
    assert (right.anchor,right.x)==('ls',p.look.center_x+80)
    center=next(line for line in lines if line.row==3)
    assert center.anchor=='ms' and center.x==p.look.center_x
    path=tmp_path/'thanks.crawl.json';p.save(str(path))
    assert Project.load(str(path)).overrides==p.overrides
    e.undo();assert not p.overrides
    e.close()


def test_thanks_dialog_applies_each_column_alignment(monkeypatch):
    from PySide6.QtWidgets import QDialog,QComboBox,QDialogButtonBox
    p=Project();e=SheetEditor(p)
    e.load([['','Special Thanks',''],['Avery Morgan','','Robin Chen']])
    e.apply_layout([0,1],'thanks',title=True,columns=2,flow='sheet')
    e.table.setCurrentCell(1,0)
    def choose(dialog):
        for key,value in [('left','right'),('right','left')]:
            control=dialog.findChild(QComboBox,'thanks_'+key+'_alignment')
            assert control.isEnabled();control.setCurrentIndex(control.findData(value))
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
        return 1
    monkeypatch.setattr(QDialog,'exec',choose)
    e.thanks_dialog()
    assert p.overrides[0]['left_alignment']=='right' and p.overrides[0]['right_alignment']=='left'
    e.close()


def test_names_only_face_center_uses_role_name_positions_and_name_style():
    p=Project();e=SheetEditor(p)
    e.load([['Avery Morgan','','Robin Chen'],['','Jamie Reed','']])
    e.apply_layout([0,1],'names_inward')
    lines=layout(load_crawl(p),p.look).lines
    assert [(line.style,line.anchor,line.x) for line in lines]==[
        ('name','rs',p.look.center_x-p.look.gutter//2),
        ('name','ls',p.look.center_x+p.look.gutter//2),
        ('name','ms',p.look.center_x)]
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QStyleOptionViewItem
    for row,column,alignment in [(0,0,Qt.AlignRight),(0,2,Qt.AlignLeft),(1,1,Qt.AlignHCenter)]:
        option=QStyleOptionViewItem()
        e.table.itemDelegate().initStyleOption(option,e.table.model().index(row,column))
        assert option.displayAlignment & alignment
    e.close()


@pytest.mark.parametrize('selected_row',[0,1])
def test_thanks_editor_recovers_names_split_from_heading(monkeypatch,selected_row):
    from PySide6.QtWidgets import QDialog,QComboBox,QDialogButtonBox
    p=Project();e=SheetEditor(p)
    e.load([['','Special Thanks',''],['Avery Morgan','','Robin Chen'],['Alex Taylor','','Jamie Reed']])
    e.apply_layout([0,1,2],'thanks',title=True,columns=2,flow='sheet')
    e.apply_layout([1,2],'names_inward')
    assert p.overrides[0]['end']==0
    e.table.setCurrentCell(selected_row,0)
    def accept(dialog):
        assert dialog.findChild(QComboBox,'thanks_left_alignment').currentData()=='right'
        assert dialog.findChild(QComboBox,'thanks_right_alignment').currentData()=='left'
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
        return 1
    monkeypatch.setattr(QDialog,'exec',accept)
    e.thanks_dialog()
    assert len(p.overrides)==1 and p.overrides[0]['start']==0 and p.overrides[0]['end']==2
    lines=[line for line in layout(load_crawl(p),p.look).lines if line.row==2]
    assert [(line.anchor,line.x) for line in lines]==[('rs',p.look.center_x-p.look.gutter//2),('ls',p.look.center_x+p.look.gutter//2)]
    e.close()
