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


class CameraController(QObject):
    """Lifecycle manager for the single active camera thread."""

    frameReady = Signal(object)   # CaptureFrame
    fpsUpdated = Signal(float)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def select(self, backend: str, index: int) -> None:
        """Switch to (and start) the given device, replacing any current one."""
        self.stop()
        if backend == "pyspin":
            self._thread = PySpinCameraThread(device_index=index, parent=self)
        else:
            self._thread = OpenCVCameraThread(device_index=index, parent=self)
        self._thread.frame_ready.connect(self.frameReady)
        self._thread.fps_updated.connect(self.fpsUpdated)
        self._thread.error.connect(self.error)
        self._thread.start()

    def stop(self) -> None:
        """Tear down the active thread and return to the off state."""
        if self._thread is not None:
            self._thread.stop()
            self._thread.deleteLater()
            self._thread = None
