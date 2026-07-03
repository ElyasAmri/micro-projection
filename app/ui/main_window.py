"""The application shell: a movable-pane workspace built on native Qt docking.
Control, the three canvas views (projected / captured / reconstructed, tabbed
together), and the Console are each a QDockWidget in a QMainWindow with dock
nesting enabled -- draggable, splittable, tab-mergeable, and floatable, with no
third-party dependency. Layouts persist across restarts (QMainWindow.saveState)
and a Reset Layout action restores the default arrangement.

(This is the native-Qt alternative to the QtAds workspace on `dev`, kept on a
branch for comparison.)"""
from __future__ import annotations

from collections import deque

from PySide6.QtCore import QByteArray, QSettings, Qt
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

# View label -> (canvas objectName, dock objectName), in display order. Tabbed
# together by default; each is an independent dock, so they can be torn apart.
VIEW_PANES = [
    ("Projected Image", "projectedCanvas", "projectedDock"),
    ("Captured Surface", "capturedCanvas", "capturedDock"),
    ("Reconstructed Surface", "reconstructedCanvas", "reconstructedDock"),
]

# Bump when the pane set / dock objectNames change so a saved layout from an
# older shape is ignored instead of restored into a mismatched tree.
LAYOUT_VERSION = 1


class MainWindow(QMainWindow):
    """Top-level window. Hosts the native-docking workspace (Control, three
    canvas views, Console as movable panes), the layout menus, and exposes
    `maestro_commands()`."""

    def __init__(self, backend: SimulationBackend | None = None) -> None:
        super().__init__()
        self.backend = backend or SimulationBackend()
        self.setObjectName("mainWindow")
        self.setWindowTitle("Micro-Projection Control")
        self.resize(1280, 820)
        self._settings = QSettings()

        # Let docks nest, tab-merge, and drag as groups; no fixed central widget
        # (a zero-size placeholder) so the panes own the whole window.
        self.setDockNestingEnabled(True)
        self.setDockOptions(
            QMainWindow.AllowNestedDocks
            | QMainWindow.AllowTabbedDocks
            | QMainWindow.AnimatedDocks
            | QMainWindow.GroupedDragging
        )
        self.setTabPosition(Qt.AllDockWidgetAreas, QTabWidget.North)  # tabs on top
        placeholder = QWidget()
        placeholder.setObjectName("centralPlaceholder")
        placeholder.setFixedSize(0, 0)
        self.setCentralWidget(placeholder)

        self.canvases: dict[str, Canvas] = {}
        self.docks: dict[str, QDockWidget] = {}
        self.view_docks: dict[str, QDockWidget] = {}

        self._build_panes()
        self._build_menus()
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

        # Dock sizing needs real window geometry, which only exists once shown,
        # so it happens in showEvent (below), not here.
        self._sized = False
        self._default_state = None

    # -- construction helpers -------------------------------------------------

    def _dock(self, title: str, name: str, widget: QWidget, area=None) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        dock.setFeatures(
            QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetClosable
        )
        if area is not None:
            self.addDockWidget(area, dock)
        self.docks[name] = dock
        return dock

    def _build_panes(self) -> None:
        """Control as a full-height left rail, the three views tab-merged in the
        main area, Console below the views:  [ Control | views / Console ].

        The console shares a vertical splitter with the views (rather than
        spanning the full bottom), so its height is actually adjustable -- a
        full-width bottom dock over a central-less layout can't be sized down."""
        self.sidebar = Sidebar(self.backend.available_surfaces(), self)
        self.sidebar.project_requested.connect(self._on_project)
        self.sidebar.capture_requested.connect(self._on_capture)
        self.sidebar.pipeline_requested.connect(self._on_pipeline)
        self._dock("Control", "controlDock", self.sidebar, Qt.LeftDockWidgetArea)

        # Build the first view alone in the right area, split the console below it
        # (a clean vertical splitter while the view is un-tabbed), THEN tab the
        # remaining views onto the first -- so they share the top sub-area and the
        # console keeps the bottom. Splitting after tabbing merges into the tabs.
        first_label, first_name, first_dockname = VIEW_PANES[0]
        first_canvas = Canvas(first_name)
        self.canvases[first_name] = first_canvas
        first_dock = self._dock(first_label, first_dockname, first_canvas, Qt.RightDockWidgetArea)
        self.view_docks[first_name] = first_dock

        self.console = Console(self)
        console = self._dock("Console", "consoleDock", self.console)
        self.splitDockWidget(first_dock, console, Qt.Vertical)

        for label, name, dock_name in VIEW_PANES[1:]:
            canvas = Canvas(name)
            self.canvases[name] = canvas
            dock = self._dock(label, dock_name, canvas)
            self.view_docks[name] = dock
            self.tabifyDockWidget(first_dock, dock)  # merge into the top tab group
        first_dock.raise_()  # open on the first view

    # -- layout menu + persistence --------------------------------------------

    def _build_menus(self) -> None:
        bar = self.menuBar()
        view = bar.addMenu("View")
        for dock in self.docks.values():
            view.addAction(dock.toggleViewAction())
        layout = bar.addMenu("Layout")
        layout.addAction("Reset Layout", self.reset_layout)

    def reset_layout(self) -> None:
        """Restore the default pane arrangement captured at first show."""
        if self._default_state is not None:
            self.restoreState(self._default_state)
        self.apply_dock_sizes()

    def _restore_layout(self) -> None:
        """Reapply the last session's layout, unless the schema version changed."""
        try:
            if int(self._settings.value("layout/version", 0)) != LAYOUT_VERSION:
                return
        except (TypeError, ValueError):
            return
        state = self._settings.value("layout/state")
        if state is None:
            return
        if not isinstance(state, QByteArray):
            state = QByteArray(state)
        self.restoreState(state)

    def closeEvent(self, event) -> None:
        """Persist the current layout on the way out."""
        self._settings.setValue("layout/version", LAYOUT_VERSION)
        self._settings.setValue("layout/state", self.saveState())
        super().closeEvent(event)

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

    def showEvent(self, event) -> None:
        """First real geometry arrives here; size the docks, snapshot the default
        layout for Reset, then reapply any persisted layout."""
        super().showEvent(event)
        if self._sized:
            return
        self._sized = True
        self.apply_dock_sizes()
        self._default_state = self.saveState()
        self._restore_layout()

    def apply_dock_sizes(self) -> None:
        """Size the docks from the current window geometry: Control ~260 wide,
        Console ~a quarter of the height. Runs once the window is shown (real
        geometry), so resizeDocks actually takes -- doing it pre-show is why the
        console swallowed the window before."""
        self.resizeDocks([self.docks["controlDock"]], [260], Qt.Horizontal)
        console_h = max(160, self.height() // 4)
        self.resizeDocks([self.docks["consoleDock"]], [console_h], Qt.Vertical)

    # -- behavior -------------------------------------------------------------

    def _show_tab(self, canvas_name: str) -> None:
        """Bring a view pane to the front of its tab group (and un-hide it)."""
        dock = self.view_docks.get(canvas_name)
        if dock is None:
            return
        dock.show()
        dock.raise_()

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
        """Raise a view pane by index or (case-insensitive) label match."""
        key = args.get("tab")
        index = None
        if isinstance(key, int) or (isinstance(key, str) and key.isdigit()):
            index = int(key)
        elif isinstance(key, str):
            wanted = key.lower()
            for i, (label, _name, _dock) in enumerate(VIEW_PANES):
                if wanted in label.lower():
                    index = i
                    break
        if index is None or not (0 <= index < len(VIEW_PANES)):
            raise ValueError(f"no tab matching {key!r}")
        label, name, _dock = VIEW_PANES[index]
        self._show_tab(name)
        return {"tab": label, "index": index}

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
