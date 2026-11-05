from crawl import ingest, lint


def near(rows):
    return [f for f in lint.lint(ingest.parse(rows)) if f.check == 'near-dup']


def test_similar_names_in_different_sections_are_not_flagged():
    assert not near([('', 'CAMERA', ''), ('Operator', '', 'Avery Morgan'),
                     ('', '', ''), ('', 'SPECIAL THANKS', ''), ('', '', 'Avery Morgon')])


def test_similar_names_in_one_section_are_still_flagged_across_blank_rows():
    found=near([('', 'CAMERA', ''), ('Operator', '', 'Avery Morgan'),
                ('', '', ''), ('Assistant', '', 'Avery Morgon')])
    assert len(found)==1 and found[0].row==4 and '(row 2)' in found[0].message


def test_unheaded_blank_separated_sections_are_independent():
    assert not near([('Operator', '', 'Avery Morgan'), ('', '', ''),
                     ('Assistant', '', 'Avery Morgon')])


def test_identical_names_remain_allowed_across_departments():
    assert not near([('', 'CAMERA', ''), ('Operator', '', 'Avery Morgan'),
                     ('', 'ADDITIONAL CREW', ''), ('Assistant', '', 'Avery Morgan')])


def test_duplicate_names_in_one_thanks_list_still_warn():
    rows=[('', 'SPECIAL THANKS', '')]+[('Avery Morgan','','')]*6
    assert any(f.check=='duplicate' for f in lint.lint(ingest.parse(rows)))
