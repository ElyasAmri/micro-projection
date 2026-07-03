"""The application shell: a workspace of movable, dockable panes (Unity-style)
driven by the Qt Advanced Docking System. The three canvas views (projected
image, captured surface, reconstructed surface), the Control pane, and the
Console are each their own dock widget -- draggable, splittable, tab-mergeable,
and floatable -- plus the command surface maestro drives.

Layouts persist across restarts and can be saved as named perspectives; a
"Reset Layout" action restores the default arrangement."""
from __future__ import annotations

from collections import deque

import PySide6QtAds as ads
from PySide6.QtCore import QByteArray, QSettings, Qt
from PySide6.QtGui import QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QInputDialog, QLabel, QMainWindow, QWidget

from logbus import get_logger, success
from version import __version__
from backend import SimulationBackend
from ui.canvas import Canvas
from ui.console import Console
from ui.imaging import gray_to_qimage
from ui.process_runner import ProcessRunner
from ui.sidebar import Sidebar
from ui.styles import qtads_stylesheet

log = get_logger("ui")

# View label -> (canvas objectName, dock objectName), in display order. These
# three panes are tab-merged into one area by default; each is independently
# dockable, so they can be pulled apart for side-by-side comparison.
VIEW_PANES = [
    ("Projected Image", "projectedCanvas", "projectedDock"),
    ("Captured Surface", "capturedCanvas", "capturedDock"),
    ("Reconstructed Surface", "reconstructedCanvas", "reconstructedDock"),
]

# Bump when the pane set / dock objectNames change so a saved layout from an
# older shape is ignored instead of restored into a mismatched tree.
LAYOUT_VERSION = 1
DEFAULT_PERSPECTIVE = "Default"


