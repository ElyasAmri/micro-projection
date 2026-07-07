"""One dark theme for the whole app: a palette, a Qt stylesheet built from it,
and a monospace font for the console. Kept in one place so every widget reads
from the same source of truth (and so a future light theme is a single swap)."""
from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase

# Instrument-console dark palette. Values are referenced by name in the
# stylesheet below and directly by the canvas painter, so change them here only.
COLORS: dict[str, str] = {
    "window": "#10141a",       # app background, behind the docks
    "viewport": "#0b0e13",     # canvas / darkest surface
    "surface": "#161b22",      # sidebar + console panels
    "surface_alt": "#1b222b",  # dock title bars, group headers
    "border": "#262d38",       # dividers, panel outlines
    "border_soft": "#1e242d",  # faint grid / inner lines
    "text": "#dfe6ee",         # primary text
    "text_dim": "#8b98a5",     # secondary text / captions
    "text_faint": "#5b6673",   # timestamps, watermarks
    "accent": "#4cc2ff",       # primary accent (cyan)
    "accent_dim": "#2b6d8f",   # accent, pressed/borders
    "ok": "#4ade80",
    "warn": "#fbbf24",
    "error": "#f87171",
}

# Level -> console text color, reused by the logging bridge.
LEVEL_COLORS: dict[str, str] = {
    "info": COLORS["accent"],
    "ok": COLORS["ok"],
    "warn": COLORS["warn"],
    "error": COLORS["error"],
}


def monospace_font(point_size: int = 12) -> QFont:
    """A fixed-width font for the console, honoring the platform's best pick."""
    font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    font.setStyleHint(QFont.Monospace)
    font.setPointSize(point_size)
    return font


