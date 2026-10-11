import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from crawl import arrangements, ingest, layout, text
from crawl.project import Project, load_crawl, prepare
from crawl.look import Look
from crawl.render import render_panel

ROWS = [['', 'MUSIC', ''], ['', '', ''], ['', '"First Song"', ''],
        ['Written by', 'Alice', ''], ['Performed by', 'One\nTwo\nThree', ''],
        ['', '', ''], ['', '"Second Song"', ''], ['Written by', 'Bob', ''],
        ['', '', ''], ['', '"Third Song"', ''], ['Written by', 'Charlie', ''],
        ['', '', ''], ['', '"Fourth Song"', ''], ['Courtesy of', 'Delta', ''],
        ['', '', ''], ['', 'AFTER', ''], ['Editor', '', 'Final Person']]


def arrangement(**kwargs):
    return dict(start=2, end=13, columns=2, gap=120, alignment='center', label='Music pairs', **kwargs)


def test_selection_requires_multiple_groups_and_expands_partial_rows():
    assert arrangements.selection_range(ROWS, range(3, 8)) == (2, 7, 2)
    with pytest.raises(ValueError, match='at least two'):
        arrangements.selection_range(ROWS, [3, 4])
    with pytest.raises(ValueError, match='continuous'):
        arrangements.selection_range(ROWS, [2, 6])


def test_grid_top_alignment_order_and_tallest_block():
    p = Project(rows=ROWS, arrangements=[arrangement()])
    crawl = load_crawl(p)
    L = layout.layout(crawl, p.look)
    titles = [next(line for line in L.lines if line.text == f'"{name} Song"')
              for name in ['First', 'Second', 'Third', 'Fourth']]
    assert titles[0].y == titles[1].y
    assert titles[2].y == titles[3].y > titles[0].y
    assert titles[0].x == titles[2].x < titles[1].x == titles[3].x
    three = next(line for line in L.lines if line.text == 'Three')
    assert titles[2].y > three.y + p.look.music_name.size
    after = next(line for line in L.lines if line.text == 'AFTER')
    assert after.y > titles[3].y
    assert L.content_height < layout.layout(ingest.parse(ROWS), p.look).content_height
    # Two songs share a single safe panel-break group.
    assert len(L.groups) == 4
    image = render_panel(L, p.look, 0, L.content_height, .25, colour=False)
    assert image.getbbox() is not None


def test_left_alignment_and_narrow_wrapping():
    p = Project(rows=ROWS, arrangements=[dict(arrangement(), alignment='left', columns=3)])
    L = layout.layout(load_crawl(p), p.look)
    title = next(l for l in L.lines if l.text == '"First Song"')
    role = next(l for l in L.lines if l.text == 'Written by')
    assert title.x == role.x and title.anchor == 'ls'
    for line in L.lines:
        width = text.width(p.look.styles()[line.style], line.text)
        left = line.x - (width / 2 if line.anchor == 'ms' else width if line.anchor == 'rs' else 0)
        assert left >= 0 and left + width <= p.look.width


def test_arrangements_save_reload_and_timing(tmp_path):
    p = Project(rows=ROWS, arrangements=[arrangement()])
    p.timing.mode = 'manual'
    p.timing.speed = 10
    path = tmp_path / 'paired.crawl.json'
    p.save(str(path))
    q = Project.load(str(path))
    assert q.arrangements == p.arrangements and q.rows == p.rows
    b = prepare(q)
    assert b.layout.content_height <= b.layout.target_height
    assert b.solution.speed == 10
    assert b.solution.content_height + q.look.height == b.solution.travel_frames * 10


def test_row_insert_delete_tracks_outline_and_forced_boundaries():
    values = [arrangement()]
    arrangements.insert_row(values, 0)
    assert (values[0]['start'], values[0]['end']) == (3, 14)
    arrangements.insert_row(values, 8)
    assert values[0]['end'] == 15
    arrangements.delete_rows(values, [0, 4, 5])
    assert (values[0]['start'], values[0]['end']) == (2, 12)
    arrangements.delete_rows(values, range(2, 13))
    assert values == []
    # Arrangement edges remain boundaries even when the blank separator is edited.
    rows = [row[:] for row in ROWS]
    rows[14] = ['Extra', '', 'Outside']
    p = Project(rows=rows, arrangements=[arrangement()])
    groups = load_crawl(p).groups
    assert any(g.first_row == 15 for g in groups)


def test_editor_outline_edit_remove_and_insert():
    from PySide6.QtWidgets import QApplication
    from crawl.ui.sheet_editor import SheetEditor
    app = QApplication.instance() or QApplication([])
    p = Project()
    e = SheetEditor(p)
    e.load(ROWS)
    e.apply_arrangement(range(2, 14), label='Music pairs')
    assert e.table.starts_at(2)
    assert e.cell_tooltip(3, 1) == 'Music pairs · 2 columns'
    e.table.setCurrentCell(3, 0)
    e.insert_row()
    assert p.arrangements[0]['end'] == 14
    assert e.arrange_button.text().startswith('Edit')    # the button edits when the cursor is inside one
    with pytest.raises(ValueError, match='overlaps'):
        e.apply_arrangement(range(2, 15))
    e.resize(750, 600)
    e.show()
    app.processEvents()
    assert not e.grab().isNull()
    e.remove_arrangement()
    assert p.arrangements == []
    assert not e.table.starts_at(2)
    e.close()


def test_incomplete_grid_row_is_centered():
    for columns, remaining in [(3, 1), (3, 2)]:
        rows = []
        for index in range(columns + remaining):
            rows += [['', f'BLOCK {index}', ''], ['Role', '', f'Person {index}'], ['', '', '']]
        p = Project(rows=rows, arrangements=[dict(start=0, end=len(rows)-2, columns=columns,
                    gap=120, alignment='center', label='Grid')])
        L = layout.layout(load_crawl(p), p.look)
        last = [line for line in L.lines if line.text in [f'BLOCK {i}' for i in range(columns, columns+remaining)]]
        assert len({line.y for line in last}) == 1
        assert abs(sum(line.x for line in last)/len(last) - p.look.center_x) <= 1


def test_song_continues_across_internal_blank_rows():
    rows = [['', 'MUSIC', ''], ['', '', ''], ['', '"Song A"', ''],
            ['Written by', 'Writer', ''], ['', '', ''], ['', '', ''],
            ['Performed by', 'Singer', ''], ['Courtesy of', 'Label', ''],
            ['', '', ''], ['', '"Song B"', ''], ['Written by', 'Other', '']]
    crawl = ingest.parse(rows)
    assert len(crawl.groups) == 3
    assert [b.row for b in crawl.groups[1].blocks] == [3, 4, 7, 8]
    assert arrangements.selection_range(rows, range(2, 11)) == (2, 10, 2)
    p = Project(rows=rows, arrangements=[dict(start=2, end=10, columns=3, gap=120, alignment='center')])
    L = layout.layout(load_crawl(p), p.look)
    singer = next(line for line in L.lines if line.text == 'Singer')
    title = next(line for line in L.lines if line.text == '"Song A"')
    assert singer.y > title.y
    assert abs(singer.x - title.x) < 300
    assert L.row_positions[7] == singer.y
