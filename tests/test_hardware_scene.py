"""Unit tests for src/gui/hardware_scene.py — Stage 4b sub-task 3.

The tests target the pure-NumPy `compute_arm_transforms()` function;
they do NOT launch a QApplication or construct `HardwareScene`. The
GUI wrapper is exercised by the smoke-test screenshots, not unit
tests — keeping the test suite Qt-free, consistent with the rest of
the project.

Coverage (10 cases)
-------------------
  1. test_compute_transforms_returns_four_named_matrices
  2. test_initial_pose_at_zero_zero_default_distances
  3. test_distinct_arm_transforms_at_asymmetric_pose
  4. test_camera_distance_affects_camera_transforms_only
  5. test_projector_lens_x_offset_applied
  6. test_lens_closer_to_origin_than_body
  7. test_projector_lens_anchored_at_origin_when_vertical   (4d.10)
  8. test_projector_body_hangs_off_axis_when_vertical       (4d.10)
  9. test_camera_lens_still_at_origin_when_vertical         (4d.10)
 10. test_projector_lens_stays_on_arm_axis_across_theta     (4d.10)

Tolerances
----------
- Position: `atol=1e-4` mm. The transform pipeline accumulates
  trig-of-degree-to-radian + matrix multiplies in float32; worst-case
  ULP drift on a 182 mm input is ~2e-5 mm. 1e-4 is comfortably loose.
- Projector lens X offset value check: `atol=1e-4` mm.
"""
from __future__ import annotations

import numpy as np

from gui.hardware_scene import (
    KEY_CAMERA_BODY,
    KEY_CAMERA_LENS,
    KEY_PROJECTOR_BODY,
    KEY_PROJECTOR_LENS,
    PROJECTOR_LENS_OFFSET_MM,
    PROJECTOR_LENS_X_OFFSET_MM,
    compute_arm_transforms,
)
from scene_compose import body_lens_offset, projector_arm_transform


def _origin_in_world(M: np.ndarray) -> np.ndarray:
    """Apply 4x4 transform to (0,0,0,1) and return the (x, y, z) part."""
    return (M @ np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32))[:3].astype(
        np.float64
    )


# ---------------------------------------------------------------------------
# Test 1 — Return contract: 4 named (4,4) float32 matrices.
# ---------------------------------------------------------------------------
def test_compute_transforms_returns_four_named_matrices():
    result = compute_arm_transforms(
        theta_camera_deg=0.0,
        theta_projector_deg=0.0,
        projector_distance_mm=150.0,
        camera_distance_mm=157.0,
    )
    assert set(result.keys()) == {
        KEY_CAMERA_BODY,
        KEY_CAMERA_LENS,
        KEY_PROJECTOR_BODY,
        KEY_PROJECTOR_LENS,
    }
    for key, M in result.items():
        assert M.shape == (4, 4), f"{key} shape {M.shape}"
        assert M.dtype == np.float32, f"{key} dtype {M.dtype}"


# ---------------------------------------------------------------------------
# Test 2 — Initial pose at zero-zero with the WD convention.
#
# Distance sliders are interpreted as lens-front-to-surface (Edmund WD
# / Pico Genie throw). Body sits further along the arm by lens_length
# + body_depth/2:
#   camera_body_z    = cam_wd + 200 + 15  = cam_wd + 215
#   projector_body_z = proj_throw + 5 + 27.5 = proj_throw + 32.5
# Lens centers sit body_depth/2 + lens_length/2 closer to the surface
# than the body center (world -Z at theta=0 after R_x(pi)):
#   camera_lens_z    = camera_body_z   - 115
#   projector_lens_z = projector_body_z - 30
# Lens *front* (the surface-facing end) lands at exactly cam_wd /
# proj_throw above the surface — that's the construction.
# ---------------------------------------------------------------------------
def test_initial_pose_at_zero_zero_default_distances():
    proj_throw = 150.0
    cam_wd = 157.0
    result = compute_arm_transforms(
        theta_camera_deg=0.0,
        theta_projector_deg=0.0,
        projector_distance_mm=proj_throw,
        camera_distance_mm=cam_wd,
    )

    expected_cam_body_z = cam_wd + 200.0 + 15.0    # 372
    expected_proj_body_z = proj_throw + 5.0 + 27.5  # 182.5

    cam_body_pos = _origin_in_world(result[KEY_CAMERA_BODY])
    np.testing.assert_allclose(
        cam_body_pos, [0.0, 0.0, expected_cam_body_z], atol=1e-4
    )

    cam_lens_pos = _origin_in_world(result[KEY_CAMERA_LENS])
    np.testing.assert_allclose(
        cam_lens_pos, [0.0, 0.0, expected_cam_body_z - 115.0], atol=1e-4
    )

    # 4d.10 anchoring: the LENS CENTER is parked over world (0,0) when
    # vertical, so the BODY hangs off-axis by the negative of the in-face
    # lens offset: (-face_x, +face_vertical) = (+6.5, +17.5) in world XY
    # (face_vertical maps to world -Y, and the body shift is -face_vertical,
    # so it lands at +face_vertical). Body Z is unchanged (shift is in-plane).
    proj_body_pos = _origin_in_world(result[KEY_PROJECTOR_BODY])
    np.testing.assert_allclose(
        proj_body_pos,
        [
            -PROJECTOR_LENS_OFFSET_MM.face_x,
            PROJECTOR_LENS_OFFSET_MM.face_vertical,
            expected_proj_body_z,
        ],
        atol=1e-4,
    )

    # Lens center lands back on the arm axis: world (0, 0, body_z - 30).
    proj_lens_pos = _origin_in_world(result[KEY_PROJECTOR_LENS])
    np.testing.assert_allclose(
        proj_lens_pos,
        [0.0, 0.0, expected_proj_body_z - 30.0],
        atol=1e-4,
    )


