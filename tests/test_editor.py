import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PIL import Image
from crawl.project import Project, load_crawl


@pytest.fixture(scope='module')
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_project_embeds_edited_rows_without_original(tmp_path):
    p = Project(source=str(tmp_path / 'missing.xlsx'), rows=[['Director', '', 'Alice\nBob'], ['', '', ''],
                                                            ['[Logo: Studio]', '', '']])
    p.logos['Studio'] = str(tmp_path / 'studio.png')
    path = tmp_path / 'edited.crawl.json'
    p.save(str(path))
    loaded = Project.load(str(path))
    crawl = load_crawl(loaded)
    assert list(crawl.blocks())[0].names == ['Alice', 'Bob']
    assert list(crawl.logos())[0].path == p.logos['Studio']
    assert loaded.rows == p.rows


def test_editor_adds_multiple_logos_and_edits(app, tmp_path):
    from crawl.ui.sheet_editor import SheetEditor
    from PySide6.QtWidgets import QTableWidgetItem
    p = Project()
    editor = SheetEditor(p)
    editor.load([['Director', '', 'Original']])
    editor.table.setItem(0, 2, QTableWidgetItem('Edited\nSecond'))
    assert p.rows[0][2] == 'Edited\nSecond'
    editor.table.setCurrentCell(0, 0)
    editor.add_logo_paths([str(tmp_path / 'studio.png'), str(tmp_path / 'partner.png')])
    editor.add_logo_paths([str(tmp_path / 'studio.png')])
    crawl = load_crawl(p)
    assert [lg.label for lg in crawl.logos()] == ['studio', 'partner', 'studio 2']
    assert len(p.rows) == 2
    editor.delete_rows()
    assert len(p.rows) == 1


def test_output_exposes_logo_row_slots(app):
    from crawl.ui.main_window import OutputPanel
    p = Project(rows=[['[Logo: A] | [Logo: B]', '', '']])
    panel = OutputPanel(p)
    panel.set_logo_slots(load_crawl(p))
    assert panel.logos_layout.rowCount() == 2


def test_playback_tracks_elapsed_time_and_seeking(app):
    from crawl.ui.widgets import PreviewPanel
    panel = PreviewPanel()
    panel.load(Image.new('L', (100, 1000)), .25, 400, 200, 10, 0, 1000, 23.976, [], str)
    now = [0.0]
    panel._clock = lambda: now[0]
    panel.play.setChecked(True)
    now[0] = 10.0  # Simulate a delayed timer: catch up instead of advancing one frame.
    panel._tick()
    assert panel.slider.value() == 239
    panel.slider.setValue(500)
    now[0] += 1.0
    panel._tick()
    assert panel.slider.value() == 523
    panel.play.setChecked(False)
    panel.view.resize(400, 200)
    assert not panel.view.grab().isNull()


def test_main_window_reparses_artwork_and_columns(app, tmp_path):
    from crawl.ui.main_window import MainWindow
    p = Project(source='missing.csv', rows=[['[Logo: A]', '', ''], ['', '', '']] +
                [[f'Partner {i}', '', ''] for i in range(6)])
    win = MainWindow(p)
    p.logos['A'] = str(tmp_path / 'a.png')
    p.list_columns = 2
    win.schedule_rebuild()
    assert list(win.crawl.logos())[0].path == p.logos['A']
    assert list(win.crawl.blocks())[1].columns == 2
    win.close()


def test_lint_jump_selects_sheet_and_seeks_preview(app):
    from crawl.ui.main_window import MainWindow
    from crawl.project import prepare
    p = Project(source='missing.csv', rows=[['', 'CAST', ''], ['Actor', '', 'Name 3']])
    p.timing.mode = 'manual'
    win = MainWindow(p)
    win._debounce.stop()
    win.build = prepare(p)
    win.preview.slider.setRange(0, win.build.solution.total_frames - 1)
    win.sheet_editor.set_findings(win.build.findings)
    finding = next(i for i, f in enumerate(win.build.findings) if f.row == 2)
    win.sheet_editor.focus_error(finding)
    assert win.tabs.currentWidget() is win.sheet_editor
    assert win.sheet_editor.table.currentRow() == 1
    assert 'Row 2:' in win.sheet_editor.finding_note.text()
    expected = round((win.build.layout.row_positions[2] + p.look.height/2)/win.build.solution.speed)
    assert win.preview.slider.value() == expected
    assert win.look_tabs.widget(1) is win.music_panel
    assert all(win.tabs.tabText(i) != 'Music' for i in range(win.tabs.count()))
    win.close()


