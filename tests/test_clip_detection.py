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

Sub-task 4d.12 — cross-arm optical-obstruction advisories
---------------------------------------------------------
Each assembly's body+lens box edges are sampled against the OTHER
arm's optical volume, axially bounded to the lens->surface segment.
Tests cover: the camera assembly obstructing the projector cone (the
live photo case) and the projector obstructing the camera prism; a
clean V-rig firing neither (and proving no arm self-triggers on its
own volume); the axial bound excluding behind-lens / beyond-surface
hardware; and edge-sampling catching a box spearing a volume with all
8 corners outside (corner-only would miss it).
"""
from __future__ import annotations

import numpy as np
import pytest

from gui.clip_detection import (
    KEY_CAMERA_BODY,
    KEY_CAMERA_LENS,
    KEY_PROJECTOR_BODY,
    KEY_PROJECTOR_LENS,
    MSG_BODY_OVERLAP,
    MSG_CAMERA_IN_PROJECTOR_CONE,
    MSG_CAMERA_SURFACE,
    MSG_PROJECTOR_IN_CAMERA_FOV,
    MSG_PROJECTOR_SURFACE,
    MSG_SURFACE_OUTSIDE_CONE,
    MSG_SURFACE_OUTSIDE_FOV,
    _CONE_HALF_U_PER_L,
    _CONE_HALF_V_PER_L,
    _LOCAL_CORNERS,
    _box_edge_samples,
    _local_bbox_corners,
    _points_in_cone,
    _points_in_prism,
    detect_clips,
)
from scene import (
    PICO_GENIE,
    WINTECH_PRO4500,
    make_projector_body,
    make_projector_lens,
)
from gui.hardware_scene import (
    _CAMERA_BODY_DEPTH_MM,
    _CAMERA_LENS_LENGTH_MM,
    _PROJECTOR_BODY_DEPTH_MM,
    _PROJECTOR_LENS_LENGTH_MM,
    KEY_CAMERA_BODY as HS_KEY_CAMERA_BODY,
    KEY_PROJECTOR_BODY as HS_KEY_PROJECTOR_BODY,
    PROJECTOR_LENS_OFFSET_MM,
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
        x_offset_mm=PROJECTOR_LENS_OFFSET_MM.face_x,
        y_offset_mm=PROJECTOR_LENS_OFFSET_MM.face_vertical,
        recess_mm=PROJECTOR_LENS_OFFSET_MM.recess,
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


# ---------------------------------------------------------------------------
# 12 — Projector-cone coverage: 2 mm advisory tolerance silences a
# documented sub-mm hairline trigger.
# ---------------------------------------------------------------------------
def test_no_cone_clip_at_documented_hairline_pose():
    """At theta_cam=0, theta_proj=-41, throw=149, WD=157 the projector
    cone spilled by 0.40 mm at two FOV-patch corners under the strict
    (pre-tolerance) check (read-only probe on fringe_demo_block_draft.stl).
    The 2 mm advisory tolerance silences this honest-but-hairline trigger.

    Reproduced with a flat 15 mm slab filling the FOV: the diagnosed
    spill sat at the -X / +/-Y corners at z=15 mm, which this synthetic
    surface places at the same world points (no STL fixture needed).
    """
    t = compute_arm_transforms(
        theta_camera_deg=0.0,
        theta_projector_deg=-41.0,
        projector_distance_mm=149.0,
        camera_distance_mm=157.0,
    )
    viewing, projection = _cone_worlds(t)
    hm = np.full((550, 680), 15.0, dtype=np.float64)
    state = detect_clips(
        t,
        heightmap_mm=hm,
        surface_pixel_size_mm=0.1,
        camera_distance_mm=157.0,
        projector_distance_mm=149.0,
        viewing_cone_world=viewing,
        projection_cone_world=projection,
    )
    assert not state.surface_outside_projector_cone
    assert MSG_SURFACE_OUTSIDE_CONE not in state.messages


# ===========================================================================
# Sub-task 4d.12 — cross-arm optical-obstruction advisories.
# ===========================================================================

# ---------------------------------------------------------------------------
# 13 — Camera assembly inside the projector cone (the live photo case):
# both arms same side, camera tilted -50, projector -25, wide throw=200.
# The camera body/lens crosses the projection beam before it reaches the
# surface. Advisory fires; banner-only so no collision flag is set.
# ---------------------------------------------------------------------------
def test_camera_assembly_obstructs_projector_cone():
    t = compute_arm_transforms(
        theta_camera_deg=-50.0,
        theta_projector_deg=-25.0,
        projector_distance_mm=200.0,
        camera_distance_mm=157.0,
    )
    viewing, projection = _cone_worlds(t)
    state = detect_clips(
        t,
        camera_distance_mm=157.0,
        projector_distance_mm=200.0,
        viewing_cone_world=viewing,
        projection_cone_world=projection,
    )
    assert state.camera_in_projector_cone
    assert MSG_CAMERA_IN_PROJECTOR_CONE in state.messages
    # Advisory only — no physical collision at this pose.
    assert not state.bodies_overlapping
    assert not state.camera_clipping_surface
    assert not state.projector_in_camera_fov


# ---------------------------------------------------------------------------
# 14 — Projector assembly inside the camera viewing prism: projector
# vertical (theta=0), camera tilted -25 toward it at a short WD-ish throw.
# The projector body (off-axis at +6.5,+17.5 when vertical) sits in the
# camera's line of sight. Advisory fires, banner-only.
# ---------------------------------------------------------------------------
def test_projector_assembly_obstructs_camera_view():
    t = compute_arm_transforms(
        theta_camera_deg=-25.0,
        theta_projector_deg=0.0,
        projector_distance_mm=100.0,
        camera_distance_mm=157.0,
    )
    viewing, projection = _cone_worlds(t)
    state = detect_clips(
        t,
        camera_distance_mm=157.0,
        projector_distance_mm=100.0,
        viewing_cone_world=viewing,
        projection_cone_world=projection,
    )
    assert state.projector_in_camera_fov
    assert MSG_PROJECTOR_IN_CAMERA_FOV in state.messages
    assert not state.bodies_overlapping
    assert not state.camera_in_projector_cone


# ---------------------------------------------------------------------------
# 15 — Clean V-rig: neither obstruction advisory fires. Also proves no arm
# self-triggers on its own volume — the camera lens front sits AT the prism
# origin and the projector lens AT the cone apex; if the pairing weren't
# strictly cross, those would false-fire even here.
# ---------------------------------------------------------------------------
def test_no_obstruction_at_clean_v_rig():
    t = compute_arm_transforms(
        theta_camera_deg=-20.0,
        theta_projector_deg=30.0,
        projector_distance_mm=150.0,
        camera_distance_mm=157.0,
    )
    viewing, projection = _cone_worlds(t)
    state = detect_clips(
        t,
        camera_distance_mm=157.0,
        projector_distance_mm=150.0,
        viewing_cone_world=viewing,
        projection_cone_world=projection,
    )
    assert not state.camera_in_projector_cone
    assert not state.projector_in_camera_fov
    assert MSG_CAMERA_IN_PROJECTOR_CONE not in state.messages
    assert MSG_PROJECTOR_IN_CAMERA_FOV not in state.messages


# ---------------------------------------------------------------------------
# 16 — Axial-bound guard (predicate level): a point laterally inside the
# volume but BEHIND the lens (s<0) or BEYOND the surface (s>max) must be
# excluded by the finite axial_max, yet INCLUDED by the unbounded coverage
# default (axial_max=inf) — locking the behavior-preserving coverage path.
# ---------------------------------------------------------------------------
def test_axial_bound_excludes_behind_and_beyond():
    world = np.eye(4, dtype=np.float64)  # origin 0, axis +Z, u=X, v=Y
    behind = np.array([[0.0, 0.0, -50.0]])   # s = -50
    beyond = np.array([[0.0, 0.0, 300.0]])   # s = 300
    within = np.array([[0.0, 0.0, 100.0]])   # s = 100

    # Prism — unbounded (coverage): along-axis is ignored, so behind AND
    # beyond are both "inside" laterally.
    assert _points_in_prism(world, behind).all()
    assert _points_in_prism(world, beyond).all()
    # Bounded to WD=157 (obstruction): both excluded, within kept.
    assert not _points_in_prism(world, behind, axial_max=157.0).any()
    assert not _points_in_prism(world, beyond, axial_max=157.0).any()
    assert _points_in_prism(world, within, axial_max=157.0).all()

    # Cone — unbounded keeps beyond (cone diverges past throw); bounded
    # drops it. (Behind the apex is excluded either way: cone needs s>=0.)
    assert _points_in_cone(world, beyond).all()
    assert not _points_in_cone(world, beyond, axial_max=150.0).any()
    assert _points_in_cone(world, within, axial_max=150.0).all()
    assert not _points_in_cone(world, behind).any()


# ---------------------------------------------------------------------------
# 17 — Edge-sampling vs corner-only (the recon-Q3 rationale): a long thin
# box whose 8 corners are ALL outside the cone but whose long edge spears
# straight through it. Corner-only sampling reports nothing; edge-sampling
# catches the crossing. This is why the 200 mm camera lens needs edges.
# ---------------------------------------------------------------------------
def test_edge_sampling_catches_box_spearing_cone():
    world = np.eye(4, dtype=np.float64)  # apex 0, axis +Z; half-U ~ 0.42*z
    # Box at z~100 (cone half-width there ~ 43.7 mm) spanning x = +/-100:
    # every corner has |x| = 100 -> outside; the x-edge crosses x=0 -> in.
    corners = _local_bbox_corners(
        np.array([[-100.0, -5.0, 99.0], [100.0, 5.0, 101.0]])
    )
    # Corner-only: nothing inside.
    assert not _points_in_cone(world, corners).any()
    # Edge-sampling: the long edge's interior samples land inside.
    samples = _box_edge_samples(corners)
    assert _points_in_cone(world, samples).any()


# ===========================================================================
# Stage 6 projector-swap 3a — detect_clips(projector_profile=PICO_GENIE) is
# field-for-field identical to the cached (no-profile) live path. The Pico-
# derived projector bbox equals the module-cached bbox, so the body-overlap
# (SAT) and cross-arm obstruction checks (the local_corners consumers) produce
# identical ClipStates. Poses chosen to trigger those branches.
# ===========================================================================
_EQ_POSES = [
    (20.0, -20.0, 150.0, 157.0),   # clean V-rig
    (30.0, 30.0, 150.0, 157.0),    # bodies overlap (SAT reads projector corners)
    (70.0, -20.0, 150.0, 132.0),   # camera lens clips surface
    (-50.0, -25.0, 200.0, 157.0),  # camera assembly in projector cone (obstruction)
    (-25.0, 0.0, 100.0, 157.0),    # projector assembly in camera FOV (obstruction)
    (0.0, -41.0, 149.0, 157.0),    # steep projector, 15 mm slab
]


@pytest.mark.parametrize(
    "theta_cam,theta_proj,throw,wd", _EQ_POSES,
    ids=["vrig", "overlap", "cam_clip", "cam_in_cone", "proj_in_fov", "steep"],
)
def test_detect_clips_pico_profile_matches_cached(theta_cam, theta_proj, throw, wd):
    """detect_clips(projector_profile=PICO_GENIE) == the no-profile cached path,
    field-for-field (all seven booleans + messages order)."""
    t = compute_arm_transforms(
        theta_camera_deg=theta_cam, theta_projector_deg=theta_proj,
        projector_distance_mm=throw, camera_distance_mm=wd,
    )
    viewing, projection = _cone_worlds(t)
    hm = np.full((550, 680), 15.0, dtype=np.float64)
    kwargs = dict(
        heightmap_mm=hm, surface_pixel_size_mm=0.1,
        camera_distance_mm=wd, projector_distance_mm=throw,
        viewing_cone_world=viewing, projection_cone_world=projection,
    )
    cached = detect_clips(t, **kwargs)                            # projector_profile=None
    pico = detect_clips(t, **kwargs, projector_profile=PICO_GENIE)
    assert cached == pico            # @dataclass eq: every field incl. messages
    assert cached.messages == pico.messages   # order, asserted explicitly


def test_derived_pico_bbox_equals_cached():
    """The on-demand Pico-derived projector bbox equals the module-cached bbox —
    the foundation of 3a's byte-identity through the profile=PICO_GENIE path."""
    np.testing.assert_array_equal(
        _local_bbox_corners(make_projector_body(PICO_GENIE)[0]),
        _LOCAL_CORNERS[KEY_PROJECTOR_BODY],
    )
    np.testing.assert_array_equal(
        _local_bbox_corners(make_projector_lens(PICO_GENIE)[0]),
        _LOCAL_CORNERS[KEY_PROJECTOR_LENS],
    )


