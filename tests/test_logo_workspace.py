import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PIL import Image
from crawl.project import Project, load_crawl, prepare
from crawl.layout import layout
from crawl.render import render_preview
from crawl.ui.widgets import pil_to_qimage


def project(tmp_path):
    paths = {}
    for label in 'ABCDE':
        path = tmp_path / f'{label}.png'
        Image.new('RGBA', (200, 100), (255, 30, 20, 255)).save(path)
        paths[label] = str(path)
    p = Project(rows=[['[Logo: A] | [Logo: B]', '', ''], ['[Logo: C]', '', ''], ['', '', ''],
                       ['[Logo: D]', '', ''], ['[Logo: E]', '', ''], ['', '', ''], ['© Company', '', '']],
                logos=paths, arrangements=[dict(start=0,end=4,columns=3,gap=120,alignment='center',label='Logo layout',logo_grid=True)])
    p.timing.mode='manual'
    return p


def test_logo_grid_flattens_rows_centers_tail_and_keeps_legal_below(tmp_path):
    p=project(tmp_path)
    L=layout(load_crawl(p),p.look)
    a,b,c,d,e=L.logos
    assert a.y==b.y==c.y and a.x<b.x<c.x
    assert d.y==e.y and d.y>a.y
    assert abs(((d.x+d.w/2)+(e.x+e.w/2))/2-p.look.center_x)<1
    assert L.lines[0].y>max(l.y+l.h for l in L.logos)
    p.arrangements[0]['columns']=1
    assert len({l.y for l in layout(load_crawl(p),p.look).logos})==5


def test_logo_color_grid_order_and_project_roundtrip(tmp_path):
    p=project(tmp_path)
    p.logo_settings['A']={'mode':'grayscale', 'dx':10,'black':5,'white':90}
    p.arrangements[0]['logo_order']=['E','A','B','C','D']
    path=tmp_path/'logos.crawl.json'
    p.save(str(path))
    q=Project.load(str(path))
    build=prepare(q)
    assert [item.label for item in build.layout.logos]==['E','A','B','C','D']
    assert build.layout.logos[1].mode=='grayscale'
    image=render_preview(build.layout,q.look,.25)
    assert image.mode=='RGB'
    qimage=pil_to_qimage(image)
    logo=build.layout.logos[0]
    pixel=qimage.pixelColor(round((logo.x+logo.w/2)*.25),round((logo.y+logo.h/2)*.25))
    assert pixel.red()>pixel.green()
    logo=build.layout.logos[1]
    pixel=qimage.pixelColor(round((logo.x+logo.w/2)*.25),round((logo.y+logo.h/2)*.25))
    assert pixel.red()==pixel.green()==pixel.blue()


def test_workspace_links_grid_undo_and_source_position(tmp_path):
    from PySide6.QtWidgets import QApplication
    from crawl.ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    p=project(tmp_path)
    p.arrangements=[]
    win=MainWindow(p)
    win._debounce.stop()
    ws=win.logo_workspace
    ws.refresh()
    ws.columns.setValue(3)
    ws.apply_grid()
    win._debounce.stop()
    assert p.arrangements[0]['logo_grid']
    ws.set_build(prepare(p))
    win.tabs.setCurrentWidget(ws)
    assert win.preview_stack.currentWidget() is win.preview
    ws.preview_mode.setCurrentIndex(1)
    assert win.preview_stack.currentWidget() is ws.canvas
    ws.preview_mode.setCurrentIndex(0)
    assert win.preview_stack.currentWidget() is win.preview
    assert len(ws.view.logos)==5
    ws.artwork.setCurrentRow(0)
    assert win.preview.view.selected=='A'
    assert ws.alignment_buttons['left'].isEnabled() is False
    assert ws.alignment_buttons['distribute_x'].isEnabled() is False
    ws.color_mode.setCurrentIndex(1)
    win._debounce.stop()
    assert p.logo_settings['A']['mode']=='grayscale'
    ws.show_row.emit(1)
    assert win.tabs.currentWidget() is win.sheet_editor
    win.sheet_editor.undo()
    win._debounce.stop()
    assert not p.logo_settings
    win._unsaved=False
    win.setWindowModified(False)
    win.close()


