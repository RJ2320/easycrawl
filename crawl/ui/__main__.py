"""python -m crawl.ui [sheet.csv | project.crawl.json]"""

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon

from PySide6.QtWidgets import QApplication

from .. import project as proj
from . import theme
from .main_window import MainWindow


def selftest() -> int:
    """Print what a packaged build needs to work, for the build to check itself."""
    from .. import __version__, fonts, tools
    print(f"EasyCrawl {__version__}")
    print("ffmpeg: ", tools.ffmpeg() or "MISSING")
    print("ffprobe:", tools.ffprobe() or "MISSING")
    print("fonts:  ", len(fonts.families()), "families")
    return 0 if tools.ffmpeg() and tools.ffprobe() else 1


def main(argv=None) -> int:
    argv = sys.argv if argv is None else argv
    if "--selftest" in argv:
        return selftest()
    if sys.platform == "win32":
        # Give source runs their own taskbar identity instead of Python's icon/group.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("easycrawl.EasyCrawl")
    app = QApplication(argv)
    app.setApplicationName("EasyCrawl")
    app.setOrganizationName("easycrawl")
    app.setWindowIcon(QIcon(str(Path(__file__).with_name("assets") / "icon.png")))
    theme.apply(app)
    project = None
    smoke_test = "--smoke-test" in argv
    path = argv[1] if len(argv) > 1 and not smoke_test else None
    win_path = None
    if path and path.endswith(proj.PROJECT_SUFFIX):
        project = proj.Project.load(path)
        win_path = path
    elif path:
        project = proj.Project(source=path)
    win = MainWindow(project)
    win.project_path = win_path
    win._title()
    win.show()
    if smoke_test:
        QTimer.singleShot(250, win.close)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
