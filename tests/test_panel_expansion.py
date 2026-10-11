import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from crawl.ui.main_window import MainWindow


def test_panel_expansion_restores_layout_and_keeps_widgets():
    app=QApplication.instance() or QApplication([])
    window=MainWindow();window.show();app.processEvents()
    sheet=window.sheet_editor;preview=window.preview
    previous=window.tabs.currentIndex()
    for panel in ('sheet','preview'):
        window._toggle_panel_expansion(panel);app.processEvents()
        assert window.isFullScreen()
        assert window._exit_expansion.isEnabled()
        assert window.preview_stack.isHidden() == (panel=='sheet')
        assert window.tabs.isHidden() == (panel=='preview')
        button=sheet.expand_button if panel=='sheet' else preview.expand_button
        assert button.text()=='Restore'
        window._exit_expansion.trigger();app.processEvents()
        assert not window.isFullScreen()
        assert not window.tabs.isHidden() and not window.preview_stack.isHidden()
        assert window.tabs.currentIndex()==previous
        assert window.sheet_editor is sheet and window.preview is preview
        assert button.text()=='Expand'
    window.close()
