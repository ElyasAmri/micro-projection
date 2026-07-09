"""backend.aim: recover a known aim offset from synthetic captures.

Same synthetic-camera scheme as test_calibrate: each projected pattern is
warped by a known affine (tilt compression, scale, translation); the aim
measurements must read back the offset that the translation implies.
"""
from __future__ import annotations

import math

import cv2
import numpy as np
import pytest

from backend.aim import (
    find_marker,
    load_frames,
    locate_patterns,
    marker_pattern,
    measure_from_marker,
    measure_from_phase,
    offset_metrics,
    write_report,
)

PROJ_W, PROJ_H = 320, 256
CAM_W, CAM_H = 400, 360
GEOMETRY = {"cam_mm_per_px_x": 0.05, "cam_mm_per_px_y": 0.05,
            "design_theta_deg": 38.7}


def _camera_matrix(theta_deg: float, scale: float,
                   center_shift_cam_px: tuple) -> np.ndarray:
    """Projector px -> camera px, with the projector field center landing
    `center_shift_cam_px` away from the camera frame center."""
    theta = math.radians(theta_deg)
    a = np.array([[math.cos(theta) * scale, 0.0], [0.0, scale]])
    center_proj = np.array([PROJ_W / 2.0, PROJ_H / 2.0])
    target = np.array([CAM_W / 2.0 + center_shift_cam_px[0],
                       CAM_H / 2.0 + center_shift_cam_px[1]])
    t = target - a @ center_proj
    return np.hstack([a, t[:, None]])


def _capture(pattern: np.ndarray, m: np.ndarray) -> np.ndarray:
    return cv2.warpAffine(pattern, m, (CAM_W, CAM_H),
                          flags=cv2.INTER_LINEAR, borderValue=0)


def test_marker_measures_known_offset():
    m = _camera_matrix(theta_deg=38.7, scale=0.6, center_shift_cam_px=(30, -20))
    frame = _capture(marker_pattern(PROJ_W, PROJ_H), m)
    metrics = measure_from_marker(frame, GEOMETRY)
    dx, dy = metrics["offset_cam_px"]
    assert dx == pytest.approx(30.0, abs=1.0)
    assert dy == pytest.approx(-20.0, abs=1.0)
    assert metrics["pan"] == ("right", "up")
    assert metrics["distance_mm"] == pytest.approx(0.05 * math.hypot(30, 20), rel=0.05)
    assert not metrics["marker_touches_border"]


def test_marker_not_in_view_raises():
    frame = np.zeros((CAM_H, CAM_W), dtype=np.uint8)
    with pytest.raises(ValueError, match="dark"):
        find_marker(frame)


def test_ambient_flooded_frame_rejected():
    # Auto-exposure on a mostly-dark projection lifts the whole scene to
    # mid-gray; the brightest "blob" is then the scene, not the marker.
    frame = np.full((CAM_H, CAM_W), 120, dtype=np.uint8)
    frame[:, -40:] = 30  # a darker strip so the blob is not the full frame
    with pytest.raises(ValueError, match="ambient|flooding"):
        find_marker(frame)


def test_marker_clipped_at_border_is_flagged():
    # Shift the marker so it straddles the camera frame edge.
    m = _camera_matrix(theta_deg=0.0, scale=0.6,
                       center_shift_cam_px=(CAM_W / 2.0 - 2, 0))
    frame = _capture(marker_pattern(PROJ_W, PROJ_H), m)
    result = find_marker(frame)
    assert result["touches_border"]


def test_absolute_phase_measures_known_offset():
    shift = (40.0, -25.0)  # camera px
    scale = 0.6
    m = _camera_matrix(theta_deg=38.7, scale=scale, center_shift_cam_px=shift)
    frames = [_capture(p, m) for p in locate_patterns(PROJ_W, PROJ_H)]
    metrics = measure_from_phase(frames, PROJ_W, PROJ_H, geometry=GEOMETRY)
    # The camera center sits `shift` away from where the field center lands,
    # so in projector coordinates it looks at center - A^-1 @ shift.
    a_inv = np.linalg.inv(m[:, :2])
    expected = a_inv @ np.array(shift)
    du, dv = metrics["offset_proj_px"]
    assert du == pytest.approx(expected[0], abs=2.0)
    assert dv == pytest.approx(expected[1], abs=2.0)
    assert metrics["pan"] == ("right", "up")


def test_absolute_phase_dark_center_raises():
    frames = [np.zeros((CAM_H, CAM_W), dtype=np.uint8) for _ in range(16)]
    with pytest.raises(ValueError, match="no projected light"):
        measure_from_phase(frames, PROJ_W, PROJ_H, geometry=GEOMETRY)


def test_report_and_frame_loading(tmp_path):
    m = _camera_matrix(theta_deg=38.7, scale=0.6, center_shift_cam_px=(10, 5))
    frame = _capture(marker_pattern(PROJ_W, PROJ_H), m)
    assert cv2.imwrite(str(tmp_path / "frame_00.png"), frame)
    frames = load_frames(tmp_path)
    assert len(frames) == 1

    metrics = measure_from_marker(frames[0], GEOMETRY)
    write_report(tmp_path / "aim.txt", metrics)
    report = (tmp_path / "aim.txt").read_text(encoding="ascii")
    assert "pan the camera" in report
    assert "mm on the plane" in report


def test_offset_metrics_without_geometry_reports_px_only():
    metrics = offset_metrics(12.0, -8.0, "marker",
                             {"cam_mm_per_px_x": None, "cam_mm_per_px_y": None,
                              "design_theta_deg": None})
    assert metrics["offset_mm"] == (None, None)
    assert metrics["distance_mm"] is None
    assert metrics["offset_cam_px"] == (12.0, -8.0)
