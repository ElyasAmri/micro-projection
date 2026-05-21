"""stl_browser.py — Stage 4d Browser tab widget (skeleton).

Third tab on the right-pane QTabWidget. Provides FOV-by-FOV
navigation of oversized STL specimens via a minimap + windowed
preview triad. Content panels are empty placeholders in sub-
task 3; sub-tasks 4-5 fill them with real rendering and the
drag handler.

State dispatch
--------------
The widget exposes two views via an internal QStackedWidget:
  - placeholder: shown when no Browser-mode STL is active
    (no STL loaded, Flat / Gaussian selected, or a small STL
    on the direct path).
  - panels: shown when MainWindow's _stl_is_browser_mode is True.
MainWindow drives the switch via show_placeholder() /
show_panels(); the widget itself reads no cache state.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


_PLACEHOLDER_TEXT = (
    "Load an oversized STL (XY larger than 68 × 55 mm but within "
    "272 × 220 mm) to browse it FOV by FOV.\n\n"
    "Currently no Browser-mode STL is active. Small STLs use the "
    "3D Scene tab directly."
)


def _panel(label_text: str) -> QFrame:
    """Build a sunken QFrame containing a centered descriptive label."""
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    frame.setFrameShadow(QFrame.Shadow.Sunken)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(8, 8, 8, 8)
    label = QLabel(label_text)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    label.setStyleSheet("color: #888; font-size: 12px;")
    layout.addWidget(label)
    return frame


class STLBrowser(QWidget):
    """Stage 4d Browser tab: FOV-by-FOV navigation of full-scale STLs.

    Three-panel layout when Browser-mode is active:
      - Top-left:    minimap (2D top-down with FOV rectangle)
      - Bottom-left: whole-STL 3D preview (orientation only)
      - Right:       windowed 3D preview (what the math measures)
    Placeholder shown otherwise.

    Panel content fills land in sub-tasks 4-5; this widget only
    builds the structural skeleton.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._stack = QStackedWidget()

        # Page 0: placeholder.
        placeholder = QWidget()
        ph_layout = QVBoxLayout(placeholder)
        ph_layout.setContentsMargins(40, 40, 40, 40)
        ph_label = QLabel(_PLACEHOLDER_TEXT)
        ph_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_label.setWordWrap(True)
        ph_label.setStyleSheet("color: #888; font-size: 13px;")
        ph_layout.addStretch(1)
        ph_layout.addWidget(ph_label)
        ph_layout.addStretch(1)
        self._stack.addWidget(placeholder)

        # Page 1: three-panel splitter layout.
        outer = QSplitter(Qt.Orientation.Horizontal)
        inner = QSplitter(Qt.Orientation.Vertical)

        self._minimap_panel = _panel("Minimap (2D top-down, FOV rectangle)")
        self._whole_stl_panel = _panel("Whole-STL 3D preview (orientation only)")
        self._windowed_panel = _panel(
            "Windowed 3D preview (what the math measures)"
        )

        inner.addWidget(self._minimap_panel)
        inner.addWidget(self._whole_stl_panel)
        inner.setSizes([440, 360])  # ~55/45 within the left half

        outer.addWidget(inner)
        outer.addWidget(self._windowed_panel)
        outer.setSizes([400, 600])  # ~40/60 of available width

        self._stack.addWidget(outer)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        self._stack.setCurrentIndex(0)

    @property
    def is_showing_panels(self) -> bool:
        """True when the three-panel layout is active; False for placeholder."""
        return self._stack.currentIndex() == 1

    def show_placeholder(self) -> None:
        """Switch to the placeholder view (no Browser-mode STL active)."""
        self._stack.setCurrentIndex(0)

    def show_panels(self) -> None:
        """Switch to the three-panel layout (Browser-mode STL active)."""
        self._stack.setCurrentIndex(1)
