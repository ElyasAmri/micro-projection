"""Hardware capture: project each phase-shifted fringe, grab a camera frame.

This is the hardware counterpart to the simulation's Blender render. It walks an
N-step phase sequence: show pattern k on the projector, let it settle, grab a
frame, write it as `frame_kk.png` -- producing exactly the `frame_*.png` stack
the shared reconstruction consumes, so downstream nothing knows or cares that
the frames came from a camera rather than a renderer.

The camera is opened, read, and closed entirely on a worker thread (PySpin
wants all its calls on one thread, and grabbing must not block the GUI). The
projector is a GUI-thread widget, so the worker asks it to change pattern via a
`BlockingQueuedConnection` signal -- the worker blocks until the pattern is
actually on screen, then waits `settle_ms` for the display + exposure to settle
before grabbing, so every frame is imaged *after* its pattern is up.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal

from backend.base import fringe_pattern
from backend.capture import CaptureController
from logbus import get_logger

log = get_logger("capture")

DEFAULT_SETTLE_MS = 200  # projector refresh + camera exposure settle per step


class _CaptureWorker(QThread):
    """Runs the project-and-grab sequence off the GUI thread."""

    line = Signal(str)
    failed = Signal(str)
    finished_ok = Signal(int)
    show_pattern = Signal(object)  # -> projector.show_pattern (blocking, GUI thread)

    def __init__(self, patterns, camera, capture_dir: Path, settle_ms: int,
                 parent=None) -> None:
        super().__init__(parent)
        self._patterns = patterns
        self._camera = camera
        self._dir = capture_dir
        self._settle_ms = settle_ms

    def run(self) -> None:
        import cv2

        n = len(self._patterns)
        try:
            self._camera.set_sequence(n)
            self._camera.open()
        except Exception as exc:  # noqa: BLE001 - report device open failure
            self.failed.emit(f"camera open failed: {exc}")
            return
        try:
            for k, pattern in enumerate(self._patterns):
                self.show_pattern.emit(pattern)     # blocks until on screen
                self.msleep(self._settle_ms)        # let display + exposure settle
                frame = self._camera.grab()
                path = self._dir / f"frame_{k:02d}.png"
                if not cv2.imwrite(str(path), frame):
                    raise RuntimeError(f"could not write {path}")
                self.line.emit(f"[capture] frame {k + 1}/{n} captured")
            self.line.emit(f"Captured {n} frames to {self._dir}")
        except Exception as exc:  # noqa: BLE001 - surface any capture failure
            self.failed.emit(f"capture failed: {exc}")
            return
        finally:
            try:
                self._camera.close()
            except Exception:  # noqa: BLE001 - best-effort release
                pass
        self.finished_ok.emit(0)


class HardwareCapture(CaptureController):
    """Async project-and-grab capture wired to a projector + a camera factory.
    Presents the same interface as the simulation's `BlenderCapture`, so the UI
    drives both identically."""

    def __init__(self, projector, camera_factory, n_periods: float,
                 out_root: Path, parent=None) -> None:
        super().__init__(parent)
        self._projector = projector
        self._camera_factory = camera_factory
        self._n_periods = n_periods
        self._out_root = out_root
        self._worker: _CaptureWorker | None = None

    def is_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def start(self, *, surface: str, n_steps: int, subdir: str,
              n_periods: float | None = None, settle_ms: int | None = None,
              **_kwargs) -> None:
        if self.is_running():
            raise RuntimeError("a capture is already running")
        n = self._n_periods if n_periods is None else n_periods
        if settle_ms is None:
            settle_ms = int(os.environ.get("MP_CAPTURE_SETTLE_MS", DEFAULT_SETTLE_MS))

        capture_dir = self._out_root / "app" / surface / subdir
        capture_dir.mkdir(parents=True, exist_ok=True)
        for stale in capture_dir.glob("frame_*.png"):  # don't mix runs
            stale.unlink()
        self.capture_dir = capture_dir
        self.n_steps = n_steps

        # Show the projector and match the pattern resolution to its screen so
        # the fringe maps 1:1 (both must happen on the GUI thread, here).
        window = self._projector.ensure_shown()
        width, height = self._projector.screen_size()
        patterns = [
            fringe_pattern(n, phase=(k / n_steps if n_steps else 0.0),
                           width=width, height=height)
            for k in range(n_steps)
        ]

        camera = self._camera_factory(n_periods=n)
        worker = _CaptureWorker(patterns, camera, capture_dir, settle_ms, self)
        worker.line.connect(self.line)
        worker.failed.connect(self._on_failed)
        worker.finished_ok.connect(self._on_finished)
        # Blocking so the worker waits until the pattern is actually displayed.
        worker.show_pattern.connect(window.show_pattern, Qt.BlockingQueuedConnection)
        self._worker = worker
        worker.start()

    def _on_finished(self, code: int) -> None:
        self._worker = None
        self.finished.emit(code)

    def _on_failed(self, message: str) -> None:
        self._worker = None
        self.failed.emit(message)
