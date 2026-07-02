"""Shared pytest fixtures.

The maestro connector's actions run against real Qt widgets, so the tests need a
QApplication. Force Qt's offscreen platform before any Qt import so the suite
runs headless (CI, no display) without spawning visible windows.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402 - must follow the platform env set above
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole session (Qt allows only one)."""
    app = QApplication.instance() or QApplication([])
    yield app
