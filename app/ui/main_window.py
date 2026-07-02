"""The application shell: a tabbed canvas in the center (projected image,
captured surface, reconstructed surface), a sidebar docked left, and a console
docked along the bottom, plus the command surface maestro drives."""
from __future__ import annotations

from collections import deque

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow, QTabWidget, QWidget

from logbus import get_logger, success
from version import __version__
from backend import SimulationBackend
from ui.canvas import Canvas
from ui.console import Console
from ui.imaging import gray_to_qimage
from ui.process_runner import ProcessRunner
from ui.sidebar import Sidebar

log = get_logger("ui")

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
        self.sidebar.pipeline_requested.connect(self._on_pipeline)
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
        self._capture_purpose = "single"  # "single" (preview) or "pipeline"

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
        self._project(self.sidebar.selected_surface())

    def _project(self, surface: str) -> None:
        fringe = self.backend.generate_fringe()
        self.canvases["projectedCanvas"].set_image(gray_to_qimage(fringe))
        self._show_tab("projectedCanvas")
        success(log, f"projected {self.backend.n_periods:g}-period fringe")

    def _display_reconstruction(self, surface: str, result) -> None:
        self.canvases["reconstructedCanvas"].set_image(QImage(str(result.height_png)))
        self._show_tab("reconstructedCanvas")
        self._log_metrics(surface, result.metrics)

    def _reconstruct(self, surface: str) -> None:
        """Reconstruct from `surface`'s latest capture stack, inline (~0.4s)."""
        self._status_left.setText(f"Reconstructing {surface}...")
        QApplication.processEvents()  # paint the status before the brief blocking run
        try:
            result = self.backend.reconstruct(surface)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the console
            log.error(f"reconstruct failed: {exc}")
        else:
            self._display_reconstruction(surface, result)
        self._status_left.setText("Ready")

    def _log_metrics(self, surface: str, m: dict) -> None:
        valid_pct = 100.0 * m["valid_pixels"] / m["total_pixels"]
        success(
            log,
            f"reconstructed {surface}: RMSE={m['rmse']:.4f} mm, "
            f"R^2={m['r2']:.4f}, valid={valid_pct:.1f}%",
        )

    # -- capture (async Blender subprocess) -----------------------------------

    def _on_capture(self) -> None:
        """Single capture: one frame of the projected fringe on the surface."""
        try:
            self._start_capture(self.sidebar.selected_surface(), purpose="single",
                                 n_steps=1, subdir="single")
        except Exception as exc:  # noqa: BLE001 - report to console, don't raise into Qt
            log.warning(f"cannot start capture: {exc}")

    def _on_pipeline(self) -> None:
        """Full pipeline: project -> capture (stack) -> reconstruct."""
        surface = self.sidebar.selected_surface()
        self._project(surface)
        try:
            self._start_capture(surface, purpose="pipeline", n_steps=8, subdir="capture")
        except Exception as exc:  # noqa: BLE001 - report to console, don't raise into Qt
            log.warning(f"cannot start pipeline: {exc}")

    def _start_capture(self, surface: str, purpose: str, n_steps: int, subdir: str, **kwargs) -> "object":
        """Kick off a Blender capture of `surface` (raises on bad state)."""
        if self._capture_runner.is_running():
            raise RuntimeError("a capture is already running")
        if not surface:
            raise ValueError("no specimen selected")
        spec = self.backend.capture_command(surface, n_steps=n_steps, subdir=subdir, **kwargs)
        self._capture_spec = spec
        self._capture_surface = surface
        self._capture_purpose = purpose
        self.sidebar.specimen.setCurrentText(surface)  # reflect what's being captured
        self._capture_tail.clear()
        self._set_capture_busy(True)
        plural = "s" if n_steps != 1 else ""
        prefix = "pipeline: capturing" if purpose == "pipeline" else "capturing"
        self._status_left.setText(f"Capturing {surface}...")
        log.info(f"{prefix} {surface}: Blender rendering {n_steps} frame{plural}...")
        self._capture_runner.start(spec.argv, str(spec.cwd))
        return spec

    def _on_capture_line(self, line: str) -> None:
        self._capture_tail.append(line)
        if "[capture_pipeline]" in line:
            log.info(line.split("]", 1)[-1].strip())
        elif line.startswith("Captured "):
            log.info(line)

    def _on_capture_finished(self, exit_code: int) -> None:
        self._set_capture_busy(False)
        self._status_left.setText("Ready")
        if exit_code != 0:
            log.error(f"capture failed (exit {exit_code})")
            for tail in list(self._capture_tail)[-6:]:
                log.error(tail)
            return
        spec = self._capture_spec
        frames = sorted(spec.capture_dir.glob("frame_*.png"))
        if frames:
            self.canvases["capturedCanvas"].set_image(QImage(str(frames[0])))
            self._show_tab("capturedCanvas")
        if self._capture_purpose == "pipeline":
            success(log, f"captured {self._capture_surface}: {spec.n_steps} frames")
            self._reconstruct(self._capture_surface)
        else:
            success(log, f"captured {self._capture_surface}: single frame")

    def _on_capture_failed(self, message: str) -> None:
        self._set_capture_busy(False)
        self._status_left.setText("Ready")
        log.error(f"capture failed: {message}")

    def _set_capture_busy(self, busy: bool) -> None:
        self.sidebar.capture_button.setEnabled(not busy)
        self.sidebar.pipeline_button.setEnabled(not busy)
        if not busy:
            self.sidebar.capture_button.setText("Capture")
            self.sidebar.pipeline_button.setText("Run Pipeline")
        elif self._capture_purpose == "pipeline":
            self.sidebar.pipeline_button.setText("Running...")
        else:
            self.sidebar.capture_button.setText("Capturing...")

    def set_maestro_status(self, text: str) -> None:
        self._status_maestro.setText(f"maestro:  {text}")

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
            "pipeline": self._cmd_pipeline,
            "reconstruct": self._cmd_reconstruct,
        }

    def _cmd_log(self, args: dict):
        message = str(args.get("message", ""))
        level = str(args.get("level", "info"))
        if level == "ok":
            success(log, message)
        elif level == "warn":
            log.warning(message)
        elif level == "error":
            log.error(message)
        else:
            log.info(message)
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
        """Start a single Blender capture (asynchronous): one frame of the
        projected fringe on the surface. Returns once it has started."""
        surface = str(args.get("surface") or self.sidebar.selected_surface())
        kwargs = {}
        if "samples" in args:
            kwargs["samples"] = int(args["samples"])
        self._start_capture(surface, purpose="single", n_steps=1, subdir="single", **kwargs)
        return {"capture": "started", "surface": surface, "frames": 1}

    def _cmd_pipeline(self, args: dict):
        """Start the full pipeline (asynchronous): project -> capture (stack) ->
        reconstruct. Returns once capture starts; reconstruct runs on finish."""
        surface = str(args.get("surface") or self.sidebar.selected_surface())
        kwargs = {}
        if "samples" in args:
            kwargs["samples"] = int(args["samples"])
        self._project(surface)
        spec = self._start_capture(surface, purpose="pipeline", n_steps=8, subdir="capture", **kwargs)
        return {"pipeline": "started", "surface": surface, "n_steps": spec.n_steps}

    def _cmd_reconstruct(self, args: dict):
        surface = str(args.get("surface") or self.sidebar.selected_surface())
        self.sidebar.specimen.setCurrentText(surface)
        result = self.backend.reconstruct(surface)
        self._display_reconstruction(surface, result)
        return {"surface": surface, "metrics": result.metrics}
