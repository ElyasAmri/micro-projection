r"""clip_detection.py — advisory collision checks for the lab scene.

Stage 4b task 4. Pure NumPy. No Qt / pyqtgraph imports. The math
layer purity principle (PROJECT_CONTEXT Sec 7.2) carries forward:
this module imports only `scene` (itself pure NumPy) to read the
hardware meshes' local bounding boxes.

All checks are advisory (the math pipeline keeps running
regardless — a silly rig still produces a valid forward/inverse
simulation; these warnings just tell the user the geometry is not
physically buildable, or the coverage is incomplete):

  1. Camera lens vs test-surface plane (z = 0).
  2. Projector lens vs test-surface plane.
  3. Camera assembly vs projector assembly (AABB overlap).
  4. Surface extends outside the camera viewing prism (coverage).
  5. Surface extends outside the projector cone (coverage).

Checks 1-3 are physical impossibilities and gray the offending
bodies. Checks 4-5 are measurement-incompleteness advisories: an
11x11 surface sample is tested against the 3D prism / cone VOLUME
(catching a tall peak poking out of a tilted prism, not just a
wide z=0 footprint). They are banner-only and never gray.

Surface-clip criterion: lens-front DISC edge, not center
---------------------------------------------------------
The lens front is a flat disc of radius `r` (camera front element
110 mm dia -> r = 55; Pico Genie 20 mm dia -> r = 10). When the arm
is tilted, the disc tilts too, so its lowest point dips below the
front-center by `r * sin(angle-between-lens-axis-and-vertical)`:

       lens axis N (tilted)
            \                     The disc is perpendicular to N.
             \   . disc center    Its lowest world point is
            __\_/__                   center_z - r * sqrt(1 - Nz^2)
           /   |   \              because sqrt(1 - Nz^2) = sin of the
          *    |    *  <- lowest  tilt of N away from world +Z.
         disc edge   edge
       ............................  z = 0 surface plane

Closed form (equivalent, for the WD-convention arm geometry):
    disc_lowest_z = WD * cos(theta) - r * sin(theta)
A center-only `z < 0` check would never fire within the slider's
working-distance range — the disc edge is what actually reaches the
surface first. We compute it from the transform directly (general
form `center_z - r * sqrt(1 - Nz^2)`) so `detect_clips` stays a pure
function of the transform dict.

AABB approximation trade-off
----------------------------
The body-vs-body check transforms each mesh's local bounding-box
corners to world space and takes an axis-aligned min/max. A rotated
body's world AABB is larger than its true oriented bounding box, so
this check is slightly OVER-sensitive: it can flag a near-miss as an
overlap. Acceptable for an advisory warning — false positives nudge
the user away from cramped geometry; they don't corrupt any math.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

from scene import (
    make_camera_body,
    make_camera_lens,
    make_projection_cone_wireframe,
    make_projector_body,
    make_projector_lens,
    make_viewing_cone_wireframe,
)


# Mesh keys — must match hardware_scene / compute_arm_transforms.
KEY_CAMERA_BODY = "camera_body"
KEY_CAMERA_LENS = "camera_lens"
KEY_PROJECTOR_BODY = "projector_body"
KEY_PROJECTOR_LENS = "projector_lens"


# Front-element radii (mm) for the surface-clip disc-edge check.
_CAMERA_LENS_FRONT_RADIUS_MM = 55.0   # Edmund 110 mm-dia front element
_PROJECTOR_LENS_FRONT_RADIUS_MM = 10.0  # Pico Genie 20 mm-dia lens

# Warning strings (kept as module constants so tests assert on the
# exact text rather than fragile substrings).
MSG_CAMERA_SURFACE = (
    "Camera lens intersecting test surface — pose not physically feasible"
)
MSG_PROJECTOR_SURFACE = (
    "Projector lens intersecting test surface — pose not physically feasible"
)
MSG_BODY_OVERLAP = (
    "Camera and projector assemblies overlapping — pose not physically feasible"
)
# Sub-task 4b.6: measurement-coverage advisories. Distinct from the
# three "not physically feasible" collisions above — nothing is
# colliding; the camera simply can't see / the projector can't light
# the whole surface, so reconstruction values in the uncovered
# region are simulation artifacts, not measurements. Banner-only.
MSG_SURFACE_OUTSIDE_FOV = (
    "Test surface extends outside camera FOV — region(s) not measurable"
)
MSG_SURFACE_OUTSIDE_CONE = (
    "Test surface extends outside projector cone — region(s) not illuminated"
)


def _local_bbox_corners(verts: np.ndarray) -> np.ndarray:
    """8 corners of a vertex array's axis-aligned local bounding box."""
    mn = verts.min(axis=0)
    mx = verts.max(axis=0)
    return np.array(
        [
            [x, y, z]
            for x in (mn[0], mx[0])
            for y in (mn[1], mx[1])
            for z in (mn[2], mx[2])
        ],
        dtype=np.float64,
    )