def test_inline_errors_cells_navigation_and_clearing(app):
    from crawl.ui.sheet_editor import SheetEditor
    from crawl.project import load_crawl
    from crawl.lint import lint
    from PySide6.QtWidgets import QTableWidgetItem
    p = Project(rows=[['', 'CAST', ''], ['Actor', '', 'Name 3'],
                      ['Producer', '', ''], ['', '', '']] +
                     [[name, '', ''] for name in ['Alice', 'Bob', 'Charlie', 'Delta', 'Echo', 'Alice']])
    editor = SheetEditor(p)
    editor.load(p.rows)
    editor.set_findings(lint(load_crawl(p)))
    assert (1, 2) in editor.table.error_cells
    assert (2, 2) in editor.table.error_cells
    assert (9, 0) in editor.table.error_cells
    assert (1, 0) not in editor.table.error_cells
    jumps = []
    editor.finding_selected.connect(lambda row, msg: jumps.append(row))
    editor.step_error(1)
    assert editor.table.currentRow() == 1 and editor.table.currentColumn() == 2
    assert 'Error' in editor.finding_note.text()
    editor.step_error(-1)
    assert editor.finding_index == len(editor.findings)-1
    assert 'Possible problem' in editor.finding_note.text()
    editor._error_clicked(2, 2)
    assert 'has no names' in editor.finding_note.text()
    assert jumps[-1] == 3
    editor.table.setItem(1, 2, QTableWidgetItem('Real Person'))
    assert (1, 2) not in editor.table.error_cells
    assert (2, 2) in editor.table.error_cells and editor.next_error.isEnabled()
    editor.insert_row()                       # a structural change invalidates every row number
    assert not editor.table.error_cells and not editor.next_error.isEnabled()
    editor.undo()
    editor.set_findings(lint(load_crawl(p)))
    assert (1, 2) not in editor.table.error_cells
    assert (2, 2) in editor.table.error_cells
    editor.close()


def test_inline_errors_keep_arrangement_outline(app):
    from crawl.ui.sheet_editor import SheetEditor
    from crawl.project import load_crawl
    from crawl.lint import lint
    p = Project(rows=[['', 'CAST', ''], ['Actor', '', 'Name 3'], ['', '', ''],
                      ['', 'CREW', ''], ['Producer', '', 'Person']])
    editor = SheetEditor(p)
    editor.load(p.rows)
    editor.apply_arrangement(range(5))
    editor.set_findings(lint(load_crawl(p)))
    assert editor.table.starts_at(0)
    assert (1, 2) in editor.table.error_cells
    assert 'template leftover' in editor.cell_tooltip(1, 2)
    assert 'Side by side' in editor.cell_tooltip(1, 2)
    editor.resize(750, 600)
    editor.show()
    app.processEvents()
    assert not editor.grab().isNull()
    editor.close()


def test_show_in_preview_and_follow_selection(app):
    from crawl.ui.main_window import MainWindow
    from crawl.project import prepare
    p = Project(source='missing.csv', rows=[['', 'CREW', ''], ['Director', '', 'Alice'],
                    ['', '', ''], ['Editor', '', 'Bob']])
    p.timing.mode = 'manual'
    win = MainWindow(p)
    win._debounce.stop()
    build = prepare(p)
    win.build = build
    win.preview.slider.setRange(0, build.solution.total_frames - 1)
    editor = win.sheet_editor
    assert editor.follow_selection.isChecked()
    editor.follow_selection.setChecked(False)
    editor.table.setCurrentCell(1, 2)
    assert win.preview.slider.value() == 0
    editor.show_in_preview.trigger()
    expected = round((build.layout.row_positions[2] + p.look.height/2)/build.solution.speed)
    assert win.preview.slider.value() == expected
    editor.follow_selection.setChecked(True)
    editor.table.setCurrentCell(3, 2)
    expected = round((build.layout.row_positions[4] + p.look.height/2)/build.solution.speed)
    assert win.preview.slider.value() == expected
    editor.table.setCurrentCell(2, 0)  # blank row, tie chooses next credit
    assert win.preview.slider.value() == expected
    editor.follow_selection.setChecked(False)
    win.build = None
    editor.table.setCurrentCell(1, 2)
    editor.show_in_preview.trigger()
    assert win._pending_finding_row == 2
    win.build = build
    win._seek_finding()
    assert win.preview.slider.value() == round((build.layout.row_positions[2]+p.look.height/2)/build.solution.speed)
    win.close()


def test_layout_override_apply_split_merge_and_row_shift(app):
    from crawl.ui.sheet_editor import SheetEditor
    from crawl.model import RolePair, ListBlock
    p = Project(rows=[['', 'FOR STUDIO', '']] + [[f'Exec {i}', '', ''] for i in range(8)])
    editor = SheetEditor(p)
    editor.load(p.rows)
    editor.apply_layout(range(1, 9), 'roles')
    assert p.overrides == [dict(start=1, end=8, kind='roles')]
    assert all(isinstance(b, RolePair) and b.names_pending for b in list(load_crawl(p).blocks())[1:])
    # Clearing the middle splits the run; re-marking merges it back.
    editor.apply_layout([4, 5], 'auto')
    assert p.overrides == [dict(start=1, end=3, kind='roles'), dict(start=6, end=8, kind='roles')]
    editor.apply_layout([4, 5], 'roles')
    assert p.overrides == [dict(start=1, end=8, kind='roles')]
    editor.apply_layout([6, 7, 8], 'center')
    assert p.overrides == [dict(start=1, end=5, kind='roles'), dict(start=6, end=8, kind='center')]
    blocks = list(load_crawl(p).blocks())
    assert isinstance(blocks[-1], ListBlock) and blocks[-1].columns == 1
    # Inserting a row above shifts the ranges with the rows.
    editor.table.setCurrentCell(0, 0)
    editor.insert_row()
    assert p.overrides == [dict(start=2, end=6, kind='roles'), dict(start=7, end=9, kind='center')]
    assert 'Layout: Roles' in editor.cell_tooltip(2, 0)
    with pytest.raises(ValueError):
        editor.apply_layout([0], 'roles')   # header row, nothing in B
    editor.close()