# ---------------------------------------------------------------------------
# Test 3 — Asymmetric pose: camera and projector transforms differ.
#
# Picks `theta_cam = 20, theta_proj = -20` so the two arms swing to
# opposite sides. The camera and projector body world X-coordinates
# must therefore differ.
# ---------------------------------------------------------------------------
def test_distinct_arm_transforms_at_asymmetric_pose():
    result = compute_arm_transforms(
        theta_camera_deg=20.0,
        theta_projector_deg=-20.0,
        projector_distance_mm=120.0,
        camera_distance_mm=157.0,
    )
    cam_body_x = _origin_in_world(result[KEY_CAMERA_BODY])[0]
    proj_body_x = _origin_in_world(result[KEY_PROJECTOR_BODY])[0]
    # Camera tilts to +X (+20°), projector tilts to -X (-20°).
    # cam_body_x > 0 and proj_body_x < 0 (so their difference is
    # substantial and signed in the expected direction).
    assert cam_body_x > 10.0, f"camera body X={cam_body_x} not on +X side"
    assert proj_body_x < -10.0, f"projector body X={proj_body_x} not on -X side"


# ---------------------------------------------------------------------------
# Test 4 — Camera distance affects only the camera arm's transforms.
#
# Catches a cross-wiring bug where varying `camera_distance` leaks
# into the projector arm. Compares two evaluations that differ only
# in `camera_distance_mm`.
# ---------------------------------------------------------------------------
def test_camera_distance_affects_camera_transforms_only():
    a = compute_arm_transforms(
        theta_camera_deg=30.0,
        theta_projector_deg=30.0,
        projector_distance_mm=150.0,
        camera_distance_mm=157.0,
    )
    b = compute_arm_transforms(
        theta_camera_deg=30.0,
        theta_projector_deg=30.0,
        projector_distance_mm=150.0,
        camera_distance_mm=182.0,
    )

    # Camera body + lens translations must differ (we pulled the camera
    # back by 25 mm; the body should move noticeably).
    cam_body_delta = np.linalg.norm(
        _origin_in_world(a[KEY_CAMERA_BODY]) - _origin_in_world(b[KEY_CAMERA_BODY])
    )
    cam_lens_delta = np.linalg.norm(
        _origin_in_world(a[KEY_CAMERA_LENS]) - _origin_in_world(b[KEY_CAMERA_LENS])
    )
    assert cam_body_delta > 1.0, f"camera body did not move (delta={cam_body_delta})"
    assert cam_lens_delta > 1.0, f"camera lens did not move (delta={cam_lens_delta})"

    # Projector body + lens translations must NOT change.
    np.testing.assert_allclose(
        _origin_in_world(a[KEY_PROJECTOR_BODY]),
        _origin_in_world(b[KEY_PROJECTOR_BODY]),
        atol=1e-6,
    )
    np.testing.assert_allclose(
        _origin_in_world(a[KEY_PROJECTOR_LENS]),
        _origin_in_world(b[KEY_PROJECTOR_LENS]),
        atol=1e-6,
    )


# ---------------------------------------------------------------------------
# Test 5 — Pico Genie face-X offset is preserved between body and lens.
#
# After 4d.10 anchoring the absolute positions moved (lens on-axis, body
# off-axis), but the body->lens face-X relationship is invariant: at
# theta=0 the lens X sits exactly face_x (= -6.5) mm relative to the body
# X. (Here body_x = +6.5, lens_x = 0, so lens_x - body_x = -6.5.) A sign
# error in either the body anchor or the lens re-offset would break this.
# ---------------------------------------------------------------------------
def test_projector_lens_x_offset_applied():
    result = compute_arm_transforms(
        theta_camera_deg=0.0,
        theta_projector_deg=0.0,
        projector_distance_mm=150.0,
        camera_distance_mm=157.0,
    )
    body_x = _origin_in_world(result[KEY_PROJECTOR_BODY])[0]
    lens_x = _origin_in_world(result[KEY_PROJECTOR_LENS])[0]
    assert lens_x - body_x == np.float32(PROJECTOR_LENS_X_OFFSET_MM)


