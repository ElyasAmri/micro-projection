"""Application entry point: build the Qt app + main window, attach the maestro
connector, and run. Also supports `--screenshot PATH` for a headless render.

    microprojection                      # run the app
    python -m microprojection            # same
    microprojection --screenshot ui.png  # render the shell offscreen, then exit
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from microprojection.maestro import attach
from microprojection.ui.main_window import MainWindow
from microprojection.ui.styles import build_stylesheet


def build_app():
    """Create the QApplication with the app-wide dark theme applied."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Micro-Projection Control")
    app.setOrganizationName("micro-projection")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="microprojection", description=__doc__)
    parser.add_argument("--screenshot", metavar="PATH", help="render the shell offscreen to PATH and exit")
    args = parser.parse_args(argv)

    if args.screenshot and "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    app = build_app()
    window = MainWindow()
    window.install_log_bridge()

    window.console.log("Micro-Projection control shell started", "ok")
    window.console.log("canvas, sidebar, console ready", "info")

    connector = attach(window, commands=window.maestro_commands(), kind="qt")
    if connector is None:
        window.set_maestro_status("unavailable")
        window.console.log("maestro connector unavailable (QtWebSockets missing)", "warn")
    else:
        window.set_maestro_status("listening")
        window.console.log("maestro connector attached (kind=qt); watching for a server", "info")

    window.show()

    if args.screenshot:
        return _render_screenshot(app, window, args.screenshot)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