def test_batch_alignment_preserves_selection_cache_and_single_undo(tmp_path):
    from PySide6.QtWidgets import QApplication
    from crawl.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    p = project(tmp_path)
    p.logo_settings={'B':{'dx':-150}}
    win=MainWindow(p);win._debounce.stop()
    ws=win.logo_workspace
    ws.set_build(prepare(p))
    ws._canvas_selection({'A','B','C'})
    before=len(win.sheet_editor._undo)
    layers=dict(ws.view.layers)
    ws.align_selected('distribute_x')
    win._debounce.stop()
    assert len(win.sheet_editor._undo)==before+1
    ws.set_build(prepare(p))
    selected=[l for l in ws.view.logos if l.label in {'A','B','C'}]
    selected.sort(key=lambda l:l.x)
    gaps=[b.x-a.x-a.w for a,b in zip(selected, selected[1:])]
    assert abs(gaps[0]-gaps[1])<=1
    assert ws.view.selection=={'A','B','C'}
    assert ws.view.layers['A'] is layers['A']
    ws.move_selected({'A','B','C'},25,35)
    win._debounce.stop()
    old={l.label:(l.x,l.y) for l in selected}
    ws.set_build(prepare(p))
    # Local origin is stable, so group movement is the same delta for all.
    for item in ws.view.logos:
        if item.label in old:
            assert (item.x-old[item.label][0],item.y-old[item.label][1])==(25,35)
    win._unsaved=False;win.setWindowModified(False);win.close()


def test_pair_gap_and_center_preserve_size_height_and_undo(tmp_path,monkeypatch):
    from crawl.ui.main_window import MainWindow
    from PySide6.QtWidgets import QInputDialog
    p=project(tmp_path);p.logo_settings={'A':{'dx':-81,'dy':35,'scale':.8}}
    win=MainWindow(p);win._debounce.stop();ws=win.logo_workspace
    ws.set_build(prepare(p));ws._canvas_selection({'A','B'})
    assert ws.set_gap_button.isEnabled() and ws.center_pair_button.isEnabled()
    old=sorted([item for item in ws.view.logos if item.label in {'A','B'}],key=lambda item:item.x)
    midpoint=(old[0].x+old[1].x+old[1].w)/2
    before=len(win.sheet_editor._undo)
    monkeypatch.setattr(QInputDialog,'getInt',lambda *args:(140,True))
    ws.set_pair_gap();win._debounce.stop();ws.set_build(prepare(p))
    pair=ws._selected_pair()
    assert pair[1].x-pair[0].x-pair[0].w==140
    assert abs((pair[0].x+pair[1].x+pair[1].w)/2-midpoint)<=.5
    assert len(win.sheet_editor._undo)==before+1
    ws.center_pair();win._debounce.stop();ws.set_build(prepare(p))
    pair=ws._selected_pair()
    assert abs((pair[0].x+pair[1].x+pair[1].w)/2-p.look.center_x)<=.5
    assert pair[1].x-pair[0].x-pair[0].w==140
    for original,item in zip(old,pair):assert (original.y,original.w,original.h)==(item.y,item.w,item.h)
    win.sheet_editor.undo();win._debounce.stop()
    win.sheet_editor.undo();win._debounce.stop()
    assert p.logo_settings=={'A':{'dx':-81,'dy':35,'scale':.8}}
    win._unsaved=False;win.setWindowModified(False);win.close()


def test_vertical_distribution_and_alignment_rebuild_exactly(tmp_path):
    from PySide6.QtWidgets import QApplication
    from crawl.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    p=project(tmp_path);p.arrangements[0]['columns']=1
    p.logo_settings={'B':{'dy':50,'scale':.7}}
    win=MainWindow(p);win._debounce.stop();ws=win.logo_workspace
    ws.set_build(prepare(p));ws._canvas_selection({'A','B','C','D','E'})
    ws.align_selected('distribute_y');win._debounce.stop()
    ws.set_build(prepare(p))
    ordered=sorted(ws.view.logos,key=lambda l:l.y)
    gaps=[b.y-a.y-a.h for a,b in zip(ordered,ordered[1:])]
    assert max(gaps)-min(gaps)<=1
    ws.align_selected('left');win._debounce.stop()
    ws.set_build(prepare(p))
    assert len({l.x for l in ws.view.logos})==1
    win._unsaved=False;win.setWindowModified(False);win.close()


def test_canvas_modifier_selection_and_group_snap(tmp_path):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from crawl.ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    win=MainWindow(project(tmp_path));win._debounce.stop()
    ws=win.logo_workspace;ws.set_build(prepare(win.project))
    win.tabs.setCurrentWidget(ws);win.show();app.processEvents()
    view=ws.view
    a,b=view.logos[:2]
    QTest.mouseClick(view,Qt.LeftButton,Qt.NoModifier,view.logo_rect(a).center().toPoint())
    QTest.mouseClick(view,Qt.LeftButton,Qt.ShiftModifier,view.logo_rect(b).center().toPoint())
    assert view.selection=={'A','B'}
    # Snapping consults the group bounds and doesn't change its membership.
    original=list(view.logos)
    view._snap(20,20,1)
    assert view.logos==original and view.selection=={'A','B'}
    win._unsaved=False;win.setWindowModified(False);win.close()


