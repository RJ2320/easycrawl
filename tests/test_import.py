"""Reading sheets that don't match the template, and sheets that live in Google Sheets."""
import io
import os
import urllib.error
import zipfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest

from crawl import gsheets, ingest
from crawl.project import Project


def _workbook(path, sheets):
    """sheets: {name: grid}. Returns the path."""
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, grid in sheets.items():
        ws = wb.create_sheet(name)
        for row in grid:
            ws.append(row)
    wb.save(path)
    return str(path)


CREDITS = [["", "", "CAST", ""], ["", "Lead", "", "Ada Blake"], ["", "Friend", "", "Ben Cho"]]
NOTES = [["Notes for the editor"], ["Deliver by Friday"]]


# ---- columns and start row -----------------------------------------------------

def test_column_specs_round_trip():
    assert ingest.parse_columns("B,C,D") == (1, 2, 3, 3)
    assert ingest.parse_columns("b, c, d-f") == (1, 2, 3, 5)
    assert ingest.parse_columns("A,B,E-C") == (0, 1, 2, 4)            # reversed range is fine
    assert ingest.format_columns(1, 2, 3, 5) == "B,C,D-F"
    assert ingest.column_index("AA") == 26
    with pytest.raises(ValueError):
        ingest.parse_columns("B,C")                                    # need three
    with pytest.raises(ValueError):
        ingest.parse_columns("B,B,C")                                  # must differ


def test_names_across_columns_are_stacked_and_title_rows_skipped():
    grid = [["END CRAWL v3", "", "", "", ""],
            ["", "", "CAST", "", ""],
            ["", "Lead", "", "Ada Blake", "Cy Dunn"],
            ["", "Friend", "", "Ben Cho", ""]]
    rows, notes = ingest.normalize_grid(grid, "B,C,D-E", start_row=2)
    assert rows[0] == ("", "", "")                                       # kept so row numbers match the sheet
    assert rows[2] == ("Lead", "", "Ada Blake\nCy Dunn")
    assert notes == []                                                   # column E is credits now, not a stray
    # Without the spec the extra names column is reported, with a pointer to the fix.
    rows, notes = ingest.normalize_grid(grid)
    assert rows[2] == ("Lead", "", "Ada Blake")
    assert any("column E" in n.message for n in notes)


def test_detected_columns_and_explicit_columns():
    shifted = [["", "CAST", ""]] + [[f"Role {i}", "", f"Person {i}"] for i in range(12)]
    assert ingest.detect_columns(shifted) == "A,B,C"
    rows, notes = ingest.normalize_grid(shifted)
    assert rows[1] == ("Role 0", "", "Person 0") and "columns A–C" in notes[0].message
    # Saying so explicitly reads the same rows and no longer counts as a deviation.
    rows2, notes2 = ingest.normalize_grid(shifted, "A,B,C")
    assert rows2 == rows and notes2 == []


# ---- worksheets ------------------------------------------------------------------

def test_workbook_sheets_are_listed_and_guessed(tmp_path):
    path = _workbook(tmp_path / "show.xlsx", {"Notes": NOTES, "Crawl": CREDITS, "Empty": []})
    infos = ingest.sheets(path)
    assert [(i.name, i.filled) for i in infos] == [("Notes", 2), ("Crawl", 3), ("Empty", 0)]
    assert infos[1].preview[0] == "CAST"
    assert ingest.guess_sheet(infos) == "Crawl"
    # No credits-like name: the fullest sheet wins.
    other = _workbook(tmp_path / "other.xlsx", {"Sheet1": NOTES, "Sheet2": CREDITS})
    assert ingest.guess_sheet(ingest.sheets(other)) == "Sheet2"
    assert ingest.read_sheet(other, "")[0][1] == ("Lead", "", "Ada Blake")       # "" = guess
    with pytest.raises(ingest.SheetNotFound) as err:
        ingest.read_sheet(other, "Crawl")
    assert err.value.available == ["Sheet1", "Sheet2"]
    # A CSV is one unnamed sheet.
    csv_path = tmp_path / "plain.csv"
    csv_path.write_text("\n".join(",".join(r) for r in CREDITS))
    assert [i.name for i in ingest.sheets(str(csv_path))] == [""]


def test_project_reads_with_its_import_settings(tmp_path):
    from crawl import project as proj
    path = _workbook(tmp_path / "wide.xlsx", {"Credits": [
        ["Title", "", "", "", ""],
        ["", "Lead", "", "Ada", "Blake"]]})
    p = Project(source=path, sheet="Credits", columns="B,C,D-E", start_row=2)
    rows, notes = proj.read_source(p, path)
    assert rows[1] == ["Lead", "", "Ada\nBlake"] and rows[0] == ["", "", ""] and notes == []
    saved = tmp_path / "wide.crawl.json"
    p.save(str(saved))
    again = Project.load(str(saved))
    assert (again.sheet, again.columns, again.start_row) == ("Credits", "B,C,D-E", 2)


# ---- Google Sheets ---------------------------------------------------------------

