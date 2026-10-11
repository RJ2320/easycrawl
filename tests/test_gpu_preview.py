import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from crawl.ui import widgets


def test_gpu_setting_off_uses_cpu():
    app = QApplication.instance() or QApplication([])
    with patch.object(widgets.QSettings, "value", return_value=False):
        view = widgets.create_frame_view()
    assert type(view) is widgets.FrameView
    view.close()


def test_gpu_context_failure_falls_back_to_cpu():
    app = QApplication.instance() or QApplication([])
    with patch.object(widgets.QSettings, "value", return_value=True), \
         patch.object(widgets.QApplication, "platformName", return_value="windows"), \
         patch.object(widgets, "QOpenGLContext") as context, \
         patch.object(widgets, "QOffscreenSurface"):
        context.return_value.create.return_value = False
        view = widgets.create_frame_view()
    assert type(view) is widgets.FrameView
    view.close()
