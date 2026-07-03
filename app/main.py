"""Application entry point: build the Qt app + main window, attach the maestro
connector, and run. Also supports `--screenshot PATH` for a headless render.

    python app/main.py                      # run the app (from the repo root)
    python app/main.py --screenshot ui.png  # render the shell offscreen, then exit
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import logbus
from backend import SimulationBackend
from maestro import attach
from single_instance import SingleInstance
from ui.console import ConsoleLogHandler
from ui.main_window import MainWindow
from ui.styles import build_stylesheet

log = logbus.get_logger("app")


def _app_icon():
    """The app icon (fringe-dome mark), assembled from the bundled PNG sizes so
    Qt can pick the best for each surface (window, Dock, task switcher)."""
    from PySide6.QtGui import QIcon

    icons = Path(__file__).resolve().parent / "ui" / "icons"
    icon = QIcon()
    for png in ("app_icon_256.png", "app_icon_512.png"):
        path = icons / png
        if path.exists():
            icon.addFile(str(path))
    return icon


def build_app():
    """Create the QApplication with the app-wide dark theme and icon applied."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Micro-Projection Control")
    app.setOrganizationName("micro-projection")
    app.setWindowIcon(_app_icon())
    app.setStyleSheet(build_stylesheet())
    return app


def _render_screenshot(app, window, path: str) -> int:
    """Let the offscreen layout settle, then grab the window to `path`."""
    window.apply_dock_sizes()
    for _ in range(8):
        app.processEvents()
    ok = window.grab().save(path)
    print(f"screenshot {'written to ' + path if ok else 'FAILED for ' + path}")
    return 0 if ok else 1


def _activate(window) -> None:
    """Bring the primary window to the front (a second launch was attempted)."""
    window.showNormal()
    window.raise_()
    window.activateWindow()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="micro-projection", description=__doc__)
    parser.add_argument("--screenshot", metavar="PATH", help="render the shell offscreen to PATH and exit")
    args = parser.parse_args(argv)

    if args.screenshot and "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    app = build_app()

    # Refuse a second interactive window; nudge the running one to the front.
    # (Headless --screenshot renders are transient and skip the guard.)
    guard = None
    if not args.screenshot:
        guard = SingleInstance()
        if guard.another_running:
            print("micro-projection is already running", file=sys.stderr)
            return 0

    backend = SimulationBackend()
    window = MainWindow(backend=backend)
    logbus.configure(ConsoleLogHandler(window.console))
    if guard is not None:
        guard.setParent(window)  # tie its lifetime to the window
        guard.activate_requested.connect(lambda: _activate(window))

    logbus.success(log, "Micro-Projection control shell started")
    specimens = backend.available_surfaces()
    if specimens:
        log.info(f"simulation backend: {len(specimens)} specimens ({', '.join(specimens)})")
    else:
        log.warning("simulation backend: no capture data found under out/surface_tests")

    connector = attach(window, commands=window.maestro_commands(), kind="qt")
    if connector is None:
        window.set_maestro_status("unavailable")
        log.warning("maestro connector unavailable (QtWebSockets missing)")
    else:
        window.set_maestro_status("listening")
        log.info("maestro connector attached (kind=qt); watching for a server")

    if args.screenshot:
        window.show()  # fixed 1280x820 for a deterministic offscreen grab
        return _render_screenshot(app, window, args.screenshot)
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
