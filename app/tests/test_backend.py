"""Backend abstraction + hardware capture path.

Covers the seam that lets the UI run unchanged against the simulation or real
hardware: the factory's backend selection, the shared fringe pattern, the
synthetic camera, and a full hardware project->capture->reconstruct loop (with
the synthetic camera, so no device is needed). The scored simulation path is
covered by the simulation's own test suite; here we prove the *hardware* path
produces a frame stack and a ground-truth-less height map.
"""
from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QEventLoop, QTimer

from backend import Backend, SimulationBackend, create_backend
from backend.base import fringe_pattern
from backend.hardware import HardwareBackend
from hardware.camera import DummyCamera, open_camera


# -- factory / selection -----------------------------------------------------

def test_factory_defaults_to_simulation():
    backend = create_backend("sim")
    assert isinstance(backend, SimulationBackend)
    assert backend.kind == "sim"


def test_factory_selects_hardware():
    backend = create_backend("hardware")
    assert isinstance(backend, HardwareBackend)
    assert backend.kind == "hardware"
    assert backend.available_surfaces() == ["live"]


def test_unknown_backend_falls_back_to_sim():
    assert isinstance(create_backend("nonsense"), SimulationBackend)


def test_both_backends_are_backends():
    for b in (create_backend("sim"), create_backend("hardware")):
        assert isinstance(b, Backend)


# -- shared projected pattern ------------------------------------------------

def test_fringe_pattern_shape_and_range():
    img = fringe_pattern(8.0, phase=0.0, width=200, height=100)
    assert img.shape == (100, 200)
    assert img.dtype == np.uint8
    assert img.min() < 10 and img.max() > 245  # spans the full 0..255 swing


def test_fringe_phase_shift_changes_the_pattern():
    a = fringe_pattern(8.0, phase=0.0, width=200, height=10)
    b = fringe_pattern(8.0, phase=0.25, width=200, height=10)
    assert not np.array_equal(a, b)


def test_backend_generate_fringe_uses_its_n_periods():
    backend = create_backend("hardware")
    img = backend.generate_fringe(width=128, height=64)
    assert img.shape == (64, 128)


# -- rig preview (simulation only) --------------------------------------------

def test_rig_preview_command_describes_a_blender_run(tmp_path, monkeypatch):
    monkeypatch.setenv("MP_BLENDER", "/stub/blender")
    monkeypatch.setenv("MP_OUT_DIR", str(tmp_path))
    backend = SimulationBackend()
    spec = backend.rig_preview_command(samples=16)
    assert spec.argv[0] == "/stub/blender"
    assert any(arg.endswith("rig_preview.py") for arg in spec.argv)
    # A script failure must fail the run: Blender's default exit code is 0
    # even when -P raises, so the argv has to opt into propagation.
    assert "--python-exit-code" in spec.argv
    assert spec.argv[spec.argv.index("--samples") + 1] == "16"
    out = backend.rig_preview_path()
    assert out == tmp_path / "rig_model" / "overview_annotated.png"
    assert spec.argv[spec.argv.index("--out") + 1] == str(out)
    # No view args -> the script's default framing (no orbit flags at all).
    assert "--azimuth" not in spec.argv


def test_rig_preview_command_orbits_the_viewpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("MP_BLENDER", "/stub/blender")
    monkeypatch.setenv("MP_OUT_DIR", str(tmp_path))
    spec = SimulationBackend().rig_preview_command(azimuth=30.0, elevation=55.5, distance=0.8)
    assert spec.argv[spec.argv.index("--azimuth") + 1] == "30"
    assert spec.argv[spec.argv.index("--elevation") + 1] == "55.5"
    assert spec.argv[spec.argv.index("--distance") + 1] == "0.8"


def test_rig_preview_is_simulation_only():
    assert not hasattr(create_backend("hardware"), "rig_preview_command")


# -- synthetic camera --------------------------------------------------------

def test_open_camera_dummy():
    cam = open_camera("dummy")
    assert isinstance(cam, DummyCamera)