# ===========================================================================
# Stage 6 projector-swap 3b — profile-aware cone-coverage slopes. Pico (and any
# lens-table-less profile) keeps the throw-ratio module-constant slopes EXACTLY;
# an FOV-rated lens (PRO4500) uses (fov_w/2)/WD, (fov_h/2)/WD. The lateral swap
# leaves axial handling untouched (a Pico-slopes==module-constants guard).
# ===========================================================================
def test_points_in_cone_default_slopes_are_module_constants():
    """_points_in_cone with no slope args == passing the module constants (the
    Pico throw-ratio slopes) — pins that part-4 does not shift Pico laterally,
    and that axial handling is unchanged."""
    world = np.eye(4, dtype=np.float64)  # apex 0, axis +Z
    # A point near the throw-ratio cone boundary at s=100 (half-width ~43.7).
    pts = np.array([[40.0, 0.0, 100.0], [60.0, 0.0, 100.0], [0.0, 0.0, -10.0]])
    default = _points_in_cone(world, pts)
    explicit = _points_in_cone(
        world, pts, half_u_per_l=_CONE_HALF_U_PER_L, half_v_per_l=_CONE_HALF_V_PER_L,
    )
    np.testing.assert_array_equal(default, explicit)
    # Axial unchanged: the behind-apex point (s<0) is excluded either way.
    assert not default[2]


