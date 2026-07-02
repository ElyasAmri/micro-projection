"""The application shell: a tabbed canvas in the center (projected image,
captured surface, reconstructed surface), an empty sidebar docked left, and a
console docked along the bottom, plus the command surface maestro drives."""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QDockWidget, QLabel, QMainWindow, QTabWidget, QWidget

from microprojection import __version__
from microprojection.ui.canvas import Canvas
from microprojection.ui.console import Console, ConsoleLogHandler
from microprojection.ui.sidebar import Sidebar

# Tab label -> canvas objectName, in display order.
CANVAS_TABS = [
    ("Projected Image", "projectedCanvas"),
    ("Captured Surface", "capturedCanvas"),
    ("Reconstructed Surface", "reconstructedCanvas"),
]


class MainWindow(QMainWindow):
    """Top-level window. Owns the tabbed canvas, sidebar, and console, and
    exposes `maestro_commands()`."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("mainWindow")
        self.setWindowTitle("Micro-Projection Control")
        self.resize(1280, 820)

        self.canvas_tabs = self._build_canvas_tabs()
        self.setCentralWidget(self.canvas_tabs)

        self.sidebar = Sidebar(self)
        self.sidebar_dock = self._dock("Control", "sidebarDock", self.sidebar,
                                       Qt.LeftDockWidgetArea, Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.console = Console(self)
        self.console_dock = self._dock("Console", "consoleDock", self.console,
                                       Qt.BottomDockWidgetArea, Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)

        # Let the console own the full width of the bottom edge; the sidebar
        # keeps the left edge above it.
        self.setCorner(Qt.BottomLeftCorner, Qt.BottomDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.BottomDockWidgetArea)

        self._build_status_bar()
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.console.clear)
        self.apply_dock_sizes()

    # -- construction helpers -------------------------------------------------

    def _build_canvas_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setObjectName("canvasTabs")
        self.canvases: dict[str, Canvas] = {}
        for label, name in CANVAS_TABS:
            canvas = Canvas(name)
            self.canvases[name] = canvas
            tabs.addTab(canvas, label)
        return tabs

    def _dock(self, title: str, name: str, widget: QWidget, area, allowed) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        dock.setAllowedAreas(allowed)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(area, dock)
        return dock

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)
        # Inset the contents so the mac window's rounded bottom corners don't
        # clip the leftmost/rightmost text.
        bar.setContentsMargins(14, 0, 14, 0)
        self._status_left = QLabel("Ready")
        bar.addWidget(self._status_left)
        self._status_maestro = QLabel("maestro:  offline")
        self._status_maestro.setObjectName("maestroStatus")
        bar.addPermanentWidget(self._status_maestro)
        # Version pinned to the far bottom-right corner.
        version = QLabel(f"v{__version__}")
        version.setObjectName("versionLabel")
        bar.addPermanentWidget(version)

    def apply_dock_sizes(self) -> None:
        """Give the docks sensible starting extents (must run after they exist,
        and is cheap to re-run e.g. right before an offscreen screenshot)."""
        self.resizeDocks([self.sidebar_dock], [260], Qt.Horizontal)
        self.resizeDocks([self.console_dock], [200], Qt.Vertical)

    # -- behavior -------------------------------------------------------------

    def set_maestro_status(self, text: str) -> None:
        self._status_maestro.setText(f"maestro:  {text}")

    def install_log_bridge(self) -> logging.Handler:
        """Mirror the maestro connector's log records into the console."""
        handler = ConsoleLogHandler(self.console)
        handler.setFormatter(logging.Formatter("maestro: %(message)s"))
        maestro_logger = logging.getLogger("microprojection.maestro")
        maestro_logger.setLevel(logging.INFO)
        maestro_logger.addHandler(handler)
        return handler

    # -- maestro command surface ---------------------------------------------

    def maestro_commands(self) -> dict:
        """Named commands exposed to the agent via the `qt` tool's `invoke`.
        Each takes an args dict and returns something JSON-serializable."""
        return {
            "log": self._cmd_log,
            "clear_console": self._cmd_clear_console,
            "select_tab": self._cmd_select_tab,
            "set_status": self._cmd_set_status,
        }

    def _cmd_log(self, args: dict):
        message = str(args.get("message", ""))
        level = str(args.get("level", "info"))
        self.console.log(message, level)
        return {"logged": message}

    def _cmd_clear_console(self, _args: dict):
        self.console.clear()
        return {"cleared": True}

    def _cmd_select_tab(self, args: dict):
        """Switch canvas tab by index or (case-insensitive) label match."""
        key = args.get("tab")
        tabs = self.canvas_tabs
        index = None
        if isinstance(key, int) or (isinstance(key, str) and key.isdigit()):
            index = int(key)
        elif isinstance(key, str):
            wanted = key.lower()
            for i in range(tabs.count()):
                if wanted in tabs.tabText(i).lower():
                    index = i
                    break
        if index is None or not (0 <= index < tabs.count()):
            raise ValueError(f"no tab matching {key!r}")
        tabs.setCurrentIndex(index)
        return {"tab": tabs.tabText(index), "index": index}

    def _cmd_set_status(self, args: dict):
        text = str(args.get("text", ""))
        self._status_left.setText(text)
        return {"status": text}
