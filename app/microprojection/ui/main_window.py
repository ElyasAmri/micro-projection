"""The application shell: a tabbed canvas in the center (projected image,
captured surface, reconstructed surface), a sidebar docked left, and a console
docked along the bottom, plus the command surface maestro drives."""
from __future__ import annotations

import logging
from collections import deque

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow, QTabWidget, QWidget

from microprojection import __version__
from microprojection.backend import SimulationBackend
from microprojection.ui.canvas import Canvas
from microprojection.ui.console import Console, ConsoleLogHandler
from microprojection.ui.imaging import gray_to_qimage
from microprojection.ui.process_runner import ProcessRunner
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

    def __init__(self, backend: SimulationBackend | None = None) -> None:
        super().__init__()
        self.backend = backend or SimulationBackend()
        self.setObjectName("mainWindow")
        self.setWindowTitle("Micro-Projection Control")
        self.resize(1280, 820)

        self.canvas_tabs = self._build_canvas_tabs()
        self.setCentralWidget(self.canvas_tabs)

        self.sidebar = Sidebar(self.backend.available_surfaces(), self)
        self.sidebar.project_requested.connect(self._on_project)
        self.sidebar.capture_requested.connect(self._on_capture)
        self.sidebar.reconstruct_requested.connect(self._on_reconstruct)
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

        # Blender capture runs as a child process, streamed to the console.
        self._capture_runner = ProcessRunner(self)
        self._capture_runner.line.connect(self._on_capture_line)
        self._capture_runner.finished.connect(self._on_capture_finished)
        self._capture_runner.failed.connect(self._on_capture_failed)
        self._capture_tail: deque[str] = deque(maxlen=25)
        self._capture_spec = None
        self._capture_surface = ""

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

    def _show_tab(self, canvas_name: str) -> None:
        self.canvas_tabs.setCurrentWidget(self.canvases[canvas_name])

    def _on_project(self) -> None:
        fringe = self.backend.generate_fringe()
        self.canvases["projectedCanvas"].set_image(gray_to_qimage(fringe))
        self._show_tab("projectedCanvas")
        self.console.log(f"projected {self.backend.n_periods:g}-period fringe", "ok")

    def _on_reconstruct(self) -> None:
        surface = self.sidebar.selected_surface()
        if not surface:
            self.console.log("no specimen selected (no capture data found)", "warn")
            return
        self._status_left.setText(f"Reconstructing {surface}...")
        QApplication.processEvents()  # paint the status before the (brief) blocking run
        try:
            result = self.backend.reconstruct(surface)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the console
            self.console.log(f"reconstruct failed: {exc}", "error")
            self._status_left.setText("Ready")
            return
        self.canvases["reconstructedCanvas"].set_image(QImage(str(result.height_png)))
        self._show_tab("reconstructedCanvas")
        self._log_metrics(surface, result.metrics)
        self._status_left.setText("Ready")

    def _log_metrics(self, surface: str, m: dict) -> None:
        valid_pct = 100.0 * m["valid_pixels"] / m["total_pixels"]
        self.console.log(
            f"reconstructed {surface}: RMSE={m['rmse']:.4f} mm, "
            f"R^2={m['r2']:.4f}, valid={valid_pct:.1f}%",
            "ok",
        )

    # -- capture (async Blender subprocess) -----------------------------------

    def _start_capture(self, surface: str, **kwargs) -> "object":
        """Kick off a Blender capture of `surface` (raises on bad state)."""
        if self._capture_runner.is_running():
            raise RuntimeError("a capture is already running")
        if not surface:
            raise ValueError("no specimen selected")
        spec = self.backend.capture_command(surface, **kwargs)
        self._capture_spec = spec
        self._capture_surface = surface
        self.sidebar.specimen.setCurrentText(surface)  # reflect what's being captured
        self._capture_tail.clear()
        self._set_capture_busy(True)
        self._status_left.setText(f"Capturing {surface} ({spec.n_steps} frames)...")
        self.console.log(f"capturing {surface}: Blender rendering {spec.n_steps} phase steps...", "info")
        self._capture_runner.start(spec.argv, str(spec.cwd))
        return spec

    def _on_capture(self) -> None:
        try:
            self._start_capture(self.sidebar.selected_surface())
        except Exception as exc:  # noqa: BLE001 - report to console, don't raise into Qt
            self.console.log(f"cannot start capture: {exc}", "warn")

    def _on_capture_line(self, line: str) -> None:
        self._capture_tail.append(line)
        if "[capture_pipeline]" in line:
            self.console.log(line.split("]", 1)[-1].strip(), "info")
        elif line.startswith("Captured "):
            self.console.log(line, "info")

    def _on_capture_finished(self, exit_code: int) -> None:
        self._set_capture_busy(False)
        self._status_left.setText("Ready")
        if exit_code != 0:
            self.console.log(f"capture failed (exit {exit_code})", "error")
            for tail in list(self._capture_tail)[-6:]:
                self.console.log(f"  {tail}", "error")
            return
        spec = self._capture_spec
        self.console.log(f"captured {self._capture_surface}: {spec.n_steps} frames in {spec.capture_dir}", "ok")
        frames = sorted(spec.capture_dir.glob("frame_*.png"))
        if frames:
            self.canvases["capturedCanvas"].set_image(QImage(str(frames[0])))
            self._show_tab("capturedCanvas")

    def _on_capture_failed(self, message: str) -> None:
        self._set_capture_busy(False)
        self._status_left.setText("Ready")
        self.console.log(f"capture failed: {message}", "error")

    def _set_capture_busy(self, busy: bool) -> None:
        self.sidebar.capture_button.setEnabled(not busy)
        self.sidebar.reconstruct_button.setEnabled(not busy)
        self.sidebar.capture_button.setText("Capturing..." if busy else "Capture (Blender)")

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
            "project": self._cmd_project,
            "capture": self._cmd_capture,
            "reconstruct": self._cmd_reconstruct,
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

    def _cmd_project(self, args: dict):
        n_periods = float(args.get("n_periods", self.backend.n_periods))
        phase = float(args.get("phase", 0.0))
        fringe = self.backend.generate_fringe(n_periods=n_periods, phase=phase)
        self.canvases["projectedCanvas"].set_image(gray_to_qimage(fringe))
        self._show_tab("projectedCanvas")
        return {"projected": {"n_periods": n_periods, "phase": phase}}

    def _cmd_capture(self, args: dict):
        """Start a Blender capture (asynchronous). Returns once it has started;
        progress streams to the console and the frame appears when it finishes."""
        surface = str(args.get("surface") or self.sidebar.selected_surface())
        kwargs = {}
        if "samples" in args:
            kwargs["samples"] = int(args["samples"])
        if "n_steps" in args:
            kwargs["n_steps"] = int(args["n_steps"])
        spec = self._start_capture(surface, **kwargs)
        return {"capture": "started", "surface": surface, "n_steps": spec.n_steps}

    def _cmd_reconstruct(self, args: dict):
        surface = str(args.get("surface") or self.sidebar.selected_surface())
        self.sidebar.specimen.setCurrentText(surface)
        result = self.backend.reconstruct(surface)
        self.canvases["reconstructedCanvas"].set_image(QImage(str(result.height_png)))
        self._show_tab("reconstructedCanvas")
        self._log_metrics(surface, result.metrics)
        return {"surface": surface, "metrics": result.metrics}
