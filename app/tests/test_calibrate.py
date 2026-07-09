"""backend.calibrate: recover a known camera angle from synthetic captures.

The synthetic camera is an affine warp of each projected pattern: an in-plane
rotation composed with a cos(theta) compression along the (rotated) tilt axis,
plus an isotropic scale -- exactly the image a telecentric camera at angle
theta produces of a projector-normal plane. Ground truth in, angle out.
"""
from __future__ import annotations

import math

import cv2
import numpy as np
import pytest

from backend.calibrate import (
    box_aspect_angle,
    calibration_patterns,
    phase_gradient_angle,
    psa_phase,
    run,
)

PROJ_W, PROJ_H = 320, 256
CAM_W, CAM_H = 400, 360


def _camera_matrix(theta_deg: float, rot_deg: float, scale: float) -> np.ndarray:
    """Projector px -> camera px: compress by cos(theta) along the tilt axis
    (rotated by rot_deg in the camera image), scale isotropically, and center
    the projected field in the camera frame."""
    theta = math.radians(theta_deg)
    rot = math.radians(rot_deg)
    compress = np.array([[math.cos(theta) * scale, 0.0], [0.0, scale]])
    rotate = np.array([[math.cos(rot), -math.sin(rot)],
                       [math.sin(rot), math.cos(rot)]])
    a = rotate @ compress
    center_proj = np.array([PROJ_W / 2.0, PROJ_H / 2.0])
    center_cam = np.array([CAM_W / 2.0, CAM_H / 2.0])
    t = center_cam - a @ center_proj
    return np.hstack([a, t[:, None]])


def _capture(pattern: np.ndarray, m: np.ndarray) -> np.ndarray:
    return cv2.warpAffine(pattern, m, (CAM_W, CAM_H),
                          flags=cv2.INTER_LINEAR, borderValue=0)


def _synthetic_stacks(theta_deg: float, rot_deg: float, scale: float = 0.6):
    spec = calibration_patterns(PROJ_W, PROJ_H)
    m = _camera_matrix(theta_deg, rot_deg, scale)
    frames = [_capture(p, m) for p in spec.patterns]
    return spec, frames


def test_phase_gradient_recovers_angle_and_axis():
    spec, frames = _synthetic_stacks(theta_deg=41.0, rot_deg=10.0)
    result = _phase_result(spec, frames)
    assert result["theta_deg"] == pytest.approx(41.0, abs=0.5)
    assert result["tilt_axis_deg"] == pytest.approx(10.0, abs=2.0)
    # Camera px per projector px: scale*cos(theta) along the tilt, scale across.
    assert result["scale_tilt"] == pytest.approx(0.6 * math.cos(math.radians(41.0)), rel=0.02)
    assert result["scale_perp"] == pytest.approx(0.6, rel=0.02)


def _phase_result(spec, frames):
    stack_v = np.stack([f.astype(np.float64) for f in frames[1:1 + spec.n_steps]])
    stack_h = np.stack([f.astype(np.float64) for f in frames[1 + spec.n_steps:]])
    phase_v, mod_v = psa_phase(stack_v)
    phase_h, mod_h = psa_phase(stack_h)
    mask = (mod_v >= 5.0) & (mod_h >= 5.0)
    return phase_gradient_angle(phase_v, phase_h, mask,
                                spec.n_periods, spec.proj_w, spec.proj_h)


def test_phase_gradient_mid_angle():
    spec, frames = _synthetic_stacks(theta_deg=20.0, rot_deg=5.0, scale=0.57)
    result = _phase_result(spec, frames)
    assert result["theta_deg"] == pytest.approx(20.0, abs=1.0)
    assert result["tilt_axis_deg"] == pytest.approx(5.0, abs=3.0)


def test_phase_gradient_flat_view_stays_small():
    # A flat (normal) view sits at the acos degeneracy: near ratio=1, tiny
    # gradient errors read as degrees, so the readout only has to stay small.
    # The scale is chosen so the fringe period is not an integer number of
    # camera px; an aligned period makes the 8-bit quantization ripple
    # systematic instead of dithering out in the median.
    spec, frames = _synthetic_stacks(theta_deg=0.0, rot_deg=0.0, scale=0.57)
    result = _phase_result(spec, frames)
    assert result["theta_deg"] < 5.0


def test_box_aspect_recovers_axis_aligned_angle():
    spec, frames = _synthetic_stacks(theta_deg=41.0, rot_deg=0.0)
    result = box_aspect_angle(frames[0])
    assert not result["touches_border"]
    assert result["theta_deg"] == pytest.approx(41.0, abs=1.0)


def test_box_aspect_flags_border_contact():
    # A camera framing so tight the box spills past the frame edge.
    spec = calibration_patterns(PROJ_W, PROJ_H)
    m = _camera_matrix(theta_deg=20.0, rot_deg=0.0, scale=3.0)
    frame = _capture(spec.patterns[0], m)
    result = box_aspect_angle(frame)
    assert result["touches_border"]


def test_run_writes_report_and_compares_methods(tmp_path):
    spec, frames = _synthetic_stacks(theta_deg=41.0, rot_deg=0.0)
    capture_dir = tmp_path / "calibration"
    capture_dir.mkdir()
    for k, frame in enumerate(frames):
        assert cv2.imwrite(str(capture_dir / f"frame_{k:02d}.png"), frame)

    metrics = run(capture_dir, capture_dir, spec)
    assert metrics["theta_phase_deg"] == pytest.approx(41.0, abs=0.5)
    assert metrics["theta_box_deg"] == pytest.approx(41.0, abs=1.0)
    assert metrics["delta_deg"] < 1.5
    # valid_fraction is coverage of the whole camera frame; the synthetic
    # projected field (320x256 at scale 0.6, compressed by cos 41 deg) covers
    # about 15% of the 400x360 frame.
    assert 0.10 < metrics["valid_fraction"] < 0.30

    report = (capture_dir / "calibration.txt").read_text(encoding="ascii")
    assert "Phase-gradient method" in report
    assert "Box-aspect method" in report
    assert "Difference between methods" in report
    assert (capture_dir / "calibration_phase_v.png").exists()
    assert (capture_dir / "calibration_phase_h.png").exists()


def test_run_rejects_wrong_frame_count(tmp_path):
    spec = calibration_patterns(PROJ_W, PROJ_H)
    capture_dir = tmp_path / "calibration"
    capture_dir.mkdir()
    cv2.imwrite(str(capture_dir / "frame_00.png"),
                np.zeros((CAM_H, CAM_W), dtype=np.uint8))
    with pytest.raises(ValueError, match="expected"):
        run(capture_dir, capture_dir, spec)