def test_pro4500_fov_slopes_differ_and_flip_inclusion():
    """The PRO4500 default (184 mm) lens FOV slopes differ from the throw-ratio
    constants, and a point between the two boundary widths flips inclusion."""
    lens = WINTECH_PRO4500.lens_options[WINTECH_PRO4500.default_lens_index]
    assert (lens.fov_w_mm, lens.working_distance_mm) == (131.2, 184.0)  # the default lens
    fov_u = (lens.fov_w_mm / 2.0) / lens.working_distance_mm   # 65.6/184 ~ 0.3565
    fov_v = (lens.fov_h_mm / 2.0) / lens.working_distance_mm   # 41/184 ~ 0.2228
    assert abs(fov_u - _CONE_HALF_U_PER_L) > 1e-3   # genuinely different
    assert abs(fov_v - _CONE_HALF_V_PER_L) > 1e-3

    world = np.eye(4, dtype=np.float64)
    s = lens.working_distance_mm                      # axial = WD (184)
    # FOV half-width here ~65.6 mm; throw-ratio half-width ~76.7 mm. A point at
    # lateral 70 is inside the throw-ratio cone but OUTSIDE the narrower FOV cone.
    pt = np.array([[70.0, 0.0, s]])
    assert _points_in_cone(world, pt)[0]                                   # throw-ratio: inside
    assert not _points_in_cone(world, pt, half_u_per_l=fov_u, half_v_per_l=fov_v)[0]  # FOV: outside


