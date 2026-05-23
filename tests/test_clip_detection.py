"""Unit tests for src/gui/clip_detection.py — Stage 4b task 4.

Pure-NumPy tests against `detect_clips`. Transform dicts are built
via `compute_arm_transforms` (the real pose math) for the slider-
reachable cases, and hand-built for the pathological all-three-clips
case where precise control is easier than reverse-engineering an
arm pose.

Note on extreme angles
----------------------
The GUI theta sliders are clamped to +/-75 deg, but
`compute_arm_transforms` itself has no clamp. The projector-surface-
clip case needs ~85 deg (the 10 mm Pico Genie lens only reaches the
surface plane at a very steep tilt). That's beyond the slider but
valid for exercising the detection logic, which is what these unit
tests verify — the slider clamp is a separate UI concern.

10 cases:
  1.  test_no_clips_at_clean_pose
  2.  test_camera_clip_at_extreme_angle
  3.  test_projector_clip_at_extreme_angle
  4.  test_body_overlap_at_same_side_pose
  5.  test_no_body_overlap_at_v_rig
  6.  test_multiple_clips_at_pathological_pose
  7.  test_surface_outside_camera_fov_lateral   (sub-task 4b.6)
  8.  test_surface_outside_camera_fov_vertical  (sub-task 4b.6)
  9.  test_surface_outside_projector_cone       (sub-task 4b.6)
  10. test_clean_pose_no_coverage_warnings      (sub-task 4b.6)

Sub-task 4b.6 (cases 7-10) — 3D-volume coverage advisories
----------------------------------------------------------
The surface is sampled on an 11x11 grid and each 3D point is tested
against the camera viewing prism / projector cone VOLUME. Case 8 is
the failure mode the old 2D z=0-footprint check missed: a tall
narrow peak whose base is inside the footprint but whose tip pokes
out of the tilted telecentric prism.
"""
from __future__ import annotations

import numpy as np

from gui.clip_detection import (
    KEY_CAMERA_BODY,
    KEY_CAMERA_LENS,
    KEY_PROJECTOR_BODY,
    KEY_PROJECTOR_LENS,
    MSG_BODY_OVERLAP,
    MSG_CAMERA_SURFACE,
    MSG_PROJECTOR_SURFACE,
    MSG_SURFACE_OUTSIDE_CONE,
    MSG_SURFACE_OUTSIDE_FOV,
    detect_clips,
)
from gui.hardware_scene import (
    _CAMERA_BODY_DEPTH_MM,
    _CAMERA_LENS_LENGTH_MM,
    _PROJECTOR_BODY_DEPTH_MM,
    _PROJECTOR_LENS_LENGTH_MM,
    KEY_CAMERA_BODY as HS_KEY_CAMERA_BODY,
    KEY_PROJECTOR_BODY as HS_KEY_PROJECTOR_BODY,
    PROJECTOR_LENS_X_OFFSET_MM,
    compute_arm_transforms,
)
from scene_compose import cone_local_to_world_transform
from test_surfaces import make_gaussian


def _cone_worlds(transforms):
    """(viewing, projection) cone world transforms, built exactly as
    hardware_scene.update_pose does — so coverage tests exercise the
    same geometry the GUI uses, Qt-free."""
    viewing = cone_local_to_world_transform(
        transforms[HS_KEY_CAMERA_BODY],
        lens_length_mm=_CAMERA_LENS_LENGTH_MM,
        body_depth_mm=_CAMERA_BODY_DEPTH_MM,
        x_offset_mm=0.0,
    )
    projection = cone_local_to_world_transform(
        transforms[HS_KEY_PROJECTOR_BODY],
        lens_length_mm=_PROJECTOR_LENS_LENGTH_MM,
        body_depth_mm=_PROJECTOR_BODY_DEPTH_MM,
        x_offset_mm=PROJECTOR_LENS_X_OFFSET_MM,
    )
    return viewing, projection


# ---------------------------------------------------------------------------
# 1 — Clean V-rig: nothing clips.
# ---------------------------------------------------------------------------
def test_no_clips_at_clean_pose():
    t = compute_arm_transforms(
        theta_camera_deg=20.0,
        theta_projector_deg=-20.0,
        projector_distance_mm=150.0,
        camera_distance_mm=157.0,
    )
    state = detect_clips(t)
    assert not state.camera_clipping_surface
    assert not state.projector_clipping_surface
    assert not state.bodies_overlapping
    assert state.messages == []
    assert not state.any_clip


# ---------------------------------------------------------------------------
# 2 — Camera lens dips through the surface at a steep tilt + min WD.
# At theta=70, WD=132: disc_lowest = 132 cos70 - 55 sin70
#                                  = 45.1 - 51.7 = -6.6 < 0.
# ---------------------------------------------------------------------------
def test_camera_clip_at_extreme_angle():
    t = compute_arm_transforms(
        theta_camera_deg=70.0,
        theta_projector_deg=-20.0,
        projector_distance_mm=150.0,
        camera_distance_mm=132.0,
    )
    state = detect_clips(t)
    assert state.camera_clipping_surface
    assert MSG_CAMERA_SURFACE in state.messages
    assert not state.projector_clipping_surface