def test_greyscale_inspector_syncs_render_save_undo_and_reset(tmp_path):
    from PySide6.QtWidgets import QApplication
    from crawl.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    p = project(tmp_path)
    win = MainWindow(p)
    win._debounce.stop()
    win.logo_workspace.refresh()
    win.logo_workspace.artwork.setCurrentRow(0)
    win.preview.view.select_logo('A')
    bar = win.preview.logo_bar
    bar.greyscale.setChecked(True)
    win._debounce.stop()
    assert p.logo_settings['A']['mode'] == 'grayscale'
    assert win.logo_workspace.inspector.greyscale.isChecked()
    assert win.logo_workspace.color_mode.currentData() == 'grayscale'
    path = tmp_path / 'grey.crawl.json'
    p.save(str(path))
    loaded = Project.load(str(path))
    build = prepare(loaded)
    image = render_preview(build.layout, loaded.look, .25)
    logo = next(item for item in build.layout.logos if item.label == 'A')
    rgb = image.getpixel((round((logo.x + logo.w / 2) * .25), round((logo.y + logo.h / 2) * .25)))
    assert rgb[0] == rgb[1] == rgb[2]
    win.sheet_editor.undo()
    win._debounce.stop()
    assert 'A' not in p.logo_settings
    assert not bar.greyscale.isChecked()
    bar.greyscale.setChecked(True)
    bar.reset.click()
    win._debounce.stop()
    assert 'A' not in p.logo_settings
    assert not bar.greyscale.isChecked()
    win._unsaved = False
    win.close()


def test_remove_placeholder_slot_keeps_other_logos_and_supports_undo(tmp_path):
    from crawl.ui.sheet_editor import SheetEditor
    p=Project();e=SheetEditor(p)
    e.load([['[Logo: Missing] | [Logo: Kept]','',''],['Next role','','Example Person']])
    p.logo_settings['Missing']={'scale':1.2};e.commit_undo()
    e.remove_logo_labels({'Missing'},0,0)
    assert e.rows()[0][0]=='[Logo: Kept]' and len(e.rows())==2
    assert [item.label for item in load_crawl(p).logos()]==['Kept']
    assert 'Missing' not in p.logo_settings
    e.undo();assert 'Missing' in e.rows()[0][0] and p.logo_settings['Missing']['scale']==1.2
    e.redo();assert e.rows()[0][0]=='[Logo: Kept]'
    e.close()


def test_remove_last_logo_clears_slot_and_empty_grid_without_deleting_file(tmp_path):
    from crawl.ui.sheet_editor import SheetEditor
    path=tmp_path/'Artwork.png';Image.new('RGBA',(100,50),'white').save(path)
    p=Project();e=SheetEditor(p);e.load([['[Logo: Artwork]','','']])
    p.logos['Artwork']=str(path)
    p.arrangements=[dict(start=0,end=0,columns=1,gap=120,logo_grid=True,logo_order=['Artwork'])]
    e.commit_undo();e.remove_logo_labels({'Artwork'},0,0)
    assert e.rows()==[['','','']] and not p.logos and not p.arrangements and path.exists()
    e.undo();assert p.logos['Artwork']==str(path) and p.arrangements[0]['logo_order']==['Artwork']
    e.close()


def test_remove_is_scoped_to_current_section_and_keeps_shared_assignment(tmp_path):
    from crawl.ui.sheet_editor import SheetEditor
    p=Project();e=SheetEditor(p)
    e.load([['[Logo: Shared]','',''],['','ANOTHER SECTION',''],['[Logo: Shared]','','']])
    p.logos['Shared']='existing.png';p.logo_settings['Shared']={'scale':1.1};e.commit_undo()
    e.remove_logo_labels({'Shared'},0,0)
    assert not e.rows()[0][0] and e.rows()[2][0]=='[Logo: Shared]'
    assert p.logos['Shared']=='existing.png' and p.logo_settings['Shared']['scale']==1.1
    e.close()


def test_remove_button_handles_selected_placeholder_and_refreshes_list():
    from crawl.ui.sheet_editor import SheetEditor
    from crawl.ui.logo_workspace import LogoWorkspace
    from PySide6.QtWidgets import QPushButton
    p=Project();e=SheetEditor(p);e.load([['[Logo: Placeholder]','','']])
    workspace=LogoWorkspace(p,e);workspace.refresh()
    assert not workspace.remove_button.isEnabled()
    workspace.artwork.setCurrentRow(0)
    assert workspace.remove_button.isEnabled() and workspace.replace_button.isEnabled()
    workspace.remove_button.click()
    assert e.rows()==[['','','']] and workspace.artwork.count()==0
    assert not workspace.view.logos and not workspace.remove_button.isEnabled()
    labels={button.text() for button in workspace.findChildren(QPushButton)}
    assert {'Replace selected logo…','Add logo…','Remove logo','Logo library…','Show locations'}<=labels
    e.undo();workspace.refresh();assert workspace.artwork.count()==1
    workspace.close();e.close()


