"""The application shell: a movable-pane workspace built on native Qt docking.
Control, the three canvas views (projected / captured / reconstructed, tabbed
together), and the Console are each a QDockWidget in a QMainWindow with dock
nesting enabled -- draggable, splittable, tab-mergeable, and floatable, with no
third-party dependency. Layouts persist across restarts (QMainWindow.saveState)
and a Reset Layout action restores the default arrangement."""
from __future__ import annotations

from collections import deque
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings, Qt, QTimer
from PySide6.QtGui import QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QTabBar,
    QTabWidget,
    QWidget,
)

from logbus import get_logger, success
from version import __version__
from backend import Backend, SimulationBackend
from ui.canvas import Canvas, OrbitCanvas
from ui.console import Console
from ui.imaging import gray_to_qimage
from ui.process_runner import ProcessRunner
from ui.sidebar import Sidebar

log = get_logger("ui")

# View label -> (canvas objectName, dock objectName), in display order. Tabbed
# together by default; each is an independent dock, so they can be torn apart.
VIEW_PANES = [
    ("Projected", "projectedCanvas", "projectedDock"),
    ("Captured", "capturedCanvas", "capturedDock"),
    ("Reconstructed", "reconstructedCanvas", "reconstructedDock"),
    ("Noise", "noiseCanvas", "noiseDock"),
    ("Roughness", "roughnessCanvas", "roughnessDock"),
    ("Rig", "rigCanvas", "rigDock"),
]

# Bump when the pane set / dock objectNames change (or the default sizing does)
# so a saved layout from an older shape is ignored instead of restored into a
# mismatched tree. v2: control width is sized by naming both sides of the split.
# v3: added the Noise view. v4: added the Roughness view. v5: added the Rig view.
LAYOUT_VERSION = 5


