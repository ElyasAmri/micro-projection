"""Owns the live camera thread and its lifecycle.

Pulls camera start/stop/swap out of MainWindow. ``select()`` tears down any
existing thread and starts the new one; ``stop()`` returns to the off state.
Backend dispatch (PySpin vs OpenCV) lives here, and the controller re-emits the
thread's fps/error signals so the UI can surface them without knowing about
threads.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from microprojection.acquisition.camera import (
    OpenCVCameraThread,
    PySpinCameraThread,
)
from microprojection.acquisition.camera_settings import CameraSettings


class CameraController(QObject):
    """Lifecycle manager for the single active camera thread."""

    frameReady = Signal(object)   # CaptureFrame
    fpsUpdated = Signal(float)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._settings = CameraSettings()
        # (backend, index) of the active device, so settings can restart it
        self._current = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def latest_frame(self):
        """The active camera's most recent frame, or None if no camera is
        running. The preview pulls this on a timer rather than receiving a
        queued signal per frame, so frames never pile up behind a slow render."""
        if self.running:
            return self._thread.latest_frame()
        return None

    def select(self, backend: str, index: int) -> None:
        """Switch to (and start) the given device, replacing any current one."""
        self.stop()
        self._current = (backend, index)
        if backend == "pyspin":
            self._thread = PySpinCameraThread(
                device_index=index, settings=self._settings, parent=self
            )
        else:
            self._thread = OpenCVCameraThread(device_index=index, parent=self)
        self._thread.frame_ready.connect(self.frameReady)
        self._thread.fps_updated.connect(self.fpsUpdated)
        self._thread.error.connect(self.error)
        self._thread.start()

    def apply_settings(self, settings: CameraSettings) -> None:
        """Store new camera settings and, if a camera is live, restart it so
        structural nodes (pixel format, ROI, etc.) take effect."""
        self._settings = settings
        if self.running and self._current is not None:
            self.select(*self._current)

    def ensure_settings(self, settings: CameraSettings) -> None:
        """Apply settings only if they differ from the active ones, avoiding a
        needless camera restart when it is already configured."""
        if settings != self._settings:
            self.apply_settings(settings)

    def stop(self) -> None:
        """Tear down the active thread and return to the off state."""
        if self._thread is not None:
            self._thread.stop()
            self._thread.deleteLater()
            self._thread = None
        self._current = None
