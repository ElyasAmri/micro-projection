"""hardware_scene.py — Live hardware bodies inside the SurfacePreview view.

Stage 4b sub-task 3. Composes the four hardware meshes from
`src/scene.py` (camera body, camera lens, projector body, projector
lens) into the same 3D scene that already shows the recovered surface,
and applies live pose updates from main_window's pose sliders.

Two layers
----------
1. `compute_arm_transforms(...)` — pure NumPy function returning the
   four 4x4 row-major transforms keyed by mesh name. No Qt, no
   pyqtgraph. Tested directly in `tests/test_hardware_scene.py`.

2. `class HardwareScene` — owns the four `GLMeshItem`s, knows how to
   add them to a `GLViewWidget` and how to push transforms into them.
   `update_pose` is a thin wrapper that calls `compute_arm_transforms`
   and `setTransform`s each item.

Pico Genie lens off-center offset
---------------------------------
The Pico Genie's measured lens position is X = -6.5 mm in
body-centered frame (PROJECT_CONTEXT Sec 2). That offset is applied
at composition time in `compute_arm_transforms`, NOT inside the lens
mesh (`make_projector_lens` returns a centered cylinder) and NOT
inside `body_lens_offset` (which is pure-Z so the helper stays
reusable for both lenses). This is the deferred-from-sub-task-2
pattern landing here.

What lives in main_window vs here
---------------------------------
- main_window owns the four pose sliders (`theta_camera`,
  `theta_projector`, `projector_distance`, `camera_distance`) and the
  `_on_pose_changed` slot.
- SurfacePreview owns a HardwareScene instance and exposes
  `update_hardware_pose(theta_cam, theta_proj, proj_dist, cam_dist)`
  so main_window doesn't reach into the HardwareScene directly.
- HardwareScene owns the four `GLMeshItem`s and the transform math.

The math is pure-NumPy (module-level function) so tests don't need a
running QApplication. Sec 7.2 math-layer-purity carries forward.
"""
from __future__ import annotations

from typing import Dict, NamedTuple

import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl

from scene import (
    make_camera_body,
    make_camera_lens,
    make_projection_cone_wireframe,
    make_projector_body,
    make_projector_lens,
    make_viewing_cone_wireframe,
)
from scene_compose import (
    body_lens_offset,
    camera_arm_transform,
    cone_local_to_world_transform,
    projector_arm_transform,
)
from src.gui.clip_detection import (
    ClipState,
    detect_clips,
)


# ---------------------------------------------------------------------------
# Hardware constants exposed for tests / GUI references.
# ---------------------------------------------------------------------------

# Body and lens dimensions used to compute body->lens offsets. These are
# duplicated from `scene.py`'s docstrings deliberately so the composition
# layer can compose without re-introspecting mesh bounding boxes at runtime.
_CAMERA_BODY_DEPTH_MM = 30.0
_CAMERA_LENS_LENGTH_MM = 200.0
_PROJECTOR_BODY_DEPTH_MM = 55.0
_PROJECTOR_LENS_LENGTH_MM = 5.0


# Pico Genie lens offset from the projector front-FACE center, measured
# in the body face frame (PROJECT_CONTEXT Sec 2). Locked hardware
# geometry, not slider-driven.
#
#   face_x        body-local +X (horizontal on the face) -> world +X at theta=0
#   face_vertical body-local +Y ("up the face")          -> world -Y at theta=0
#   recess        mm the lens exit sits BEHIND the front face (optical axis)
#
# These anchor the projector LENS CENTER over world (0,0) when vertical
# (see compute_arm_transforms); the body then hangs off-axis. Promote a
# projector swap to a one-line constant edit.
#
# FACE-VERTICAL SIGN UNVERIFIED: +17.5 "up the face" maps to world -Y under
# the sim's current orientation convention. The physical rig is not built
# yet; confirm against the real projector at mount time and flip the sign
# if the lens sits on the opposite world-Y side. Magnitude (17.5) and the
# anchoring behavior are correct regardless.
class ProjectorLensOffset(NamedTuple):
    face_x: float
    face_vertical: float
    recess: float


PROJECTOR_LENS_OFFSET_MM = ProjectorLensOffset(
    face_x=-6.5,
    face_vertical=17.5,
    recess=1.5,
)

