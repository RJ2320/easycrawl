from PySide6.QtWidgets import QWidget,QVBoxLayout,QTabWidget
from crawl.project import Project,crawl_from_rows
from crawl.ui.sheet_editor import SheetEditor
from crawl.ui.workspace_navigation import WorkspaceNavigation,StyleDisclosure
from crawl.ui.widgets import StyleEditor


def test_navigation_jumps_to_source_row_without_changing_project():
    class Window:
        def seek_row(self,row):self.seek=row
    window=Window();window.project=Project(rows=[['','CAST',''],['Role','','Avery Morgan'],
          ['','',''],['','SPECIAL THANKS',''],['[Logo: A]','','']])
    window.sheet_editor=SheetEditor(window.project);window.sheet_editor.load(window.project.rows)
    nav=WorkspaceNavigation(window)
    nav.refresh(crawl_from_rows(window.project,window.project.rows))
    assert nav.sections.count()==3
    nav.jump(1)
    assert window.sheet_editor.table.currentRow()==3 and window.seek==4
    nav.jump(2)
    assert nav.logos.isHidden() is False and nav.format.isHidden()
    assert not window.project.cell_formats
    window.sheet_editor.close();nav.close()


def test_collapsed_styles_keep_controls_and_update_summary():
    p=Project();editor=StyleEditor('Names',p.look.name)
    disclosure=StyleDisclosure(editor)
    assert editor.isHidden()
    disclosure.button.setChecked(True)
    assert not editor.isHidden()
    editor.size.setValue(72)
    assert p.look.name.size==72 and '72 px' in disclosure.button.text()
    disclosure.button.setChecked(False)
    assert editor.isHidden() and p.look.name.size==72
    disclosure.close()
