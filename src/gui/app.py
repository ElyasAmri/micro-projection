"""app.py — QApplication setup and entry point.

Launch via:
    python -m src.gui

Imports MainWindow from main_window.py. Nothing here imports the math
layer (Stage 4a task 2 is a layout-only skeleton).
"""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from src.gui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