def test_clicking_a_cell_snaps_preview(app):
    from crawl.ui.sheet_editor import SheetEditor
    from crawl.lint import lint
    p = Project(rows=[['', 'CAST', ''], ['Actor', '', 'Name 3'], ['Editor', '', 'Bob']])
    editor = SheetEditor(p)
    editor.load(p.rows)
    editor.set_findings(lint(load_crawl(p)))
    previews, findings = [], []
    editor.preview_requested.connect(previews.append)
    editor.finding_selected.connect(lambda row, msg: findings.append(row))
    editor._cell_clicked(2, 2)
    assert previews == [3] and findings == []
    editor._cell_clicked(1, 2)           # error cell: the finding drives the jump
    assert previews == [3] and findings == [2]
    editor.close()


def test_drag_logo_in_preview_and_logo_bar(app, tmp_path):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent
    from crawl.ui.main_window import MainWindow
    from crawl.project import prepare
    Image.new('RGBA', (200, 100), (20, 20, 20, 255)).save(tmp_path / 'a.png')
    p = Project(source='missing.csv', rows=[['[Logo: A]', '', '']], logos={'A': str(tmp_path / 'a.png')})
    p.timing.mode = 'manual'
    win = MainWindow(p)
    win._debounce.stop()
    build = prepare(p)
    win.build = build
    view = win.preview.view
    view.resize(960, 540)
    view.width_px, view.height_px, view.speed, view.head = p.look.width, p.look.height, build.solution.speed, 0
    view.set_logos(build.layout.logos)
    logo = build.layout.logos[0]
    # Put the logo mid-frame, then press on its centre and drag 96 display px right, 48 down.
    view.set_frame(round((logo.y + p.look.height / 2) / build.solution.speed))
    centre = view.logo_rect(logo).center()
    k = view._geom()[4]

    def mouse(kind, pos, buttons=Qt.LeftButton, mods=Qt.AltModifier):
        return QMouseEvent(kind, pos, view.mapToGlobal(pos), Qt.LeftButton, buttons, mods)

    view.mousePressEvent(mouse(QEvent.MouseButtonPress, centre))
    assert view.selected == 'A' and win.preview.logo_bar.dx.isEnabled()
    view.mouseMoveEvent(mouse(QEvent.MouseMove, centre + QPointF(96, 48)))
    view.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, centre + QPointF(96, 48), Qt.NoButton))
    win._debounce.stop()
    assert p.logo_settings['A']['dx'] == round(96 / k) and p.logo_settings['A']['dy'] == round(48 / k)
    assert win.preview.logo_bar.dx.value() == round(96 / k)

    # The bar edits the same settings; Output's Invert tick follows without re-emitting.
    win.preview.logo_bar.invert.setChecked(True)
    win.preview.logo_bar.scale.setValue(150)
    win._debounce.stop()
    assert p.logo_settings['A']['invert'] is True and p.logo_settings['A']['scale'] == 1.5
    assert win.output_panel._invert_boxes['A'].isChecked()
    win.output_panel._invert_boxes['A'].setChecked(False)
    win._debounce.stop()
    assert p.logo_settings['A']['invert'] is False and not win.preview.logo_bar.invert.isChecked()

    # Reset drops the entry entirely; clicking empty space clears the selection.
    win.preview.logo_bar.reset.click()
    win._debounce.stop()
    assert 'A' not in p.logo_settings
    view.mousePressEvent(mouse(QEvent.MouseButtonPress, QPointF(3, 3)))
    assert view.selected == '' and not win.preview.logo_bar.dx.isEnabled()
    assert not view.grab().isNull()
    win._unsaved = False
    win.close()


def test_logo_drag_snaps_to_alignments(app):
    from crawl.layout import LogoItem
    from crawl.ui.widgets import FrameView
    view = FrameView()
    view.resize(960, 540)                       # k = 0.25 → reach 7 / 0.25 = 28 delivery px
    view.width_px, view.height_px = 3840, 2160
    a = LogoItem('A', None, 1000, 500, 400, 200, dx=30, dy=-12)
    b = LogoItem('B', None, 2400, 560, 300, 100)
    view.set_logos([a, b])
    view.selected = 'A'
    reach = 28
    # Near its automatic spot on both axes → back to zero offset.
    assert view._snap(-25, 13, reach) == (-30, 12)
    assert {axis for axis, _ in view._guides} == {'v', 'h'}
    # Frame centre line: A's centre is at 1200, the frame's at 1920.
    view._guides = []
    assert view._snap(715, 300, reach)[0] == 720 and ('v', 1920.0) in view._guides
    # Vertical centre of the neighbour: B's centre y is 610, A's is 600.
    view._guides = []
    assert view._snap(300, 9, reach) == (300, 10) and view._guides == [('h', 610.0)]
    # Out of reach of everything: untouched, no guides.
    view._guides = []
    assert view._snap(300, 250, reach) == (300, 250) and view._guides == []
    view.close()


