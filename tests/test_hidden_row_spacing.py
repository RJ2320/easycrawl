import json
from pathlib import Path
import openpyxl
from crawl import ingest,lint,changes
from crawl.model import ListBlock
from crawl.project import Project,load_crawl,read_source
from crawl.layout import layout
from crawl.ui.sheet_editor import SheetEditor


def workbook(tmp_path,visible_blank=False):
    path=tmp_path/'credits.xlsx'
    wb=openpyxl.Workbook();ws=wb.active;ws.title='Crawl'
    ws.append(['','Role One','','Avery Morgan'])
    ws.append(['','Hidden role','','Hidden Person'])
    ws.append(['','Hidden role','','Hidden Person'])
    if visible_blank:ws.append(['','','',''])
    ws.append(['','Role Two','','Robin Chen'])
    ws.row_dimensions[2].hidden=True;ws.row_dimensions[3].hidden=True
    wb.save(path);wb.close()
    return path


def imported(path):
    p=Project(source=str(path))
    rows,notes=read_source(p,str(path))
    p.rows=[list(row) for row in rows];p.base_rows=[list(row) for row in rows]
    p.hidden_rows=ingest.hidden_ranges(rows);p.base_hidden_rows=ingest.hidden_ranges(rows)
    return p,rows


def test_hidden_cast_rows_do_not_add_gap_and_keep_original_numbers(tmp_path):
    path=workbook(tmp_path)
    rows=ingest.read_rows(str(path));crawl=ingest.parse(rows)
    result=layout(crawl,Project().look)
    assert len(rows)==4 and rows[1:3]==[('','','')]*2
    assert [block.row for block in crawl.blocks()]==[1,4]
    assert result.row_positions[4]-result.row_positions[1]==80
    assert len(crawl.groups)==1


def test_visible_blank_still_adds_group_spacing(tmp_path):
    p,rows=imported(workbook(tmp_path,True))
    result=layout(load_crawl(p),p.look)
    assert result.row_positions[5]-result.row_positions[1]==p.look.name.leading+p.look.group_gap
    assert len(load_crawl(p).groups)==2


def test_hidden_list_names_keep_source_rows_for_render_and_warnings(tmp_path):
    path=tmp_path/'names.xlsx';wb=openpyxl.Workbook();ws=wb.active;ws.title='Crawl'
    ws.append(['','Person One'])
    ws.append(['','Hidden Person']);ws.row_dimensions[2].hidden=True
    for name in ['Person Two','Person Three','Person Four','Person Five','Name 4']:
        ws.append(['',name])
    wb.save(path);wb.close()
    crawl=ingest.parse(ingest.read_rows(str(path)))
    block=next(crawl.blocks())
    assert isinstance(block,ListBlock) and block.source_rows==[1,3,4,5,6,7]
    result=layout(crawl,Project().look)
    assert 7 in result.row_positions and 2 not in result.row_positions
    assert any(f.row==7 and f.check=='placeholder' for f in lint.lint(crawl))


def test_visibility_roundtrip_and_local_row_insert_delete_undo(tmp_path):
    p,rows=imported(workbook(tmp_path));e=SheetEditor(p);e.load(p.rows)
    assert e.table.isRowHidden(1) and e.table.isRowHidden(2)
    e.table.setCurrentCell(1,0);e.insert_rows(above=True,count=1)
    assert ingest.hidden_indices(p.hidden_rows)=={2,3}
    assert not e.table.isRowHidden(1) and e.table.isRowHidden(2)
    e.undo();assert ingest.hidden_indices(p.hidden_rows)=={1,2}
    e.redo();assert ingest.hidden_indices(p.hidden_rows)=={2,3}
    path=tmp_path/'saved.crawl.json';p.save(str(path))
    restored=Project.load(str(path));assert restored.hidden_rows==p.hidden_rows
    assert restored.base_hidden_rows==[dict(start=1,end=2)]
    e.close()


def test_old_saved_project_recovers_hidden_metadata_from_matching_source(tmp_path):
    p,rows=imported(workbook(tmp_path))
    p.rows.append(['Local role','','Local Person'])
    data=p.to_dict();data.pop('hidden_rows');data.pop('base_hidden_rows')
    path=tmp_path/'old.crawl.json';path.write_text(json.dumps(data))
    restored=Project.load(str(path))
    assert ingest.hidden_indices(restored.hidden_rows)=={1,2}
    result=layout(load_crawl(restored),restored.look)
    assert result.row_positions[4]-result.row_positions[1]==restored.look.name.leading
    assert restored.rows[-1]==['Local role','','Local Person']


def test_visibility_only_update_and_undo_keep_visible_blank_behavior(tmp_path):
    p,rows=imported(workbook(tmp_path));e=SheetEditor(p);e.load(p.rows)
    visible=ingest.SheetRows(p.rows)
    assert changes.diff(p.base_rows,e.rows(),visible)==[]
    e.apply_update(visible,[])
    assert not p.hidden_rows
    result=layout(load_crawl(p),p.look)
    assert result.row_positions[4]-result.row_positions[1]==p.look.name.leading+p.look.group_gap
    e.undo();assert ingest.hidden_indices(p.hidden_rows)=={1,2}
    e.close()


def test_hidden_row_metadata_follows_revised_source_row_numbers(tmp_path):
    p,rows=imported(workbook(tmp_path));e=SheetEditor(p);e.load(p.rows)
    revised=ingest.SheetRows([['New role','','New Person']]+list(rows),hidden_rows={2,3})
    accepted=changes.diff(p.base_rows,e.rows(),revised)
    e.apply_update(revised,accepted)
    assert ingest.hidden_indices(p.hidden_rows)=={2,3}
    assert p.base_hidden_rows==[dict(start=2,end=3)]
    e.undo();assert ingest.hidden_indices(p.hidden_rows)=={1,2}
    e.close()
