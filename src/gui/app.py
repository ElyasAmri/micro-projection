"""app.py — QApplication setup and entry point.

Launch via:
    python -m src.gui

Imports MainWindow from main_window.py. As of Stage 4a task 4, the GUI
transitively imports the math layer (pipeline -> calibration / phase_
shifting / etc.); those modules use bare-name inter-module imports, so
we prepend `src/` to sys.path the same way tests/conftest.py does.
"""
from __future__ import annotations

import os
import sys

# Add src/ to sys.path before importing main_window so the math
# modules' bare-name inter-module imports (`from calibration import
# ...`) resolve when the GUI is launched via `python -m src.gui`.
# Matches the setup in tests/conftest.py.
_SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from PyQt6.QtWidgets import QApplication

from src.gui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
