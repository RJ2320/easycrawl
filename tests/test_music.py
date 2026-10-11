from dataclasses import replace

import numpy as np
from crawl import ingest, layout, text
from crawl.look import Look, TextStyle
from crawl.model import Header, RolePair
from crawl.project import Project
from crawl.render import render_panel


ROWS = [('', 'MUSIC', ''), ('', '', ''), ('', '"Song One"', ''),
        ('Written by', 'Alice', ''), ('', 'BOB', ''),
        ('Performed by', 'Artist', ''), ('Produced by', '', ''),
        ('', '', ''), ('', '*"Song Two"*', ''), ('*Courtesy of*', '', 'Label'),
        ('', '', ''), ('', 'POST PRODUCTION', ''), ('Editor', '', 'Casey')]


def test_music_keeps_labels_continuations_and_section_boundary():
    blocks = list(ingest.parse(ROWS).blocks())
    roles = [b for b in blocks if isinstance(b, RolePair)]
    assert [(b.role, b.names, b.music) for b in roles] == [
        ('Written by', ['Alice'], True), ('', ['BOB'], True),
        ('Performed by', ['Artist'], True), ('Produced by', [], True),
        ('*Courtesy of*', ['Label'], True), ('Editor', ['Casey'], False)]
    assert [b.text for b in blocks if isinstance(b, Header)] == ['MUSIC', '"Song One"', '*"Song Two"*', 'POST PRODUCTION']


def test_music_spacing_and_centering():
    crawl = ingest.parse(ROWS)
    look = Look()
    L = layout.layout(crawl, look)
    role = next(l for l in L.lines if l.text == 'Written by')
    name = next(l for l in L.lines if l.text == 'Alice')
    assert role.y == name.y
    assert abs(name.x - (role.x + text.width(look.music_role, role.text)) - look.music_inline_gap) < .01
    assert abs((role.x + name.x + text.width(look.music_name, name.text))/2 - look.center_x) < .01
    look.music_name.leading = 48
    assert layout.layout(crawl, look).content_height < L.content_height
    for scale in (.8, 1.3):
        fixed, flexible = layout.measure(crawl, look)
        assert abs(layout.layout(crawl, look, scale).content_height - (fixed + flexible * scale)) <= 3


def test_italic_runs_draw_without_markers_and_wrap():
    look = Look()
    look.width = 1000
    look.center_x = 500
    regular = ingest.parse([('', '"Hello"', '')])
    italic = ingest.parse([('', '*"Hello"*', '')])
    a = layout.layout(regular, look)
    b = layout.layout(italic, look)
    ia = np.asarray(render_panel(a, look, 0, 200, colour=False))
    ib = np.asarray(render_panel(b, look, 0, 200, colour=False))
    assert ib.max() > 0 and not np.array_equal(ia, ib)
    st = look.song
    assert text.width(st, '*Hello*') == text.width(replace(st, italic=True), 'Hello')
    lines = text.wrap(st, '*Alice Bob Charlie*', text.width(st, '*Charlie*') + 1)
    assert len(lines) >= 2
    assert all(line.startswith('*') and line.endswith('*') for line in lines)
    assert text.wrap(st, 'A*B*C', 1000) == ['A*B*C']


def test_music_settings_roundtrip_and_old_project_defaults(tmp_path):
    p = Project(rows=ROWS)
    p.look.music_inline_gap = 12
    p.look.music_name.leading = 58
    p.look.music_role.italic = True
    path = tmp_path / 'music.crawl.json'
    p.save(str(path))
    loaded = Project.load(str(path))
    assert loaded.look.music_inline_gap == 12
    assert loaded.look.music_name.leading == 58
    assert loaded.look.music_role.italic
    assert not Look.from_dict({'song': {'font': 'Helvetica Neue:Medium'}}).song.italic
