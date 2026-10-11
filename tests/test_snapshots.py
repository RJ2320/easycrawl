import copy
import json
import os
import shutil

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from crawl.project import Project


def test_snapshot_restores_whole_project_and_keeps_way_back():
    p = Project(rows=[["Director", "", "Alice"]], base_rows=[["Director", "", "Client"]],
                source_url="https://docs.google.com/spreadsheets/d/example/edit",
                sheet="Credits", columns="A,B,C", start_row=3,
                logos={"Studio": "/art/studio.png"}, logo_settings={"Studio": {"dx": 20}},
                arrangements=[{"start": 0, "end": 0, "columns": 2}], dismissed=["checked"])
    p.look.name.size = 51
    p.timing.speed = 9
    p.codec = "h264"
    original = copy.deepcopy(p.to_dict())
    snapshot = p.create_snapshot(" Client review 1 ")
    assert snapshot["name"] == "Client review 1"
    assert "snapshots" not in snapshot["state"]
    p.rows[0][2] = "Bob"
    p.logo_settings["Studio"]["dx"] = 80
    p.look.name.size = 20
    p.timing.speed = 3
    p.codec = "png"
    recovery = p.restore_snapshot(snapshot["id"])
    restored = p.to_dict()
    restored.pop("snapshots")
    original.pop("snapshots")
    assert restored == original
    assert recovery["state"]["rows"][0][2] == "Bob"
    assert len(p.snapshots) == 2
    p.restore_snapshot(recovery["id"])
    assert p.rows[0][2] == "Bob"
    assert p.logo_settings["Studio"]["dx"] == 80
    assert p.look.name.size == 20
    assert len(p.snapshots) == 3


def test_snapshot_captures_unedited_source_and_survives_missing_sheet(tmp_path):
    source = tmp_path / "credits.csv"
    source.write_text("A,B,C,D\n,Director,,Alice\n")
    p = Project(source=str(source))
    snapshot = p.create_snapshot("Original")
    source.unlink()
    p.rows = [["Editor", "", "Bob"]]
    p.restore_snapshot(snapshot["id"])
    assert any(row[2] == "Alice" for row in p.rows)


def test_snapshot_portability_and_no_mutation_on_save(tmp_path):
    folder = tmp_path / "job"
    folder.mkdir()
    art = folder / "logo.png"
    art.write_bytes(b"art")
    p = Project(rows=[], source=str(folder / "sheet.xlsx"), logos={"Studio": str(art)},
                output_dir=str(folder / "render"))
    snapshot = p.create_snapshot("Approved")
    path = folder / "job.crawl.json"
    p.save(str(path))
    disk = json.loads(path.read_text())
    assert disk["snapshots"][0]["state"]["logos"]["Studio"] == "logo.png"
    assert snapshot["state"]["logos"]["Studio"] == str(art)
    moved = tmp_path / "moved"
    shutil.move(str(folder), str(moved))
    loaded = Project.load(str(moved / path.name))
    loaded.restore_snapshot(snapshot["id"])
    assert loaded.logos["Studio"] == str(moved / "logo.png")
    assert loaded.source == str(moved / "sheet.xlsx")
    assert loaded.output_dir == str(moved / "render")


def test_collect_keeps_snapshot_assets_and_distinct_same_names(tmp_path):
    job = tmp_path / "job"
    job.mkdir()
    paths = []
    for n in (1, 2):
        folder = tmp_path / str(n)
        folder.mkdir()
        path = folder / "logo.png"
        path.write_bytes(str(n).encode())
        paths.append(str(path))
    p = Project(rows=[], logos={"Studio": paths[0]})
    snapshot = p.create_snapshot("Original logo")
    p.logos["Studio"] = paths[1]
    copied = p.collect(str(job / "job.crawl.json"))
    assert len(copied) == 2
    assert p.logos["Studio"] != snapshot["state"]["logos"]["Studio"]
    assert open(p.logos["Studio"], "rb").read() == b"2"
    assert open(snapshot["state"]["logos"]["Studio"], "rb").read() == b"1"


def test_invalid_snapshot_requests_leave_project_unchanged():
    p = Project(rows=[])
    with pytest.raises(ValueError):
        p.create_snapshot(" ")
    with pytest.raises(StopIteration):
        p.restore_snapshot("missing")
    assert not p.snapshots
    assert Project.from_dict({"rows": []}).snapshots == []


@pytest.fixture
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_snapshot_dialog_save_rename_delete(app, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    from crawl.ui.snapshot_dialog import SnapshotDialog
    p = Project(rows=[["Director", "", "Alice"]])
    dialog = SnapshotDialog(p)
    changes = []
    dialog.changed.connect(lambda: changes.append(True))
    assert not dialog.restore_button.isEnabled()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Review", True))
    dialog.save_snapshot()
    assert dialog.selected()["name"] == "Review"
    assert "1 rows" in dialog.details.text()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Approved", True))
    dialog.rename_snapshot()
    assert dialog.selected()["name"] == "Approved"
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    dialog.delete_snapshot()
    assert not p.snapshots
    assert len(changes) == 3
    dialog.close()


def test_window_restore_refreshes_panels_and_pauses_google(app):
    from crawl.ui.main_window import MainWindow
    p = Project(rows=[["Director", "", "Alice"]])
    p.timing.mode = "manual"
    snapshot = p.create_snapshot("Review")
    p.rows = [["Editor", "", "Bob"]]
    p.look.name.size = 21
    p.source_url = "https://docs.google.com/spreadsheets/d/example/edit"
    win = MainWindow(p)
    win._debounce.stop()
    win.restore_snapshot(snapshot["id"])
    win._debounce.stop()
    assert win.sheet_editor.rows() == [["Director", "", "Alice"]]
    assert win.project.look.name.size == snapshot["state"]["look"]["name"]["size"]
    assert win.look_panel.project is win.project
    assert win.project.snapshots[-1]["state"]["rows"] == [["Editor", "", "Bob"]]
    assert not win._watch_timer.isActive()
    assert win._unsaved
    assert not win.sheet_editor.can_undo()
    win._unsaved = False
    win.close()
