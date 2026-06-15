"""Persistent application configuration (QSettings-backed).

A thin wrapper over ``QSettings`` so the rest of the app never touches Qt's
settings API directly. Storage location comes from the organization/application
name set on ``QApplication`` in ``app.py`` (on Windows: HKCU registry).

Add further persisted settings as properties here as the app grows.
"""
from __future__ import annotations

import json
from dataclasses import asdict, fields

from PySide6.QtCore import QSettings

from microprojection.acquisition.camera_settings import CameraSettings


class AppConfig:
    """Remembers the last user configuration across runs."""

    _KEY_LAST_BACKEND = "camera/last_backend"
    _KEY_LAST_INDEX = "camera/last_index"
    _KEY_LAST_PROJECTOR = "projector/last_index"
    _KEY_SIDEBAR_WIDTH = "ui/sidebar_width"
    _KEY_CAMERA_SETTINGS = "camera/settings"

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
    def last_projector(self) -> int | None:
        """Screen index of the last projector display, or None."""
        value = self._settings.value(self._KEY_LAST_PROJECTOR, None)
        return int(value) if value is not None else None

    @last_projector.setter
    def last_projector(self, index: int | None) -> None:
        if index is None:
            self._settings.remove(self._KEY_LAST_PROJECTOR)
        else:
            self._settings.setValue(self._KEY_LAST_PROJECTOR, int(index))

    @property
    def camera_settings(self) -> CameraSettings:
        """The saved camera configuration, or defaults if none/invalid.

        Stored as a single JSON blob. Unknown keys are dropped so an older saved
        value still loads after the settings schema grows.
        """
        raw = self._settings.value(self._KEY_CAMERA_SETTINGS, None)
        if not raw:
            return CameraSettings()
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return CameraSettings()
        if not isinstance(data, dict):
            return CameraSettings()
        valid = {f.name for f in fields(CameraSettings)}
        kwargs = {k: v for k, v in data.items() if k in valid}
        try:
            return CameraSettings(**kwargs)
        except TypeError:
            return CameraSettings()

    @camera_settings.setter
    def camera_settings(self, settings: CameraSettings) -> None:
        self._settings.setValue(
            self._KEY_CAMERA_SETTINGS, json.dumps(asdict(settings))
        )
        # Flush now so a change survives even if the app is killed or crashes
        # before QSettings' periodic/at-exit flush.
        self._settings.sync()

    @property
    def sidebar_width(self) -> int | None:
        """Last sidebar width in pixels, or None if never set."""
        value = self._settings.value(self._KEY_SIDEBAR_WIDTH, None)
        return int(value) if value is not None else None

    @sidebar_width.setter
    def sidebar_width(self, width: int) -> None:
        self._settings.setValue(self._KEY_SIDEBAR_WIDTH, int(width))
