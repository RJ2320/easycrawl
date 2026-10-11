"""The app's look: a dark palette, one accent colour, an 8 px grid.

Dark because the tool exists to judge light type on black; a bright panel
beside the preview throws the eye off. Colour is used sparingly:

    ACCENT    selection, focus, the primary action, alignment guides
    ERROR     something must be fixed before export
    WARNING   worth a look

Everything else is a grey. Widgets that draw themselves (the preview, the
sheet's overlays, the timeline) import the constants below rather than
hard-coding colours.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPen, QPixmap

BG = "#16171a"          # window
PANEL = "#1e1f23"       # tab pages, toolbars
RAISED = "#282a30"      # buttons, headers
FIELD = "#111215"       # inputs, table
BORDER = "#33353c"
BORDER_STRONG = "#4b4e58"
TEXT = "#e8e9ec"
MUTED = "#9a9ea8"
FAINT = "#676b76"

ACCENT = "#4c9ffe"
ACCENT_HOVER = "#74b4ff"
ACCENT_DIM = "#1d3657"   # selected rows, pressed states

ERROR = "#f0646a"
WARNING = "#e3aa3d"

SEVERITY = {"error": ERROR, "warning": WARNING, "info": MUTED}

GRID = 8                 # spacing unit
RADIUS = 6


def color(hex_: str, alpha: int = 255) -> QColor:
    c = QColor(hex_)
    c.setAlpha(alpha)
    return c


# --------------------------------------------------------------------------- #
# Small glyphs the stylesheet needs as image files (arrows, check mark)
# --------------------------------------------------------------------------- #

def _glyph(kind: str, colour: str, px: int) -> QPixmap:
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(QPen(QColor(colour), max(1.4, px / 7), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    u = px / 12
    if kind == "down":
        p.drawPolyline([QPointF(3 * u, 4.5 * u), QPointF(6 * u, 7.5 * u), QPointF(9 * u, 4.5 * u)])
    elif kind == "up":
        p.drawPolyline([QPointF(3 * u, 7.5 * u), QPointF(6 * u, 4.5 * u), QPointF(9 * u, 7.5 * u)])
    elif kind == "check":
        p.drawPolyline([QPointF(2.8 * u, 6.2 * u), QPointF(5 * u, 8.4 * u), QPointF(9.2 * u, 3.8 * u)])
    p.end()
    return pm


def _write_glyphs() -> Path:
    """Write the glyph PNGs (1x and @2x) and return their folder."""
    folder = Path(tempfile.mkdtemp(prefix="crawl-ui-"))
    for name, kind, colour in (("down", "down", MUTED), ("up", "up", MUTED), ("check", "check", "#ffffff")):
        _glyph(kind, colour, 12).save(str(folder / f"{name}.png"))
        _glyph(kind, colour, 24).save(str(folder / f"{name}@2x.png"))
    return folder


# --------------------------------------------------------------------------- #

def _palette() -> QPalette:
    pal = QPalette()
    roles = {
        QPalette.Window: BG, QPalette.WindowText: TEXT, QPalette.Base: FIELD, QPalette.AlternateBase: PANEL,
        QPalette.Text: TEXT, QPalette.Button: RAISED, QPalette.ButtonText: TEXT, QPalette.BrightText: "#ffffff",
        QPalette.ToolTipBase: RAISED, QPalette.ToolTipText: TEXT, QPalette.Highlight: ACCENT,
        QPalette.HighlightedText: "#ffffff", QPalette.Link: ACCENT, QPalette.PlaceholderText: FAINT,
        QPalette.Light: BORDER_STRONG, QPalette.Midlight: BORDER, QPalette.Mid: BORDER, QPalette.Dark: "#0c0d0f",
        QPalette.Shadow: "#000000",
    }
    for role, value in roles.items():
        pal.setColor(role, QColor(value))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(FAINT))
    return pal


def stylesheet(glyphs: Path) -> str:
    g = glyphs.as_posix()
    return f"""