def build_stylesheet() -> str:
    """The application-wide Qt stylesheet, interpolated from COLORS."""
    c = COLORS
    return f"""
    QWidget {{
        background-color: {c['window']};
        color: {c['text']};
        font-size: 13px;
    }}

    QMainWindow::separator {{
        background: {c['border']};
        width: 1px;
        height: 1px;
    }}

    /* -- Docks: sidebar (left) and console (bottom) ---------------------- */
    QDockWidget {{
        titlebar-close-icon: none;
        titlebar-normal-icon: none;
        color: {c['text_dim']};
        font-size: 11px;
        font-weight: 600;
    }}
    QDockWidget::title {{
        background: {c['surface_alt']};
        padding: 6px 10px;
        border-bottom: 1px solid {c['border']};
        text-transform: uppercase;
        letter-spacing: 1px;
    }}

    /* -- Sidebar -------------------------------------------------------- */
    QWidget#sidebar {{
        background: {c['surface']};
        border-right: 1px solid {c['border']};
    }}
    /* -- Patterns dialog -------------------------------------------------- */
    QListWidget#patternList {{
        background: {c['viewport']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        color: {c['text']};
        outline: none;
        padding: 4px;
    }}
    QListWidget#patternList::item {{
        padding: 5px 8px;
        border-radius: 4px;
    }}
    QListWidget#patternList::item:selected {{
        background: {c['accent_dim']};
        color: {c['text']};
    }}
    QListWidget#patternList::item:hover:!selected {{
        background: {c['surface_alt']};
    }}
    QLabel[role="sectionHeader"] {{
        color: {c['text_faint']};
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        padding: 2px 2px 4px 2px;
    }}
    QLabel#fieldLabel {{
        color: {c['text_dim']};
        font-size: 11px;
        padding-top: 6px;
    }}
    QComboBox {{
        background: {c['surface_alt']};
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 6px 10px;
    }}
    QComboBox:hover {{ border-color: {c['accent_dim']}; }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QComboBox QAbstractItemView {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        color: {c['text']};
        selection-background-color: {c['accent_dim']};
        outline: none;
    }}

    /* -- Canvas tabs ---------------------------------------------------- */
    QTabWidget#canvasTabs::pane {{
        border: 1px solid {c['border']};
        background: {c['viewport']};
        top: -1px;
    }}
    QTabBar {{
        background: {c['window']};
    }}
    QTabBar::tab {{
        background: {c['surface']};
        color: {c['text_dim']};
        min-width: 92px;
        padding: 8px 20px;
        border: 1px solid {c['border']};
        border-bottom: none;
        border-top-left-radius: 5px;
        border-top-right-radius: 5px;
        margin-right: 2px;
        font-size: 12px;
    }}
    QTabBar::tab:selected {{
        background: {c['viewport']};
        color: {c['accent']};
    }}
    QTabBar::tab:hover:!selected {{
        color: {c['text']};
    }}

    /* -- Standalone dock header: a single Unity-style tab ---------------- */
    QWidget#dockTabBar {{
        background: {c['window']};
    }}
    QLabel#dockTab {{
        background: {c['viewport']};
        color: {c['accent']};
        min-width: 92px;
        padding: 8px 20px;
        border: 1px solid {c['border']};
        border-bottom: none;
        border-top-left-radius: 5px;
        border-top-right-radius: 5px;
        font-size: 12px;
    }}

    /* -- Buttons -------------------------------------------------------- */
    QPushButton {{
        background: {c['surface_alt']};
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 7px 12px;
        text-align: left;
    }}
    QPushButton:hover {{
        border-color: {c['accent_dim']};
        color: {c['accent']};
    }}
    QPushButton:pressed {{
        background: {c['viewport']};
    }}
    QPushButton:disabled {{
        color: {c['text_faint']};
        border-color: {c['border_soft']};
    }}
    QPushButton[variant="primary"] {{
        background: {c['accent_dim']};
        border-color: {c['accent']};
        color: {c['text']};
        font-weight: 600;
    }}
    QPushButton[variant="primary"]:hover {{
        background: {c['accent']};
        color: {c['viewport']};
    }}
    QPushButton[role="chip"] {{
        padding: 4px 9px;
        text-align: center;
        font-size: 11px;
    }}

    /* -- Console -------------------------------------------------------- */
    QWidget#consolePanel {{
        background: {c['surface']};
        border-top: 1px solid {c['border']};
    }}
    QPlainTextEdit#console {{
        background: {c['viewport']};
        border: none;
        color: {c['text']};
        selection-background-color: {c['accent_dim']};
    }}
    QLabel#consoleHeader {{
        color: {c['text_faint']};
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1.5px;
    }}

    /* -- Menu bar (Layout / View) --------------------------------------- */
    QMenuBar {{
        background: {c['surface_alt']};
        color: {c['text_dim']};
        border-bottom: 1px solid {c['border']};
    }}
    QMenuBar::item {{
        background: transparent;
        padding: 5px 11px;
    }}
    QMenuBar::item:selected {{ background: {c['surface']}; color: {c['text']}; }}
    QMenuBar::item:pressed {{ background: {c['surface']}; color: {c['accent']}; }}
    QMenu {{
        background: {c['surface']};
        color: {c['text']};
        border: 1px solid {c['border']};
        padding: 4px;
    }}
    QMenu::item {{ padding: 5px 22px 5px 14px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {c['accent_dim']}; color: {c['text']}; }}
    QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}

    /* -- Status bar ----------------------------------------------------- */
    QStatusBar {{
        background: {c['surface_alt']};
        color: {c['text_dim']};
        border-top: 1px solid {c['border']};
    }}
    QStatusBar::item {{ border: none; }}
    QStatusBar QLabel {{ padding: 0 6px; background: transparent; }}
    QLabel#versionLabel {{ color: {c['text_faint']}; font-size: 11px; }}

    /* -- Scrollbars ----------------------------------------------------- */
    QScrollBar:vertical {{
        background: transparent; width: 10px; margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {c['border']}; border-radius: 4px; min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {c['accent_dim']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollBar:horizontal {{
        background: transparent; height: 10px; margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {c['border']}; border-radius: 4px; min-width: 24px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {c['accent_dim']}; }}
    """