# Local bounding-box corners per body, computed once from the actual
# scene meshes (so the check tracks scene.py if dims ever change).
_LOCAL_CORNERS: Dict[str, np.ndarray] = {
    KEY_CAMERA_BODY: _local_bbox_corners(make_camera_body()[0]),
    KEY_CAMERA_LENS: _local_bbox_corners(make_camera_lens()[0]),
    KEY_PROJECTOR_BODY: _local_bbox_corners(make_projector_body()[0]),
    KEY_PROJECTOR_LENS: _local_bbox_corners(make_projector_lens()[0]),
}

# Lens-front local +Z coordinate (the surface-facing disc) per lens.
# Lenses are centered on their own origin, so the front is at
# +half-length: camera 200/2 = 100, projector 5/2 = 2.5.
_LENS_FRONT_LOCAL_Z = {
    KEY_CAMERA_LENS: 100.0,
    KEY_PROJECTOR_LENS: 2.5,
}
_LENS_FRONT_RADIUS = {
    KEY_CAMERA_LENS: _CAMERA_LENS_FRONT_RADIUS_MM,
    KEY_PROJECTOR_LENS: _PROJECTOR_LENS_FRONT_RADIUS_MM,
}


# Coverage-advisory geometry, derived ONCE from the cone builders so
# it tracks scene.py rather than duplicating the 68x55 / 1.2:1 / 16:9
# spec numbers. Viewing prism is telecentric: a fixed rectangular
# cross-section (front rect of make_viewing_cone_wireframe). The
# projection cone diverges linearly: half-extents per unit axial
# distance from the apex (base rect of make_projection_cone_wireframe
# at L=1).
_vc_verts, _ = make_viewing_cone_wireframe(100.0)
_PRISM_HALF_U_MM = float(np.abs(_vc_verts[0:4, 0]).max())   # 34.0
_PRISM_HALF_V_MM = float(np.abs(_vc_verts[0:4, 1]).max())   # 27.5

_pc_verts, _ = make_projection_cone_wireframe(1.0)
_CONE_HALF_U_PER_L = float(np.abs(_pc_verts[1:5, 0]).max())  # (1/1.2)/2
_CONE_HALF_V_PER_L = float(np.abs(_pc_verts[1:5, 1]).max())  # *9/16


@dataclass
class ClipState:
    """Snapshot of which bodies are in collision and why."""

    camera_clipping_surface: bool = False
    projector_clipping_surface: bool = False
    bodies_overlapping: bool = False
    # Sub-task 4b.6: measurement-coverage advisories. No physical
    # collision — the surface just extends past the camera FOV /
    # projector lit volume. Advisory only (banner, no gray).
    surface_outside_camera_fov: bool = False
    surface_outside_projector_cone: bool = False
    messages: List[str] = field(default_factory=list)

    @property
    def any_clip(self) -> bool:
        return (
            self.camera_clipping_surface
            or self.projector_clipping_surface
            or self.bodies_overlapping
            or self.surface_outside_camera_fov
            or self.surface_outside_projector_cone
        )