LINK = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcd/edit?usp=sharing#gid=42"


def test_google_links_are_recognised_and_canonicalised():
    assert gsheets.is_link(LINK) and not gsheets.is_link("https://example.com/sheet.xlsx")
    doc, gid = gsheets.parse(LINK)
    assert doc.startswith("1AbCdEf") and gid == "42"
    assert gsheets.canonical(LINK) == f"https://docs.google.com/spreadsheets/d/{doc}/edit#gid=42"
    assert gsheets.export_url(LINK).endswith("/export?format=xlsx")
    with pytest.raises(gsheets.GoogleSheetError):
        gsheets.parse("not a link")


class _Response:
    def __init__(self, data, kind="application/octet-stream", url=""):
        self._data, self.headers, self.url = data, {"Content-Type": kind}, url

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _xlsx_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
    return buf.getvalue()


def test_google_fetch_writes_workbook_and_explains_sharing(tmp_path):
    path = gsheets.fetch(LINK, str(tmp_path / "sheets"), opener=lambda req, timeout: _Response(_xlsx_bytes()))
    assert path.endswith(".xlsx") and open(path, "rb").read(2) == b"PK"

    def wall(req, timeout):
        return _Response(b"<!DOCTYPE html><html>sign in</html>", "text/html; charset=utf-8",
                         "https://accounts.google.com/ServiceLogin")
    with pytest.raises(gsheets.GoogleSheetError) as err:
        gsheets.fetch(LINK, str(tmp_path), opener=wall)
    assert "Anyone with the link" in str(err.value)

    def forbidden(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
    with pytest.raises(gsheets.GoogleSheetError) as err:
        gsheets.fetch(LINK, str(tmp_path), opener=forbidden)
    assert "isn't shared" in str(err.value)


def test_fetch_worker_reports_whether_the_sheet_changed(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from crawl.ui.worker import SheetFetchWorker
    QApplication.instance() or QApplication([])
    path = _workbook(tmp_path / "live.xlsx", {"Crawl": CREDITS})
    monkeypatch.setattr(gsheets, "fetch", lambda url, folder: path)
    p = Project(source=path, source_url=gsheets.canonical(LINK), sheet="Crawl",
                base_rows=[list(r) for r in ingest.read_sheet(path, "Crawl")[0]])
    results = []
    worker = SheetFetchWorker(p, str(tmp_path))
    worker.changed.connect(lambda where: results.append(("changed", where)))
    worker.unchanged.connect(lambda where: results.append(("unchanged", where)))
    worker.failed.connect(lambda msg: results.append(("failed", msg)))
    worker.run()
    assert results == [("unchanged", path)]
    p.base_rows[1][2] = "Someone Else"                 # what was brought in no longer matches the sheet
    worker2 = SheetFetchWorker(p, str(tmp_path))
    worker2.changed.connect(lambda where: results.append(("changed", where)))
    worker2.run()
    assert results[-1] == ("changed", path)


# ---- the dialog and the window -----------------------------------------------------

@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_import_dialog_picks_sheet_and_columns(app, tmp_path):
    from crawl.ui.import_dialog import ImportDialog
    path = _workbook(tmp_path / "multi.xlsx", {"Notes": NOTES, "Crawl": [
        ["Title row", "", "", "", ""],
        ["", "", "CAST", "", ""],
        ["", "Lead", "", "Ada", "Blake"]]})
    dialog = ImportDialog(path)
    assert dialog.sheet == "Crawl" and dialog.columns == "" and dialog.start_row == 1
    assert "1 heading" in dialog.summary.text() and "2 credits" in dialog.summary.text()
    dialog.last_box.setCurrentIndex(4)                 # names D–E
    dialog.start_spin.setValue(2)
    assert dialog.columns == "B,C,D-E" and dialog.start_row == 2
    assert "flagged" not in dialog.summary.text()      # column E is credits now, title row skipped
    dialog.sheet_list.setCurrentRow(0)                 # switching sheets re-detects columns
    assert dialog.sheet == "Notes"
    dialog.close()


def test_window_settles_import_without_asking_when_obvious(app, tmp_path):
    from crawl.ui.main_window import MainWindow
    win = MainWindow(Project())
    single = _workbook(tmp_path / "single.xlsx", {"Sheet1": CREDITS})
    assert win._prepare_import(single) and win.project.sheet == "Sheet1"
    assert win.load_sheet(single) and win.project.sheet == "Sheet1" and not win.project.source_url
    assert "Sheet1" in win.subtitle_label.text()
    # Import settings travel with the project and the subtitle shows the Google source.
    win.project.source_url = gsheets.canonical(LINK)
    win._title()
    win._sync_google()
    assert win.subtitle_label.text().startswith("Google Sheet") and win.refresh_action.isEnabled()
    assert win._watch_timer.isActive() == win.watch_action.isChecked()
    win.project.source_url = ""
    win._sync_google()
    assert not win.refresh_action.isEnabled() and not win._watch_timer.isActive()
    win.close()
