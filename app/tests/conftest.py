"""Shared pytest fixtures.

The maestro connector's actions run against real Qt widgets, so the tests need a
QApplication. Force Qt's offscreen platform before any Qt import so the suite
runs headless (CI, no display) without spawning visible windows.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Make the app's top-level packages (maestro, ui, backend) importable no matter
# where pytest is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402 - must follow the platform env set above
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole session (Qt allows only one)."""
    app = QApplication.instance() or QApplication([])
    yield app
