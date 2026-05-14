"""Unit tests for src/scene_compose.py — Stage 4b pose-composition layer.

Coverage
--------
- `test_arm_transform_placement_and_lens_axis` (6 cases) — parametrized
  over `(transform_fn, theta_deg)` for both camera and projector arms at
  three angles each (0°, +30°, -30°). Each case verifies:
    (a) The body-local origin maps to world position
        `(d * sin(theta), 0, d * cos(theta))`.
    (b) The body-local +Z direction maps to a unit vector pointing from
        the placed body back at the world origin (i.e., the lens
        optical axis aims at the surface center).

  Three angles per arm constrain three independent positions and
  three independent direction vectors. Together these implicitly
  validate the rotation block is orthonormal (no scaling/skew), so we
  skip a dedicated SE(3) validity test.

- `test_body_lens_offset_is_pure_translation` (1 case) — rotation block
  is the identity; only the (0,3), (1,3), (2,3) translation entries
  carry data.

- `test_body_lens_offset_camera_assembly_z` and
  `test_body_lens_offset_projector_assembly_z` (2 cases) — z-translation
  matches `body/2 + lens/2` per the module spec (camera: 30/2 + 200/2 =
  115 mm; projector: 55/2 + 5/2 = 30 mm).

Tolerances
----------
Float32 + degree-to-radian + trig means worst-case round-off is small
but non-zero. `atol = 1e-4` for positions in mm (157 mm * float32_eps ~=
1e-5; with trig accumulation, 1e-4 is safe). Direction vectors are
normalized so `atol = 1e-6` works for those.
"""
from __future__ import annotations

import numpy as np
import pytest

from scene_compose import (
    body_lens_offset,
    camera_arm_transform,
    projector_arm_transform,
)


CAM_DIST_MM = 157.0
PROJ_DIST_MM = 150.0


def _apply(M: np.ndarray, point_or_dir: np.ndarray) -> np.ndarray:
    """Apply a 4x4 row-major transform to a 4-vector and return the (x, y, z) part."""
    out = M @ point_or_dir
    return np.asarray(out[:3], dtype=np.float64)


# ---------------------------------------------------------------------------
# Placement + lens axis: 6 parametrized cases (2 fns x 3 angles).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "transform_fn,distance_mm,theta_deg",
    [
        (camera_arm_transform,    CAM_DIST_MM,  0.0),
        (camera_arm_transform,    CAM_DIST_MM, +30.0),
        (camera_arm_transform,    CAM_DIST_MM, -30.0),
        (projector_arm_transform, PROJ_DIST_MM, 0.0),
        (projector_arm_transform, PROJ_DIST_MM, +30.0),
        (projector_arm_transform, PROJ_DIST_MM, -30.0),
    ],
    ids=[
        "camera_0deg", "camera_+30deg", "camera_-30deg",
        "projector_0deg", "projector_+30deg", "projector_-30deg",
    ],
)
def test_arm_transform_placement_and_lens_axis(transform_fn, distance_mm, theta_deg):
    M = transform_fn(theta_deg, distance_mm)
    assert M.shape == (4, 4)
    assert M.dtype == np.float32

    theta_rad = np.deg2rad(theta_deg)
    expected_pos = np.array(
        [
            distance_mm * np.sin(theta_rad),
            0.0,
            distance_mm * np.cos(theta_rad),
        ],
        dtype=np.float64,
    )

    # (a) Local origin maps to expected arm-end position.
    placed_origin = _apply(M, np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32))
    np.testing.assert_allclose(placed_origin, expected_pos, atol=1e-4)

    # (b) Local +Z direction maps to the unit vector pointing back at
    # the world origin from the placed position.
    # Note: pass a direction vector (w=0) so translation doesn't apply.
    placed_local_z = _apply(M, np.array([0.0, 0.0, 1.0, 0.0], dtype=np.float32))
    expected_dir = -expected_pos / np.linalg.norm(expected_pos)
    np.testing.assert_allclose(placed_local_z, expected_dir, atol=1e-6)


# ---------------------------------------------------------------------------
# body_lens_offset — pure-translation property and value checks.
# ---------------------------------------------------------------------------
def test_body_lens_offset_is_pure_translation():
    # Try a couple of (body, lens) arg combinations; rotation block must be I.
    for body_mm, lens_mm in [(30.0, 200.0), (55.0, 5.0), (10.0, 10.0)]:
        M = body_lens_offset(body_mm, lens_mm)
        assert M.shape == (4, 4)
        assert M.dtype == np.float32

        # Rotation block (top-left 3x3) is identity.
        np.testing.assert_allclose(
            M[:3, :3], np.eye(3, dtype=np.float32), atol=1e-6
        )
        # No translation in X or Y (Pico Genie's off-center X is composed
        # at sub-task 3 GUI assembly time, not here).
        assert M[0, 3] == 0.0
        assert M[1, 3] == 0.0
        # Bottom row is (0, 0, 0, 1).
        np.testing.assert_allclose(
            M[3], np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32), atol=1e-6
        )


def test_body_lens_offset_camera_assembly_z():
    # Camera: body 30 mm deep, lens 200 mm long.
    # tz = 30/2 + 200/2 = 115 mm
    M = body_lens_offset(30.0, 200.0)
    assert M[2, 3] == pytest.approx(115.0, abs=1e-6)


def test_body_lens_offset_projector_assembly_z():
    # Projector: body 55 mm deep, lens 5 mm long.
    # tz = 55/2 + 5/2 = 30 mm
    M = body_lens_offset(55.0, 5.0)
    assert M[2, 3] == pytest.approx(30.0, abs=1e-6)
