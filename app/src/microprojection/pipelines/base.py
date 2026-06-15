"""Shared base for acquisition pipelines.

A pipeline coordinates the projector window and the live camera to capture a
fixed number of frames. The camera free-runs in its own thread and emits
``frameReady``; the pipeline listens for those frames and advances a small state
machine, so nothing blocks the GUI thread.

The steps in order:

1. ``start`` checks the camera is running and a projector is selected.
2. The camera is (re)configured with the given settings.
3. For each frame index the pipeline asks ``pattern_for(i)``. If it returns a
   pattern, that pattern is projected and the next few frames are discarded
   (settling) before one is kept; if it returns None the current projection is
   left in place. The kept frame goes to ``handle_frame(i, frame)``.
4. After the last frame ``finalize`` runs (typically writing files), then
   ``finished`` fires with the output directory.

Subclasses implement ``total``, ``pattern_for``, ``handle_frame``, and usually
``finalize``. The pattern dimensions come from ``self.width``/``self.height``
(the projector's resolution), available once ``start`` has validated.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QObject, Signal


class CapturePipeline(QObject):
    # current, total captured frames
    progress = Signal(int, int)
    status = Signal(str)
    # output directory when done
    finished = Signal(str)
    # reason a precondition or run failed
    failed = Signal(str)
    # the run was cancelled by the user
    cancelled = Signal()

    # frames to discard after a pattern change so the camera integrates a clean
    # frame of the new projection before one is kept
    settle_frames = 2

    def __init__(self, camera, projector_window, settings, output_dir,
                 parent=None):
        super().__init__(parent)
        self._camera = camera
        self._projector_window = projector_window
        self._settings = settings
        self._output_dir = output_dir
        self.width = 0
        self.height = 0
        self._i = 0
        self._skip = 0
        self._active = False

    # Subclass hooks.

    @property
    def total(self) -> int:
        raise NotImplementedError

    def pattern_for(self, i: int):
        """Return the pattern (HxW ndarray) to project for frame ``i``, or None
        to keep the current projection."""
        raise NotImplementedError

    def handle_frame(self, i: int, frame) -> None:
        """Consume the captured frame for index ``i``."""
        raise NotImplementedError

    def finalize(self) -> None:
        """Run after the last frame (e.g. write files). Default: nothing."""

    # Lifecycle.

    @property
    def running(self) -> bool:
        return self._active

    def start(self) -> None:
        if not self._camera.running:
            self.failed.emit("Camera is not running. Select a camera first.")
            return
        win = self._projector_window
        if win is None:
            self.failed.emit("No projector selected.")
            return
        width, height = win.target_size()
        if width <= 0 or height <= 0:
            self.failed.emit("Projector size unknown. Select a projector.")
            return
        self.width, self.height = width, height

        # Configure the camera with the settings (no-op restart if already set).
        self._camera.ensure_settings(self._settings)

        os.makedirs(self._output_dir, exist_ok=True)
        self._i = 0
        self._active = True
        self._camera.frameReady.connect(self._on_frame)
        self._project_for_index()
        self.status.emit(f"Capturing {self.total} frame(s)...")

    def cancel(self) -> None:
        if self._active:
            self._teardown()
            self.status.emit("Capture cancelled.")
            self.cancelled.emit()

    # Internals.

    def _project_for_index(self) -> None:
        pattern = self.pattern_for(self._i)
        if pattern is not None:
            self._projector_window.update_pattern(pattern)
            self._skip = self.settle_frames

    def _on_frame(self, frame) -> None:
        if not self._active:
            return
        if self._skip > 0:
            self._skip -= 1
            return
        try:
            self.handle_frame(self._i, frame)
        except Exception as exc:  # noqa: BLE001. surface any save/processing error
            self._teardown()
            self.failed.emit(f"Capture failed: {exc}")
            return
        self._i += 1
        self.progress.emit(self._i, self.total)
        if self._i >= self.total:
            self._teardown()
            try:
                self.finalize()
            except Exception as exc:  # noqa: BLE001
                self.failed.emit(f"Saving failed: {exc}")
                return
            self.finished.emit(self._output_dir)
            return
        self._project_for_index()

    def _teardown(self) -> None:
        self._active = False
        try:
            self._camera.frameReady.disconnect(self._on_frame)
        except (TypeError, RuntimeError):
            pass
