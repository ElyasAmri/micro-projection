"""The left sidebar: an empty panel for now.

Kept in the shell (docked left, styled) but intentionally without content --
controls land here later.
"""
from __future__ import annotations

from PySide6.QtWidgets import QSizePolicy, QWidget


class Sidebar(QWidget):
    """Empty fixed-width left panel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.setMinimumWidth(230)
