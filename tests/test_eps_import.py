import struct
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from crawl import logo_import
from crawl.logo_library import LogoLibrary
from crawl.project import Project, load_crawl
from crawl.ui.sheet_editor import SheetEditor


def eps(bounds='0 0 200 100', extra=b''):
    return (b'%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: '+bounds.encode()+b'\n'+extra+
            b'%%EndComments\n1 1 1 setrgbcolor\n20 20 moveto 180 20 lineto 180 80 lineto 20 80 lineto closepath fill\nshowpage\n%%EOF\n')


requires_gs=pytest.mark.skipif(not logo_import.find_ghostscript(),reason='Ghostscript is optional')
GS=logo_import.find_ghostscript()


@requires_gs
def test_eps_becomes_transparent_png_and_cache_works_without_helper(tmp_path,monkeypatch):
    source=tmp_path/'Example Mark.eps';data=eps();source.write_bytes(data)
    prepared=Path(logo_import.prepare_logo(source,root=tmp_path/'cache'))
    with Image.open(prepared) as image:
        assert image.size==(4096,2048) and image.mode=='RGBA'
        assert image.getpixel((0,0))[3]==0 and image.getchannel('A').getbbox()
    assert logo_import.original_eps(prepared).read_bytes()==data
    assert source.read_bytes()==data
    monkeypatch.setattr(logo_import,'find_ghostscript',lambda:None)
    assert logo_import.prepare_logo(source,root=tmp_path/'cache')==str(prepared)


@requires_gs
def test_library_retains_original_and_project_survives_moved_source(tmp_path,monkeypatch):
    from crawl import logo_library
    monkeypatch.setattr(logo_library,'default_root',lambda:tmp_path/'cache')
    monkeypatch.setattr(logo_import,'find_ghostscript',lambda:GS)
    source=tmp_path/'Studio.eps';source.write_bytes(eps())
    p=Project();editor=SheetEditor(p);editor.load([['','CREDITS','']]);editor.table.setCurrentCell(0,0)
    editor.add_logo_paths([str(source)])
    assert list(p.logos)==['Studio'] and Path(p.logos['Studio']).suffix=='.png'
    library=LogoLibrary(tmp_path/'library')
    entry=library.import_file(next(iter(p.logos.values())),name='Studio')
    assert library.asset_path(entry['original']).read_bytes()==source.read_bytes()
    source.unlink()
    file=tmp_path/'show.crawl.json';p.save(str(file))
    restored=Project.load(str(file))
    assert Path(next(iter(restored.logos.values()))).exists()
    assert next(load_crawl(restored).logos()).path.endswith('.png')
    editor.undo();assert not p.logos
    editor.redo();assert p.logos
    editor.close()


@requires_gs
def test_dos_preview_and_fractional_and_atend_bounds(tmp_path):
    program=eps(extra=b'%%HiResBoundingBox: 0.25 0.25 199.75 99.75\n')
    header=b'\xc5\xd0\xd3\xc6'+struct.pack('<IIIIIIH',30,len(program),0,0,0,0,0xffff)
    source=tmp_path/'preview.EPS';source.write_bytes(header+program)
    prepared=logo_import.prepare_logo(source,root=tmp_path/'cache')
    with Image.open(prepared) as image:assert max(image.size)<=4096 and image.getchannel('A').getbbox()
    source=tmp_path/'at end.eps';source.write_bytes(eps('(atend)')+b'%%Trailer\n%%BoundingBox: 0 0 200 100\n')
    with Image.open(logo_import.prepare_logo(source,root=tmp_path/'cache')) as image:assert image.size==(4096,2048)


def test_missing_helper_and_failed_conversion_do_not_change_editor(tmp_path,monkeypatch):
    source=tmp_path/'Studio.eps';source.write_bytes(eps())
    from crawl import logo_library
    monkeypatch.setattr(logo_library,'default_root',lambda:tmp_path/'cache')
    monkeypatch.setattr(logo_import,'find_ghostscript',lambda:None)
    p=Project();editor=SheetEditor(p);editor.load([['Role','','Avery Morgan']])
    before=editor._state()
    with pytest.raises(logo_import.MissingGhostscript):editor.add_logo_paths([str(source)])
    assert editor._state()==before
    monkeypatch.setattr(logo_import,'find_ghostscript',lambda:'ghostscript')
    def timeout(*args,**kwargs):raise subprocess.TimeoutExpired(args[0],45)
    monkeypatch.setattr(logo_import.subprocess,'run',timeout)
    with pytest.raises(ValueError,match='one cell'):editor.apply_logo_cells([(0,0),(0,2)],path=str(source))
    assert editor._state()==before
    # Single-cell assignment reaches conversion only after validation succeeds.
    editor.load([['Studio','','']]);before=editor._state()
    with pytest.raises(ValueError,match='too long'):editor.apply_logo_cells([(0,0)],path=str(source))
    assert editor._state()==before
    editor.close()


@pytest.mark.parametrize('data',[b'not eps',b'%!PS-Adobe-3.0 EPSF-3.0\n',eps('0 0 0 100'),b'\xc5\xd0\xd3\xc6'])
def test_invalid_eps_has_a_useful_error(tmp_path,data):
    source=tmp_path/'bad.eps';source.write_bytes(data)
    with pytest.raises(ValueError):logo_import.prepare_logo(source,root=tmp_path/'cache')
    assert not list((tmp_path/'cache').glob('**/*.png'))


@requires_gs
def test_library_import_dialog_converts_in_background(tmp_path,monkeypatch):
    from crawl import logo_library
    from crawl.ui.logo_library_dialog import LogoLibraryDialog
    monkeypatch.setattr(logo_library,'default_root',lambda:tmp_path/'cache')
    monkeypatch.setattr(logo_import,'find_ghostscript',lambda:GS)
    source=tmp_path/'Personal Mark.eps';source.write_bytes(eps())
    library=LogoLibrary(tmp_path/'library');dialog=LogoLibraryDialog(library=library)
    dialog.import_paths([str(source)])
    entry=library.entries(scope='personal')[0]
    assert entry['name']=='Personal Mark' and entry['original']['format']=='EPS'
    assert dialog.results.count()==1 and dialog.use.isEnabled()
    dialog.close()
