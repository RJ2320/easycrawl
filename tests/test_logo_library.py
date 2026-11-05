import io
import zipfile
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import Qt

from crawl.logo_library import LogoLibrary, CATALOG
from crawl.project import Project, load_crawl
from crawl.ui.logo_library_dialog import LogoLibraryDialog
from crawl.ui.sheet_editor import SheetEditor


def artwork(color='white'):
    data=io.BytesIO()
    Image.new('RGBA',(200,100),color).save(data,format='PNG')
    return data.getvalue()


def response(data):
    return lambda *args,**kwargs:io.BytesIO(data)


def test_personal_import_is_copied_deduplicated_searchable_and_private(tmp_path):
    source=tmp_path/'Studio.png';source.write_bytes(artwork())
    library=LogoLibrary(tmp_path/'library')
    entry=library.import_file(source,name='My Studio',tags='production film')
    path=library.asset_path(entry['assets'][0])
    assert path.exists() and path!=source
    assert library.import_file(source)['id']==entry['id']
    source.unlink()
    restored=LogoLibrary(library.root)
    assert restored.entries('studio film','personal')[0]['name']=='My Studio'
    assert restored.entries('studio film','official')==[]
    assert path.exists() and entry['source']==''


def test_removing_personal_entry_keeps_artwork_used_by_projects(tmp_path):
    source=tmp_path/'Studio.png';source.write_bytes(artwork())
    library=LogoLibrary(tmp_path/'library');entry=library.import_file(source)
    asset=library.asset_path(entry['assets'][0])
    library.remove_personal(entry['id'])
    assert library.entries(scope='personal')==[] and asset.exists()


def test_official_refresh_keeps_existing_artwork_immutable(tmp_path):
    library=LogoLibrary(tmp_path)
    first=library.fetch('tcs',opener=response(artwork('white')))[0]
    second=library.fetch('tcs',opener=response(artwork('red')))[0]
    assert first['path']!=second['path']
    assert library.asset_path(first).exists()
    assert library.entries('TCS','official')[0]['assets']==[second]
    assert LogoLibrary(tmp_path).asset_path(first).exists()


def test_zip_download_has_variants_and_does_not_extract_archive_paths(tmp_path):
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w') as archive:
        archive.writestr('../../outside.png',artwork('black'))
        archive.writestr('Logo White.png',artwork())
        archive.writestr('__MACOSX/._logo.png',b'not artwork')
        archive.writestr('readme.txt','Use official brand guidelines.')
    library=LogoLibrary(tmp_path/'library')
    assets=library.fetch('panavision',opener=response(data.getvalue()))
    assert len(assets)==2 and 'White' in assets[0]['name']
    assert not (tmp_path/'outside.png').exists()
    assert all(library.asset_path(asset).is_relative_to(library.root) for asset in assets)


def test_failed_download_keeps_cached_version(tmp_path):
    library=LogoLibrary(tmp_path)
    first=library.fetch('tcs',opener=response(artwork()))
    with pytest.raises(OSError):
        library.fetch('tcs',opener=response(b'<html>not a logo</html>'))
    assert LogoLibrary(tmp_path).entries('TCS','official')[0]['assets']==first


def test_library_refuses_asset_paths_outside_its_root(tmp_path):
    with pytest.raises(ValueError,match='path'):
        LogoLibrary(tmp_path/'library').asset_path({'path':'../../outside.png'})


def test_library_dialog_inserts_offline_personal_logo_and_supports_undo(tmp_path):
    source=tmp_path/'Studio.png';source.write_bytes(artwork())
    library=LogoLibrary(tmp_path/'library');library.import_file(source)
    dialog=LogoLibraryDialog(library=library)
    dialog.scope.setCurrentIndex(dialog.scope.findData('personal'))
    assert dialog.results.count()==1 and dialog.use.isEnabled()
    dialog.use_logo()
    p=Project();editor=SheetEditor(p);editor.load([['','THANKS','']])
    editor.add_logo_paths(dialog.selected_paths)
    assert len(p.logos)==1 and len(list(load_crawl(p).logos()))==1
    editor.undo();assert not p.logos
    editor.redo();assert len(p.logos)==1
    path=tmp_path/'project.crawl.json';p.save(str(path))
    assert Path(next(iter(Project.load(str(path)).logos.values()))).exists()
    editor.close();dialog.close()


def test_missing_cached_artwork_cannot_be_inserted(tmp_path):
    source=tmp_path/'Studio.png';source.write_bytes(artwork())
    library=LogoLibrary(tmp_path/'library');entry=library.import_file(source)
    library.asset_path(entry['assets'][0]).unlink()
    dialog=LogoLibraryDialog(library=library)
    dialog.scope.setCurrentIndex(dialog.scope.findData('personal'))
    assert not dialog.use.isEnabled()
    dialog.close()


def test_catalog_is_official_and_does_not_bundle_third_party_artwork():
    assert len(CATALOG)>=8 and len({entry['id'] for entry in CATALOG})==len(CATALOG)
    assert all(entry['source'].startswith('https://') and entry['usage'] for entry in CATALOG)


def test_download_worker_refreshes_library_without_changing_project_logos(tmp_path,monkeypatch):
    from PySide6.QtCore import QEventLoop,QTimer
    real_fetch=LogoLibrary.fetch
    monkeypatch.setattr(LogoLibrary,'fetch',lambda self,entry_id:real_fetch(self,entry_id,opener=response(artwork())))
    assigned={'Existing logo':'existing.png'}
    dialog=LogoLibraryDialog(assigned,library=LogoLibrary(tmp_path))
    dialog.search.setText('TCS')
    assert not dialog.use.isEnabled()
    dialog.download_logo()
    loop=QEventLoop()
    dialog.worker.finished.connect(loop.quit)
    QTimer.singleShot(10000,loop.quit)
    loop.exec()
    assert not dialog.worker.isRunning()
    assert dialog.use.isEnabled() and dialog.variant.count()==1
    assert assigned=={'Existing logo':'existing.png'}
    dialog.close()