# Backward-compat alias: pre-4d.10 readers referenced the scalar face-X
# offset by this name. Kept so external/test imports stay valid.
PROJECTOR_LENS_X_OFFSET_MM: float = PROJECTOR_LENS_OFFSET_MM.face_x


# Mesh-item keys; used by `compute_arm_transforms` return dict and
# `HardwareScene` to look up meshes consistently.
KEY_CAMERA_BODY = "camera_body"
KEY_CAMERA_LENS = "camera_lens"
KEY_PROJECTOR_BODY = "projector_body"
KEY_PROJECTOR_LENS = "projector_lens"

# Cone keys (wireframe GLLinePlotItems, not in the transforms dict).
KEY_VIEWING_CONE = "viewing_cone"
KEY_PROJECTION_CONE = "projection_cone"


# Visual colors for the four bodies. Yellow / gold for the camera assembly,
# cyan / teal for the projector assembly.
COLORS: Dict[str, tuple] = {
    KEY_CAMERA_BODY:    (1.00, 0.90, 0.20, 1.0),
    KEY_CAMERA_LENS:    (0.85, 0.70, 0.15, 1.0),
    KEY_PROJECTOR_BODY: (0.20, 0.80, 0.90, 1.0),
    KEY_PROJECTOR_LENS: (0.15, 0.65, 0.75, 1.0),
}

# Faded wireframe cone colors (alpha 0.4 = ghostly, doesn't compete
# visually with the solid bodies).
CONE_COLORS: Dict[str, tuple] = {
    KEY_VIEWING_CONE:    (1.00, 0.90, 0.20, 0.4),   # faded yellow
    KEY_PROJECTION_CONE: (0.20, 0.80, 0.90, 0.4),   # faded cyan
}

# Gray override applied to any body/cone involved in a clip.
GRAY_RGBA: tuple = (0.4, 0.4, 0.4, 1.0)
# Cones keep their ghostly alpha even when grayed.
GRAY_CONE_RGBA: tuple = (0.4, 0.4, 0.4, 0.4)


def _translation(tx: float, ty: float, tz: float) -> np.ndarray:
    """Build a row-major float32 translation matrix."""
    M = np.eye(4, dtype=np.float32)
    M[0, 3] = tx
    M[1, 3] = ty
    M[2, 3] = tz
    return M