# ---- spreadsheet behaviour ---------------------------------------------------

def _editor(rows):
    from crawl.ui.sheet_editor import SheetEditor
    p = Project(rows=[list(r) for r in rows])
    editor = SheetEditor(p)
    editor.load(p.rows)
    return p, editor


def test_copy_paste_ranges_roundtrip_multiline_and_grow(app):
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QTableWidgetSelectionRange
    p, editor = _editor([['Producer', '', 'Ada\nBen'], ['Editor', '', 'Cy'], ['', '', '']])
    editor.table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 2), True)
    editor.copy()
    text = QGuiApplication.clipboard().text()
    assert text == 'Producer\t\t"Ada\nBen"\nEditor\t\tCy'          # what Sheets/Excel put on the clipboard
    # Paste past the end: the sheet grows, multi-line cells survive, it is one undo step.
    editor.table.clearSelection()
    editor.table.setCurrentCell(2, 0)
    editor.paste()
    assert p.rows == [['Producer', '', 'Ada\nBen'], ['Editor', '', 'Cy'],
                      ['Producer', '', 'Ada\nBen'], ['Editor', '', 'Cy']]
    assert editor.table.rowHeight(2) > editor.table.rowHeight(1)   # the two-line cell got its height
    editor.undo()
    assert p.rows == [['Producer', '', 'Ada\nBen'], ['Editor', '', 'Cy'], ['', '', '']]
    editor.redo()
    assert len(p.rows) == 4
    # Columns past D are dropped rather than wrapping.
    editor.table.clearSelection()
    editor.table.setCurrentCell(0, 2)
    editor.paste('X\tY\tZ')
    assert p.rows[0] == ['Producer', '', 'X']
    editor.close()


def test_single_value_fills_selection_delete_clears_cut_moves(app):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QTableWidgetSelectionRange
    p, editor = _editor([['a', '', '1'], ['b', '', '2'], ['c', '', '3']])
    steps = []
    editor.changed.connect(lambda: steps.append(1))
    editor.table.setRangeSelected(QTableWidgetSelectionRange(0, 2, 2, 2), True)
    editor.paste('Same')
    assert [r[2] for r in p.rows] == ['Same', 'Same', 'Same'] and len(steps) == 1
    QTest.keyClick(editor.table, Qt.Key_Delete)
    assert [r[2] for r in p.rows] == ['', '', ''] and len(steps) == 2
    editor.table.clearSelection()
    editor.table.setCurrentCell(1, 0)
    editor.cut()
    assert QGuiApplication.clipboard().text() == 'b' and p.rows[1][0] == ''
    editor.undo(); editor.undo(); editor.undo()
    assert p.rows == [['a', '', '1'], ['b', '', '2'], ['c', '', '3']] and not editor.can_undo()
    editor.close()


def test_typing_replaces_enter_commits_and_moves_alt_enter_adds_line(app):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from crawl.ui.arrangement_table import CellEditor
    p, editor = _editor([['Producer', '', 'Old'], ['Editor', '', 'Keep'], ['', '', '']])
    editor.resize(700, 400)
    editor.show()
    table = editor.table
    table.setFocus()
    table.setCurrentCell(0, 2)

    def cell_editor():
        found = table.findChildren(CellEditor)
        assert found, 'no in-cell editor open'
        return found[-1]

    # Typing on a selected cell replaces its contents.
    QTest.keyClicks(table, 'N')
    ed = cell_editor()
    QTest.keyClicks(ed, 'ew')
    QTest.keyClick(ed, Qt.Key_Return, Qt.AltModifier)        # a second line, in place
    QTest.keyClicks(ed, 'Second')
    QTest.keyClick(ed, Qt.Key_Return)                         # commit and move down
    app.processEvents()
    assert p.rows[0][2] == 'New\nSecond'
    assert (table.currentRow(), table.currentColumn()) == (1, 2)

    # Enter on a cell edits it with the cursor at the end; Tab commits and moves right... to the edge.
    QTest.keyClick(table, Qt.Key_Return)
    ed = cell_editor()
    QTest.keyClicks(ed, '!')
    QTest.keyClick(ed, Qt.Key_Tab)
    app.processEvents()
    assert p.rows[1][2] == 'Keep!' and (table.currentRow(), table.currentColumn()) == (1, 2)

    # Shift+Enter commits and moves up; Escape abandons the edit.
    table.setCurrentCell(1, 0)
    QTest.keyClicks(table, 'Z')
    QTest.keyClick(cell_editor(), Qt.Key_Return, Qt.ShiftModifier)
    app.processEvents()
    assert p.rows[1][0] == 'Z' and table.currentRow() == 0
    QTest.keyClicks(table, 'Q')
    QTest.keyClick(cell_editor(), Qt.Key_Escape)
    app.processEvents()
    assert p.rows[0][0] == 'Producer'
    editor.close()


