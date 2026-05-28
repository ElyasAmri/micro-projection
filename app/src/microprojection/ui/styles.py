"""Application-wide visual styling for the MicroProjection app.

Exports:
- `dark_palette()`  -  Fusion-compatible QPalette tuned for the dark theme.
- `STYLESHEET`      -  Qt stylesheet (QSS) layered on top of the palette: tab,
                       group, button, progress-bar, log, menu, status-bar,
                       splitter, scrollbar, tooltip rules.
- `BASE_FONT`       -  application-wide font (Segoe UI 10pt).

All three are applied to `QApplication` in `microprojection.app.main`.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette

# Design tokens
_BG_BASE = "#0f1216"
_BG_PANEL = "#181c23"
_BG_RAISED = "#232934"
_BG_RAISED_HOVER = "#2c3441"
_BG_INPUT = "#0f1216"
_BORDER = "#2a3140"
_BORDER_HOVER = "#3a4256"
_FG_PRIMARY = "#e6eaf2"
_FG_MUTED = "#9aa3b6"
_FG_DISABLED = "#5c6478"
_ACCENT = "#4a9eff"
_ACCENT_DIM = "#2f7ed0"


STYLESHEET = f"""
* {{
    color: {_FG_PRIMARY};
}}

/* --- Top-level window --- */
QMainWindow {{
    background-color: {_BG_BASE};
}}

/* --- Tabs --- */
QTabWidget::pane {{
    border: 1px solid {_BORDER};
    background-color: {_BG_PANEL};
    border-radius: 4px;
    top: -1px;
}}
QTabBar::tab {{
    background-color: {_BG_PANEL};
    color: {_FG_MUTED};
    padding: 8px 18px;
    border: 1px solid {_BORDER};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
    font-weight: 500;
}}
QTabBar::tab:selected {{
    background-color: {_BG_RAISED};
    color: {_FG_PRIMARY};
    border-bottom: 2px solid {_ACCENT};
}}
QTabBar::tab:hover:!selected {{
    background-color: {_BG_RAISED_HOVER};
    color: {_FG_PRIMARY};
}}

/* --- Group boxes --- */
QGroupBox {{
    background-color: {_BG_PANEL};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    margin-top: 16px;
    padding: 14px 12px 12px 12px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 8px;
    color: {_ACCENT};
    background-color: {_BG_BASE};
    border-radius: 3px;
}}

/* --- Buttons --- */
QPushButton {{
    background-color: {_BG_RAISED};
    color: {_FG_PRIMARY};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    padding: 7px 16px;
    font-weight: 500;
    min-height: 18px;
}}
QPushButton:hover {{
    background-color: {_BG_RAISED_HOVER};
    border-color: {_BORDER_HOVER};
}}
QPushButton:focus {{
    border-color: {_ACCENT};
    outline: none;
}}
QPushButton:pressed {{
    background-color: {_BG_PANEL};
}}
QPushButton:disabled {{
    color: {_FG_DISABLED};
    background-color: {_BG_PANEL};
    border-color: {_BORDER};
}}

/* --- Labels / form rows --- */
QLabel {{
    color: {_FG_PRIMARY};
    padding: 1px 0;
}}

/* --- Progress bar --- */
QProgressBar {{
    background-color: {_BG_INPUT};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    height: 10px;
    text-align: center;
    color: {_FG_MUTED};
}}
QProgressBar::chunk {{
    background-color: {_ACCENT};
    border-radius: 3px;
}}

/* --- Log / text edits --- */
QTextEdit, QPlainTextEdit {{
    background-color: {_BG_INPUT};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    color: #cdd3df;
    font-family: "Consolas", "Cascadia Mono", "Menlo", monospace;
    padding: 4px;
}}

/* --- Line edits / spin boxes / combos --- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {_BG_INPUT};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: {_ACCENT_DIM};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {_ACCENT};
}}
QComboBox QAbstractItemView {{
    background-color: {_BG_PANEL};
    border: 1px solid {_BORDER};
    selection-background-color: {_BG_RAISED_HOVER};
}}

/* --- Menu bar / menus --- */
QMenuBar {{
    background-color: {_BG_PANEL};
    color: {_FG_PRIMARY};
    padding: 2px;
}}
QMenuBar::item {{
    padding: 6px 10px;
    background: transparent;
    border-radius: 3px;
}}
QMenuBar::item:selected {{
    background-color: {_BG_RAISED_HOVER};
}}
QMenu {{
    background-color: {_BG_PANEL};
    color: {_FG_PRIMARY};
    border: 1px solid {_BORDER};
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 18px;
    border-radius: 3px;
}}
QMenu::item:selected {{
    background-color: {_BG_RAISED_HOVER};
}}
QMenu::separator {{
    height: 1px;
    background-color: {_BORDER};
    margin: 4px 8px;
}}

/* --- Status bar --- */
QStatusBar {{
    background-color: {_BG_BASE};
    color: {_FG_MUTED};
    border-top: 1px solid {_BORDER};
}}
QStatusBar QLabel {{
    color: {_FG_MUTED};
    padding: 0 8px;
}}

/* --- Splitters --- */
QSplitter::handle {{
    background-color: {_BORDER};
}}
QSplitter::handle:horizontal {{
    width: 1px;
}}
QSplitter::handle:vertical {{
    height: 1px;
}}

/* --- Scroll bars (minimal) --- */
QScrollBar:vertical, QScrollBar:horizontal {{
    background-color: {_BG_PANEL};
    border: none;
}}
QScrollBar:vertical {{
    width: 10px;
}}
QScrollBar:horizontal {{
    height: 10px;
}}
QScrollBar::handle {{
    background-color: #2f3645;
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}}
QScrollBar::handle:hover {{
    background-color: {_BORDER_HOVER};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0; height: 0;
    background: transparent;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* --- Tooltips --- */
QToolTip {{
    background-color: {_BG_PANEL};
    color: {_FG_PRIMARY};
    border: 1px solid {_BORDER};
    border-radius: 3px;
    padding: 4px 8px;
}}
"""


# ---------------------------------------------------------------------------
# Palette + font
# ---------------------------------------------------------------------------

BASE_FONT = QFont("Segoe UI", 10)


def dark_palette() -> QPalette:
    """Fusion-compatible dark QPalette underlying the QSS above."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(208, 208, 208))
    palette.setColor(QPalette.ColorRole.Base, QColor(22, 22, 22))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(35, 35, 35))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(40, 40, 40))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(208, 208, 208))
    palette.setColor(QPalette.ColorRole.Text, QColor(208, 208, 208))
    palette.setColor(QPalette.ColorRole.Button, QColor(40, 40, 40))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(208, 208, 208))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Link, QColor(86, 156, 214))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(46, 100, 160))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(230, 230, 230))
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(100, 100, 100)
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(100, 100, 100)
    )
    return palette