# ---------------------------------------------------------------------------
# 3 — Projector lens through the surface. The 10 mm lens needs a very
# steep tilt; at min throw (50 mm) the lens-front disc only dips below
# z=0 past ~87 deg (the Pico Genie's -6.5 mm body-frame X offset and
# the body->lens composition shift the front a few mm versus the naive
# WD formula). 88 deg gives a clear ~1.7 mm clip. Beyond the +/-75 deg
# slider clamp but valid for the detection logic (see module docstring).
# ---------------------------------------------------------------------------
def test_projector_clip_at_extreme_angle():
    t = compute_arm_transforms(
        theta_camera_deg=-20.0,
        theta_projector_deg=88.0,
        projector_distance_mm=50.0,
        camera_distance_mm=157.0,
    )
    state = detect_clips(t)
    assert state.projector_clipping_surface
    assert MSG_PROJECTOR_SURFACE in state.messages
    assert not state.camera_clipping_surface


# ---------------------------------------------------------------------------
# 4 — Same-side stack (Stage 4a default-ish): bodies overlap.
# ---------------------------------------------------------------------------
def test_body_overlap_at_same_side_pose():
    t = compute_arm_transforms(
        theta_camera_deg=30.0,
        theta_projector_deg=30.0,
        projector_distance_mm=150.0,
        camera_distance_mm=157.0,
    )
    state = detect_clips(t)
    assert state.bodies_overlapping
    assert MSG_BODY_OVERLAP in state.messages


# ---------------------------------------------------------------------------
# 5 — V-rig (opposite sides): no body overlap.
# ---------------------------------------------------------------------------
def test_no_body_overlap_at_v_rig():
    t = compute_arm_transforms(
        theta_camera_deg=-20.0,
        theta_projector_deg=30.0,
        projector_distance_mm=150.0,
        camera_distance_mm=157.0,
    )
    state = detect_clips(t)
    assert not state.bodies_overlapping
    assert MSG_BODY_OVERLAP not in state.messages


# ---------------------------------------------------------------------------
# 6 — Pathological hand-built pose: all three clips fire at once.
#
# Lens transforms use Rx(180) (flip local +Z to world -Z) plus a small
# +z translation so each lens-front lands below z=0. Bodies sit at
# identity so all four AABBs straddle the origin and overlap.
# ---------------------------------------------------------------------------
def _flip_z_then_translate(tz: float) -> np.ndarray:
    """Rx(180) then translate (0,0,tz): maps local (0,0,zc) -> (0,0,tz-zc)."""
    M = np.eye(4, dtype=np.float32)
    M[1, 1] = -1.0   # Rx(180): y -> -y
    M[2, 2] = -1.0   # Rx(180): z -> -z
    M[2, 3] = tz
    return M


def test_multiple_clips_at_pathological_pose():
    transforms = {
        KEY_CAMERA_BODY: np.eye(4, dtype=np.float32),
        # camera lens front (local z=+100) -> world z = 50 - 100 = -50
        KEY_CAMERA_LENS: _flip_z_then_translate(50.0),
        KEY_PROJECTOR_BODY: np.eye(4, dtype=np.float32),
        # projector lens front (local z=+2.5) -> world z = 1 - 2.5 = -1.5
        KEY_PROJECTOR_LENS: _flip_z_then_translate(1.0),
    }
    state = detect_clips(transforms)
    assert state.camera_clipping_surface
    assert state.projector_clipping_surface
    assert state.bodies_overlapping
    assert MSG_CAMERA_SURFACE in state.messages
    assert MSG_PROJECTOR_SURFACE in state.messages
    assert MSG_BODY_OVERLAP in state.messages
    assert len(state.messages) == 3


# ===========================================================================
# Sub-task 4b.6 — 3D-volume FOV / projector-cone coverage advisories.
# ===========================================================================

# ---------------------------------------------------------------------------
# 7 — Lateral spill: a wide Gaussian (sigma=20) on a 120x120 mm grid
# overflows the ~68 mm-wide telecentric prism even at a clean V-rig.
# Advisory fires; banner-only so no collision flag is set.
# ---------------------------------------------------------------------------
def test_surface_outside_camera_fov_lateral():
    t = compute_arm_transforms(
        theta_camera_deg=-20.0,
        theta_projector_deg=30.0,
        projector_distance_mm=150.0,
        camera_distance_mm=157.0,
    )
    viewing, projection = _cone_worlds(t)
    hm = make_gaussian((121, 121), 1.0, amplitude_mm=10.0, sigma_mm=20.0)
    state = detect_clips(
        t,
        heightmap_mm=hm,
        surface_pixel_size_mm=1.0,
        camera_distance_mm=157.0,
        projector_distance_mm=150.0,
        viewing_cone_world=viewing,
        projection_cone_world=projection,
    )
    assert state.surface_outside_camera_fov
    assert MSG_SURFACE_OUTSIDE_FOV in state.messages
    assert not state.camera_clipping_surface
    assert not state.bodies_overlapping


