import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QInputDialog,QFileDialog
from crawl.project import Project
from crawl.ui.main_window import MainWindow,RECENT_LIMIT

URL='https://docs.google.com/spreadsheets/d/'+'a'*30+'/edit#gid=0'


@pytest.fixture
def recent_window(tmp_path,monkeypatch):
    settings=QSettings(str(tmp_path/'settings.ini'),QSettings.IniFormat)
    monkeypatch.setattr(MainWindow,'_settings',lambda self:settings)
    win=MainWindow(Project());win._debounce.stop()
    yield win,settings
    win._unsaved=False;win.close()


def actions(menu):
    return [a for a in menu.actions() if a.data()]


def test_old_mixed_recent_list_becomes_separate_readable_menus(recent_window,tmp_path,monkeypatch):
    win,settings=recent_window
    project=tmp_path/'Example Film.crawl.json';Project(rows=[],source_url=URL).save(str(project))
    source=tmp_path/'Revised credits.csv';source.write_text('')
    cache=tmp_path/('google-sheet-'+'a'*12+'.xlsx');cache.write_text('')
    settings.setValue('recent',[str(source),URL,str(project),str(cache)])
    win._rebuild_recent_menu()
    assert win.recent_menu.title()=='Recent projects'
    assert [a.text() for a in actions(win.recent_menu)]==['Example Film']
    assert [a.text() for a in actions(win.recent_sheets_menu)]==['Revised credits — CSV sheet','Example Film — Google Sheet']
    opened=[];monkeypatch.setattr(win,'open_path',opened.append)
    actions(win.recent_menu)[0].trigger();assert opened==[str(project)]


def test_many_sources_do_not_evict_saved_project(recent_window,tmp_path):
    win,settings=recent_window
    project=tmp_path/'Example Film.crawl.json';Project(rows=[]).save(str(project))
    win._remember(str(project))
    for i in range(RECENT_LIMIT+4):
        path=tmp_path/f'source-{i}.csv';path.write_text('');win._remember(str(path))
    assert [a.data() for a in actions(win.recent_menu)]==[str(project)]
    assert len(actions(win.recent_sheets_menu))==RECENT_LIMIT


def test_current_google_sheet_has_friendly_name_and_can_be_renamed(recent_window,tmp_path,monkeypatch):
    win,settings=recent_window
    win.project.source_url=URL;win.project_path=str(tmp_path/'Example Film.crawl.json')
    win._remember(URL)
    assert actions(win.recent_sheets_menu)[0].text()=='Example Film — Google Sheet'
    monkeypatch.setattr(QInputDialog,'getText',lambda *args,**kwargs:('Master credits',True))
    win._rename_current_recent_sheet()
    assert actions(win.recent_sheets_menu)[0].text()=='Master credits — Google Sheet'
    win._rebuild_recent_menu()
    assert actions(win.recent_sheets_menu)[0].text()=='Master credits — Google Sheet'


def test_same_project_names_show_folders_and_missing_files_are_omitted(recent_window,tmp_path):
    win,settings=recent_window
    files=[]
    for directory in ['first','second']:
        folder=tmp_path/directory;folder.mkdir()
        path=folder/'Film.crawl.json';Project(rows=[]).save(str(path));files.append(str(path))
    settings.setValue('recent',files+[str(tmp_path/'missing.crawl.json')])
    win._rebuild_recent_menu()
    assert len(actions(win.recent_menu))==2
    assert all(' — ' in a.text() for a in actions(win.recent_menu))
    assert len({a.text() for a in actions(win.recent_menu)})==2


def test_newly_saved_project_appears_immediately(recent_window,tmp_path,monkeypatch):
    win,settings=recent_window
    path=tmp_path/'New Film.crawl.json'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args,**kwargs:(str(path),''))
    win.save_project()
    assert path.exists()
    assert actions(win.recent_menu)[0].text()=='New Film'
