import os
from datetime import datetime
from pathlib import Path
import pytest
from PIL import Image
from crawl import relink
from crawl.project import Project


def test_search_and_apply_preserve_settings_and_ambiguous_matches(tmp_path):
    root = tmp_path / 'art'
    root.mkdir()
    nested = root / 'nested'
    nested.mkdir()
    for path in (root / 'studio.png', nested / 'studio.png', nested / 'partner.PNG'):
        path.write_bytes(b'art')
    sheet = nested / 'credits.xlsx'
    sheet.write_bytes(b'sheet')
    p = Project(source='/old/credits.xlsx', logos={'Studio': '/old/studio.png', 'source': '/old/partner.png'},
                logo_settings={'Studio': {'dx': 50, 'invert': True, 'black': 20}})
    items = relink.missing(p)
    matches = relink.search(str(root), items)
    assert len(matches['logo:Studio']) == 2
    assert len(matches['logo:source']) == 1
    relink.apply(p, items, {'logo:source': matches['logo:source'][0], 'source': str(sheet)})
    assert p.logos['Studio'] == '/old/studio.png'
    assert p.logos['source'] == str(nested / 'partner.PNG')
    assert p.source == str(sheet)
    assert p.logo_settings['Studio'] == {'dx': 50, 'invert': True, 'black': 20}
    assert len(relink.missing(p)) == 1


def test_timestamp_output_names_group_movie_and_report(tmp_path, monkeypatch):
    from crawl import project
    from types import SimpleNamespace
    class Clock:
        @staticmethod
        def now():
            return datetime(2026, 10, 7, 14, 30, 5).astimezone()
    monkeypatch.setattr(project, 'datetime', Clock)
    def movie(*args, **kwargs):
        path = Path(args[4] + '.mov')
        path.touch()
        return path
    monkeypatch.setattr(project.export, 'export_movie', movie)
    monkeypatch.setattr(project, 'write_report', lambda p, b, path, panels, movie: path.touch())
    p = Project(output_dir=str(tmp_path), basename='show', timestamp_output=True, write_report=True)
    build = SimpleNamespace(layout=None, solution=None)
    paths = project.render(p, build)
    assert [p.name for p in paths] == ['show_2026-10-07_14-30-05.mov', 'show_2026-10-07_14-30-05_report.txt']
    assert p.basename == 'show'
    p.save(str(tmp_path / 'show.crawl.json'))
    assert Project.load(str(tmp_path / 'show.crawl.json')).timestamp_output
    p.timestamp_output = False
    assert project.render(p, build)[0].name == 'show.mov'


@pytest.fixture
def app():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_relink_review_requires_choice_for_duplicates(app, tmp_path):
    from crawl.ui.relink_dialog import RelinkDialog
    p = Project(logos={'A': '/old/a.png', 'B': '/old/b.png'})
    dialog = RelinkDialog(p)
    a, b = str(tmp_path / 'a.png'), str(tmp_path / 'b.png')
    dialog.show_matches({'logo:A': [a], 'logo:B': [b, '/another/b.png']})
    assert dialog.choices[0].currentData() == a
    assert dialog.choices[1].currentData() == ''
    dialog.apply()
    assert dialog.replacements == {'logo:A': a}
    assert p.logos['A'] == '/old/a.png'


def test_logo_worker_prepares_layers_and_ui_reuses_them(app, tmp_path, monkeypatch):
    from crawl.ui.worker import RebuildWorker
    from crawl.ui.sheet_editor import SheetEditor
    from crawl.ui.logo_workspace import LogoWorkspace
    from crawl.project import load_crawl
    path = tmp_path / 'a.png'
    Image.new('RGBA', (200, 100), 'white').save(path)
    p = Project(rows=[['[Logo: A]', '', '']], logos={'A': str(path)})
    p.timing.mode = 'manual'
    worker = RebuildWorker(p, load_crawl(p))
    results = []
    worker.done.connect(lambda build, img: results.append(build))
    worker.run()
    assert results and 'A' in results[0].logo_layers
    editor = SheetEditor(p)
    editor.load(p.rows)
    workspace = LogoWorkspace(p, editor)
    monkeypatch.setattr(Image, 'open', lambda *a, **k: pytest.fail('UI must not decode artwork'))
    workspace.set_build(results[0])
    assert 'A' in workspace.view.layers
    assert not workspace.view.busy