class MainWindow(QMainWindow):
    """Top-level window. Hosts the QtAds dock manager (Control, three canvas
    views, and Console as movable panes), the layout menus, and exposes
    `maestro_commands()`."""

    def __init__(self, backend: SimulationBackend | None = None) -> None:
        super().__init__()
        self.backend = backend or SimulationBackend()
        self.setObjectName("mainWindow")
        self.setWindowTitle("Micro-Projection Control")
        self.resize(1280, 820)
        self._settings = QSettings()

        # The dock manager is the central widget; every pane is a CDockWidget.
        self._configure_dock_flags()
        self.dock_manager = ads.CDockManager(self)
        self.dock_manager.setStyleSheet(qtads_stylesheet())
        self.setCentralWidget(self.dock_manager)

        self.canvases: dict[str, Canvas] = {}
        self.docks: dict[str, ads.CDockWidget] = {}       # dock objectName -> dock
        self.view_docks: dict[str, ads.CDockWidget] = {}  # canvas name -> dock

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

        # Load any user-saved perspectives first (this replaces the in-memory
        # set), THEN snapshot the just-built arrangement as "Default" so Reset
        # Layout always restores the current code's default, not a stale copy.
        # Finally restore the last session's layout if its schema still matches.
        self.dock_manager.loadPerspectives(self._settings)
        self.dock_manager.addPerspective(DEFAULT_PERSPECTIVE)
        self._rebuild_layout_menu()
        self.apply_dock_sizes()
        self._restore_layout()

    # -- construction helpers -------------------------------------------------

    @staticmethod
    def _configure_dock_flags() -> None:
        """Global QtAds behavior. Must be set before the manager is created."""
        cm = ads.CDockManager
        f = cm.eConfigFlag
        cm.setConfigFlag(f.OpaqueSplitterResize, True)      # live resize while dragging
        cm.setConfigFlag(f.FocusHighlighting, True)         # accent the focused pane
        cm.setConfigFlag(f.EqualSplitOnInsertion, True)     # even splits when tearing off
        cm.setConfigFlag(f.AllTabsHaveCloseButton, False)   # close via the area button, Unity-style
        cm.setConfigFlag(f.ActiveTabHasCloseButton, False)  # ...including the active tab
        cm.setConfigFlag(f.DisableTabTextEliding, True)     # tabs size to their full label
        cm.setConfigFlag(f.DockAreaHasCloseButton, True)
        cm.setConfigFlag(f.DockAreaHasUndockButton, True)
        cm.setConfigFlag(f.DockAreaHasTabsMenuButton, True)
        cm.setConfigFlag(f.MiddleMouseButtonClosesTab, True)
        cm.setConfigFlag(f.FloatingContainerHasWidgetTitle, True)

    def _make_dock(self, title: str, object_name: str, widget: QWidget) -> "ads.CDockWidget":
        dock = ads.CDockWidget(self.dock_manager, title)
        dock.setObjectName(object_name)
        dock.setWidget(widget)
        self.docks[object_name] = dock
        return dock

    def _build_panes(self) -> None:
        """Create the panes and their default arrangement. QtAds builds outward
        from the center, so add the views first, then Control to their left, then
        Console across the bottom:  [ Control | views ] / [ Console ]."""
        # The three views, tab-merged into one central area.
        center_area = None
        for label, name, dock_name in VIEW_PANES:
            canvas = Canvas(name)
            self.canvases[name] = canvas
            dock = self._make_dock(label, dock_name, canvas)
            self.view_docks[name] = dock
            if center_area is None:
                center_area = self.dock_manager.addDockWidget(ads.CenterDockWidgetArea, dock)
            else:
                self.dock_manager.addDockWidget(ads.CenterDockWidgetArea, dock, center_area)
        self._center_area = center_area

        # Control pane, docked to the left of the views.
        self.sidebar = Sidebar(self.backend.available_surfaces(), self)
        self.sidebar.project_requested.connect(self._on_project)
        self.sidebar.capture_requested.connect(self._on_capture)
        self.sidebar.pipeline_requested.connect(self._on_pipeline)
        control = self._make_dock("Control", "controlDock", self.sidebar)
        self.dock_manager.addDockWidget(ads.LeftDockWidgetArea, control)

        # Console spanning the full width along the bottom.
        self.console = Console(self)
        console = self._make_dock("Console", "consoleDock", self.console)
        self.dock_manager.addDockWidget(ads.BottomDockWidgetArea, console)

        # Open on the first view (Projected), not whichever was added last.
        self._show_tab(VIEW_PANES[0][1])

    # -- layout menu, perspectives, persistence -------------------------------

    def _build_menus(self) -> None:
        bar = self.menuBar()
        view = bar.addMenu("View")
        for dock in self.docks.values():
            view.addAction(dock.toggleViewAction())
        self._layout_menu = bar.addMenu("Layout")

    def _rebuild_layout_menu(self) -> None:
        """(Re)populate the Layout menu: fixed actions plus one entry per saved
        perspective (Unity's Layouts dropdown)."""
        m = self._layout_menu
        m.clear()
        m.addAction("Reset Layout", self.reset_layout)
        m.addAction("Save Layout As...", self._save_layout_as)
        names = [n for n in self.dock_manager.perspectiveNames() if n != DEFAULT_PERSPECTIVE]
        if names:
            m.addSeparator()
            for name in names:
                m.addAction(name, lambda checked=False, n=name: self.dock_manager.openPerspective(n))

    def reset_layout(self) -> None:
        """Restore the default pane arrangement."""
        self.dock_manager.openPerspective(DEFAULT_PERSPECTIVE)
        self.apply_dock_sizes()

    def _save_layout_as(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Layout", "Layout name:")
        name = name.strip()
        if not (ok and name) or name == DEFAULT_PERSPECTIVE:
            return
        self.dock_manager.addPerspective(name)
        self.dock_manager.savePerspectives(self._settings)
        self._rebuild_layout_menu()
        success(log, f"saved layout {name!r}")

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
        self.dock_manager.restoreState(state)

    def closeEvent(self, event) -> None:
        """Persist the current layout and saved perspectives on the way out."""
        self._settings.setValue("layout/version", LAYOUT_VERSION)
        self._settings.setValue("layout/state", self.dock_manager.saveState())
        self.dock_manager.savePerspectives(self._settings)
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

    def apply_dock_sizes(self) -> None:
        """Nudge the default split proportions (Control ~260px, Console ~200px).
        Best-effort: QtAds otherwise distributes space evenly, and a restored
        layout supersedes this. Cheap to re-run (e.g. before an offscreen grab)."""
        try:
            width, height = max(self.width(), 800), max(self.height(), 600)
            control_area = self.docks["controlDock"].dockAreaWidget()
            console_area = self.docks["consoleDock"].dockAreaWidget()
            if control_area is not None:
                self.dock_manager.setSplitterSizes(control_area, [260, width - 260])
            if console_area is not None:
                self.dock_manager.setSplitterSizes(console_area, [height - 200, 200])
        except Exception:  # noqa: BLE001 - sizing is cosmetic; never block startup
            pass

    # -- behavior -------------------------------------------------------------

    def _show_tab(self, canvas_name: str) -> None:
        """Bring a view pane to the front: restore it if closed, make it the
        current tab in its dock area, and raise its window if floated."""
        dock = self.view_docks.get(canvas_name)
        if dock is None:
            return
        dock.toggleView(True)
        area = dock.dockAreaWidget()
        if area is not None:
            area.setCurrentDockWidget(dock)
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