def compute_arm_transforms(
    theta_camera_deg: float,
    theta_projector_deg: float,
    projector_distance_mm: float,
    camera_distance_mm: float,
) -> Dict[str, np.ndarray]:
    """Return the four 4x4 row-major transforms for the hardware bodies.

    Pure NumPy. No Qt / pyqtgraph dependency. Tests target this directly;
    HardwareScene is a thin GUI wrapper.

    Distance convention (optics: lens-front-to-surface)
    ---------------------------------------------------
    Both `camera_distance_mm` and `projector_distance_mm` are interpreted
    as **lens-front to test-surface distance** — the standard optical
    "working distance" / "throw distance" convention. The Edmund
    #58-259's WD range is 132-182 mm; the Pico Genie's throw is the
    distance from projector lens to projected image plane. The body
    sits further from the surface along the arm by `lens_length +
    body_depth/2`, so:

        camera_body_distance    = WD     + 200 + 15 = WD + 215 mm
        projector_body_distance = throw  +   5 + 27.5 = throw + 32.5 mm

    These are the values fed into `camera_arm_transform` /
    `projector_arm_transform`, whose `distance_mm` parameter is the
    distance from the world origin to the body's local origin (body
    center) along the arm axis.

    Parameters
    ----------
    theta_camera_deg : float
        Camera arm tilt from surface normal, degrees. +theta tilts toward +X.
    theta_projector_deg : float
        Projector arm tilt, degrees. Same sign convention.
    projector_distance_mm : float
        Projector THROW distance: lens-front to surface. Pico Genie
        spec.
    camera_distance_mm : float
        Camera WORKING DISTANCE: lens-front to surface. Edmund #58-259
        WD range is 132-182 mm.

    Returns
    -------
    dict mapping mesh key -> (4, 4) float32 row-major transform.
        Keys: 'camera_body', 'camera_lens', 'projector_body', 'projector_lens'.

    Composition
    -----------
    M_cam_body  = camera_arm_transform(theta_cam, camera_distance_mm + 215)
    M_cam_lens  = M_cam_body @ body_lens_offset(30, 200)
    M_proj_body = projector_arm_transform(theta_proj, projector_distance_mm + 32.5)
                              @ _translation(-face_x, -face_vertical, 0)
    M_proj_lens = M_proj_body @ body_lens_offset(55, 5)
                              @ _translation(+face_x, +face_vertical, 0)

    Projector lens anchoring (4d.10)
    --------------------------------
    The Pico Genie lens sits off-center on the body's front face
    (face_x = -6.5, face_vertical = +17.5 mm). To park the LENS CENTER
    over world (0,0) when the projector points straight down, the BODY
    is shifted by the negative of the in-face offset (the
    `_translation(-face_x, -face_vertical, 0)` on M_proj_body), and the
    lens re-applies `+face_x, +face_vertical` so it lands back on the
    arm axis. Net: lens on-axis at (0,0,...), body hanging off-axis at
    (+6.5, +17.5, ...) when vertical. Both translations are
    right-multiplied (body-local frame, BEFORE the parent arm
    transform), so the anchoring composes correctly at every theta —
    face_vertical maps to world -Y invariantly under the R_y arm swing.
    The camera lens is centered (no offset), so it is untouched.
    """
    face_x = PROJECTOR_LENS_OFFSET_MM.face_x
    face_vertical = PROJECTOR_LENS_OFFSET_MM.face_vertical
    camera_body_distance = (
        camera_distance_mm
        + _CAMERA_LENS_LENGTH_MM
        + _CAMERA_BODY_DEPTH_MM / 2.0
    )
    projector_body_distance = (
        projector_distance_mm
        + _PROJECTOR_LENS_LENGTH_MM
        + _PROJECTOR_BODY_DEPTH_MM / 2.0
    )

    M_cam_body = camera_arm_transform(theta_camera_deg, camera_body_distance)
    M_cam_lens = M_cam_body @ body_lens_offset(
        _CAMERA_BODY_DEPTH_MM, _CAMERA_LENS_LENGTH_MM
    )

    # Anchor the projector LENS CENTER over world (0,0) when vertical by
    # shifting the BODY by the negative of the in-face lens offset. Body-
    # local right-multiply, so it composes correctly at all theta.
    M_proj_body = (
        projector_arm_transform(theta_projector_deg, projector_body_distance)
        @ _translation(-face_x, -face_vertical, 0.0)
    ).astype(np.float32, copy=False)
    # Lens re-applies +face offsets, landing back on the arm axis (0,0).
    M_proj_lens = (
        M_proj_body
        @ body_lens_offset(_PROJECTOR_BODY_DEPTH_MM, _PROJECTOR_LENS_LENGTH_MM)
        @ _translation(face_x, face_vertical, 0.0)
    ).astype(np.float32, copy=False)

    return {
        KEY_CAMERA_BODY:    M_cam_body.astype(np.float32, copy=False),
        KEY_CAMERA_LENS:    M_cam_lens.astype(np.float32, copy=False),
        KEY_PROJECTOR_BODY: M_proj_body.astype(np.float32, copy=False),
        KEY_PROJECTOR_LENS: M_proj_lens,
    }


def _camera_cone_world(camera_body_transform: np.ndarray) -> np.ndarray:
    """Camera viewing-cone world transform (apex at the lens-front).

    Shared by `update_pose` (cone rendering) and `arm_lens_front_world`
    (coordinate readout) so the two never drift. Camera lens is
    centered (no in-face offset, no recess).
    """
    return cone_local_to_world_transform(
        camera_body_transform,
        lens_length_mm=_CAMERA_LENS_LENGTH_MM,
        body_depth_mm=_CAMERA_BODY_DEPTH_MM,
        x_offset_mm=0.0,
    )


def _projector_cone_world(projector_body_transform: np.ndarray) -> np.ndarray:
    """Projector cone world transform (apex at the anchored lens-front).

    Shared by `update_pose` and `arm_lens_front_world`. Re-applies the
    Pico Genie in-face offsets + recess to the already-anchored body
    transform so the apex lands on the optical axis (0,0,~throw) when
    vertical (4d.10).
    """
    return cone_local_to_world_transform(
        projector_body_transform,
        lens_length_mm=_PROJECTOR_LENS_LENGTH_MM,
        body_depth_mm=_PROJECTOR_BODY_DEPTH_MM,
        x_offset_mm=PROJECTOR_LENS_OFFSET_MM.face_x,
        y_offset_mm=PROJECTOR_LENS_OFFSET_MM.face_vertical,
        recess_mm=PROJECTOR_LENS_OFFSET_MM.recess,
    )


