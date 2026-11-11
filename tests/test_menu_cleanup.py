from PySide6.QtWidgets import QToolButton
from crawl.project import Project
from crawl.ui.sheet_editor import SheetEditor


def menu_structure(menu):
    return [(action.text(),menu_structure(action.menu()) if action.menu() else None)
            for action in menu.actions() if not action.isSeparator()]


def editor():
    p=Project();e=SheetEditor(p);e.load([['Role','','Example Person'],['','',''],['Other','','Another Person']])
    return p,e


def test_context_layout_matches_toolbar_and_duplicates_are_removed():
    p,e=editor()
    toolbar=next(button.menu() for button in e._toolbar.findChildren(QToolButton) if button.text()=='Layout')
    context=e._build_context_menu()
    layout=next(action.menu() for action in context.actions() if action.text()=='Layout')
    assert menu_structure(toolbar)==menu_structure(layout)
    roots=[action.text() for action in context.actions()]
    assert 'Rows' in roots and 'Music…' not in roots and 'Add logos…' not in roots
    assert not any(label.startswith('Insert ') for label in roots)
    assert 'List in columns' not in [action.text() for action in layout.actions()]
    advanced=next(action.menu() for action in layout.actions() if action.text()=='More layouts')
    assert [action.text() for action in advanced.actions()]==['List in columns']
    e.close()


def test_layout_menu_action_dispatches_actual_kind(monkeypatch):
    p,e=editor();e.table.setCurrentCell(0,2)
    e.project.rows=e.rows()
    menu=next(button.menu() for button in e._toolbar.findChildren(QToolButton) if button.text()=='Layout')
    next(action for action in menu.actions() if action.data()=='roles').trigger()
    assert p.overrides[0]['kind']=='roles'
    e.close()


def test_music_grid_edit_button_and_context_use_music_editor(monkeypatch):
    p,e=editor();p.arrangements=[dict(start=0,end=2,columns=1,gap=120,music=True)]
    e.table.setCurrentCell(0,0);e.refresh_arrangements()
    calls=[];monkeypatch.setattr(e,'music_dialog',lambda:calls.append('music'))
    monkeypatch.setattr(e,'arrange_dialog',lambda **kwargs:calls.append('generic'))
    assert e.arrange_button.text()=='Edit music layout…'
    e.arrange_button.click()
    menu=e._build_context_menu()
    next(action for action in menu.actions() if action.text()=='Edit music layout…').trigger()
    assert calls==['music','music']
    e.close()


def test_logo_grid_edit_button_and_context_request_logo_editor():
    p,e=editor();p.arrangements=[dict(start=0,end=2,columns=1,gap=120,logo_grid=True)]
    e.table.setCurrentCell(2,0);e.refresh_arrangements()
    rows=[];e.logo_layout_requested.connect(rows.append)
    assert e.arrange_button.text()=='Edit logo grid…'
    e.arrange_button.click()
    menu=e._build_context_menu()
    next(action for action in menu.actions() if action.text()=='Edit logo grid…').trigger()
    assert rows==[3,3]
    e.close()


def test_generic_arrangement_still_uses_side_by_side_editor(monkeypatch):
    p,e=editor();p.arrangements=[dict(start=0,end=2,columns=2,gap=120)]
    e.table.setCurrentCell(0,0);e.refresh_arrangements()
    calls=[];monkeypatch.setattr(e,'arrange_dialog',lambda edit=False:calls.append(edit))
    e.arrange_button.click();assert calls==[True]
    e.close()


def test_main_window_opens_logo_editor_at_matching_section(tmp_path,monkeypatch):
    from PySide6.QtCore import QSettings
    from crawl.ui.main_window import MainWindow
    settings=QSettings(str(tmp_path/'settings.ini'),QSettings.IniFormat)
    monkeypatch.setattr(MainWindow,'_settings',lambda self:settings)
    rows=[['[Logo: First]','',''],['','SECOND SECTION',''],['[Logo: Second]','','']]
    p=Project(rows=rows,arrangements=[dict(start=2,end=2,columns=1,gap=120,logo_grid=True)])
    win=MainWindow(p);win._debounce.stop()
    win.sheet_editor.table.setCurrentCell(2,0);win.sheet_editor.refresh_arrangements()
    win.sheet_editor.arrange_button.click()
    assert win.tabs.currentWidget() is win.logo_workspace
    assert win.logo_workspace.current()['start']==2
    win._unsaved=False;win.close()


def test_logo_block_without_grid_opens_and_selects_its_artwork(tmp_path,monkeypatch):
    from PySide6.QtCore import QSettings
    from crawl.ui.main_window import MainWindow
    settings=QSettings(str(tmp_path/'settings.ini'),QSettings.IniFormat)
    monkeypatch.setattr(MainWindow,'_settings',lambda self:settings)
    rows=[['[Logo: First]','',''],['','',''],['[Logo: Second]','','']]
    win=MainWindow(Project(rows=rows));win._debounce.stop()
    e=win.sheet_editor;e.table.setCurrentCell(2,0)
    assert e.arrange_button.text()=='Edit logo block…'
    e.arrange_button.click()
    assert win.tabs.currentWidget() is win.logo_workspace
    assert [item.text() for item in win.logo_workspace.artwork.selectedItems()]==['Second']
    assert win.logo_workspace.inspector.label=='Second'
    win.tabs.setCurrentWidget(e)
    next(action for action in e._build_context_menu().actions() if action.text()=='Edit logo block…').trigger()
    assert win.logo_workspace.inspector.label=='Second'
    win._unsaved=False;win.close()
