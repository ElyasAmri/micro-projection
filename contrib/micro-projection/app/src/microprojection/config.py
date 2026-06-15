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

    _KEY_LAST_BACKEND = "camera/last_backend"
    _KEY_LAST_INDEX = "camera/last_index"
    _KEY_SIDEBAR_WIDTH = "ui/sidebar_width"

    def __init__(self):
        self._settings = QSettings()

    @property
    def last_camera(self) -> tuple[str, int] | None:
        """Device coordinates (backend, index) of the last camera, or None.

        Identified by coordinates rather than display name so we never persist
        an encoded device-name string.
        """
        backend = self._settings.value(self._KEY_LAST_BACKEND, None)
        index = self._settings.value(self._KEY_LAST_INDEX, None)
        if not backend or index is None:
            return None
        return (str(backend), int(index))

    @last_camera.setter
    def last_camera(self, value: tuple[str, int] | None) -> None:
        if value is None:
            self._settings.remove(self._KEY_LAST_BACKEND)
            self._settings.remove(self._KEY_LAST_INDEX)
        else:
            backend, index = value
            self._settings.setValue(self._KEY_LAST_BACKEND, backend)
            self._settings.setValue(self._KEY_LAST_INDEX, int(index))

    @property
    def sidebar_width(self) -> int | None:
        """Last sidebar width in pixels, or None if never set."""
        value = self._settings.value(self._KEY_SIDEBAR_WIDTH, None)
        return int(value) if value is not None else None

    @sidebar_width.setter
    def sidebar_width(self, width: int) -> None:
        self._settings.setValue(self._KEY_SIDEBAR_WIDTH, int(width))
