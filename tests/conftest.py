"""Keep Qt alive until all test widgets have been cleaned up."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope='session', autouse=True)
def qt_application_lifetime():
    app = QApplication.instance() or QApplication([])
    yield app
    # Test fixtures may retain widget wrappers until interpreter shutdown.
    # Destroy their native objects while the application still exists.
    for widget in app.topLevelWidgets():
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()

    import shiboken6
    shiboken6.delete(app)
