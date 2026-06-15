"""Persistent application configuration (QSettings-backed).

A thin wrapper over ``QSettings`` so the rest of the app never touches Qt's
settings API directly. Storage location comes from the organization/application
name set on ``QApplication`` in ``app.py`` (on Windows: HKCU registry).

Add further persisted settings as properties here as the app grows.
"""
from __future__ import annotations

from PySide6.QtCore import QSettings


class AppConfig:
    """Remembers the last user configuration across runs."""

    _KEY_LAST_CAMERA = "camera/last_name"
    _KEY_SIDEBAR_WIDTH = "ui/sidebar_width"

    def __init__(self):
        self._settings = QSettings()

    @property
    def last_camera(self) -> str | None:
        """Name of the camera selected when the app last closed, or None."""
        value = self._settings.value(self._KEY_LAST_CAMERA, None)
        return value or None

    @last_camera.setter
    def last_camera(self, name: str | None) -> None:
        if name:
            self._settings.setValue(self._KEY_LAST_CAMERA, name)
        else:
            self._settings.remove(self._KEY_LAST_CAMERA)

    @property
    def sidebar_width(self) -> int | None:
        """Last sidebar width in pixels, or None if never set."""
        value = self._settings.value(self._KEY_SIDEBAR_WIDTH, None)
        return int(value) if value is not None else None

    @sidebar_width.setter
    def sidebar_width(self, width: int) -> None:
        self._settings.setValue(self._KEY_SIDEBAR_WIDTH, int(width))
