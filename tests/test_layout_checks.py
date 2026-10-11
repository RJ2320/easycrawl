import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PIL import Image
from crawl.layout import Layout, Line, LogoItem
from crawl.look import Look
from crawl.layout_checks import regions, check_layout
from crawl.project import Project, prepare


def test_bounds_overlap_and_no_vertical_safe_warning(tmp_path):
    look = Look()
    path = tmp_path/'tiny.png'
    Image.new('RGB',(10,10),'red').save(path)
    layout = Layout(look.width,1000,
                    lines=[Line('A','name',-10,50,'ls',1,'name'),
                           Line('B','name',look.width/2,200,'ls',2,'name')],
                    logos=[LogoItem('logo',str(path),int(look.width/2),150,100,100,row=3)])
    findings = check_layout(layout,look)
    assert any(f.check=='layout-frame' and f.row==1 for f in findings)
    assert {f.row for f in findings if f.check=='layout-overlap'}=={2,3}
    assert any(f.check=='layout-resolution' and f.row==3 for f in findings)
    assert not any(f.check=='layout-safe' and f.row==2 for f in findings)


def test_layout_dismissal_survives_row_insert_and_returns_after_change():
    p=Project(rows=[['Very long role '*50,'','Alice']])
    p.timing.mode='manual'
    first=prepare(p)
    finding=next(f for f in first.findings if f.check=='layout-frame')
    p.dismissed.append(finding.key)
    p.rows.insert(0,['','',''])
    assert not any(f.check=='layout-frame' for f in prepare(p).findings)
    p.rows[1][0]+=' changed'
    assert any(f.check=='layout-frame' for f in prepare(p).findings)


def test_preview_click_selects_source_without_seeking():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QPointF,Qt,QEvent
    from PySide6.QtGui import QMouseEvent
    from crawl.ui.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    p=Project(rows=[['Director','','Alice'],['','',''],['Producer','','Bob']])
    p.timing.mode='manual'
    win=MainWindow(p)
    win._debounce.stop()
    build=prepare(p)
    win._built(build,Image.new('RGB',(384,100),'black'))
    view=win.preview.view
    region=next(r for r in view.hit_regions if r.row==3 and r.target=='name')
    win.preview.slider.setValue(win._row_frame(build,(region.box[1]+region.box[3])/2))
    before=win.preview.slider.value()
    ox,oy,w,h,k,top=view._geom()
    a,b,c,d=region.box
    point=QPointF(ox+(a+c)/2*k,oy+(top+(b+d)/2)*k)
    assert view.credit_at(point)==region
    win.sheet_editor.follow_selection.setChecked(True)
    view.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress,point,point,Qt.LeftButton,Qt.LeftButton,Qt.NoModifier))
    assert win.sheet_editor.table.currentRow()==2
    assert win.sheet_editor.table.currentColumn()==2
    assert win.preview.slider.value()==before
    view.set_busy(True)
    assert view.credit_at(point) is None
    win.close()


def test_arranged_wrapped_lines_keep_source_cell():
    p=Project(rows=[['','"Song One"',''],['Written by','Alice '*20,''],['','',''],
                    ['','"Song Two"',''],['Written by','Bob','']],
              arrangements=[dict(start=0,end=4,columns=2,gap=120,alignment='center')])
    p.timing.mode='manual'
    build=prepare(p)
    names=[r for r in regions(build.layout,p.look) if r.row==2 and r.target=='name']
    assert len(names)>1
    assert all(r.contains((r.box[0]+r.box[2])/2,(r.box[1]+r.box[3])/2) for r in names)