class _DockTitleTab(QWidget):
    """The title bar for a dock that stands alone: a single tab chip, so a lone
    pane reads as a tab (Unity-style) instead of a full-width title bar. It is
    transparent to the mouse, so dragging anywhere on it moves / re-docks the
    pane just like a native title bar (and double-click still floats it)."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("dockTabBar")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        chip = QLabel(title)
        chip.setObjectName("dockTab")
        chip.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(chip, 0, Qt.AlignLeft | Qt.AlignBottom)
        layout.addStretch(1)


class MainWindow(QMainWindow):
    """Top-level window. Hosts the native-docking workspace (Control, three
    canvas views, Console as movable panes), the layout menus, and exposes
    `maestro_commands()`."""

    def __init__(self, backend: Backend | None = None) -> None:
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

        # Capture runs asynchronously (Blender subprocess in sim, project+grab
        # worker on hardware); the backend supplies the controller, but both
        # report through the same line/finished/failed signals.
        self._capture_runner = self.backend.new_capture_controller(self)
        self._capture_runner.line.connect(self._on_capture_line)
        self._capture_runner.finished.connect(self._on_capture_finished)
        self._capture_runner.failed.connect(self._on_capture_failed)
        self._capture_tail: deque[str] = deque(maxlen=25)
        self._capture_surface = ""
        self._capture_purpose = "single"  # "single" / "pipeline" / "pipeline_mf"
        # Multi-frequency ("pipeline_mf") ladder sequencing state: the rungs to
        # capture, the current index, and the per-rung dirs collected so far.
        self._ladder: list[float] = []
        self._ladder_i = 0
        self._ladder_dirs: list = []
        self._ladder_n_steps = 8
        self._ladder_kwargs: dict = {}

        # The rig-overview render is its own Blender run (independent of the
        # capture runner, so it never gates or is gated by a capture).
        self._rig_runner = ProcessRunner(self)
        self._rig_runner.line.connect(self._on_rig_line)
        self._rig_runner.finished.connect(self._on_rig_finished)
        self._rig_runner.failed.connect(self._on_rig_failed)
        self._rig_tail: deque[str] = deque(maxlen=25)
        # Orbit state for the Rig view (degrees / meters; matches the script's
        # default framing). Dragging updates it, then the debounce timer fires
        # one fast re-render; input landing mid-render sets the pending flag so
        # exactly one more render (with the latest state) follows.
        self._rig_view = {"azimuth": 49.2, "elevation": 14.0, "distance": 1.55}
        # For the canvas HUD: the view of the image on screen, and of the
        # render in flight (becomes displayed when it lands). The startup
        # image's true view is unknown (older session) -- assume the default.
        self._rig_view_displayed = dict(self._rig_view)
        self._rig_view_inflight: dict | None = None
        self._rig_render_pending = False
        self._rig_orbit_timer = QTimer(self)
        self._rig_orbit_timer.setSingleShot(True)
        self._rig_orbit_timer.setInterval(200)
        self._rig_orbit_timer.timeout.connect(self._request_rig_render)
        self._load_rig_preview()  # show the last render, if one exists

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
        # Moving/re-tabbing/floating a dock rebuilds its tab bar and changes
        # whether it stands alone; refresh tab + title-bar chrome on any change.
        dock.dockLocationChanged.connect(self._refresh_dock_chrome)
        dock.topLevelChanged.connect(self._refresh_dock_chrome)
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
        self.sidebar = Sidebar(
            self.backend.available_surfaces(),
            header=getattr(self.backend, "kind_label", "Backend"),
            parent=self,
        )
        self.sidebar.project_requested.connect(self._on_project)
        self.sidebar.capture_requested.connect(self._on_capture)
        self.sidebar.pipeline_requested.connect(self._on_pipeline)
        self.sidebar.multifreq_requested.connect(self._on_pipeline_multifreq)
        self.sidebar.noise_requested.connect(self._on_estimate_noise)
        self.sidebar.rig_requested.connect(self._on_render_rig)
        self._dock("Control", "controlDock", self.sidebar, Qt.LeftDockWidgetArea)

        # Build the first view alone in the right area, split the console below it
        # (a clean vertical splitter while the view is un-tabbed), THEN tab the
        # remaining views onto the first -- so they share the top sub-area and the
        # console keeps the bottom. Splitting after tabbing merges into the tabs.
        first_label, first_name, first_dockname = VIEW_PANES[0]
        first_canvas = self._make_canvas(first_name)
        self.canvases[first_name] = first_canvas
        first_dock = self._dock(first_label, first_dockname, first_canvas, Qt.RightDockWidgetArea)
        self.view_docks[first_name] = first_dock

        self.console = Console(self)
        console = self._dock("Console", "consoleDock", self.console)
        self.splitDockWidget(first_dock, console, Qt.Vertical)

        for label, name, dock_name in VIEW_PANES[1:]:
            canvas = self._make_canvas(name)
            self.canvases[name] = canvas
            dock = self._dock(label, dock_name, canvas)
            self.view_docks[name] = dock
            self.tabifyDockWidget(first_dock, dock)  # merge into the top tab group
        first_dock.raise_()  # open on the first view
        # Title bars are managed by _sync_title_bars: a tab-merged dock gets an
        # empty one (the shared tab bar labels it); a standalone dock gets a
        # single-tab header -- so every pane always reads as a tab.

    def _make_canvas(self, name: str) -> Canvas:
        """One view canvas; the Rig view gets the orbitable variant, wired to
        the debounced re-render."""
        if name != "rigCanvas":
            return Canvas(name)
        canvas = OrbitCanvas(name)
        canvas.orbited.connect(self._on_rig_orbit)
        canvas.zoomed.connect(self._on_rig_zoom)
        canvas.released.connect(self._request_rig_render)
        return canvas

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
        self._refresh_dock_chrome()

    def _restore_layout(self) -> bool:
        """Reapply the last session's layout unless the schema version changed;
        return True if a layout was actually restored."""
        try:
            if int(self._settings.value("layout/version", 0)) != LAYOUT_VERSION:
                return False
        except (TypeError, ValueError):
            return False
        state = self._settings.value("layout/state")
        if state is None:
            return False
        if not isinstance(state, QByteArray):
            state = QByteArray(state)
        return bool(self.restoreState(state))

    def closeEvent(self, event) -> None:
        """Persist the current layout on the way out, and let the backend
        release any hardware (e.g. close the projector window)."""
        self._settings.setValue("layout/version", LAYOUT_VERSION)
        self._settings.setValue("layout/state", self.saveState())
        shutdown = getattr(self.backend, "shutdown", None)
        if callable(shutdown):
            shutdown()
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
        """First show: snapshot the default arrangement for Reset, then bring the
        layout up on the next tick. Both restoreState and resizeDocks are
        silently dropped if issued during this first show (before the window
        reaches its final, maximized geometry), so the actual layout work is
        deferred to _init_layout; Reset works synchronously only because by then
        the window has already settled."""
        super().showEvent(event)
        if self._sized:
            return
        self._sized = True
        self._default_state = self.saveState()
        QTimer.singleShot(0, self._init_layout)

    def _init_layout(self) -> None:
        """Reapply the persisted layout, or size to defaults on a first-ever
        launch. Runs once the window has its final geometry (see showEvent)."""
        if not self._restore_layout():
            self.apply_dock_sizes()
        self._apply_dock_chrome()

    def _apply_dock_chrome(self) -> None:
        """Keep tab bars and title bars consistent after any rearrangement."""
        self._show_tabs_in_full()
        self._sync_title_bars()

    def _refresh_dock_chrome(self, *_) -> None:
        """Deferred so the just-rebuilt tab/title bars exist before we restyle."""
        QTimer.singleShot(0, self._apply_dock_chrome)

    def _show_tabs_in_full(self) -> None:
        """Stop the dock tab bars from eliding tab text -- Qt defaults to
        ElideRight even with room to spare, which clipped the single-word labels
        ("Projected" -> "Project..."). Also give the bar its natural width and
        drop the scroll buttons so every tab renders full."""
        for tab_bar in self.findChildren(QTabBar):
            tab_bar.setElideMode(Qt.ElideNone)
            tab_bar.setExpanding(False)
            tab_bar.setUsesScrollButtons(False)

    def _sync_title_bars(self) -> None:
        """Every pane reads as a tab (Unity-style). Qt only draws a real tab bar
        for a tab-merged group, so a dock that stands alone (or floats) gets a
        one-tab header (`_DockTitleTab`) in place of a full-width title bar, while
        a tab-merged dock gets an empty title bar so only the shared tab bar
        shows. The single-tab header doubles as the drag handle, so a torn-out
        pane can always be moved or re-docked."""
        for dock in self.docks.values():
            merged = bool(self.tabifiedDockWidgets(dock)) and not dock.isFloating()
            want = "empty" if merged else "tab"
            if getattr(dock, "_tb_kind", None) == want:
                continue  # already in the right state; don't churn the widget
            dock._tb_kind = want
            if want == "empty":
                dock.setTitleBarWidget(QWidget())
            else:
                dock.setTitleBarWidget(_DockTitleTab(dock.windowTitle()))

    def apply_dock_sizes(self) -> None:
        """Size the docks from the current window geometry: Control ~260 wide,
        Console ~a quarter of the height. Runs once the window is shown (real
        geometry), so resizeDocks actually takes -- doing it pre-show is why the
        console swallowed the window before.

        Control lives in the Left area and the views/console in the Right column;
        resizeDocks on the control dock ALONE is ignored across that division (Qt
        leaves it at ~half the window), so name both sides of the split and give
        the right column the remaining width."""
        control = self.docks["controlDock"]
        right = next(iter(self.view_docks.values()))
        self.resizeDocks([control, right], [260, max(320, self.width() - 260)], Qt.Horizontal)
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
        self.backend.project(fringe)  # push to the physical projector (no-op in sim)
        self._show_tab("projectedCanvas")
        success(log, f"projected {self.backend.n_periods:g}-period fringe")

    # -- rig overview (annotated Blender render of the scene geometry) --------

    def _rig_preview_path(self) -> Path | None:
        getter = getattr(self.backend, "rig_preview_path", None)
        return Path(getter()) if callable(getter) else None

    def _load_rig_preview(self) -> bool:
        """Show the last rig-overview render in the Rig pane, if one exists."""
        path = self._rig_preview_path()
        if path is None or not path.is_file():
            return False
        self.canvases["rigCanvas"].set_image(QImage(str(path)))
        return True

    def _on_render_rig(self, **kwargs) -> bool:
        """Render the annotated rig overview with Blender (asynchronous), then
        show it in the Rig pane. Available on backends that model the rig in
        Blender (simulation); on hardware the last render, if any, still shows.
        Renders at the pane's current orbit state; explicit view kwargs
        (azimuth / elevation / distance) win and update that state. Returns
        whether a render was actually started (failures are logged, not
        raised -- this doubles as a Qt slot)."""
        command = getattr(self.backend, "rig_preview_command", None)
        if not callable(command):
            log.warning(f"rig preview not available on the {self.backend.kind_label} backend")
            return False
        if self._rig_runner.is_running():
            log.warning("a rig render is already running")
            return False
        for key in ("azimuth", "elevation", "distance"):
            if key in kwargs:
                self._rig_view[key] = float(kwargs[key])
            kwargs[key] = self._rig_view[key]
        try:
            spec = command(**kwargs)
        except Exception as exc:  # noqa: BLE001 - report to console, don't raise into Qt
            log.warning(f"cannot render rig view: {exc}")
            return False
        self._rig_tail.clear()
        log.info("rig view: rendering the annotated overview...")
        self._rig_runner.start(spec.argv, str(spec.cwd))
        self._rig_view_inflight = {k: self._rig_view[k]
                                   for k in ("azimuth", "elevation", "distance")}
        self._push_rig_hint()
        return True

    # Orbit re-renders trade quality for latency; the sidebar button still
    # renders at the backend's default samples.
    ORBIT_SAMPLES = 16

    def _on_rig_orbit(self, d_azimuth: float, d_elevation: float) -> None:
        view = self._rig_view
        view["azimuth"] = (view["azimuth"] + d_azimuth) % 360.0
        # Clamped short of the pole, where the camera's roll flips around.
        view["elevation"] = min(85.0, max(5.0, view["elevation"] + d_elevation))
        self._on_rig_view_changed()

    def _on_rig_zoom(self, factor: float) -> None:
        view = self._rig_view
        view["distance"] = min(1.4, max(0.35, view["distance"] * factor))
        self._on_rig_view_changed()

    def _on_rig_view_changed(self) -> None:
        view = self._rig_view
        if not self._capture_runner.is_running():
            self._status_left.setText(
                f"Rig view: az {view['azimuth']:.0f}°  el {view['elevation']:.0f}°  "
                f"dist {view['distance']:.2f} m"
            )
        self._push_rig_hint()
        canvas = self.canvases.get("rigCanvas")
        if isinstance(canvas, OrbitCanvas) and canvas.is_orbiting():
            return  # mid-drag: the gizmo tracks; the render fires on release
        self._rig_orbit_timer.start()  # wheel zoom etc.: fire once input settles

    def _push_rig_hint(self) -> None:
        """Keep the Rig canvas HUD current: it shows the queued rotation (the
        gap between the drag target and the on-screen render) the moment the
        mouse moves, hiding the render latency."""
        canvas = self.canvases.get("rigCanvas")
        if isinstance(canvas, OrbitCanvas):
            canvas.set_view_hint(self._rig_view, self._rig_view_displayed,
                                 self._rig_runner.is_running())

    def _request_rig_render(self) -> None:
        """Orbit re-render (on drag release / settled wheel zoom): fast
        samples; a no-op interaction (plain click, drag back to the start)
        renders nothing, and input landing mid-render coalesces into exactly
        one follow-up render at the latest state."""
        target, shown = self._rig_view, self._rig_view_displayed
        if (abs(OrbitCanvas._az_delta(target["azimuth"], shown["azimuth"])) < 0.5
                and abs(target["elevation"] - shown["elevation"]) < 0.5
                and abs(target["distance"] - shown["distance"]) < 0.005):
            self._push_rig_hint()  # clears a stale "waiting" readout
            return
        if self._rig_runner.is_running():
            self._rig_render_pending = True
            return
        self._on_render_rig(samples=self.ORBIT_SAMPLES)

    def _on_rig_line(self, line: str) -> None:
        self._rig_tail.append(line)
        # Progress lines are tagged "[rig_preview] ..."; surface just those.
        if line.startswith("[rig_preview]"):
            log.info(line.split("]", 1)[-1].strip())

    def _on_rig_finished(self, exit_code: int) -> None:
        if exit_code != 0:
            self._rig_render_pending = False  # don't chain renders after a failure
            self._rig_view_inflight = None
            self._push_rig_hint()
            log.error(f"rig render failed (exit {exit_code})")
            for tail in list(self._rig_tail)[-6:]:
                log.error(tail)
            return
        if self._load_rig_preview():
            if self._rig_view_inflight is not None:
                self._rig_view_displayed = self._rig_view_inflight
                self._rig_view_inflight = None
            self._show_tab("rigCanvas")
            success(log, "rig view rendered")
        else:
            log.error("rig render finished but produced no image")
        if self._rig_render_pending:  # orbit input arrived mid-render
            self._rig_render_pending = False
            self._request_rig_render()  # re-checks: the drag may have come back
        elif not self._capture_runner.is_running():
            self._status_left.setText("Ready")
        self._push_rig_hint()

    def _on_rig_failed(self, message: str) -> None:
        self._rig_render_pending = False
        self._rig_view_inflight = None
        self._push_rig_hint()
        log.error(f"rig render failed: {message}")

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

    def _reconstruct_multifreq(self, surface: str) -> None:
        """Coarse->fine unwrap of the ladder just captured (self._ladder_dirs),
        then roughness off the resulting height map."""
        self._status_left.setText(f"Reconstructing {surface} (multi-frequency)...")
        QApplication.processEvents()  # paint the status before the brief blocking run
        try:
            result = self.backend.reconstruct_multifreq(
                surface, capture_dirs=self._ladder_dirs, n_periods_ladder=self._ladder
            )
        except Exception as exc:  # noqa: BLE001 - surface any failure to the console
            log.error(f"multi-frequency reconstruct failed: {exc}")
            self._status_left.setText("Ready")
            return
        self._display_reconstruction(surface, result)
        self._measure_roughness(surface)  # roughness rides on the just-made height map
        self._status_left.setText("Ready")

    def _measure_roughness(self, surface: str) -> None:
        """Measure roughness off `surface`'s latest reconstruction (the one just
        produced). Uses the finest ladder rung for the noise floor when known."""
        self._status_left.setText(f"Measuring roughness of {surface}...")
        QApplication.processEvents()
        fine_dir = self._ladder_dirs[-1] if self._ladder_dirs else None
        fine_n = self._ladder[-1] if self._ladder else None
        try:
            result = self.backend.measure_roughness(
                surface, fine_capture_dir=fine_dir, fine_n_periods=fine_n
            )
        except Exception as exc:  # noqa: BLE001 - surface any failure to the console
            log.error(f"roughness measurement failed: {exc}")
        else:
            self._display_roughness(surface, result)

    def _display_roughness(self, surface: str, result) -> None:
        self.canvases["roughnessCanvas"].set_image(QImage(str(result.roughness_png)))
        self._show_tab("roughnessCanvas")
        self._log_roughness_metrics(surface, result.metrics)

    def _log_roughness_metrics(self, surface: str, m: dict) -> None:
        line = (f"roughness {surface}: Sa={m['Sa_um']:.2f} um, "
                f"Sq={m['Sq_um']:.2f} um, Sz={m['Sz_um']:.2f} um")
        if "Sq_true_um" in m:  # known specimen: scored against ground truth
            line += f" (true Sq={m['Sq_true_um']:.2f} um, err {m['Sq_err_um']:+.2f} um)"
        success(log, line)
        if "roughness_snr" in m:  # random-noise floor + SNR reported
            success(
                log,
                f"  random floor {m['noise_floor_um']:.2f} um -> "
                f"Sq(denoised)={m['Sq_denoised_um']:.2f} um, random-SNR={m['roughness_snr']:.1f}",
            )
            if m.get("systematic_error"):  # temporal >> spatial: not just noise
                log.warning(
                    f"  systematic error present (temporal/spatial = {m['systematic_ratio']:.0f}x); "
                    "the random floor does not bound the roughness map's fidelity"
                )

    def _log_metrics(self, surface: str, m: dict) -> None:
        valid_pct = 100.0 * m["valid_pixels"] / m["total_pixels"]
        if "rmse" in m:  # a known specimen was scored against its ground truth
            success(
                log,
                f"reconstructed {surface}: RMSE={m['rmse']:.4f} mm, "
                f"R^2={m['r2']:.4f}, valid={valid_pct:.1f}%",
            )
        else:  # real capture: no ground truth to score against
            success(log, f"reconstructed {surface}: height map, valid={valid_pct:.1f}%")
        if "n_periods_ladder" in m:  # multi-frequency: note the ladder's range/resolution
            success(
                log,
                f"  multi-frequency {m['n_periods_ladder']}: lambda_eq "
                f"{m['lambda_eq_coarse_mm']:.2f} -> {m['lambda_eq_mm']:.2f} mm "
                f"(unambiguous +/-{m['unambiguous_range_mm']:.2f} mm)",
            )

    # -- noise estimation (inline, ~0.4s) -------------------------------------

    def _on_estimate_noise(self) -> None:
        self._estimate_noise(self.sidebar.selected_surface())

    def _estimate_noise(self, surface: str) -> None:
        """Analyze the error a capture imposes on the reconstruction -- random
        noise and auto-exposure brightness swing. In simulation the injected
        levels (sidebar) are recovered and their cost shown; for a real capture
        the noise and swing already in the frames are measured."""
        injected = self.sidebar.injected_noise_dn()
        swing = self.sidebar.exposure_swing_pct()
        self._status_left.setText(f"Analyzing errors for {surface}...")
        QApplication.processEvents()  # paint the status before the brief blocking run
        try:
            result = self.backend.estimate_noise(
                surface, injected_sigma_dn=injected, gain_swing_pct=swing
            )
        except Exception as exc:  # noqa: BLE001 - surface any failure to the console
            log.error(f"error analysis failed: {exc}")
        else:
            self._display_noise(surface, result)
        self._status_left.setText("Ready")

    def _display_noise(self, surface: str, result) -> None:
        self.canvases["noiseCanvas"].set_image(QImage(str(result.uncertainty_png)))
        self._show_tab("noiseCanvas")
        self._log_noise_metrics(surface, result.metrics)

    def _log_noise_metrics(self, surface: str, m: dict) -> None:
        parts = [f"noise {surface}: sigma={m['sigma_est_dn']:.2f} DN (spatial {m['sigma_spatial_dn']:.2f})"]
        if "injected_sigma_dn" in m:  # controlled run: scored against the injected level
            parts.append(f"injected {m['injected_sigma_dn']:.2f} DN, err {100 * m['sigma_rel_error']:+.1f}%")
        parts.append(f"exposure swing {m['brightness_swing_pct']:.1f}%")
        parts.append(
            f"noise margin mean {m['height_uncertainty_um_mean']:.0f} um / "
            f"p95 {m['height_uncertainty_um_p95']:.0f} um"
        )
        success(log, "; ".join(parts))
        # The exposure swing's cost, and how much correcting it recovers.
        if m.get("rmse_raw_mm") is not None and m.get("rmse_corrected_mm") is not None:
            raw_um = m["rmse_raw_mm"] * 1000
            cor_um = m["rmse_corrected_mm"] * 1000
            if raw_um - cor_um > 1.0:
                success(log, f"  recon RMSE {raw_um:.0f} um -> {cor_um:.0f} um after exposure correction")
            else:
                success(log, f"  recon RMSE {cor_um:.0f} um (no exposure swing to correct)")

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

    def _on_pipeline_multifreq(self, **kwargs) -> None:
        """Multi-frequency pipeline: capture the coarse->fine ladder rung by rung,
        then reconstruct by temporal unwrapping. Each rung is an ordinary capture
        into out/app/<surface>/capture_f<i>; the sequencing (advance on `finished`)
        lives in _advance_or_reconstruct_ladder."""
        surface = self.sidebar.selected_surface()
        try:
            ladder = self.backend.capture_ladder()
        except Exception as exc:  # noqa: BLE001 - sim/ladder unavailable
            log.warning(f"cannot start multi-frequency pipeline: {exc}")
            return
        if len(ladder) < 2:
            log.warning("multi-frequency needs >= 2 ladder rungs; use Run Pipeline")
            return
        self._project(surface)
        self._ladder = ladder
        self._ladder_i = 0
        self._ladder_dirs = []
        self._ladder_kwargs = {k: v for k, v in kwargs.items() if k in ("samples",)}
        log.info(f"multi-frequency: {len(ladder)} frequencies {[f'{n:g}' for n in ladder]}")
        try:
            self._start_capture(
                surface, purpose="pipeline_mf", n_steps=self._ladder_n_steps,
                subdir=self.backend.multifreq_subdir(0), n_periods=ladder[0],
                **self._ladder_kwargs,
            )
        except Exception as exc:  # noqa: BLE001 - report to console, don't raise into Qt
            log.warning(f"cannot start multi-frequency pipeline: {exc}")

    def _start_capture(self, surface: str, purpose: str, n_steps: int, subdir: str, **kwargs) -> "object":
        """Kick off a capture of `surface` through the backend's controller
        (raises on bad state). Returns the controller, which knows where the
        frames will land and how many to expect."""
        if self._capture_runner.is_running():
            raise RuntimeError("a capture is already running")
        if not surface:
            raise ValueError("no specimen selected")
        self._capture_surface = surface
        self._capture_purpose = purpose
        self.sidebar.specimen.setCurrentText(surface)  # reflect what's being captured
        self._capture_tail.clear()
        self._set_capture_busy(True)
        plural = "s" if n_steps != 1 else ""
        prefix = "pipeline: capturing" if purpose == "pipeline" else "capturing"
        self._status_left.setText(f"Capturing {surface}...")
        log.info(f"{prefix} {surface}: acquiring {n_steps} frame{plural}...")
        self._capture_runner.start(surface=surface, n_steps=n_steps, subdir=subdir, **kwargs)
        return self._capture_runner

    def _on_capture_line(self, line: str) -> None:
        self._capture_tail.append(line)
        # Progress lines are tagged "[capture_pipeline] ..." (Blender) or
        # "[capture] ..." (hardware); surface either, plus the final summary.
        if line.startswith("[") and "]" in line:
            log.info(line.split("]", 1)[-1].strip())
        elif line.startswith("Captured "):
            log.info(line)

    def _on_capture_finished(self, exit_code: int) -> None:
        if exit_code != 0:
            self._finish_capture_idle()
            log.error(f"capture failed (exit {exit_code})")
            for tail in list(self._capture_tail)[-6:]:
                log.error(tail)
            return
        capture_dir = self._capture_runner.capture_dir
        frames = sorted(capture_dir.glob("frame_*.png")) if capture_dir else []
        if frames:
            self.canvases["capturedCanvas"].set_image(QImage(str(frames[0])))
            self._show_tab("capturedCanvas")

        if self._capture_purpose == "pipeline_mf":
            self._ladder_dirs.append(capture_dir)
            self._advance_or_reconstruct_ladder()  # keeps busy until the ladder is done
            return

        self._finish_capture_idle()
        if self._capture_purpose == "pipeline":
            success(log, f"captured {self._capture_surface}: {self._capture_runner.n_steps} frames")
            self._reconstruct(self._capture_surface)
        else:
            success(log, f"captured {self._capture_surface}: single frame")

    def _advance_or_reconstruct_ladder(self) -> None:
        """After one ladder rung finishes: start the next, or (all captured)
        reconstruct by multi-frequency unwrapping. Stays 'busy' throughout."""
        surface = self._capture_surface
        self._ladder_i += 1
        if self._ladder_i < len(self._ladder):
            n = self._ladder[self._ladder_i]
            log.info(f"multi-frequency: rung {self._ladder_i + 1}/{len(self._ladder)} (n={n:g})...")
            self._status_left.setText(f"Capturing {surface} (rung {self._ladder_i + 1}/{len(self._ladder)})...")
            self._capture_tail.clear()
            try:
                self._capture_runner.start(
                    surface=surface, n_steps=self._ladder_n_steps,
                    subdir=self.backend.multifreq_subdir(self._ladder_i),
                    n_periods=n, **self._ladder_kwargs,
                )
            except Exception as exc:  # noqa: BLE001 - abort the ladder on a failed start
                self._finish_capture_idle()
                log.error(f"multi-frequency capture aborted: {exc}")
            return
        self._finish_capture_idle()
        success(log, f"captured {surface}: {len(self._ladder)} frequencies "
                     f"({self._ladder_n_steps} frames each)")
        self._reconstruct_multifreq(surface)

    def _finish_capture_idle(self) -> None:
        self._set_capture_busy(False)
        self._status_left.setText("Ready")

    def _on_capture_failed(self, message: str) -> None:
        self._finish_capture_idle()
        log.error(f"capture failed: {message}")

    def _set_capture_busy(self, busy: bool) -> None:
        self.sidebar.capture_button.setEnabled(not busy)
        self.sidebar.pipeline_button.setEnabled(not busy)
        self.sidebar.multifreq_button.setEnabled(not busy)
        if not busy:
            self.sidebar.capture_button.setText("Capture")
            self.sidebar.pipeline_button.setText("Run Pipeline")
            self.sidebar.multifreq_button.setText("Run Multi-Freq")
        elif self._capture_purpose == "pipeline_mf":
            self.sidebar.multifreq_button.setText("Running...")
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
            "run_multifreq": self._cmd_run_multifreq,
            "reconstruct": self._cmd_reconstruct,
            "reconstruct_multifreq": self._cmd_reconstruct_multifreq,
            "measure_roughness": self._cmd_measure_roughness,
            "estimate_noise": self._cmd_estimate_noise,
            "render_rig": self._cmd_render_rig,
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
        self.backend.project(fringe)  # push to the physical projector (no-op in sim)
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

    def _cmd_run_multifreq(self, args: dict):
        """Start the multi-frequency pipeline (asynchronous): capture the
        coarse->fine ladder rung by rung, then reconstruct by unwrapping. Returns
        once the first rung's capture starts."""
        surface = str(args.get("surface") or self.sidebar.selected_surface())
        self.sidebar.specimen.setCurrentText(surface)
        kwargs = {}
        if "samples" in args:
            kwargs["samples"] = int(args["samples"])
        self._on_pipeline_multifreq(**kwargs)
        return {"multifreq": "started", "surface": surface, "ladder": self._ladder}

    def _cmd_reconstruct(self, args: dict):
        surface = str(args.get("surface") or self.sidebar.selected_surface())
        self.sidebar.specimen.setCurrentText(surface)
        result = self.backend.reconstruct(surface)
        self._display_reconstruction(surface, result)
        return {"surface": surface, "metrics": result.metrics}

    def _cmd_reconstruct_multifreq(self, args: dict):
        """Reconstruct from an already-captured ladder (out/app/<surface>/capture_f*),
        without re-capturing. `n_periods_ladder` optionally overrides the default."""
        surface = str(args.get("surface") or self.sidebar.selected_surface())
        self.sidebar.specimen.setCurrentText(surface)
        ladder = args.get("n_periods_ladder")
        ladder = [float(n) for n in ladder] if ladder is not None else None
        result = self.backend.reconstruct_multifreq(surface, n_periods_ladder=ladder)
        self._display_reconstruction(surface, result)
        return {"surface": surface, "metrics": result.metrics}

    def _cmd_measure_roughness(self, args: dict):
        """Measure roughness from `surface`'s latest reconstruction (run pipeline /
        multi-freq first). `cutoff_mm` overrides the form/roughness separation
        wavelength. Reads the finest ladder rung for the noise floor, if known."""
        surface = str(args.get("surface") or self.sidebar.selected_surface())
        self.sidebar.specimen.setCurrentText(surface)
        cutoff = float(args.get("cutoff_mm", 10.0))
        fine_dir = self._ladder_dirs[-1] if self._ladder_dirs else None
        fine_n = self._ladder[-1] if self._ladder else None
        result = self.backend.measure_roughness(
            surface, cutoff_mm=cutoff, fine_capture_dir=fine_dir, fine_n_periods=fine_n
        )
        self._display_roughness(surface, result)
        return {"surface": surface, "metrics": result.metrics}

    def _cmd_render_rig(self, args: dict):
        """Start the annotated rig-overview render (asynchronous); the Rig pane
        updates when it finishes. `samples` overrides the render quality;
        `azimuth`/`elevation` (degrees) and `distance` (m) orbit the viewpoint
        (and become the pane's current orbit state)."""
        kwargs = {k: float(args[k]) for k in ("azimuth", "elevation", "distance") if k in args}
        if "samples" in args:
            kwargs["samples"] = int(args["samples"])
        if not self._on_render_rig(**kwargs):
            raise ValueError("rig render not started (see console)")
        return {"rig_render": "started", "view": dict(self._rig_view)}

    def _cmd_estimate_noise(self, args: dict):
        """Analyze reconstruction error (noise + exposure swing). `injected_sigma_dn`
        and `gain_swing_pct` override the sidebar's injected levels (simulation
        only; ignored for a real capture)."""
        surface = str(args.get("surface") or self.sidebar.selected_surface())
        injected = args.get("injected_sigma_dn", self.sidebar.injected_noise_dn())
        injected = float(injected) if injected is not None else None
        swing = float(args.get("gain_swing_pct", self.sidebar.exposure_swing_pct()))
        self.sidebar.specimen.setCurrentText(surface)
        result = self.backend.estimate_noise(
            surface, injected_sigma_dn=injected, gain_swing_pct=swing
        )
        self._display_noise(surface, result)
        return {"surface": surface, "metrics": result.metrics}