def test_italic_toggle_in_cell_editor(app):
    from crawl.ui.arrangement_table import CellEditor
    ed = CellEditor()
    ed.setPlainText('Song Title')
    ed.selectAll()
    ed.toggle_italic()
    assert ed.toPlainText() == '*Song Title*'
    ed.selectAll()
    ed.toggle_italic()
    assert ed.toPlainText() == 'Song Title'


def test_insert_rows_matches_selection_and_find_and_filter(app):
    from PySide6.QtWidgets import QTableWidgetSelectionRange
    from crawl.lint import lint
    p, editor = _editor([['', 'CAST', ''], ['Actor', '', 'Name 3'], ['Editor', '', 'Bob'], ['Grip', '', 'Cy']])
    editor.table.setRangeSelected(QTableWidgetSelectionRange(1, 0, 2, 0), True)
    editor.insert_rows(above=True)                     # two rows selected → two rows inserted
    assert len(p.rows) == 6 and p.rows[1] == p.rows[2] == ['', '', ''] and p.rows[3][0] == 'Actor'
    editor.undo()
    assert len(p.rows) == 4

    found = []
    editor.preview_requested.connect(found.append)
    editor.table.setCurrentCell(0, 0)
    assert editor.find_next('BOB') and editor.table.currentRow() == 2 and found[-1] == 3
    assert editor.find_next('b') and editor.table.currentRow() == 2      # wraps back to the only match
    assert not editor.find_next('zzz')

    editor.set_findings(lint(load_crawl(p)))
    assert 'error' in editor.errors_chip.text()
    editor.errors_chip.setChecked(True)                # show only rows with problems
    assert [editor.table.isRowHidden(r) for r in range(4)] == [True, False, True, True]
    editor.errors_chip.setChecked(False)
    assert not any(editor.table.isRowHidden(r) for r in range(4))
    editor.close()


def test_window_undo_covers_logo_moves_and_marks_modified(app, tmp_path):
    from crawl.ui.main_window import MainWindow
    Image.new('RGBA', (200, 100), (240, 240, 240, 255)).save(tmp_path / 'a.png')
    p = Project(source='missing.csv', rows=[['[Logo: A]', '', '']], logos={'A': str(tmp_path / 'a.png')})
    win = MainWindow(p)
    win._debounce.stop()
    assert not win._unsaved and not win.undo_action.isEnabled()
    assert '[*]' in win.windowTitle() and [win.tabs.tabText(i) for i in range(5)] == ['Credits', 'Logos', 'Look', 'Timing', 'Export']
    win.set_logo_setting('A', {'dx': 40, 'invert': True})
    win._debounce.stop()
    assert win._unsaved and win.isWindowModified() and win.undo_action.isEnabled()
    win.undo()
    win._debounce.stop()
    assert 'A' not in p.logo_settings and win.redo_action.isEnabled()
    win.redo()
    win._debounce.stop()
    assert p.logo_settings['A']['dx'] == 40 and p.logo_settings['A']['invert'] is True
    assert win.export_btn.text() == 'Export ProRes 422 HQ'
    win.output_panel.codec.setCurrentIndex(win.output_panel.codec.findData('h264'))
    assert win.export_btn.text().startswith('Export H.264')
    win._debounce.stop()
    win._unsaved = False
    win.close()


def test_empty_state_and_start_blank(app):
    from crawl.ui.main_window import MainWindow
    win = MainWindow()
    editor = win.sheet_editor
    assert editor._stack.currentIndex() == 0 and win.preview.view.strip is None
    win.new_blank()
    win._debounce.stop()
    assert editor._stack.currentIndex() == 1 and editor.table.rowCount() == 40
    win._rebuild()                                   # blank rows: an empty frame, not an error
    assert win.build is None and win.statusBar().currentMessage() == 'No credits yet'
    win._unsaved = False
    win.close()


def test_timeline_markers_and_keyboard_transport(app):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from crawl.ui.widgets import PreviewPanel
    panel = PreviewPanel()
    panel.load(Image.new('L', (100, 1000)), .25, 400, 200, 10, 0, 1000, 24.0, [], str)
    panel.slider.set_markers([(600, 'MUSIC'), (200, 'CAST')])
    panel.slider.setValue(300)
    panel.slider.jump(1)
    assert panel.slider.value() == 600
    panel.slider.jump(-1)
    assert panel.slider.value() == 200
    panel.slider.jump(-1)                            # nothing before the first section
    assert panel.slider.value() == 200
    QTest.keyClick(panel.view, Qt.Key_Right)
    QTest.keyClick(panel.view, Qt.Key_Right, Qt.ShiftModifier)
    assert panel.slider.value() == 211
    QTest.keyClick(panel.view, Qt.Key_Down)
    assert panel.slider.value() == 600
    panel.toggle_play()
    assert panel.play.isChecked()
    panel.step(-1)                                   # stepping pauses
    assert not panel.play.isChecked() and panel.slider.value() == 599
    panel.resize(900, 560)
    assert not panel.grab().isNull()


