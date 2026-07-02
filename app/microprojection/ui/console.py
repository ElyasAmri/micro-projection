"""The bottom console: a read-only, timestamped, color-coded log view.

`Console.log(msg, level)` is the app's single sink for user-facing messages.
`ConsoleLogHandler` bridges the stdlib `logging` module into it, so anything
the maestro connector logs (connects, registrations, request errors) surfaces
here too.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime

from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from microprojection.ui.styles import LEVEL_COLORS, COLORS, monospace_font

MAX_BLOCKS = 5000  # cap scrollback so a long session can't grow without bound


class Console(QWidget):
    """A titled panel wrapping a read-only monospace log with a Clear action."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("consolePanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("Console")
        title.setObjectName("consoleHeader")
        header.addWidget(title)
        header.addStretch(1)

        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("clearConsoleButton")
        self.clear_button.setProperty("role", "chip")
        self.clear_button.clicked.connect(self.clear)
        header.addWidget(self.clear_button)
        layout.addLayout(header)

        self.view = QPlainTextEdit()
        self.view.setObjectName("console")
        self.view.setReadOnly(True)
        self.view.setFont(monospace_font(12))
        self.view.setMaximumBlockCount(MAX_BLOCKS)
        self.view.setFrameShape(QPlainTextEdit.NoFrame)
        self.view.setWordWrapMode(QTextOption.NoWrap)
        layout.addWidget(self.view, 1)

    def log(self, message: str, level: str = "info") -> None:
        """Append one timestamped, level-colored line and scroll to it."""
        color = LEVEL_COLORS.get(level, COLORS["text"])
        stamp = datetime.now().strftime("%H:%M:%S")
        tag = level.upper().ljust(5)
        line = (
            f'<span style="color:{COLORS["text_faint"]}">{stamp}</span> '
            f'<span style="color:{color}">{html.escape(tag)}</span> '
            f'<span style="color:{COLORS["text"]}">{html.escape(message)}</span>'
        )
        self.view.appendHtml(line)
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def clear(self) -> None:
        self.view.clear()


class ConsoleLogHandler(logging.Handler):
    """Routes stdlib log records into a `Console`, mapping levels to its colors."""

    _LEVEL_MAP = {
        logging.DEBUG: "info",
        logging.INFO: "info",
        logging.WARNING: "warn",
        logging.ERROR: "error",
        logging.CRITICAL: "error",
    }

    def __init__(self, console: Console) -> None:
        super().__init__()
        self._console = console

    def emit(self, record: logging.LogRecord) -> None:
        level = self._LEVEL_MAP.get(record.levelno, "info")
        try:
            self._console.log(self.format(record), level)
        except RuntimeError:
            # Console was destroyed (app shutting down); drop the record.
            pass
