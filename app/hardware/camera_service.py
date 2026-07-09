"""Persistent camera ownership: open once, serve frames for the app lifetime.

The Spinnaker SDK is unstable under repeated System init/teardown cycles: a
capture design that opens and closes the device per run eventually dies with a
native access violation (observed live), and a killed process leaves the driver
handle poisoned (-1004) for the next open. This service opens the camera once
on its own thread and keeps it until shutdown; everything else borrows frames.

Two modes, switched by the capture layer:

* Stream (default): grab continuously, keep the latest frame, and emit
  `frameReady` at a throttled rate -- the live view the aim guide watches.
* Step (during a capture): streaming pauses and each `grab_step()` performs
  exactly one camera grab on the service thread. This preserves the classic
  project -> settle -> grab semantics, and keeps the synthetic DummyCamera's
  one-phase-step-per-grab behavior exact for the offline tests.

All device calls stay on this one thread (PySpin wants that); other threads
talk to it through locks and request objects.
"""
from __future__ import annotations

import threading
import time

from PySide6.QtCore import QThread, Signal

from logbus import get_logger

log = get_logger("camera")

# Stream pacing: cap the grab loop (the synthetic camera returns instantly and
# would otherwise spin a core) and throttle UI-bound frame emissions.
_MIN_GRAB_PERIOD_S = 0.02
_EMIT_PERIOD_S = 0.10


class _StepRequest:
    """One step-mode grab: created by the caller, fulfilled on the service
    thread, waited on by the caller."""

    def __init__(self) -> None:
        self._done = threading.Event()
        self._frame = None
        self._error: str | None = None

    def deliver(self, frame) -> None:
        self._frame = frame
        self._done.set()

    def fail(self, message: str) -> None:
        self._error = message
        self._done.set()

    def wait(self, timeout_s: float):
        if not self._done.wait(timeout_s):
            raise RuntimeError("camera frame request timed out")
        if self._error is not None:
            raise RuntimeError(self._error)
        return self._frame


class CameraService(QThread):
    """Owns a `hardware.camera.Camera` for the app's lifetime and serves
    frames to the live view (stream mode) and to captures (step mode)."""

    # Latest stream frame (throttled); connect for a live camera view.
    frameReady = Signal(object)
    # The camera could not be opened or died mid-stream.
    failed = Signal(str)

    def __init__(self, camera, parent=None) -> None:
        super().__init__(parent)
        self._camera = camera
        self._cond = threading.Condition()
        self._latest = None
        self._seq = 0
        self._stop = False
        self._step_mode = False
        self._requests: list[_StepRequest] = []
        self._ready = threading.Event()
        self._error: str | None = None

    # -- thread body -----------------------------------------------------------

    def run(self) -> None:
        try:
            self._camera.open()
        except Exception as exc:  # noqa: BLE001 - report device open failure
            self._error = str(exc)
            self._ready.set()
            self.failed.emit(f"camera open failed: {exc}")
            return
        self._ready.set()
        log.info(f"camera service streaming ({self._camera.name})")
        last_emit = 0.0
        try:
            while True:
                with self._cond:
                    if self._stop:
                        break
                    request = self._requests.pop(0) if self._requests else None
                    stepping = self._step_mode
                if request is not None:
                    try:
                        request.deliver(self._camera.grab())
                    except Exception as exc:  # noqa: BLE001 - fail that request
                        request.fail(str(exc))
                    continue
                if stepping:
                    # Idle between step grabs; requests arrive via the list.
                    time.sleep(0.005)
                    continue
                t0 = time.monotonic()
                try:
                    frame = self._camera.grab()
                except Exception as exc:  # noqa: BLE001 - stream died
                    self._error = str(exc)
                    self.failed.emit(f"camera grab failed: {exc}")
                    break
                with self._cond:
                    self._latest = frame
                    self._seq += 1
                    self._cond.notify_all()
                now = time.monotonic()
                if now - last_emit >= _EMIT_PERIOD_S:
                    last_emit = now
                    self.frameReady.emit(frame)
                spare = _MIN_GRAB_PERIOD_S - (now - t0)
                if spare > 0:
                    time.sleep(spare)
        finally:
            with self._cond:
                pending, self._requests = self._requests, []
            for request in pending:
                request.fail("camera service stopped")
            try:
                self._camera.close()
            except Exception:  # noqa: BLE001 - best-effort release
                pass
            log.info("camera service stopped")

    # -- calling-thread API ------------------------------------------------------

    def wait_ready(self, timeout_s: float = 10.0) -> None:
        """Block until the camera is open (or raise with its open error)."""
        if not self._ready.wait(timeout_s):
            raise RuntimeError("camera service did not become ready")
        if self._error is not None:
            raise RuntimeError(self._error)

    def acquire_step(self, n_steps: int) -> None:
        """Enter step mode for a capture: streaming pauses, and each
        `grab_step()` maps to exactly one camera grab."""
        self.wait_ready()
        self._camera.set_sequence(n_steps)
        with self._cond:
            self._step_mode = True

    def release_step(self) -> None:
        """Leave step mode; streaming resumes."""
        with self._cond:
            self._step_mode = False

    def grab_step(self, timeout_s: float = 10.0):
        """One freshly exposed frame, grabbed on the service thread."""
        self.wait_ready()
        request = _StepRequest()
        with self._cond:
            self._requests.append(request)
        return request.wait(timeout_s)

    def latest(self):
        """The most recent stream frame (None before the first grab)."""
        with self._cond:
            return self._latest

    def wait_fresh(self, min_advance: int = 2, timeout_s: float = 5.0):
        """A stream frame at least `min_advance` grabs newer than now (i.e.
        exposed after the call), for callers that need a post-event frame."""
        with self._cond:
            target = self._seq + min_advance
            end = time.monotonic() + timeout_s
            while self._seq < target:
                remaining = end - time.monotonic()
                if remaining <= 0 or self._stop:
                    raise RuntimeError("timed out waiting for a fresh frame")
                self._cond.wait(remaining)
            return self._latest

    def stop_service(self, timeout_ms: int = 5000) -> None:
        """Stop streaming, close the camera, and join the thread."""
        with self._cond:
            self._stop = True
            self._cond.notify_all()
        if not self.wait(timeout_ms):
            log.warning("camera service did not stop in time")