def arm_lens_front_world(
    theta_cam_deg: float,
    theta_proj_deg: float,
    proj_dist_mm: float,
    cam_dist_mm: float,
) -> Dict[str, tuple]:
    """Camera + projector lens-front world positions (mm), surface frame.

    Single source of truth for the hardware-coordinate readout — both
    the GUI "Hardware Coordinates" panel and the `scripts/hardware_
    coords.py` CLI call this; neither re-extracts the geometry.

    Composes `compute_arm_transforms` with the same cone placement
    `update_pose` renders (via the shared `_camera_cone_world` /
    `_projector_cone_world` helpers), then returns each lens-front
    (cone apex) world position — the translation column of the cone
    transform.

    Frame: world origin at the stage-surface center, +z up toward the
    rig (z=0 is the stage). After 4d.10 anchoring, the projector
    lens-front sits at (0, 0, ~throw) when vertical (theta_proj=0) and
    the camera at (0, 0, WD).

    Pure NumPy — creates no QApplication, so it is headlessly
    unit-testable and safe to call from the CLI.

    Returns
    -------
    dict
        ``{"camera": (x, y, z), "projector": (x, y, z)}`` — float mm.
    """
    transforms = compute_arm_transforms(
        theta_camera_deg=theta_cam_deg,
        theta_projector_deg=theta_proj_deg,
        projector_distance_mm=proj_dist_mm,
        camera_distance_mm=cam_dist_mm,
    )
    cam = _camera_cone_world(transforms[KEY_CAMERA_BODY])
    proj = _projector_cone_world(transforms[KEY_PROJECTOR_BODY])
    return {
        "camera": (float(cam[0, 3]), float(cam[1, 3]), float(cam[2, 3])),
        "projector": (float(proj[0, 3]), float(proj[1, 3]), float(proj[2, 3])),
    }