def test_detect_clips_coverage_uses_active_profile_slopes():
    """Same cone world + surface, different projector profile -> the cone-
    coverage advisory flips, because PRO4500's FOV cone is narrower than Pico's
    throw-ratio cone at the same working distance."""
    wd = 184.0
    t = compute_arm_transforms(
        theta_camera_deg=0.0, theta_projector_deg=0.0,
        projector_distance_mm=wd, camera_distance_mm=157.0,
    )
    viewing, projection = _cone_worlds(t)
    # Flat slab ~ +/-72 mm wide (x) but only +/-20 mm tall (y): the x corners
    # sit inside Pico's wide throw-ratio cone at WD (half-width ~79 mm) but
    # outside the narrower PRO4500 default-lens FOV cone (131.2 mm -> half-width
    # ~68 mm); the y extent is inside both. So the cone-coverage advisory fires
    # for PRO4500 only.
    # shape (H, W): H rows -> y (+/-20), W cols -> x (+/-72), at 0.1 mm/px.
    hm = np.zeros((400, 1440), dtype=np.float64)
    kwargs = dict(
        heightmap_mm=hm, surface_pixel_size_mm=0.1,
        camera_distance_mm=157.0, projector_distance_mm=wd,
        viewing_cone_world=viewing, projection_cone_world=projection,
    )
    pico = detect_clips(t, **kwargs, projector_profile=PICO_GENIE)
    pro = detect_clips(t, **kwargs, projector_profile=WINTECH_PRO4500)
    assert not pico.surface_outside_projector_cone   # throw-ratio cone covers it
    assert pro.surface_outside_projector_cone        # FOV cone does not


