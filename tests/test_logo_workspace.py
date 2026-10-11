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
    assert win.preview_stack.currentWidget() is ws.canvas
    assert len(ws.view.logos)==5
    ws.artwork.setCurrentRow(0)
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