def test_dummy_camera_advances_phase():
    cam = DummyCamera(width=64, height=32)
    cam.set_sequence(4)
    with cam:
        frames = [cam.grab() for _ in range(4)]
    for f in frames:
        assert f.shape == (32, 64) and f.dtype == np.uint8
    # consecutive phase steps differ; the sequence repeats after N
    assert not np.array_equal(frames[0], frames[1])
    cam2 = DummyCamera(width=64, height=32)
    cam2.set_sequence(4)
    cam2.open()
    first_cycle = [cam2.grab() for _ in range(4)]
    assert np.array_equal(frames[0], first_cycle[0])  # deterministic (seeded)


# -- full hardware capture loop (synthetic camera, no device) ----------------

def _run_capture(controller, **kwargs) -> dict:
    """Start a capture and pump the event loop until it terminates."""
    outcome: dict = {}
    loop = QEventLoop()
    controller.finished.connect(lambda code: (outcome.update(code=code), loop.quit()))
    controller.failed.connect(lambda msg: (outcome.update(failed=msg), loop.quit()))
    QTimer.singleShot(20000, loop.quit)  # safety: never hang the suite
    controller.start(**kwargs)
    loop.exec()
    return outcome


def test_hardware_capture_and_reconstruct(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("MP_OUT_DIR", str(tmp_path))
    monkeypatch.setenv("MP_CAMERA", "dummy")

    backend = create_backend("hardware")
    controller = backend.new_capture_controller()

    outcome = _run_capture(
        controller, surface="live", n_steps=8, subdir="capture", settle_ms=1
    )
    assert outcome.get("code") == 0, f"capture failed: {outcome}"

    frames = sorted(controller.capture_dir.glob("frame_*.png"))
    assert len(frames) == 8
    assert controller.n_steps == 8

    # Reconstruct the (ground-truth-less) real capture: height map, no score.
    result = backend.reconstruct("live")
    assert result.height_png.exists()
    assert "rmse" not in result.metrics  # nothing to score a real target against
    assert result.metrics["valid_pixels"] > 0


def test_hardware_multifreq_ladder_capture_and_reconstruct(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("MP_OUT_DIR", str(tmp_path))
    monkeypatch.setenv("MP_CAMERA", "dummy")

    backend = create_backend("hardware")
    controller = backend.new_capture_controller()

    # Walk a 2-rung ladder through the one controller, each rung into its own
    # capture_f<i> subdir -- exactly what the UI's multi-frequency pipeline does.
    ladder = [8.0, 24.0]
    for i, n in enumerate(ladder):
        outcome = _run_capture(
            controller, surface="live", n_steps=8,
            subdir=backend.multifreq_subdir(i), n_periods=n, settle_ms=1,
        )
        assert outcome.get("code") == 0, f"rung {i} failed: {outcome}"

    for d in backend.multifreq_capture_dirs("live", len(ladder)):
        assert len(sorted(d.glob("frame_*.png"))) == 8

    result = backend.reconstruct_multifreq("live", n_periods_ladder=ladder)
    assert result.height_png.exists()
    assert "rmse" not in result.metrics  # live target: no ground truth
    assert result.metrics["valid_pixels"] > 0
    assert result.metrics["n_periods_ladder"] == ladder


def test_capture_rejects_concurrent_start(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("MP_OUT_DIR", str(tmp_path))
    monkeypatch.setenv("MP_CAMERA", "dummy")
    backend = create_backend("hardware")
    controller = backend.new_capture_controller()
    controller.start(surface="live", n_steps=2, subdir="capture", settle_ms=1)
    with pytest.raises(RuntimeError):
        controller.start(surface="live", n_steps=2, subdir="capture", settle_ms=1)
    # drain so the worker thread finishes cleanly before the test ends
    loop = QEventLoop()
    controller.finished.connect(lambda _c: loop.quit())
    controller.failed.connect(lambda _m: loop.quit())
    QTimer.singleShot(20000, loop.quit)
    loop.exec()
