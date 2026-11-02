import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from crawl.layout import LogoItem
from crawl.ui.logo_layers import prepare
from crawl.ui.worker import RebuildWorker
from crawl.project import Project, load_crawl


@pytest.mark.parametrize('path',[None,'','missing-example-artwork.png'])
def test_missing_artwork_uses_placeholder(path):
    image=prepare(LogoItem(label='Example',path=path,x=0,y=0,w=200,h=100),0.25)
    assert not image.isNull()
    assert (image.width(),image.height())==(50,25)


def test_imported_logo_slots_do_not_abort_preview_worker():
    project=Project(rows=[['','CREDITS',''],['Director','','Example Name'],['','',''],['[Logo: Example]','','']])
    project.timing.mode='manual'
    worker=RebuildWorker(project,load_crawl(project))
    completed=[];errors=[]
    worker.done.connect(lambda build,image: completed.append((build,image)))
    worker.failed.connect(errors.append)
    worker.run()
    assert errors==[]
    assert len(completed)==1
    build,image=completed[0]
    assert image.width>0
    assert build.layout.logos[0].path is None
    assert not build.logo_layers['Example'][1].isNull()


def test_import_preview_can_show_the_full_worksheet(tmp_path):
    from openpyxl import Workbook
    from crawl.ui.import_dialog import ImportDialog
    workbook=Workbook()
    sheet=workbook.active;sheet.title='Crawl'
    sheet.append(['','','CREDITS',''])
    for index in range(120):
        sheet.append(['','Role '+str(index),'','Example Name'])
    path=tmp_path/'example.xlsx';workbook.save(path);workbook.close()
    dialog=ImportDialog(str(path))
    assert dialog.table.rowCount()==80
    assert 'full selected worksheet' in dialog.summary.text()
    dialog.preview_toggle.click()
    assert dialog.table.rowCount()==121
    assert dialog.table.item(120,1).text()=='Role 119'
    dialog.preview_toggle.click()
    assert dialog.table.rowCount()==80
    dialog.close()