def test_switching_tabs_or_export_settings_does_not_relayout(app):
    from crawl.ui.main_window import MainWindow
    from crawl.project import prepare
    p = Project(source='missing.csv', rows=[['', 'CAST', ''], ['Actor', '', 'Ada']])
    p.timing.mode = 'manual'
    win = MainWindow(p)
    win._debounce.stop()
    win.build = build = prepare(p)
    win.show()
    # Fields report "editing finished" when they lose focus; that must not count as a change.
    win.timing_panel._apply()
    win.output_panel._apply()
    for i in range(win.tabs.count()):
        win.tabs.setCurrentIndex(i)
        app.processEvents()
    assert win.build is build and not win._unsaved and not win._debounce.isActive()
    # An export-only setting dirties the project but keeps the layout.
    win.output_panel.basename.setText('final')
    win.output_panel._apply()
    assert p.basename == 'final' and win._unsaved and win.build is build and not win._debounce.isActive()
    # A real picture change re-lays-out.
    win.timing_panel.speed.setValue(p.timing.speed + 3)
    assert win.build is None and win._debounce.isActive()
    win._debounce.stop()
    win._unsaved = False
    win.close()


# ---- dismissing problems, updating from a revised sheet ----------------------

def test_dismiss_steps_on_persists_and_restores(app):
    from crawl.ui.sheet_editor import SheetEditor
    from crawl.project import findings_for
    p = Project(rows=[['', 'CAST', ''], ['Actor', '', 'Name 3'], ['Producer', '', ''], ['', '', '']] +
                     [[n, '', ''] for n in ['Alice', 'Bob', 'Cy', 'Di', 'Ed', 'Alice']])
    editor = SheetEditor(p)
    editor.load(p.rows)
    editor.set_findings(findings_for(p, load_crawl(p)))
    assert len(editor.findings) == 3
    signals = []
    editor.dismissed_changed.connect(lambda: signals.append(1))
    editor.step_error(1)                                   # the placeholder on row 2
    assert 'Name 3' in editor.finding_note.text() and editor.dismiss_button.isVisibleTo(editor._finding_bar)
    editor.dismiss()
    assert p.dismissed == ['placeholder|name 3'] and len(editor.findings) == 2 and signals
    assert 'has no names' in editor.finding_note.text()    # moved on to the next one
    assert (1, 2) not in editor.table.error_cells
    # From a selection (the context menu's route), then undo brings it back.
    editor.table.setCurrentCell(9, 0)
    editor.dismiss(editor._selected_finding_indices())
    assert 'duplicate|alice' in p.dismissed and len(editor.findings) == 1
    editor.undo()
    assert p.dismissed == ['placeholder|name 3']
    # A re-check honours the dismissals; restoring clears them.
    editor.set_findings(findings_for(p, load_crawl(p)))
    assert len(editor.findings) == 2
    editor._sync_more_menu()
    assert editor.restore_action.isEnabled() and '1 dismissed' in editor.restore_action.text()
    editor.restore_dismissed()
    assert p.dismissed == [] and len(findings_for(p, load_crawl(p))) == 3
    editor.close()


def test_dismissal_updates_the_build_that_gates_export(app):
    from crawl.ui.main_window import MainWindow
    from crawl.project import prepare
    p = Project(source='missing.csv', rows=[['', 'CAST', ''], ['Actor', '', 'Name 3']])
    p.timing.mode = 'manual'
    win = MainWindow(p)
    win._debounce.stop()
    win.build = prepare(p)
    win.sheet_editor.set_findings(win.build.findings)
    assert win.build.errors == 1
    win.sheet_editor.focus_error(0)
    win.sheet_editor.dismiss()
    assert win.build.errors == 0 and win._unsaved and p.dismissed == ['placeholder|name 3']
    assert prepare(p).errors == 0                          # and it stays dismissed on the next build
    win._debounce.stop()
    win._unsaved = False
    win.close()


