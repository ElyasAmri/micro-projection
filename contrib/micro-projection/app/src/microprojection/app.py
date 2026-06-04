"""Application entry point."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from microprojection.ui.main_window import MainWindow
from microprojection.ui.styles import BASE_FONT, STYLESHEET, dark_palette


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MicroProjection")
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    app.setFont(BASE_FONT)
    app.setStyleSheet(STYLESHEET)

    window = MainWindow()
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