class HardwareScene:
    """Owns the four GLMeshItems for the hardware bodies in a 3D view.

    Construction adds the meshes to `view` at identity transforms.
    `update_pose` is the live wire: main_window calls it on every slider
    drag, and it pushes fresh transforms into the four items via
    `setTransform(pg.Transform3D(M))`.

    Designed so that:
    - All four meshes live in the same coordinate frame as the recovered
      surface (no separate sub-view, no z-exaggeration on the bodies).
    - Initial pose is identity; main_window calls `update_pose` once
      after construction to position the bodies at slider defaults
      before the view is shown.
    """

    def __init__(self, view: gl.GLViewWidget) -> None:
        self._items: Dict[str, gl.GLMeshItem] = {}
        for key, builder in [
            (KEY_CAMERA_BODY,    make_camera_body),
            (KEY_CAMERA_LENS,    make_camera_lens),
            (KEY_PROJECTOR_BODY, make_projector_body),
            (KEY_PROJECTOR_LENS, make_projector_lens),
        ]:
            verts, faces = builder()
            md = gl.MeshData(vertexes=verts, faces=faces)
            item = gl.GLMeshItem(
                meshdata=md,
                smooth=False,
                color=COLORS[key],
                shader="shaded",
                drawEdges=False,
            )
            view.addItem(item)
            self._items[key] = item

        # Two wireframe cones (GLLinePlotItem, mode='lines'). Vertices
        # are rebuilt every pose because cone dimensions depend on the
        # live throw / WD slider values. Initial empty pos; update_pose
        # fills them.
        self._cones: Dict[str, gl.GLLinePlotItem] = {}
        for key in (KEY_VIEWING_CONE, KEY_PROJECTION_CONE):
            line = gl.GLLinePlotItem(
                pos=np.zeros((2, 3), dtype=np.float32),
                color=CONE_COLORS[key],
                width=1.0,
                mode="lines",
                antialias=True,
            )
            view.addItem(line)
            self._cones[key] = line

    @staticmethod
    def _edges_to_segments(verts: np.ndarray, edges: np.ndarray) -> np.ndarray:
        """Expand (verts, edges) to a (2M, 3) line-segment pos array.

        GLLinePlotItem(mode='lines') consumes consecutive vertex pairs
        as independent segments, so each edge (a, b) becomes the two
        rows verts[a], verts[b].
        """
        return verts[edges.reshape(-1)].astype(np.float32, copy=False)

    def update_pose(
        self,
        theta_camera_deg: float,
        theta_projector_deg: float,
        projector_distance_mm: float,
        camera_distance_mm: float,
        heightmap_mm: "np.ndarray | None" = None,
        surface_pixel_size_mm: float = 0.0,
    ) -> ClipState:
        """Recompute and apply transforms; refresh cones; detect clips.

        Returns the `ClipState` so main_window can drive the warning
        banner. Bodies (and their cones) involved in a clip are
        recolored gray; un-clipped ones are restored to their normal
        colors.

        `heightmap_mm` + `surface_pixel_size_mm` feed the 3D-volume
        FOV / projector-cone coverage advisories (both default
        inert for callers that don't pass them).

        Still cheap: a handful of small matrix multiplies, four mesh
        `setTransform` calls, two tiny wireframe rebuilds, the
        AABB / disc-edge clip arithmetic, and a 121-point volume
        test. Safe on every slider tick.
        """
        transforms = compute_arm_transforms(
            theta_camera_deg=theta_camera_deg,
            theta_projector_deg=theta_projector_deg,
            projector_distance_mm=projector_distance_mm,
            camera_distance_mm=camera_distance_mm,
        )
        for key, item in self._items.items():
            item.setTransform(pg.Transform3D(transforms[key]))

        # --- Cones: rebuild verts from live throw/WD, then place. ---
        view_verts, view_edges = make_viewing_cone_wireframe(
            camera_distance_mm
        )
        view_world = _camera_cone_world(transforms[KEY_CAMERA_BODY])
        self._cones[KEY_VIEWING_CONE].setData(
            pos=self._edges_to_segments(view_verts, view_edges)
        )
        self._cones[KEY_VIEWING_CONE].setTransform(pg.Transform3D(view_world))

        proj_verts, proj_edges = make_projection_cone_wireframe(
            projector_distance_mm
        )
        proj_world = _projector_cone_world(transforms[KEY_PROJECTOR_BODY])
        self._cones[KEY_PROJECTION_CONE].setData(
            pos=self._edges_to_segments(proj_verts, proj_edges)
        )
        self._cones[KEY_PROJECTION_CONE].setTransform(
            pg.Transform3D(proj_world)
        )

        # --- Clip detection + gray override. ---
        clip_state = detect_clips(
            transforms,
            heightmap_mm=heightmap_mm,
            surface_pixel_size_mm=surface_pixel_size_mm,
            camera_distance_mm=camera_distance_mm,
            projector_distance_mm=projector_distance_mm,
            viewing_cone_world=view_world,
            projection_cone_world=proj_world,
        )
        self._apply_clip_colors(clip_state)
        return clip_state

    def _apply_clip_colors(self, clip_state: ClipState) -> None:
        """Recolor bodies/cones gray when clipping, else normal.

        Camera-side items (camera body, camera lens, viewing cone) gray
        out when the camera lens clips the surface OR the assemblies
        overlap. Projector-side likewise. Body-overlap grays BOTH
        assemblies (it's a mutual collision).
        """
        cam_clip = (
            clip_state.camera_clipping_surface
            or clip_state.bodies_overlapping
        )
        proj_clip = (
            clip_state.projector_clipping_surface
            or clip_state.bodies_overlapping
        )

        self._items[KEY_CAMERA_BODY].setColor(
            GRAY_RGBA if cam_clip else COLORS[KEY_CAMERA_BODY]
        )
        self._items[KEY_CAMERA_LENS].setColor(
            GRAY_RGBA if cam_clip else COLORS[KEY_CAMERA_LENS]
        )
        self._items[KEY_PROJECTOR_BODY].setColor(
            GRAY_RGBA if proj_clip else COLORS[KEY_PROJECTOR_BODY]
        )
        self._items[KEY_PROJECTOR_LENS].setColor(
            GRAY_RGBA if proj_clip else COLORS[KEY_PROJECTOR_LENS]
        )
        self._cones[KEY_VIEWING_CONE].setData(
            color=GRAY_CONE_RGBA if cam_clip
            else CONE_COLORS[KEY_VIEWING_CONE]
        )
        self._cones[KEY_PROJECTION_CONE].setData(
            color=GRAY_CONE_RGBA if proj_clip
            else CONE_COLORS[KEY_PROJECTION_CONE]
        )
