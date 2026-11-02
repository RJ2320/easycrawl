import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QApplication
from crawl.ui.widgets import framing_guide_rect, PreviewPanel


@pytest.mark.parametrize('ratio',[2.39,1.85,2.00])
@pytest.mark.parametrize('frame',[QRectF(12,20,1920,1080),QRectF(0,0,1080,1920),QRectF(0,0,4096,1716)])
def test_framing_guide_fits_and_is_centered(ratio,frame):
    guide=framing_guide_rect(frame,ratio)
    assert guide.width()/guide.height()==pytest.approx(ratio)
    assert guide.center()==frame.center()
    assert guide.width()<=frame.width()+1e-6
    assert guide.height()<=frame.height()+1e-6


def test_preview_guides_toggle_independently():
    app=QApplication.instance() or QApplication([])
    panel=PreviewPanel()
    assert panel.view.ratio_guides==[]
    panel.aspect_guides[2.39].setChecked(True)
    panel.aspect_guides[1.85].setChecked(True)
    panel.title_safe.setChecked(True)
    assert panel.view.ratio_guides==[2.39,1.85]
    assert panel.view.show_title_safe
    assert not panel.view.show_safe
    panel.aspect_guides[2.39].setChecked(False)
    assert panel.view.ratio_guides==[1.85]
    panel.close()
