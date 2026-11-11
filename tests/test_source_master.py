from crawl import changes
from crawl.project import Project
from crawl.ui.change_dialog import ChangeDialog


def test_master_comparison_recovers_previous_skipped_case_changes_and_new_rows():
    current=[['','EXAMPLE GROUP',''],['Avery Morgan','','Robin Chen'],['Alex Taylor','','Casey Reed']]
    incoming=[current[0],['AVERY MORGAN','','ROBIN CHEN'],['New Person','','New Person Two'],['ALEX TAYLOR','','CASEY REED']]
    found=changes.source_diff(current,incoming)
    assert sum(c.capitalization_only for c in found)==2
    assert any(c.kind=='add' for c in found)
    assert all(c.accepted and not c.conflict for c in found)
    result,_,_=changes.apply(current,found)
    assert result==incoming
    # The source already matches the baseline after a previous partial import.
    assert changes.diff(incoming,current,incoming)==[]
    assert changes.source_diff(current,incoming)


def test_master_includes_deletions_and_local_text_differences():
    current=[['Role','','Local spelling'],['Local added role','','Local Person'],['Other','','Old name']]
    incoming=[['Role','','Source spelling'],['Other','','New name']]
    result,_,_=changes.apply(current,changes.source_diff(current,incoming))
    assert result==incoming


def test_case_only_label_is_visible_and_selected_by_default():
    found=changes.source_diff([['Role','','Avery Morgan']],[['Role','','AVERY MORGAN']])
    dialog=ChangeDialog(found,'Master sheet',authoritative=True)
    assert dialog.table.item(0,0).text()=='Capitalization'
    assert dialog.accepted_changes()==found
    dialog.close()


def test_master_setting_saves_with_project_and_can_be_disabled(tmp_path):
    p=Project();assert p.google_sheet_master
    p.google_sheet_master=False
    path=tmp_path/'master.crawl.json';p.save(str(path))
    assert not Project.load(str(path)).google_sheet_master


def test_real_google_master_update_includes_old_skipped_names_and_keeps_layout(tmp_path,monkeypatch):
    import csv
    from crawl.ui.main_window import MainWindow
    path=tmp_path/'incoming.csv'
    incoming=[['Role','','AVERY MORGAN'],['','','ROBIN CHEN']]
    with path.open('w',newline='') as stream:
        csv.writer(stream).writerows([['']+row for row in incoming])
    p=Project(source=str(path),source_url='https://docs.google.com/spreadsheets/d/'+'x'*30+'/edit',
              rows=[['Role','','Avery Morgan'],['','','Robin Chen']],base_rows=incoming,
              overrides=[dict(start=1,end=1,kind='center_name')])
    win=MainWindow(p);win._debounce.stop()
    monkeypatch.setattr(win,'_prepare_import',lambda *args,**kwargs:True)
    monkeypatch.setattr(ChangeDialog,'exec',lambda self:ChangeDialog.Accepted)
    win.update_from_sheet(str(path),from_google=True);win._debounce.stop()
    assert p.rows==incoming and p.overrides==[dict(start=1,end=1,kind='center_name')]
    win._unsaved=False;win.close()


def test_google_watch_detects_skipped_differences_even_when_source_matches_baseline(monkeypatch,tmp_path):
    from crawl import gsheets
    from crawl.ui import worker
    from crawl import project as project_module
    p=Project(rows=[['Role','','Avery Morgan']],base_rows=[['Role','','AVERY MORGAN']])
    monkeypatch.setattr(gsheets,'fetch',lambda *args:str(tmp_path/'source.xlsx'))
    monkeypatch.setattr(project_module,'read_source',lambda *args:([['Role','','AVERY MORGAN']],[]))
    task=worker.SheetFetchWorker(p,str(tmp_path))
    changed=[];unchanged=[]
    task.changed.connect(changed.append);task.unchanged.connect(unchanged.append)
    task.run();assert changed and not unchanged
    p.google_sheet_master=False
    legacy=worker.SheetFetchWorker(p,str(tmp_path))
    legacy.unchanged.connect(unchanged.append);legacy.run()
    assert unchanged


def test_master_preserves_configured_logos_while_updating_all_credit_text():
    current=[['Role','','Avery Morgan'],['[Logo: Studio A] | [Logo: Studio B]','','']]
    incoming=[['Role','','AVERY MORGAN'],['New role','','Robin Chen'],['','[OTHER EQUIPMENT LOGOS]','']]
    found=changes.source_diff(current,incoming,protected_logos={'Studio A','Studio B'})
    result,_,_=changes.apply(current,found)
    assert result==incoming[:2]+[current[1]]
    assert changes.source_diff(result,incoming,protected_logos={'Studio A','Studio B'})==[]


def test_master_still_updates_unassigned_source_logo_placeholders():
    current=[['[Logo: Old placeholder]','','']]
    incoming=[['','[Logo: New placeholder]','']]
    result,_,_=changes.apply(current,changes.source_diff(current,incoming))
    assert result==incoming
