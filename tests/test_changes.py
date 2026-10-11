"""Updating a built crawl from a revised sheet."""
from crawl import changes
from crawl.changes import apply, diff, replay

BASE = [
    ("", "CAST", ""),                 # 0
    ("Lead", "", "Ada Blake"),        # 1
    ("Friend", "", "Ben Cho"),        # 2
    ("", "", ""),                     # 3
    ("", "CREW", ""),                 # 4
    ("Director", "", "Cy Dunn"),      # 5
    ("Editor", "", "Di Evans"),       # 6
    ("Gaffer", "", "Ed Fox"),         # 7
]


def rows(*r):
    return [tuple(x) for x in r]


def applied(current, new, base=BASE):
    result, shifts, marks = apply(current, diff(base, current, new))
    return [tuple(r) for r in result], shifts, marks


def test_client_edits_are_found_row_by_row():
    new = list(BASE)
    new[2] = ("Friend", "", "Benjamin Cho")          # a spelling change
    new[6] = ("Editor", "", "Di Evans\nFay Grey")    # a name added
    found = diff(BASE, BASE, new)
    assert [(c.kind, c.start, c.end, c.conflict) for c in found] == [("change", 2, 3, False), ("change", 6, 7, False)]
    assert found[0].old == [BASE[2]] and found[0].new == [new[2]] and found[0].sheet_row == 3
    result, shifts, marks = applied(BASE, new)
    assert result == new and shifts == [] and marks == [(2, 2), (6, 6)]


def test_added_and_removed_rows():
    new = BASE[:2] + [("Villain", "", "Gus Hart")] + BASE[2:6] + BASE[7:]     # one added, Editor removed
    found = diff(BASE, BASE, new)
    assert [(c.kind, c.start, c.end) for c in found] == [("add", 2, 2), ("remove", 6, 7)]
    result, shifts, marks = applied(BASE, new)
    assert result == new and marks == [(2, 2)]


def test_local_edits_survive_and_are_not_offered():
    # In the app: a typo fixed in row 1, a logo row inserted after the cast, the gaffer deleted.
    current = [BASE[0], ("Lead", "", "Ada Blake-Smith"), BASE[2], ("[Logo: Studio]", "", ""),
               BASE[3], BASE[4], BASE[5], BASE[6]]
    # The client, meanwhile, changes the director and adds a producer at the end of the crew.
    new = BASE[:5] + [("Director", "", "Cyrus Dunn")] + BASE[6:] + [("Producer", "", "Hal Ives")]
    found = diff(BASE, current, new)
    assert [(c.kind, c.conflict) for c in found] == [("change", False), ("add", False)]
    result, _, marks = applied(current, new)
    assert result == [BASE[0], ("Lead", "", "Ada Blake-Smith"), BASE[2], ("[Logo: Studio]", "", ""),
                      BASE[3], BASE[4], ("Director", "", "Cyrus Dunn"), BASE[6], ("Producer", "", "Hal Ives")]
    assert marks == [(6, 6), (8, 8)]


def test_client_insert_lands_after_a_local_insert_at_the_same_spot():
    current = BASE[:3] + [("[Logo: Studio]", "", "")] + BASE[3:]          # local row after the cast
    new = BASE[:3] + [("Extra", "", "Ivy Jones")] + BASE[3:]              # client row at the same place
    result, _, _ = applied(current, new)
    assert result == BASE[:3] + [("[Logo: Studio]", "", ""), ("Extra", "", "Ivy Jones")] + BASE[3:]


def test_conflict_when_both_changed_the_same_row_and_rejecting_keeps_mine():
    current = list(BASE)
    current[5] = ("Director", "", "C. Dunn")                 # edited here
    new = list(BASE)
    new[5] = ("Directed by", "", "Cy Dunn")                  # and by the client, differently
    found = diff(BASE, current, new)
    assert [(c.kind, c.conflict, c.old, c.new) for c in found] == [
        ("change", True, [("Director", "", "C. Dunn")], [("Directed by", "", "Cy Dunn")])]
    assert "also edited here" in changes.summary(found)
    found[0].accepted = False
    assert [tuple(r) for r in apply(current, found)[0]] == current
    # The same edit made on both sides is not a change at all.
    assert diff(BASE, new, new) == []


def test_ranges_follow_the_rows():
    # A layout override on the crew roles (rows 5–7) and an arrangement over everything.
    overrides = [dict(start=5, end=7, kind="roles")]
    arrangement = [dict(start=0, end=7, columns=2)]
    new = [("", "PRESENTS", ""), ("", "", "")] + BASE[:6] + BASE[7:]       # two rows added on top, Editor removed
    result, shifts, _ = applied(BASE, new)
    assert result == new
    replay(overrides, shifts)
    replay(arrangement, shifts)
    assert overrides == [dict(start=7, end=8, kind="roles")]              # Director, Gaffer in the new rows
    assert [new[r][0] for r in range(7, 9)] == ["Director", "Gaffer"]
    assert arrangement[0]["end"] == 8