# ===========================================================================
# Stage 6 projector-swap 4 — active-lens index threading.
# ===========================================================================
def test_detect_clips_active_lens_index_default_is_default_lens_index():
    """Omitting active_lens_index == passing the profile's default_lens_index —
    the additive byte-identical guard so 3b-era calls are unchanged."""
    wd = 184.0
    t = compute_arm_transforms(
        theta_camera_deg=0.0, theta_projector_deg=0.0,
        projector_distance_mm=wd, camera_distance_mm=157.0,
    )
    viewing, projection = _cone_worlds(t)
    hm = np.zeros((400, 1440), dtype=np.float64)
    kwargs = dict(
        heightmap_mm=hm, surface_pixel_size_mm=0.1,
        camera_distance_mm=157.0, projector_distance_mm=wd,
        viewing_cone_world=viewing, projection_cone_world=projection,
        projector_profile=WINTECH_PRO4500,
    )
    omitted = detect_clips(t, **kwargs)
    explicit = detect_clips(t, **kwargs, active_lens_index=WINTECH_PRO4500.default_lens_index)
    assert omitted == explicit


def test_pro4500_lenses_share_cone_half_angle():
    """Both PRO4500 lenses have the SAME cone half-angle: (fov/2)/WD is equal for
    the 92 and 184 mm lenses. So the coverage SLOPE is lens-invariant — the lens
    selector changes coverage via the working distance (apex height), not the
    slope (see the GL update_pose coverage test). Documents why the detect_clips
    active_lens_index has no slope effect for these two specific lenses."""
    near, far = WINTECH_PRO4500.lens_options
    np.testing.assert_allclose(
        (near.fov_w_mm / 2) / near.working_distance_mm,
        (far.fov_w_mm / 2) / far.working_distance_mm, rtol=1e-9,
    )
    np.testing.assert_allclose(
        (near.fov_h_mm / 2) / near.working_distance_mm,
        (far.fov_h_mm / 2) / far.working_distance_mm, rtol=1e-9,
    )