def test_versions_use_existing_outputs_and_work_with_dates(tmp_path):
    from crawl.project import export_basename
    p = Project(basename='show', version_output=True, timestamp_output=True)
    now = datetime(2026, 10, 7, 14, 30, 5)
    assert export_basename(p, tmp_path, now) == 'show_v001_2026-10-07_14-30-05'
    (tmp_path / 'show_v001_2026-10-06_12-00-00.mov').touch()
    (tmp_path / 'show_v003_report.txt').touch()
    (tmp_path / 'other_v099.mov').touch()
    assert export_basename(p, tmp_path, now) == 'show_v004_2026-10-07_14-30-05'
    p.timestamp_output = False
    assert export_basename(p, tmp_path, now) == 'show_v004'
    assert p.basename == 'show'


def test_output_naming_controls_persist_without_rebuilding(app):
    from crawl.ui.main_window import OutputPanel
    p = Project()
    panel = OutputPanel(p)
    panel.timestamp_output.setChecked(True)
    panel.version_output.setChecked(True)
    assert p.timestamp_output and p.version_output
    restored = Project.from_dict(p.to_dict())
    assert restored.timestamp_output and restored.version_output


def test_apply_relinks_updates_window_preview_and_saved_project(app, tmp_path, monkeypatch):
    from PySide6.QtCore import QTimer
    from crawl.ui.main_window import MainWindow
    from crawl.ui.relink_dialog import RelinkDialog
    from crawl.project import prepare
    image = tmp_path / 'studio.png'
    Image.new('RGBA', (200, 100), 'white').save(image)
    p = Project(rows=[['[Logo: Studio]', '', '']], logos={'Studio': '/missing/studio.png'},
                logo_settings={'Studio': {'dx': 30, 'invert': True}})
    p.timing.mode = 'manual'
    win = MainWindow(p)
    win._debounce.stop()
    original_exec = RelinkDialog.exec
    def choose_and_apply(dialog):
        def apply():
            dialog.show_matches({'logo:Studio': [str(image)]})
            dialog.apply_button.click()
        QTimer.singleShot(0, apply)
        return original_exec(dialog)
    monkeypatch.setattr(RelinkDialog, 'exec', choose_and_apply)
    win.relink_files()
    win._debounce.stop()
    assert p.logos['Studio'] == str(image)
    assert p.logo_settings['Studio'] == {'dx': 30, 'invert': True}
    assert list(win.crawl.logos())[0].path == str(image)
    assert win._unsaved
    assert not relink.missing(p)
    build = prepare(p)
    assert build.layout.logos[0].path == str(image)
    project_path = tmp_path / 'show.crawl.json'
    p.save(str(project_path))
    assert Project.load(str(project_path)).logos['Studio'] == str(image)
    win._unsaved = False
    win.close()


def test_cancel_relink_keeps_original_paths(app, monkeypatch):
    from PySide6.QtCore import QTimer
    from crawl.ui.main_window import MainWindow
    from crawl.ui.relink_dialog import RelinkDialog
    p = Project(rows=[['[Logo: Studio]', '', '']], logos={'Studio': '/missing/studio.png'})
    win = MainWindow(p)
    win._debounce.stop()
    original_exec = RelinkDialog.exec
    def cancel(dialog):
        QTimer.singleShot(0, dialog.reject)
        return original_exec(dialog)
    monkeypatch.setattr(RelinkDialog, 'exec', cancel)
    win.relink_files()
    assert p.logos['Studio'] == '/missing/studio.png'
    assert not win._unsaved
    win.close()


def test_report_is_optional_and_saved_with_project(tmp_path, monkeypatch):
    from crawl import project
    from types import SimpleNamespace
    def movie(*args, **kwargs):
        path = Path(args[4] + '.mov')
        path.touch()
        return path
    monkeypatch.setattr(project.export, 'export_movie', movie)
    reports = []
    def report(p, b, path, panels, movie):
        reports.append(path)
        path.touch()
    monkeypatch.setattr(project, 'write_report', report)
    p = Project(output_dir=str(tmp_path), basename='optional')
    build = SimpleNamespace(layout=None, solution=None)
    assert len(project.render(p, build)) == 1
    assert not reports
    p.write_report = True
    p.save(str(tmp_path / 'optional.crawl.json'))
    restored = Project.load(str(tmp_path / 'optional.crawl.json'))
    assert restored.write_report
    assert len(project.render(restored, build)) == 2
    assert len(reports) == 1