def _apply(M: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Apply a 4x4 row-major transform to (N,3) points -> (N,3) world."""
    pts = np.asarray(pts, dtype=np.float64)
    homog = np.concatenate([pts, np.ones((pts.shape[0], 1))], axis=1)
    out = homog @ np.asarray(M, dtype=np.float64).T
    return out[:, :3]


def _lens_front_disc_lowest_z(M_lens: np.ndarray, key: str) -> float:
    """Lowest world-z of the lens-front disc edge.

    `center_z - r * sqrt(1 - Nz^2)` where N is the (unit) lens-axis
    world direction and r the front-element radius. See module
    docstring for the geometry.
    """
    front_local_z = _LENS_FRONT_LOCAL_Z[key]
    r = _LENS_FRONT_RADIUS[key]

    front_center = _apply(
        M_lens, np.array([[0.0, 0.0, front_local_z]])
    )[0]
    # Lens axis: local +Z mapped to world (direction vector, w=0).
    axis = (
        np.asarray(M_lens, dtype=np.float64)
        @ np.array([0.0, 0.0, 1.0, 0.0])
    )[:3]
    norm = np.linalg.norm(axis)
    nz = axis[2] / norm if norm > 0 else 0.0
    radial_drop = r * np.sqrt(max(0.0, 1.0 - nz * nz))
    return float(front_center[2] - radial_drop)


def _world_aabb(M: np.ndarray, local_corners: np.ndarray) -> tuple:
    """World-space AABB (min, max) of local bbox corners under M."""
    w = _apply(M, local_corners)
    return w.min(axis=0), w.max(axis=0)


def _aabb_overlap(a_min, a_max, b_min, b_max) -> bool:
    """Standard 3-axis interval-intersection AABB overlap test."""
    return bool(
        np.all(a_min <= b_max) and np.all(b_min <= a_max)
    )


def _world_unit(M: np.ndarray, local_dir) -> np.ndarray:
    """Local direction (w=0) -> world, normalized (row-major convention)."""
    d = (np.asarray(M, dtype=np.float64) @ np.asarray(local_dir, float))[:3]
    n = np.linalg.norm(d)
    return d / n if n > 0 else d


def _sample_surface_points(
    heightmap_mm: np.ndarray, pixel_size_mm: float, n: int = 11
) -> np.ndarray:
    """(n*n, 3) world points sampled on an n x n grid over the surface.

    World mapping mirrors surface_preview exactly: column index ->
    x, row index -> y, height -> z. z is honest mm (the scene runs
    at Z_EXAGGERATION = 1.0, so the rendered surface and these
    sample points share one frame with the hardware/cones).
    """
    H, W = heightmap_mm.shape
    rs = np.linspace(0, H - 1, n).round().astype(int)
    cs = np.linspace(0, W - 1, n).round().astype(int)
    rg, cg = np.meshgrid(rs, cs, indexing="ij")
    x = (cg - (W - 1) / 2.0) * pixel_size_mm
    y = (rg - (H - 1) / 2.0) * pixel_size_mm
    z = heightmap_mm[rg, cg]
    return np.stack([x.ravel(), y.ravel(), z.ravel()], axis=1)


def _surface_exceeds_prism(
    viewing_cone_world: np.ndarray, pts: np.ndarray
) -> bool:
    """Any sample point outside the telecentric viewing prism volume?

    Telecentric => parallel sides => the along-axis coordinate is
    irrelevant; only the two perpendicular cross-section offsets
    matter (constant 68 x 55 mm regardless of working distance).
    """
    C = _apply(viewing_cone_world, np.array([[0.0, 0.0, 0.0]]))[0]
    u = _world_unit(viewing_cone_world, [1.0, 0.0, 0.0, 0.0])
    v = _world_unit(viewing_cone_world, [0.0, 1.0, 0.0, 0.0])
    d = pts - C
    du = d @ u
    dv = d @ v
    inside = (np.abs(du) <= _PRISM_HALF_U_MM) & (
        np.abs(dv) <= _PRISM_HALF_V_MM
    )
    return bool(np.any(~inside))


def _surface_exceeds_cone(
    projection_cone_world: np.ndarray,
    pts: np.ndarray,
    throw_mm: float,
) -> bool:
    """Any sample point outside the diverging projection-cone volume?

    The cone grows linearly from the apex; half-extents at axial
    distance s from the apex are `(_CONE_HALF_*_PER_L) * s`. A point
    is lit iff it is in front of the projector (s >= 0) and within
    the angular cross-section at its own depth.

    Note: there is deliberately NO `s <= throw` upper bound. `throw`
    is only the nominal DLP focus distance; the light cone keeps
    diverging past it. Bounding at the (tilted) throw plane would
    false-flag the outer regions of a flat surface, which sit a few
    mm beyond that plane yet are physically still illuminated. The
    angular test is the correct coverage criterion. `throw_mm` is
    accepted for API symmetry / future focus checks.
    """
    apex = _apply(projection_cone_world, np.array([[0.0, 0.0, 0.0]]))[0]
    axis = _world_unit(projection_cone_world, [0.0, 0.0, 1.0, 0.0])
    u = _world_unit(projection_cone_world, [1.0, 0.0, 0.0, 0.0])
    v = _world_unit(projection_cone_world, [0.0, 1.0, 0.0, 0.0])

    rel = pts - apex
    s = rel @ axis
    lat = rel - np.outer(s, axis)
    lu = lat @ u
    lv = lat @ v
    hw = _CONE_HALF_U_PER_L * s
    hh = _CONE_HALF_V_PER_L * s
    inside = (s >= 0.0) & (np.abs(lu) <= hw) & (np.abs(lv) <= hh)
    return bool(np.any(~inside))


def detect_clips(
    transforms: Dict[str, np.ndarray],
    *,
    heightmap_mm: "np.ndarray | None" = None,
    surface_pixel_size_mm: float = 0.0,
    camera_distance_mm: float = 0.0,
    projector_distance_mm: float = 0.0,
    viewing_cone_world: "np.ndarray | None" = None,
    projection_cone_world: "np.ndarray | None" = None,
) -> ClipState:
    """Run the three collision checks plus two coverage advisories.

    Parameters
    ----------
    transforms : dict
        Mapping of mesh key -> (4,4) row-major world transform, as
        returned by `hardware_scene.compute_arm_transforms`. Keys:
        camera_body, camera_lens, projector_body, projector_lens.
    heightmap_mm : (H, W) array or None, keyword-only
        Current surface heightmap in honest mm. Required for the
        coverage advisories; None makes them inert.
    surface_pixel_size_mm : float, keyword-only
        Surface grid pitch (mm/px). 0.0 makes the advisories inert.
    camera_distance_mm, projector_distance_mm : float, keyword-only
        Live WD / throw. Throw bounds the projection-cone depth.
    viewing_cone_world, projection_cone_world : (4,4) or None
        Cone world transforms (as hardware_scene already computes).
        Required for the respective advisory; None makes it inert.

    Returns
    -------
    ClipState
        Three collision booleans + two coverage booleans, plus a
        `messages` list (fixed order: camera-surface, projector-
        surface, body-overlap, surface-outside-FOV, surface-
        outside-cone). The coverage lines extend `any_clip` and emit
        a banner line but do NOT gray the hardware (no collision).
    """
    state = ClipState()

    # 1 & 2 — lens-front disc vs surface plane (z = 0).
    cam_low = _lens_front_disc_lowest_z(
        transforms[KEY_CAMERA_LENS], KEY_CAMERA_LENS
    )
    if cam_low < 0.0:
        state.camera_clipping_surface = True
        state.messages.append(MSG_CAMERA_SURFACE)

    proj_low = _lens_front_disc_lowest_z(
        transforms[KEY_PROJECTOR_LENS], KEY_PROJECTOR_LENS
    )
    if proj_low < 0.0:
        state.projector_clipping_surface = True
        state.messages.append(MSG_PROJECTOR_SURFACE)

    # 3 — camera assembly AABB vs projector assembly AABB.
    cam_body_min, cam_body_max = _world_aabb(
        transforms[KEY_CAMERA_BODY], _LOCAL_CORNERS[KEY_CAMERA_BODY]
    )
    cam_lens_min, cam_lens_max = _world_aabb(
        transforms[KEY_CAMERA_LENS], _LOCAL_CORNERS[KEY_CAMERA_LENS]
    )
    cam_min = np.minimum(cam_body_min, cam_lens_min)
    cam_max = np.maximum(cam_body_max, cam_lens_max)

    proj_body_min, proj_body_max = _world_aabb(
        transforms[KEY_PROJECTOR_BODY], _LOCAL_CORNERS[KEY_PROJECTOR_BODY]
    )
    proj_lens_min, proj_lens_max = _world_aabb(
        transforms[KEY_PROJECTOR_LENS], _LOCAL_CORNERS[KEY_PROJECTOR_LENS]
    )
    proj_min = np.minimum(proj_body_min, proj_lens_min)
    proj_max = np.maximum(proj_body_max, proj_lens_max)

    if _aabb_overlap(cam_min, cam_max, proj_min, proj_max):
        state.bodies_overlapping = True
        state.messages.append(MSG_BODY_OVERLAP)

    # 4 & 5 — measurement-coverage advisories (banner-only, no gray).
    # Sample the surface on an 11x11 grid and test each 3D point
    # against the camera viewing prism / projector cone VOLUME. This
    # catches both lateral spill (wide surface) and vertical spill (a
    # tall peak poking out of a tilted prism) — the 2D z=0 footprint
    # approach missed the latter.
    if heightmap_mm is not None and surface_pixel_size_mm > 0.0:
        pts = _sample_surface_points(
            np.asarray(heightmap_mm, dtype=np.float64),
            float(surface_pixel_size_mm),
        )
        if viewing_cone_world is not None and _surface_exceeds_prism(
            viewing_cone_world, pts
        ):
            state.surface_outside_camera_fov = True
            state.messages.append(MSG_SURFACE_OUTSIDE_FOV)

        if (
            projection_cone_world is not None
            and projector_distance_mm > 0.0
            and _surface_exceeds_cone(
                projection_cone_world, pts, projector_distance_mm
            )
        ):
            state.surface_outside_projector_cone = True
            state.messages.append(MSG_SURFACE_OUTSIDE_CONE)

    return state
