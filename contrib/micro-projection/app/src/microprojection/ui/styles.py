"""Visual styling: `dark_palette()` + `STYLESHEET` (QSS) + `BASE_FONT` (Segoe UI 10pt)."""
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


# Stylesheet cleared out -- the previous QSS looked weak. Rebuild from scratch.
# Only the structural sidebar surface is kept so it reads as a full-height panel
# (not a floating card). The app also applies the Fusion dark palette + base
# font (see app.py).
STYLESHEET = f"""
QWidget#sidebar {{
    background-color: {_BG_PANEL};
    border-right: 1px solid {_BORDER};
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
