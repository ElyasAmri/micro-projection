r"""clip_detection.py — advisory collision checks for the lab scene.

Stage 4b task 4. Pure NumPy. No Qt / pyqtgraph imports. The math
layer purity principle (PROJECT_CONTEXT Sec 7.2) carries forward:
this module imports only `scene` (itself pure NumPy) to read the
hardware meshes' local bounding boxes.

Three checks, all advisory (the math pipeline keeps running
regardless — a silly rig still produces a valid forward/inverse
simulation; these warnings just tell the user the geometry is not
physically buildable):

  1. Camera lens vs test-surface plane (z = 0).
  2. Projector lens vs test-surface plane.
  3. Camera assembly vs projector assembly (AABB overlap).

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
    make_projector_body,
    make_projector_lens,
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
MSG_CAMERA_SURFACE_HIT = (
    "Test surface contacts camera lens — pose / surface height not "
    "physically feasible"
)
MSG_PROJECTOR_SURFACE_HIT = (
    "Test surface contacts projector lens — pose / surface height not "
    "physically feasible"
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


@dataclass
class ClipState:
    """Snapshot of which bodies are in collision and why."""

    camera_clipping_surface: bool = False
    projector_clipping_surface: bool = False
    bodies_overlapping: bool = False
    # Stage 4b task 4 (2/2): the test surface peak reaching UP to a
    # lens that sits above the surface plane. Distinct from
    # *_clipping_surface (lens dipping BELOW z=0).
    camera_lens_hit_by_surface: bool = False
    projector_lens_hit_by_surface: bool = False
    messages: List[str] = field(default_factory=list)

    @property
    def any_clip(self) -> bool:
        return (
            self.camera_clipping_surface
            or self.projector_clipping_surface
            or self.bodies_overlapping
            or self.camera_lens_hit_by_surface
            or self.projector_lens_hit_by_surface
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


def detect_clips(
    transforms: Dict[str, np.ndarray],
    surface_peak_mm: float = 0.0,
) -> ClipState:
    """Run all five advisory clip checks on world-space body poses.

    Parameters
    ----------
    transforms : dict
        Mapping of mesh key -> (4,4) row-major world transform, as
        returned by `hardware_scene.compute_arm_transforms`. Keys:
        camera_body, camera_lens, projector_body, projector_lens.
    surface_peak_mm : float
        Max height of the (recovered / ground-truth) test surface, in
        mm. Default 0.0 (flat / legacy callers): the surface-vs-lens
        checks are then inert unless a lens is also dipping below z=0,
        and even then the `disc_lowest_z > 0` guard suppresses them
        so they don't double-fire with the surface-PLANE checks.

    Returns
    -------
    ClipState
        Five booleans plus a `messages` list (one line per triggered
        check, fixed order: camera-surface, projector-surface,
        body-overlap, camera-surface-hit, projector-surface-hit).

    Two distinct surface failure modes
    ----------------------------------
    - `*_clipping_surface`: the lens-front disc dips BELOW z=0 (the
      lens has gone through the surface plane).
    - `*_lens_hit_by_surface`: the lens sits ABOVE z=0 but the
      surface PEAK reaches up to it. Guarded by `disc_lowest_z > 0`
      so it never co-fires with the lens-below-plane case.
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

    # 4 & 5 — surface peak reaching UP to a lens that is ABOVE the
    # plane. The `> 0` guard means: if the lens is already below z=0
    # (checks 1/2 fired), this distinct mode stays silent — no
    # double-message for the same physical situation.
    if cam_low > 0.0 and surface_peak_mm >= cam_low:
        state.camera_lens_hit_by_surface = True
        state.messages.append(MSG_CAMERA_SURFACE_HIT)

    if proj_low > 0.0 and surface_peak_mm >= proj_low:
        state.projector_lens_hit_by_surface = True
        state.messages.append(MSG_PROJECTOR_SURFACE_HIT)

    return state