def test_no_base_snapshot_offers_every_difference_and_report_reads_well():
    current = list(BASE)
    current[1] = ("Lead", "", "A. Blake")
    new = list(BASE) + [("Caterer", "", "Jo Kay")]
    found = diff(None, current, new)
    assert [(c.kind, c.conflict) for c in found] == [("change", False), ("add", False)]
    text = changes.report(found, "Changes from v2")
    assert "Changes from v2" in text and "1 changed, 1 added" in text
    assert "Change row 2: Lead — A. Blake  →  Lead — Ada Blake" in text
    assert "Add after row 8: Caterer — Jo Kay" in text
    assert changes.row_text(("", "CAST", "")) == "CAST" and changes.row_text(("", "", "")) == "(blank row)"


# ---- sheets that don't follow the template -----------------------------------

LEGAL = ("The characters and events depicted in this motion picture are fictional. Any similarity to "
         "actual persons, living or dead, is purely coincidental.")


def test_text_in_column_a_is_rescued_and_reported(tmp_path):
    import csv
    from crawl import ingest
    from crawl.model import Legal
    path = tmp_path / "drift.csv"
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows([
            ["", "", "CAST", ""],
            ["", "Lead", "", "Ada Blake"],
            ["", "", "", ""],
            [LEGAL, "", "", ""],                       # typed in column A by mistake
            ["check spelling", "Friend", "", "Ben Cho"],   # a note beside real credits
        ])
    rows, notes = ingest.read_sheet(str(path))
    assert rows[3] == (LEGAL, "", "") and rows[4] == ("Friend", "", "Ben Cho")
    assert [n.row for n in notes] == [4, 5]
    assert "column A" in notes[0].message and "moved into column B" in notes[0].message
    assert "Not imported" in notes[1].message and "check spelling" in notes[1].message
    assert ingest.read_rows(str(path)) == rows                      # same rows through the old entry point
    assert isinstance(list(ingest.parse(rows).blocks())[-2], Legal)


def test_whole_table_one_column_over_and_note_summary():
    from crawl import ingest
    grid = [["", "CAST", ""]] + [[f"Role {i}", "", f"Person {i}"] for i in range(12)]    # A–C, not B–D
    rows, notes = ingest.normalize_grid(grid)
    assert rows[1] == ("Role 0", "", "Person 0") and len(notes) == 1
    assert "columns A–C" in notes[0].message
    # A clean template sheet produces no notes and is not shifted by a stray cell or two.
    clean = [["", "", "CAST", ""]] + [["", f"Role {i}", "", f"Person {i}"] for i in range(12)]
    assert ingest.normalize_grid(clean)[1] == []
    # Lots of cells beside credits (a notes column) are reported once, not per row.
    noisy = [[f"note {i}", f"Role {i}", "", f"Person {i}"] for i in range(20)]
    rows, notes = ingest.normalize_grid(noisy)
    assert rows[0] == ("Role 0", "", "Person 0") and len(notes) == 1 and "20 cells" in notes[0].message


def test_import_notes_are_findings_and_dismissals_stick():
    from crawl.project import Project, findings_for, load_crawl
    p = Project(rows=[["", "CAST", ""], ["Actor", "", "Name 3"], ["", "", ""]] +
                     [[n, "", ""] for n in ["Alice", "Bob", "Cy", "Di", "Ed", "Alice"]],
                import_notes=[dict(start=1, end=1, message="Text was in column A…")])
    found = findings_for(p, load_crawl(p))
    assert {f.check for f in found} == {"placeholder", "import", "duplicate"}
    assert all(f.key for f in found)
    p.dismissed = [f.key for f in found if f.check in ("import", "duplicate")]
    assert [f.check for f in findings_for(p, load_crawl(p))] == ["placeholder"]
    # A dismissal is about the content, so it survives the row moving…
    p.rows.insert(0, ["", "", ""])
    assert [f.check for f in findings_for(p, load_crawl(p))] == ["placeholder"]
    # …and lapses when the text it was about changes.
    p.rows[-1] = ["Bob", "", ""]
    assert sorted(f.check for f in findings_for(p, load_crawl(p))) == ["duplicate", "placeholder"]
    saved = Project.from_dict(p.to_dict())
    assert saved.dismissed == p.dismissed and saved.import_notes == p.import_notes