# ---------------------------------------------------------------------------
# 8 — Vertical spill (the bug the 2D footprint missed): a tall narrow
# Gaussian (amp=100, sigma=8) on the real 68x55 mm grid, camera tilted
# +50 deg. The peak's BASE is inside the footprint but its TIP rises
# out of the tilted prism volume. 3D test catches it.
# ---------------------------------------------------------------------------
def test_surface_outside_camera_fov_vertical():
    t = compute_arm_transforms(
        theta_camera_deg=50.0,
        theta_projector_deg=-30.0,
        projector_distance_mm=150.0,
        camera_distance_mm=157.0,
    )
    viewing, projection = _cone_worlds(t)
    hm = make_gaussian((550, 680), 0.1, amplitude_mm=100.0, sigma_mm=8.0)
    state = detect_clips(
        t,
        heightmap_mm=hm,
        surface_pixel_size_mm=0.1,
        camera_distance_mm=157.0,
        projector_distance_mm=150.0,
        viewing_cone_world=viewing,
        projection_cone_world=projection,
    )
    assert state.surface_outside_camera_fov
    assert MSG_SURFACE_OUTSIDE_FOV in state.messages


# ---------------------------------------------------------------------------
# 9 — Projector cone too small: at throw=50 mm the lit footprint is
# ~42 mm wide, narrower than the 68 mm surface. Clean V-rig, low flat
# Gaussian so the camera prism still covers it (isolating the cone
# advisory).
# ---------------------------------------------------------------------------
def test_surface_outside_projector_cone():
    t = compute_arm_transforms(
        theta_camera_deg=-20.0,
        theta_projector_deg=30.0,
        projector_distance_mm=50.0,
        camera_distance_mm=157.0,
    )
    viewing, projection = _cone_worlds(t)
    hm = make_gaussian((550, 680), 0.1, amplitude_mm=5.0, sigma_mm=8.0)
    state = detect_clips(
        t,
        heightmap_mm=hm,
        surface_pixel_size_mm=0.1,
        camera_distance_mm=157.0,
        projector_distance_mm=50.0,
        viewing_cone_world=viewing,
        projection_cone_world=projection,
    )
    assert state.surface_outside_projector_cone
    assert MSG_SURFACE_OUTSIDE_CONE in state.messages
    assert not state.surface_outside_camera_fov
    assert not state.bodies_overlapping


# ---------------------------------------------------------------------------
# 10 — Clean baseline: real 68x55 mm surface, default-ish V-rig,
# mid-range Gaussian. Both coverage checks pass, nothing fires.
# ---------------------------------------------------------------------------
def test_clean_pose_no_coverage_warnings():
    t = compute_arm_transforms(
        theta_camera_deg=-20.0,
        theta_projector_deg=30.0,
        projector_distance_mm=150.0,
        camera_distance_mm=157.0,
    )
    viewing, projection = _cone_worlds(t)
    hm = make_gaussian((550, 680), 0.1, amplitude_mm=10.0, sigma_mm=8.0)
    state = detect_clips(
        t,
        heightmap_mm=hm,
        surface_pixel_size_mm=0.1,
        camera_distance_mm=157.0,
        projector_distance_mm=150.0,
        viewing_cone_world=viewing,
        projection_cone_world=projection,
    )
    assert not state.surface_outside_camera_fov
    assert not state.surface_outside_projector_cone
    assert not state.any_clip
    assert state.messages == []


# ---------------------------------------------------------------------------
# 11 — SAT body-overlap regression: two poses the old assembly-AABB check
# flagged as overlapping despite several cm of true clearance.
# ---------------------------------------------------------------------------
def test_no_body_overlap_at_documented_false_positive_poses():
    """Two poses the old assembly-AABB check flagged as overlapping
    despite >2 cm of true clearance (read-only OBB probes measured
    31.6 mm and 22.3 mm). SAT must report no overlap at both.

    Pose 1: a long camera lens tilted -45 deg inflated its world AABB
    into the projector body's box. Pose 2: an ordinary symmetric 30/30
    close pose did the same. Locks the SAT fix against regression.
    """
    fp = compute_arm_transforms(
        theta_camera_deg=-13.0,
        theta_projector_deg=-45.0,
        projector_distance_mm=200.0,
        camera_distance_mm=180.0,
    )
    fp_state = detect_clips(fp)
    assert not fp_state.bodies_overlapping
    assert MSG_BODY_OVERLAP not in fp_state.messages

    sym = compute_arm_transforms(
        theta_camera_deg=30.0,
        theta_projector_deg=30.0,
        projector_distance_mm=50.0,
        camera_distance_mm=132.0,
    )
    assert not detect_clips(sym).bodies_overlapping