def test_replace_placeholder_artwork_is_undoable(tmp_path,monkeypatch):
    from crawl.ui.sheet_editor import SheetEditor
    from crawl.ui.logo_workspace import LogoWorkspace
    from PySide6.QtWidgets import QFileDialog
    path=tmp_path/'Artwork.png';Image.new('RGBA',(100,50),'white').save(path)
    p=Project();e=SheetEditor(p);e.load([['[Logo: Placeholder]','','']])
    workspace=LogoWorkspace(p,e);workspace.refresh();workspace.artwork.setCurrentRow(0)
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *args,**kwargs:(str(path),''))
    workspace.replace_button.click();assert p.logos['Placeholder']==str(path)
    e.undo();assert 'Placeholder' not in p.logos and e.rows()[0][0]=='[Logo: Placeholder]'
    workspace.close();e.close()


def reorder_workspace():
    from crawl.ui.sheet_editor import SheetEditor
    from crawl.ui.logo_workspace import LogoWorkspace
    p=Project();e=SheetEditor(p)
    e.load([['[Logo: A] | [Logo: B] | [Logo: C]','','']])
    w=LogoWorkspace(p,e);w.refresh()
    return p,e,w


def logo_list(workspace):
    return [workspace.artwork.item(i).text() for i in range(workspace.artwork.count())]


def test_move_buttons_update_immediately_keep_selection_and_repeat():
    p,e,w=reorder_workspace()
    w.artwork.setCurrentRow(2)
    w.move_buttons[-1].click()
    assert logo_list(w)==['A','C','B']
    assert w.artwork.currentItem().text()=='C'
    w.move_buttons[-1].click()
    assert logo_list(w)==['C','A','B']
    assert w.artwork.currentItem().text()=='C' and not w.move_buttons[-1].isEnabled()
    w.refresh()
    assert w.artwork.currentItem().text()=='C'
    w.move_buttons[1].click();assert logo_list(w)==['A','C','B']
    assert p.arrangements[0]['logo_order']==['A','C','B']
    w.close();e.close()


def test_first_reorder_and_auto_grid_are_one_undo_step():
    p,e,w=reorder_workspace()
    w.artwork.setCurrentRow(1);w.reorder(-1)
    assert p.arrangements[0]['logo_grid'] and logo_list(w)==['B','A','C']
    e.undo();w.refresh()
    assert not p.arrangements and logo_list(w)==['A','B','C']
    e.redo();w.refresh();assert logo_list(w)==['B','A','C']
    w.close();e.close()


def test_drag_drop_order_uses_same_persistent_layout_and_survives_save(tmp_path):
    from PySide6.QtCore import QModelIndex
    from PySide6.QtWidgets import QAbstractItemView
    p,e,w=reorder_workspace()
    assert w.artwork.dragDropMode()==QAbstractItemView.InternalMove
    w.artwork.setCurrentRow(2)
    assert w.artwork.model().moveRows(QModelIndex(),2,1,QModelIndex(),0)
    w.artwork.order_dropped.emit()
    assert logo_list(w)==['C','A','B']
    assert [item.label for item in layout(load_crawl(p),p.look).logos]==['C','A','B']
    path=tmp_path/'ordered.crawl.json';p.save(str(path))
    assert Project.load(str(path)).arrangements[0]['logo_order']==['C','A','B']
    e.undo();w.refresh();assert logo_list(w)==['A','B','C']
    w.close();e.close()


def test_move_multiple_selected_logos_keeps_their_relative_order():
    p,e,w=reorder_workspace()
    w.artwork.item(1).setSelected(True);w.artwork.item(2).setSelected(True)
    w.reorder(-1)
    assert logo_list(w)==['B','C','A']
    assert {item.text() for item in w.artwork.selectedItems()}=={'B','C'}
    w.reorder(1);assert logo_list(w)==['A','B','C']
    w.close();e.close()


def test_move_without_selection_or_past_boundary_does_not_create_grid():
    p,e,w=reorder_workspace()
    w.reorder(1);assert not p.arrangements
    w.artwork.setCurrentRow(0);w.reorder(-1)
    assert not p.arrangements and logo_list(w)==['A','B','C']
    w.close();e.close()
