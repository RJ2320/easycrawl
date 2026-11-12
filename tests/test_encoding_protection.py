import codecs,json
import pytest
from crawl.encoding_checks import suggest_correction
from crawl.project import Project,crawl_from_rows
from crawl.lint import lint,Finding
from crawl.ui.sheet_editor import SheetEditor
from crawl.ui.issue_review import IssueReview


@pytest.mark.parametrize('broken,correct',[
    ('Ren\u00c3\u00a9e','Ren\u00e9e'),('O\u00e2\u20ac\u2122Brien','O\u2019Brien'),
    ('\u00c3\u2026sa','\u00c5sa'),('Copyright \u00c2\u00a9','Copyright \u00a9'),
    ('\u6771\u4eac Ren\u00c3\u00a9e','\u6771\u4eac Ren\u00e9e')])
def test_reversible_encoding_suggestions_preserve_other_text(broken,correct):
    assert suggest_correction(broken)==correct


@pytest.mark.parametrize('value',['Ren\u00e9e','\u00c2ngelo','\u00c5sa','\u6771\u4eac','O\u2019Brien','\u00a9 \u00ae','Fran\u00e7ois'])
def test_valid_international_text_has_no_suggestion(value):
    assert suggest_correction(value) is None


def test_project_load_accepts_utf8_and_bom_and_roundtrips_unicode(tmp_path):
    path=tmp_path/'project.crawl.json'
    data=Project(rows=[['Role','','Ren\u00e9e \u6771\u4eac']]).to_dict()
    path.write_bytes(codecs.BOM_UTF8+json.dumps(data,ensure_ascii=False).encode('utf-8'))
    p=Project.load(str(path));assert p.rows==data['rows']
    p.save(str(path));assert Project.load(str(path)).rows==data['rows']
    assert json.loads(path.read_text(encoding='utf-8'))['rows']==data['rows']


def test_review_correction_is_explicit_targets_exact_cell_and_undoes():
    p=Project();e=SheetEditor(p)
    original=[['Role','','Ren\u00c3\u00a9e'],['Other','','Robin Chen']]
    e.load(original)
    findings=lint(crawl_from_rows(p,e.rows()));e.set_findings(findings)
    dialog=IssueReview(e)
    assert e.rows()==original
    encoding=next(f for f in findings if f.check=='encoding')
    assert encoding.column==2 and encoding.suggestion=='Ren\u00e9e'
    dialog.category.setCurrentIndex(dialog.category.findData('encoding'))
    dialog.show_selected();assert e.table.currentRow()==0 and e.table.currentColumn()==2
    dialog.apply_correction()
    assert e.rows()==[['Role','','Ren\u00e9e'],original[1]]
    e.undo();assert e.rows()==original
    dialog.close();e.close()


def test_review_filters_notes_and_replacement_character_is_not_auto_fixed():
    p=Project();e=SheetEditor(p);e.load([['Role','','Un\ufffdreadable']])
    findings=lint(crawl_from_rows(p,e.rows()));findings.append(Finding('empty','info',1,'Informational note'))
    e.set_findings(findings);dialog=IssueReview(e)
    assert '1 note' in dialog.summary.text() and '1 note' in e.errors_chip.text()
    dialog.severity.setCurrentIndex(dialog.severity.findData('warning'))
    assert all(f.severity=='warning' for f in dialog.visible_findings)
    assert dialog.selected().check=='encoding' and not dialog.selected().suggestion
    before=e.rows();dialog.apply_correction();assert e.rows()==before
    dialog.close();e.close()
