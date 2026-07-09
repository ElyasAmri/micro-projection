"""hardware.camera_service: persistent ownership, stream + step modes."""
from __future__ import annotations

import time

import numpy as np
import pytest

from hardware.camera import Camera, DummyCamera
from hardware.camera_service import CameraService


class FailingCamera(Camera):
    """A camera whose open always fails (device missing)."""

    def open(self) -> None:
        raise RuntimeError("no device attached")

    def grab(self):  # pragma: no cover - never reached
        raise AssertionError

    def close(self) -> None:
        pass


def _service(width: int = 64, height: int = 32) -> CameraService:
    return CameraService(DummyCamera(width=width, height=height))


def test_stream_produces_frames_and_stops_cleanly():
    service = _service()
    service.start()
    try:
        service.wait_ready()
        frame = service.wait_fresh(min_advance=2, timeout_s=5.0)
        assert frame.shape == (32, 64) and frame.dtype == np.uint8
        assert service.latest() is not None
    finally:
        service.stop_service()
    assert service.isFinished()


def test_step_mode_pauses_stream_and_steps_phases():
    service = _service()
    service.start()
    try:
        service.wait_ready()
        service.wait_fresh(min_advance=1)
        service.acquire_step(4)
        seq_before = service._seq
        frames = [service.grab_step() for _ in range(4)]
        # Streaming is paused: the stream sequence number did not advance.
        assert service._seq == seq_before
        assert all(f.shape == (32, 64) for f in frames)
        # set_sequence reset the synthetic phase, so steps differ pairwise
        # and the cycle wraps after N.
        assert not np.array_equal(frames[0], frames[1])
        assert not np.array_equal(frames[1], frames[2])
        service.release_step()
        # Streaming resumes after release.
        service.wait_fresh(min_advance=2, timeout_s=5.0)
    finally:
        service.stop_service()


def test_open_failure_reports_and_raises(qapp):
    service = CameraService(FailingCamera())
    failures: list[str] = []
    service.failed.connect(failures.append)
    service.start()
    with pytest.raises(RuntimeError, match="no device"):
        service.wait_ready(timeout_s=5.0)
    service.wait(5000)
    # The queued signal needs the event loop to deliver.
    end = time.monotonic() + 5.0
    while not failures and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.005)
    assert failures and "no device" in failures[0]


class CountingCamera(DummyCamera):
    """A dummy that counts live settings pushes."""

    def __init__(self) -> None:
        super().__init__(width=64, height=32)
        self.applied = 0

    def apply_settings(self) -> None:
        self.applied += 1


def test_request_apply_settings_runs_on_service_thread():
    camera = CountingCamera()
    service = CameraService(camera)
    service.start()
    try:
        service.wait_ready()
        service.request_apply_settings()
        end = time.monotonic() + 5.0
        while camera.applied == 0 and time.monotonic() < end:
            time.sleep(0.01)
        assert camera.applied == 1
        # Also honored while a capture holds step mode.
        service.acquire_step(2)
        service.request_apply_settings()
        end = time.monotonic() + 5.0
        while camera.applied == 1 and time.monotonic() < end:
            time.sleep(0.01)
        assert camera.applied == 2
        service.release_step()
    finally:
        service.stop_service()


def test_grab_step_after_stop_raises():
    service = _service()
    service.start()
    service.wait_ready()
    service.stop_service()
    with pytest.raises(RuntimeError):
        service.grab_step(timeout_s=0.5)