def test_update_from_revised_sheet_keeps_work_and_marks_changes(app, tmp_path):
    import csv
    from crawl.ui.main_window import MainWindow
    from crawl.ui.change_dialog import ChangeDialog
    from crawl import changes

    def write(name, rows):
        path = tmp_path / name
        with open(path, 'w', newline='') as f:
            csv.writer(f).writerows([[''] + list(r) for r in rows])
        return str(path)

    v1 = [['', 'CAST', ''], ['Lead', '', 'Ada Blake'], ['Friend', '', 'Ben Cho'], ['', '', ''],
          ['', 'FOR STUDIO', ''], ['Chief Exec', '', ''], ['Finance', '', ''], ['', '', ''],
          ['Thanks to', '', 'Everyone']]
    win = MainWindow(Project(source=write('v1.csv', v1)))
    win._debounce.stop()
    p, editor = win.project, win.sheet_editor
    assert p.base_rows == v1 and p.rows is None

    # Work done in the app: a layout override, a typo fixed, a logo row added.
    editor.apply_layout([5, 6], 'roles')
    editor.table.item(1, 2).setText('Ada Blake-Smith')
    editor.table.setCurrentCell(7, 0)
    editor.add_logo_paths([str(tmp_path / 'studio.png')])
    assert p.rows[8] == ['[Logo: studio]', '', ''] and p.overrides == [dict(start=5, end=6, kind='roles')]

    # The client's revision: a new cast member, a renamed role, the thanks line reworded.
    v2 = [v1[0], v1[1], v1[2], ['Villain', '', 'Gus Hart'], v1[3], v1[4],
          ['Chief Executive', '', ''], v1[6], v1[7], ['With thanks to', '', 'Everyone']]
    new_rows, notes = __import__('crawl.project', fromlist=['x']).read_source(p, write('v2.csv', v2))
    found = changes.diff(p.base_rows, editor.rows(), new_rows)
    assert [(c.kind, c.conflict) for c in found] == [('add', False), ('change', False), ('change', False)]

    dialog = ChangeDialog(found, 'v2.csv')
    assert dialog.apply_button.text() == 'Apply 3 changes' and dialog.table.rowCount() == 3
    dialog.table.item(2, 0).setCheckState(Qt_Unchecked())           # keep our thanks line
    assert dialog.apply_button.text() == 'Apply 2 changes'
    dialog._copy()
    from PySide6.QtGui import QGuiApplication
    assert '(not applied) Change row 10' in QGuiApplication.clipboard().text()

    editor.apply_update(new_rows, dialog.accepted_changes(), notes)
    win._debounce.stop()
    rows = p.rows
    assert rows[1] == ['Lead', '', 'Ada Blake-Smith']               # our typo fix survived
    assert rows[3] == ['Villain', '', 'Gus Hart']                   # their addition is in
    assert rows[6] == ['Chief Executive', '', '']                   # their rename is in
    assert rows[9] == ['[Logo: studio]', '', ''] and rows[10] == ['Thanks to', '', 'Everyone']
    assert p.overrides == [dict(start=6, end=7, kind='roles')]      # the override followed its rows
    assert [(m['start'], m['end']) for m in editor.table.change_marks] == [(3, 3), (6, 6)]
    assert editor.changes_chip.text() == '2 changed rows' and 'was: Chief Exec' in editor.cell_tooltip(6, 0)
    assert p.base_rows == v2
    editor.changes_chip.setChecked(True)
    assert [r for r in range(len(rows)) if not editor.table.isRowHidden(r)] == [3, 6]
    editor.changes_chip.setChecked(False)

    # The rejected change is not offered again; a later revision only shows what is new.
    assert changes.diff(p.base_rows, editor.rows(), v2) == []
    # One undo puts everything back, including the snapshot and the marks.
    editor.undo()
    win._debounce.stop()
    assert p.rows[3] == ['', '', ''] and p.base_rows == v1 and editor.table.change_marks == []
    assert p.overrides == [dict(start=5, end=6, kind='roles')]
    win._unsaved = False
    win.close()


def Qt_Unchecked():
    from PySide6.QtCore import Qt
    return Qt.Unchecked


def test_off_template_sheet_is_flagged_on_open(app, tmp_path):
    import csv
    from crawl.ui.main_window import MainWindow
    from crawl.project import findings_for
    legal = 'This motion picture is protected by the copyright laws of the USA and other countries. ' * 2
    path = tmp_path / 'drift.csv'
    with open(path, 'w', newline='') as f:
        csv.writer(f).writerows([['', '', 'CAST', ''], ['', 'Lead', '', 'Ada'], ['', '', '', ''], [legal, '', '', '']])
    win = MainWindow(Project(source=str(path)))
    win._debounce.stop()
    p = win.project
    assert win.sheet_editor.rows()[3][0] == legal.strip()
    assert p.import_notes == [dict(start=3, end=3, message=p.import_notes[0]['message'])]
    found = findings_for(p, win.crawl)
    assert [(f.check, f.row) for f in found] == [('import', 4)]
    # The note follows its row when rows are inserted above it.
    win.sheet_editor.table.setCurrentCell(0, 0)
    win.sheet_editor.insert_rows(above=True)
    win._debounce.stop()
    assert p.import_notes[0]['start'] == 4
    win._unsaved = False
    win.close()


