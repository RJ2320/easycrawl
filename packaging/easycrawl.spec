# PyInstaller spec: one self-contained app with ffmpeg inside.
#   python packaging/fetch_ffmpeg.py && python packaging/make_icon.py
#   pyinstaller packaging/easycrawl.spec --noconfirm
import os
import sys
from pathlib import Path
import PySide6

from PyInstaller.utils.hooks import collect_submodules, copy_metadata
from importlib.metadata import PackageNotFoundError

root = os.path.abspath(os.path.join(SPECPATH, ".."))
sys.path.insert(0, root)
from crawl import __version__  # noqa: E402

ffmpeg_dir = os.path.join(SPECPATH, "ffmpeg")
binaries = [(os.path.join(ffmpeg_dir, f), "ffmpeg") for f in os.listdir(ffmpeg_dir)] if os.path.isdir(ffmpeg_dir) else []
# Prefer Qt's own ICU libraries over unrelated tools on the build machine's PATH.
# A same-named ICU from another application can omit the symbols Qt requires.
if sys.platform == "win32":
    qt_dir = Path(PySide6.__file__).resolve().parent
    qt_icu = list(qt_dir.glob("icu*.dll"))
    binaries += [(str(path), ".") for path in qt_icu]
icon = {"darwin": "icon.icns", "win32": "icon.ico"}.get(sys.platform, "icon.png")
icon = os.path.join(SPECPATH, icon) if os.path.exists(os.path.join(SPECPATH, icon)) else None

license_data = [(os.path.join(root, "LICENSE"), "licenses"),
                (os.path.join(SPECPATH, "licenses"), "licenses")]
for dependency in ("Pillow", "numpy", "openpyxl", "fonttools", "certifi", "PySide6",
                   "PySide6_Essentials", "PySide6_Addons", "shiboken6"):
    try:
        license_data += copy_metadata(dependency)
    except PackageNotFoundError:
        pass
python_license = os.path.join(sys.base_prefix, "LICENSE.txt")
if os.path.isfile(python_license):
    license_data.append((python_license, "licenses/python"))

a = Analysis(
    [os.path.join(SPECPATH, "launch.py")],
    pathex=[root],
    binaries=binaries,
    datas=[(os.path.join(root, "examples", "sample_crawl.csv"), "examples"),
           (os.path.join(root, "crawl", "ui", "assets", "icon.png"), "crawl/ui/assets"),
           *license_data],
    hiddenimports=collect_submodules("crawl"),
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts",
              "PySide6.QtDataVisualization", "PySide6.QtPdf", "matplotlib", "scipy"],
    noarchive=False,
)
if sys.platform == "win32" and not qt_icu:
    # Recent Qt wheels use Windows' native ICU. Do not bundle an incompatible
    # same-named library found in other tools on PATH (e.g. Poppler).
    a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() != "icuuc.dll"]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, exclude_binaries=True, name="EasyCrawl", console=os.environ.get("EASYCRAWL_BUILD_CONSOLE") == "1", icon=icon,
          argv_emulation=False)
coll = COLLECT(exe, a.binaries, a.datas, name="EasyCrawl")
if sys.platform == "darwin":
    app = BUNDLE(coll, name="EasyCrawl.app", icon=icon, bundle_identifier="app.easycrawl",
                 info_plist={"CFBundleShortVersionString": __version__, "CFBundleVersion": __version__,
                             "NSHighResolutionCapable": True, "LSMinimumSystemVersion": "12.0",
                             "CFBundleDocumentTypes": [{"CFBundleTypeExtensions": ["json", "csv", "xlsx"],
                                                        "CFBundleTypeRole": "Editor"}]})
