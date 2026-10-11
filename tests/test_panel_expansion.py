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
        assert window.isMaximized() and not window.isFullScreen()
        assert window._exit_expansion.isEnabled()
        assert window.preview_stack.isHidden() == (panel=='sheet')
        assert window.tabs.isHidden() == (panel=='preview')
        button=sheet.expand_button if panel=='sheet' else preview.expand_button
        assert button.accessibleName().startswith('Restore')
        assert button.text()=='' and not button.icon().isNull()
        window._exit_expansion.trigger();app.processEvents()
        assert not window.isFullScreen()
        assert not window.tabs.isHidden() and not window.preview_stack.isHidden()
        assert window.tabs.currentIndex()==previous
        assert window.sheet_editor is sheet and window.preview is preview
        assert button.accessibleName().startswith('Expand')
    window.close()


def test_expansion_and_row_measurement_keep_scroll_anchor():
    from PySide6.QtCore import Qt, QPoint, QPointF
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtTest import QTest
    app=QApplication.instance() or QApplication([])
    window=MainWindow()
    window.sheet_editor.load([['Role '+str(i),'','A long credit name that wraps in a narrow column'] for i in range(800)])
    window.show();QTest.qWait(180)
    table=window.sheet_editor.table
    table.verticalScrollBar().setValue(3000)
    original_row=table.rowAt(0)
    original_size=window.size()
    QTest.mouseClick(window.sheet_editor.expand_button,Qt.LeftButton)
    QTest.qWait(180)
    assert table.rowAt(0)==original_row
    assert window._expanded_panel=='sheet'
    before=table.verticalScrollBar().value()
    point=QPointF(table.viewport().rect().center())
    wheel=QWheelEvent(point,QPointF(table.viewport().mapToGlobal(point.toPoint())),QPoint(),QPoint(0,-120),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False)
    QApplication.sendEvent(table.viewport(),wheel)
    assert table.verticalScrollBar().value()>before
    assert window._expanded_panel=='sheet'
    row=table.rowAt(0)
    table._remeasure_rows()
    assert table.rowAt(0)==row
    QTest.mouseClick(window.sheet_editor.expand_button,Qt.LeftButton)
    QTest.qWait(180)
    assert table.rowAt(0)==row
    assert window.size()==original_size
    assert window._expanded_panel is None
    window.close()