* {{ font-size: 13px; }}
QWidget {{ color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QToolTip {{ background: {RAISED}; color: {TEXT}; border: 1px solid {BORDER_STRONG}; padding: 5px 7px; }}

/* ---- header ---- */
#header {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
#title {{ font-size: 14px; font-weight: 600; }}
#subtitle, QLabel[role="caption"] {{ color: {MUTED}; font-size: 12px; }}
QLabel[role="chip"] {{ color: {MUTED}; background: {RAISED}; border-radius: 9px; padding: 2px 9px; font-size: 12px; }}

/* ---- tabs: text with an accent underline ---- */
QTabWidget::pane {{ border: none; border-top: 1px solid {BORDER}; background: {PANEL}; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 9px 14px 8px; margin-right: 2px;
               border: none; border-bottom: 2px solid transparent; font-weight: 500; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}

/* ---- section headers ---- */
QGroupBox {{ border: none; border-top: 1px solid {BORDER}; margin-top: 26px; padding-top: 6px; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 0px; top: 6px;
                    color: {MUTED}; font-size: 11px; font-weight: 600; }}

/* ---- buttons ---- */
QPushButton, QToolButton {{ background: {RAISED}; border: 1px solid {BORDER}; border-radius: {RADIUS}px;
                           padding: 5px 12px; }}
QPushButton:hover, QToolButton:hover {{ border-color: {BORDER_STRONG}; background: #30333a; }}
QPushButton:pressed, QToolButton:pressed, QToolButton:checked {{ background: {ACCENT_DIM}; border-color: {ACCENT}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {FAINT}; background: {PANEL}; border-color: {BORDER}; }}
QPushButton[primary="true"] {{ background: {ACCENT}; border-color: {ACCENT}; color: #06121f; font-weight: 600;
                              padding: 6px 16px; }}
QPushButton[primary="true"]:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton[primary="true"]:disabled {{ background: {ACCENT_DIM}; border-color: {ACCENT_DIM}; color: {MUTED}; }}
QToolButton[flat="true"] {{ background: transparent; border: 1px solid transparent; padding: 4px 8px; }}
QToolButton[flat="true"]:hover {{ background: {RAISED}; border-color: {BORDER}; }}
QToolButton[flat="true"]:checked {{ background: {ACCENT_DIM}; border-color: {ACCENT}; }}
QToolButton::menu-indicator {{ image: url("{g}/down.png"); subcontrol-position: right center; right: 5px; }}
QToolButton[popupMode="2"], QToolButton[menu="true"] {{ padding-right: 20px; }}
QToolButton[chip="error"] {{ color: {ERROR}; }}
QToolButton[chip="warning"] {{ color: {WARNING}; }}

/* ---- inputs ---- */
QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {FIELD}; border: 1px solid {BORDER}; border-radius: {RADIUS}px; padding: 4px 7px;
    selection-background-color: {ACCENT}; selection-color: #ffffff; min-height: 18px; }}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{ border-color: {BORDER_STRONG}; }}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{ color: {FAINT}; background: {PANEL}; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right;
    width: 18px; border: none; border-left: 1px solid {BORDER}; border-top-right-radius: {RADIUS}px; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right;
    width: 18px; border: none; border-left: 1px solid {BORDER}; border-bottom-right-radius: {RADIUS}px; }}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background: {RAISED}; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{g}/up.png"); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{g}/down.png"); width: 10px; height: 10px; }}
QComboBox::drop-down {{ subcontrol-origin: border; subcontrol-position: center right; width: 22px; border: none; }}
QComboBox::down-arrow {{ image: url("{g}/down.png"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {RAISED}; border: 1px solid {BORDER_STRONG};
    selection-background-color: {ACCENT}; selection-color: #ffffff; outline: none; }}

QCheckBox, QRadioButton {{ spacing: 7px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {BORDER_STRONG}; border-radius: 3px; background: {FIELD}; }}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url("{g}/check.png"); }}
QCheckBox::indicator:disabled {{ border-color: {BORDER}; background: {PANEL}; }}
QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {BORDER_STRONG}; border-radius: 8px; background: {FIELD}; }}
QRadioButton::indicator:checked {{ width: 6px; height: 6px; border: 5px solid {ACCENT}; border-radius: 8px; background: #ffffff; }}

/* ---- sheet ---- */
QTableView {{ background: {FIELD}; alternate-background-color: {FIELD}; gridline-color: {BORDER};
    border: 1px solid {BORDER}; border-radius: 0px; selection-background-color: {ACCENT_DIM};
    selection-color: {TEXT}; outline: none; }}
QHeaderView {{ background: {PANEL}; }}
QHeaderView::section {{ background: {PANEL}; color: {MUTED}; border: none; border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER}; padding: 5px 8px; font-size: 12px; font-weight: 500; }}
QHeaderView::section:vertical {{ padding: 0 6px; }}
QHeaderView::section:checked {{ color: {TEXT}; background: {RAISED}; }}
QTableCornerButton::section {{ background: {PANEL}; border: none; border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER}; }}

/* ---- chrome ---- */
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 0; }}
QScrollBar::handle {{ background: {BORDER_STRONG}; border-radius: 3px; margin: 3px; min-height: 28px; min-width: 28px; }}
QScrollBar::handle:hover {{ background: {FAINT}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none;
    width: 0; height: 0; }}
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QMenuBar {{ background: {PANEL}; }}
QMenuBar::item:selected {{ background: {RAISED}; }}
QMenu {{ background: {RAISED}; border: 1px solid {BORDER_STRONG}; padding: 4px; }}
QMenu::item {{ padding: 5px 22px 5px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT}; color: #ffffff; }}
QMenu::item:disabled {{ color: {FAINT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}
QMenu::indicator {{ width: 12px; height: 12px; left: 6px; }}
QMenu::indicator:checked {{ image: url("{g}/check.png"); }}
QStatusBar {{ background: {PANEL}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QStatusBar::item {{ border: none; }}
QProgressBar {{ background: {FIELD}; border: 1px solid {BORDER}; border-radius: {RADIUS}px; text-align: center;
    color: {TEXT}; min-height: 18px; font-size: 12px; }}
QProgressBar::chunk {{ background: {ACCENT_DIM}; border-radius: {RADIUS - 1}px; }}
#inspector {{ background: {RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: 8px; }}
#transport {{ background: {PANEL}; border-top: 1px solid {BORDER}; }}
#toolbar {{ background: {PANEL}; }}
#banner {{ background: {ACCENT_DIM}; border-bottom: 1px solid {BORDER}; }}
#banner QLabel {{ color: {TEXT}; }}
#findingNote {{ color: {TEXT}; background: {RAISED}; border-radius: {RADIUS}px; padding: 5px 9px; }}
#emptyTitle {{ font-size: 16px; font-weight: 600; }}
#cellEditor {{ background: {FIELD}; border: 2px solid {ACCENT}; border-radius: 0px; padding: 0px; }}
"""


def apply(app) -> None:
    """Install the theme on a QApplication."""
    app.setStyle("Fusion")
    app.setPalette(_palette())
    app.setStyleSheet(stylesheet(_write_glyphs()))
