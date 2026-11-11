import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QToolButton
from crawl.project import Project
from crawl.ui.main_window import MainWindow


@pytest.fixture
def window(tmp_path,monkeypatch):
    settings=QSettings(str(tmp_path/'settings.ini'),QSettings.IniFormat)
    monkeypatch.setattr(MainWindow,'_settings',lambda self:settings)
    win=MainWindow(Project());win._debounce.stop()
    yield win
    win._render_worker=None;win._unsaved=False;win.close()


def descendants(menu):
    for action in menu.actions():
        yield action
        if action.menu():yield from descendants(action.menu())


def test_csv_export_has_one_home_and_review_contains_only_review_tools(window):
    actions=[]
    for action in window.menuBar().actions():
        actions.extend(descendants(action.menu()))
    assert sum(action.text()=='Export Credits as CSV…' for action in actions)==1
    export=next(action.menu() for action in window.menuBar().actions() if action.text().replace('&','')=='Export')
    assert any(action.text()=='Export Credits as CSV…' for action in export.actions())
    rows=next(button.menu() for button in window.sheet_editor._toolbar.findChildren(QToolButton) if button.text()=='Rows')
    assert any(action.text()=='Review' for action in rows.actions())
    assert not any('CSV' in action.text() for action in descendants(rows))


def test_export_action_follows_format_and_requires_a_ready_build(window):
    assert not window.export_action.isEnabled() and not window.cancel_export_action.isEnabled()
    window.project.codec='png';window._sync_export_label()
    assert window.export_action.text()=='Export PNG sequence'
    assert window.export_btn.text()=='Export PNG sequence'
    window.build=object();window._sync_ready()
    assert window.export_action.isEnabled()
    window.project.codec='h264';window._sync_export_label()
    assert 'PNG' not in window.export_action.text()


def test_cancel_action_is_only_enabled_during_active_non_canceling_export(window):
    class Worker:
        running=True
        canceled=False
        def isRunning(self):return self.running
        def cancel(self):self.canceled=True
    task=Worker();window._render_worker=task;window.build=object()
    window._set_exporting(True)
    assert window.cancel_export_action.isEnabled() and not window.export_action.isEnabled()
    window.cancel_export_action.trigger()
    assert task.canceled and not window.cancel_export_action.isEnabled()
    window._sync_export_label()
    assert not window.cancel_export_action.isEnabled()
    task.running=False;window._set_exporting(False)
    assert not window.cancel_export_action.isEnabled() and window.export_action.isEnabled()