def test_resolution_lives_on_export_and_can_scale_the_look(app):
    from crawl.ui.main_window import MainWindow
    p = Project(source='missing.csv', rows=[['', 'CAST', ''], ['Actor', '', 'Ada']])
    p.timing.mode = 'manual'
    win = MainWindow(p)
    win._debounce.stop()
    out = win.output_panel
    assert out.selected_size() == (3840, 2160) and not out.custom.isVisibleTo(out)
    assert win.format_chip.text() == '3840 × 2160  ·  23.976 fps'
    from PySide6.QtWidgets import QLabel
    assert 'Canvas' not in [l.text() for l in win.look_panel.findChildren(QLabel)]   # no longer buried in Look

    win.change_resolution(1920, 1080, scale_look=True)
    assert (p.look.width, p.look.height, p.look.center_x, p.look.name.size) == (1920, 1080, 960, 28)
    assert out.selected_size() == (1920, 1080) and win.format_chip.text().startswith('1920 × 1080')
    assert win.look_panel.center_x.value() == 960 and win.look_panel.editors['name'].size.value() == 28
    assert win.timing_panel.speed.value() == p.timing.speed == 5
    assert win._unsaved and win._debounce.isActive()
    win._debounce.stop()

    win.change_resolution(3840, 2160, scale_look=False)      # canvas only: sizes stay, column re-centred
    assert (p.look.center_x, p.look.name.size) == (1920, 28)
    win._debounce.stop()

    win.change_resolution(2000, 1000, scale_look=False)      # not a preset: shown as custom
    assert out.resolution.currentText() == 'Custom…' and out.custom.isVisibleTo(out)
    assert (out.custom_w.value(), out.custom_h.value()) == (2000, 1000)
    win._debounce.stop()

    # Frame rate is editable from Export and stays in step with Timing; the runtime is kept.
    seconds = p.timing.runtime_frames / p.timing.fps
    out.fps_requested.emit('25')
    assert p.timing.fps == 25 and win.timing_panel.fps.currentText() == '25'
    assert abs(p.timing.runtime_frames / 25 - seconds) < 0.05 and '25 fps' in win.format_chip.text()
    win._debounce.stop()
    win._unsaved = False
    win.close()


def test_logo_inspector_levels_and_auto(app, tmp_path):
    from PIL import ImageDraw
    from crawl.ui.main_window import MainWindow
    im = Image.new('RGBA', (400, 200), (50, 50, 50, 255))
    ImageDraw.Draw(im).rectangle([100, 60, 300, 140], fill=(235, 235, 235, 255))
    im.save(tmp_path / 'boxed.png')
    p = Project(source='missing.csv', rows=[['[Logo: A]', '', '']], logos={'A': str(tmp_path / 'boxed.png')})
    win = MainWindow(p)
    win._debounce.stop()
    bar = win.preview.logo_bar
    from crawl.layout import LogoItem
    win.preview.view.set_logos([LogoItem('A', p.logos['A'], 100, 100, 400, 200)])
    win.preview.view.select_logo('A')         # as clicking it in the preview does
    assert bar.label == 'A' and (bar.black.value(), bar.white.value()) == (0, 100)
    bar.auto.click()
    win._debounce.stop()
    assert p.logo_settings['A']['black'] == 22 and bar.black.value() == 22       # (50 + 6) / 255
    assert 'black point set to 22' in win.statusBar().currentMessage()
    bar.white.setValue(10)                    # can't cross below the black point
    win._debounce.stop()
    assert p.logo_settings['A']['white'] == 24
    list(win.crawl.logos())
    logo = next(iter(win.crawl.logos()))
    assert logo.black == pytest.approx(0.22) and logo.white == pytest.approx(0.24)
    bar.reset.click()
    win._debounce.stop()
    assert 'A' not in p.logo_settings
    win.undo()
    win._debounce.stop()
    assert p.logo_settings['A']['black'] == 22
    win._unsaved = False
    win.close()


def test_export_button_becomes_cancel_and_cleans_up(app, tmp_path):
    import shutil
    from PySide6.QtCore import QEventLoop, QTimer
    from crawl.ui.main_window import MainWindow
    from crawl.project import prepare
    if shutil.which('ffmpeg') is None:
        pytest.skip('ffmpeg not installed')
    rows = [['', 'CAST', '']] + [[f'Grip {i}', '', f'Person {i}'] for i in range(200)]
    p = Project(source='missing.csv', rows=rows, output_dir=str(tmp_path), codec='h264', basename='show')
    p.set_resolution(960, 540)
    p.timing.mode = 'manual'
    p.timing.speed = 2
    win = MainWindow(p)
    win._debounce.stop()
    win.build = prepare(p)
    win._sync_ready()
    assert win.export_btn.text().startswith('Export H.264') and win.export_btn.isEnabled()

    def wait(condition, timeout=20000):
        loop = QEventLoop()
        poll = QTimer()
        poll.timeout.connect(lambda: condition() and loop.quit())
        poll.start(20)
        QTimer.singleShot(timeout, loop.quit)
        loop.exec()
        poll.stop()
        assert condition(), 'timed out'

    win.export_btn.click()
    assert win.export_btn.text() == 'Cancel export' and win.header_progress.isVisibleTo(win)
    wait(lambda: 'encoding' in win.header_progress.format())          # frames are going to ffmpeg
    win.export_btn.click()                                             # now it cancels
    assert win.export_btn.text() == 'Cancelling…' and not win.export_btn.isEnabled()
    wait(lambda: win.export_btn.text().startswith('Export H.264'))
    assert win.export_btn.isEnabled() and not win.header_progress.isVisibleTo(win)
    assert win.statusBar().currentMessage() == 'Export cancelled'
    assert not (tmp_path / 'show.mp4').exists() and not win._exporting()
    win._unsaved = False
    win.close()
