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


def test_old_mixed_recent_list_shows_only_saved_projects(recent_window,tmp_path,monkeypatch):
    win,settings=recent_window
    project=tmp_path/'Example Film.crawl.json';Project(rows=[],source_url=URL).save(str(project))
    source=tmp_path/'Revised credits.csv';source.write_text('')
    cache=tmp_path/('google-sheet-'+'a'*12+'.xlsx');cache.write_text('')
    settings.setValue('recent',[str(source),URL,str(project),str(cache)])
    win._rebuild_recent_menu()
    assert win.recent_menu.title()=='Recent projects'
    assert [a.text() for a in actions(win.recent_menu)]==['Example Film']
    file_menu=win.menuBar().actions()[0].menu()
    assert file_menu.actions()[0].text()=='Open Project…'
    assert not any(a.text()=='Recent source sheets' for a in file_menu.actions())
    opened=[];monkeypatch.setattr(win,'open_path',opened.append)
    actions(win.recent_menu)[0].trigger();assert opened==[str(project)]


def test_many_sources_do_not_evict_saved_project(recent_window,tmp_path):
    win,settings=recent_window
    project=tmp_path/'Example Film.crawl.json';Project(rows=[]).save(str(project))
    win._remember(str(project))
    for i in range(RECENT_LIMIT+4):
        path=tmp_path/f'source-{i}.csv';path.write_text('');win._remember(str(path))
    assert [a.data() for a in actions(win.recent_menu)]==[str(project)]
    assert len(actions(win.recent_menu))==1


def test_export_settings_is_top_navigation_not_left_tab(recent_window):
    win,_=recent_window
    visible=[win.tabs.tabText(i) for i in range(win.tabs.count()) if win.tabs.isTabVisible(i)]
    assert visible==['Credits','Logos']
    win.top_page_buttons[win.output_panel].click()
    assert win.tabs.currentWidget() is win.output_panel
    assert win.top_page_buttons[win.output_panel].isChecked()


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
