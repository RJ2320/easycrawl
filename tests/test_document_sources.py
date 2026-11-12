import pytest
from docx import Document as Word
from numbers_parser import Document as Numbers
from pypdf import PdfReader
from crawl import ingest, changes
from crawl.project import Project,prepare
from crawl.ui.change_dialog import revision_labels
from crawl.ui.review_pdf import section_choices,write_review


def test_document_and_text_sources(tmp_path):
    doc=Word()
    doc.add_heading("CAMERA")
    row=doc.add_table(rows=1,cols=2).rows[0]
    row.cells[0].text="Operator";row.cells[1].text="Renée"
    doc.add_paragraph("Final line")
    path=tmp_path/"credits.docx";doc.save(path)
    assert ingest.read_rows(path)==[("","CAMERA",""),("Operator","","Renée"),("Final line","","")]
    tsv=tmp_path/"credits.tsv"
    tsv.write_text('Operator\t\t"Renée\nAlex"\n',encoding="utf-16")
    assert ingest.read_rows(tsv)==[("Operator","","Renée\nAlex")]
    txt=tmp_path/"credits.txt";txt.write_text('A, B and "C"\n',encoding='utf8')
    assert ingest.read_rows(txt)==[('A, B and "C"','','')]


def test_numbers_table_selection(tmp_path):
    doc=Numbers(sheet_name="Credits",table_name="Cast",num_rows=1,num_cols=3)
    doc.sheets[0].tables[0].write(0,2,"First")
    doc.sheets[0].add_table(table_name="Crew",num_rows=1,num_cols=3)
    doc.sheets[0].tables[1].write(0,2,"Second")
    path=tmp_path/"credits.numbers";doc.save(str(path))
    assert [v.name for v in ingest.sheets(path)]==["Credits / Cast","Credits / Crew"]
    assert "Second" in ingest.read_grid(path,"Credits / Crew")[0]


def test_review_pdf_scope_pagination_and_text(tmp_path,request):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase,QFont
    from crawl import text
    app=QApplication.instance() or QApplication([])
    # The offscreen Qt platform on Windows starts with an empty font database.
    if not QFontDatabase.families():
        previous_font=app.font()
        font_id=QFontDatabase.addApplicationFont(str(text.font_for(Project().look.name).path))
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0]))
        request.addfinalizer(lambda:(app.setFont(previous_font),QFontDatabase.removeApplicationFont(font_id)))
    p=Project(rows=[['','CAST',''],['Lead','','Renée'],['','CREW','']]+
                   [['Helper','','Example '+str(i)] for i in range(140)])
    p.timing.mode='manual'
    build=prepare(p)
    path=tmp_path/'proof.pdf'
    write_review(path,build,p.look,section_choices(build)[0][1])
    pages=PdfReader(path).pages
    assert len(pages)==1 and 'Renée' in pages[0].extract_text()
    assert 'CREW' not in pages[0].extract_text()
    assert 'Renée' in str(ingest.read_rows(path))
    write_review(path,build,p.look)
    pages=PdfReader(path).pages
    assert len(pages)>1 and '139' in pages[-1].extract_text()


def test_revision_types():
    old=[('','CAST',''),('Lead','','Avery'),('','','Blair'),('','','Robin'),('','','Elle'),
         ('','TRANSPORT',''),('Driver','','Jo')]
    new=[old[0],('Lead','','Avary'),old[3],old[4],old[2]]
    found=changes.diff(old,old,new)
    labels=revision_labels(found,old,new)
    assert any('spelling' in label for label,_ in labels)
    assert any('moved' in label for label,_ in labels)
    assert any('heading removed' in label for label,_ in labels)