# ---------------------------------------------------------------------------
# Test 6 — Lens sits CLOSER to origin than the body it's attached to.
#
# The lens hangs out in front of the body's surface-facing face, between
# the body and the world origin. Sub-task 2's smoke-test screenshot
# confirmed this orientation. A `body_lens_offset` sign error would put
# the lens behind the body (further from origin) and this test would
# catch it.
# ---------------------------------------------------------------------------
def test_lens_closer_to_origin_than_body():
    result = compute_arm_transforms(
        theta_camera_deg=30.0,
        theta_projector_deg=30.0,
        projector_distance_mm=150.0,
        camera_distance_mm=157.0,
    )
    cam_body_dist = np.linalg.norm(_origin_in_world(result[KEY_CAMERA_BODY]))
    cam_lens_dist = np.linalg.norm(_origin_in_world(result[KEY_CAMERA_LENS]))
    proj_body_dist = np.linalg.norm(_origin_in_world(result[KEY_PROJECTOR_BODY]))
    proj_lens_dist = np.linalg.norm(_origin_in_world(result[KEY_PROJECTOR_LENS]))

    assert cam_lens_dist < cam_body_dist, (
        f"camera lens (d={cam_lens_dist:.2f}) is not closer to origin "
        f"than camera body (d={cam_body_dist:.2f})"
    )
    assert proj_lens_dist < proj_body_dist, (
        f"projector lens (d={proj_lens_dist:.2f}) is not closer to origin "
        f"than projector body (d={proj_body_dist:.2f})"
    )


# ---------------------------------------------------------------------------
# Test 7 (4d.10) — Projector lens center is anchored over world (0,0) when
# the projector points straight down (theta=0). This is the headline of the
# geometry correction: the lens, not the body, sits on the optical axis.
# ---------------------------------------------------------------------------
def test_projector_lens_anchored_at_origin_when_vertical():
    result = compute_arm_transforms(
        theta_camera_deg=0.0,
        theta_projector_deg=0.0,
        projector_distance_mm=150.0,
        camera_distance_mm=157.0,
    )
    lens_xy = _origin_in_world(result[KEY_PROJECTOR_LENS])[:2]
    np.testing.assert_allclose(lens_xy, [0.0, 0.0], atol=1e-4)


# ---------------------------------------------------------------------------
# Test 8 (4d.10) — The body hangs off-axis once the lens is anchored: it
# carries the negative of the in-face offset, landing at world XY
# (-face_x, +face_vertical) = (+6.5, +17.5) when vertical.
# ---------------------------------------------------------------------------
def test_projector_body_hangs_off_axis_when_vertical():
    result = compute_arm_transforms(
        theta_camera_deg=0.0,
        theta_projector_deg=0.0,
        projector_distance_mm=150.0,
        camera_distance_mm=157.0,
    )
    body_xy = _origin_in_world(result[KEY_PROJECTOR_BODY])[:2]
    np.testing.assert_allclose(
        body_xy,
        [-PROJECTOR_LENS_OFFSET_MM.face_x, PROJECTOR_LENS_OFFSET_MM.face_vertical],
        atol=1e-4,
    )


# ---------------------------------------------------------------------------
# Test 9 (4d.10) — Regression: the camera lens is centered (no offset) and
# must remain anchored at world (0,0) when vertical. The projector
# correction must not perturb the camera arm.
# ---------------------------------------------------------------------------
def test_camera_lens_still_at_origin_when_vertical():
    result = compute_arm_transforms(
        theta_camera_deg=0.0,
        theta_projector_deg=0.0,
        projector_distance_mm=150.0,
        camera_distance_mm=157.0,
    )
    cam_lens_xy = _origin_in_world(result[KEY_CAMERA_LENS])[:2]
    np.testing.assert_allclose(cam_lens_xy, [0.0, 0.0], atol=1e-4)


# ---------------------------------------------------------------------------
# Test 10 (4d.10) — The anchor holds at every theta, not just vertical: the
# body shift is body-local, so the lens center stays exactly on the arm
# axis as the arm swings. Compare the lens origin against an offset-free
# (centered) lens placed on the same arm.
# ---------------------------------------------------------------------------
def test_projector_lens_stays_on_arm_axis_across_theta():
    throw = 150.0
    body_dist = throw + 32.5  # lens_length 5 + body_depth/2 27.5
    for theta in (-40.0, -10.0, 25.0, 60.0):
        result = compute_arm_transforms(
            theta_camera_deg=0.0,
            theta_projector_deg=theta,
            projector_distance_mm=throw,
            camera_distance_mm=157.0,
        )
        lens_pos = _origin_in_world(result[KEY_PROJECTOR_LENS])
        # An offset-free lens on the same arm: body center -> lens midpoint
        # along body-local +Z, no in-face shift. The anchored lens must land
        # exactly here at every theta.
        on_axis = _origin_in_world(
            projector_arm_transform(theta, body_dist) @ body_lens_offset(55.0, 5.0)
        )
        np.testing.assert_allclose(
            lens_pos, on_axis, atol=1e-4,
            err_msg=f"lens off the arm axis at theta={theta}",
        )
