"""scene.py — Pure-NumPy mesh-builder functions for the unified 3D scene.

Stage 4b adds the lab apparatus (camera body, projector body, lens
cylinders, projection / viewing cones) into the same 3D scene that
already shows the recovered surface. This module produces the raw
geometry primitives; the GUI layer wraps each `(verts, faces)` tuple
into a `pyqtgraph.opengl.GLMeshItem` separately.

Scope (sub-tasks 1 and 2)
-------------------------
- `make_camera_body()`   — FLIR Blackfly S body, 29 x 29 x 30 mm box.
- `make_projector_body(profile)` — projector body box from a
                           `ProjectorProfile` (default `PICO_GENIE`, the
                           55 mm cube; `WINTECH_PRO4500` available too).
- `make_camera_lens()`   — Edmund Optics #58-259 stepped lens body,
                           total length 200 mm along local +Z.
- `make_projector_lens(profile)` — projector lens stub cylinder from a
                           `ProjectorProfile` (default `PICO_GENIE`,
                           20 x 5 mm).

Projector profiles (Stage 6 projector-swap commit 1)
----------------------------------------------------
`ProjectorProfile` carries the per-projector VISUAL specs (body box, lens
stub, lens face offset) and a registry `PROJECTOR_PROFILES` mirrors
`main_window.FOV_PRESETS`. This is an Option-A (visual-only) swap: profiles
hold NO simulation-math parameters — `p`, `theta_projector`, `a` stay sealed
in `geometry.py` (PROJECT_CONTEXT Sec 7.11). The default profile is the
Pico Genie, so the no-arg builders are byte-identical to before.

All bodies and lenses are centered on the origin of their own local
frame. Pose (translation + rotation into the lab/world frame) is the
concern of `scene_compose.py`; this module just produces geometrically
correct primitives in local frames.

Lens-local frame convention
---------------------------
Lenses are oriented along their local +Z axis (length runs from
z = -L/2 to z = +L/2). The composition layer in `scene_compose.py`
assumes "+Z is the optical axis pointing OUT of the lens (toward the
test surface)." For the camera lens, the wider front element (110 mm
dia) sits at +Z (closer to the surface) and the rear mount (55 mm
dia) sits at -Z (closer to the camera body). The taper sits between.

Return contract
---------------
Every builder returns `(verts, faces)`:

- `verts`: `(N, 3) float32` array of vertex positions in millimeters.
- `faces`: `(M, 3) uint32` array of triangle indices into `verts`.
- Winding is counter-clockwise viewed from outside the mesh, so the
  cross product `(verts[b] - verts[a]) x (verts[c] - verts[a])` for a
  face `(a, b, c)` points away from the body center. pyqtgraph's
  'shaded' shader uses this convention; inverted winding produces a
  dark, inside-out render.

Module scope
------------
- No pyqtgraph imports, no Qt imports. Pure NumPy. The math-layer-purity
  principle from PROJECT_CONTEXT Sec 7.2 applies here too: the GUI
  consumes these tuples, the math layer is unaware of them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple, Optional, Tuple

import numpy as np


# Vertex enumeration for a centered box of dimensions (Lx, Ly, Lz):
# bit 0 = sign of x, bit 1 = sign of y, bit 2 = sign of z (0 = minus,
# 1 = plus). The indices below are used in `_BOX_FACES` and never
# renumbered; reordering the vertex list would invalidate every face.
#
#     6 ----------- 7        z+
#    /|            /|        |   y+
#   2 ----------- 3 |        | /
#   | |           | |        +---- x+
#   | 4 --------- | 5
#   |/            |/
#   0 ----------- 1
#
# Faces are built with CCW outward winding (verified analytically per
# face by cross-product direction; see tests/test_scene.py).
_BOX_FACES = np.array(
    [
        # Bottom (-z outward)
        [0, 2, 1], [1, 2, 3],
        # Top (+z outward)
        [4, 5, 6], [5, 7, 6],
        # Front (-y outward)
        [0, 1, 4], [1, 5, 4],
        # Back (+y outward)
        [2, 6, 3], [3, 6, 7],
        # Left (-x outward)
        [0, 4, 2], [4, 6, 2],
        # Right (+x outward)
        [1, 3, 5], [3, 7, 5],
    ],
    dtype=np.uint32,
)


def _centered_box(lx: float, ly: float, lz: float) -> Tuple[np.ndarray, np.ndarray]:
    """Build a centered axis-aligned box of dimensions (lx, ly, lz) mm.

    Returns 8 vertices and 12 triangles per the module contract. Used
    by both `make_camera_body` and `make_projector_body`.
    """
    hx, hy, hz = lx / 2.0, ly / 2.0, lz / 2.0
    verts = np.array(
        [
            [-hx, -hy, -hz],  # 0
            [+hx, -hy, -hz],  # 1
            [-hx, +hy, -hz],  # 2
            [+hx, +hy, -hz],  # 3
            [-hx, -hy, +hz],  # 4
            [+hx, -hy, +hz],  # 5
            [-hx, +hy, +hz],  # 6
            [+hx, +hy, +hz],  # 7
        ],
        dtype=np.float32,
    )
    return verts, _BOX_FACES.copy()


def make_camera_body() -> Tuple[np.ndarray, np.ndarray]:
    """Build the FLIR Blackfly S camera body mesh.

    Dimensions: 29 x 29 x 30 mm (BFS-U3-13Y3M-C body, per PROJECT_CONTEXT
    Sec 2). Centered origin in the scene frame: the bounding box spans
    [-14.5, +14.5] on x and y, and [-15, +15] on z.

    Body-axis orientation in the lab frame (which face points toward the
    surface, which direction the lens protrudes) is a sub-task-2 concern.
    This builder produces an orientation-agnostic centered box; the GUI
    composes pose via translation + rotation when placing the body in
    the scene.

    Returns
    -------
    verts : (8, 3) float32, units mm
    faces : (12, 3) uint32
        CCW outward winding.
    """
    return _centered_box(29.0, 29.0, 30.0)


# ---------------------------------------------------------------------------
# Projector profiles (Stage 6 projector-swap commit 1).
#
# A ProjectorProfile bundles the VISUAL specs needed to render a projector's
# body + lens in the lab view. Option-A (visual-only) swap: a profile carries
# NO simulation-math parameters — p, theta_projector, a stay sealed in
# geometry.py (PROJECT_CONTEXT Sec 7.11). Switching the active profile changes
# only what the 3D scene draws, never the recovered surface. The registry
# mirrors main_window.FOV_PRESETS; the first entry is the default/active
# projector (Pico Genie), so the no-arg mesh builders stay byte-identical.
# ---------------------------------------------------------------------------
class LensOption(NamedTuple):
    """One field-swappable projector lens: a rated (working distance -> FOV) pair.

    Stage 6 projector-swap commit 2. A PRO4500-class projector's lens does NOT
    project by a single throw ratio; each lens has a FIXED working distance and
    the FOV it covers there (with the resulting projected pixel size). The
    projection cone for such a lens is therefore its rated FOV rectangle at its
    rated WD — see `make_projection_cone_from_fov` — not a throw-ratio
    extrapolation.

    Fields
    ------
    working_distance_mm : float
        Lens-front to projected-image-plane (the cone's draw distance).
    fov_w_mm, fov_h_mm : float
        Field of view covered on the surface at `working_distance_mm`
        (full width / height, image-horizontal / image-vertical).
    projected_pixel_um : float
        Projected pixel pitch on the surface at this WD (display fact;
        NOT a simulation-math parameter).
    """

    working_distance_mm: float
    fov_w_mm: float
    fov_h_mm: float
    projected_pixel_um: float


@dataclass(frozen=True)
class ProjectorProfile:
    """Per-projector VISUAL specs for building the lab-view body + lens meshes.

    Fields
    ------
    name : str
        Human-readable projector name (e.g. for the future selector label).
    body_dims_mm : (lx, ly, lz)
        Body box dimensions in mm, centered on the local origin. `lz` is the
        OPTICAL-AXIS DEPTH — the dimension perpendicular to the lens front
        face, along local +Z (so a long unit standing lens-down at theta=0
        carries its long dimension in `lz`). `lx`/`ly` are the in-face
        horizontal / vertical spread.
    lens_diameter_mm, lens_length_mm : float
        Lens stub-cylinder size (length runs along local +Z).
    lens_face_offset_mm : (face_x, face_vertical, recess)
        Lens position on the body front face, mm, in the body-centered face
        frame: `face_x` horizontal offset, `face_vertical` vertical offset,
        `recess` how far the lens exit sits behind the front face. A plain
        3-tuple by design — the projector-swap dropdown commit unifies it
        against hardware_scene's existing `ProjectorLensOffset`, so a second
        near-twin type here would only be torn down. NOT consumed by the mesh
        builders (the lens mesh is a centered cylinder); used by the compose
        layer, wired to the active profile in a later commit.
    lens_options : tuple of LensOption
        Field-swappable lens table (rated WD -> FOV -> pixel). Empty for a
        single-lens / throw-ratio projector (e.g. Pico Genie); populated for
        the PRO4500. The active lens is `lens_options[default_lens_index]`.
    default_lens_index : int
        Index into `lens_options` of the currently-chosen lens (the cone is
        drawn from that lens's rated FOV/WD). Moot when `lens_options` is empty.
        The commit-4 selector will drive this; it is the "active lens" home.
    cone_params : object or None
        SLOT — reserved projection-cone optics hook. None this commit; the
        PRO4500 cone is built from `lens_options` via
        `make_projection_cone_from_fov`, and the Pico cone stays the
        throw-ratio `make_projection_cone_wireframe`. Kept for any future
        cone parameter that is not a per-lens FOV row.
    """

    name: str
    body_dims_mm: Tuple[float, float, float]
    lens_diameter_mm: float
    lens_length_mm: float
    lens_face_offset_mm: Tuple[float, float, float]
    lens_options: Tuple[LensOption, ...] = ()
    default_lens_index: int = 0
    cone_params: Optional[object] = None


# Pico Genie Impact 2.0 Plus Elite — the current/default ACTIVE projector.
# Values EXACTLY reproduce the prior hardcoded mesh (55^3 mm body, 20 x 5 mm
# lens, measured -6.5 / 17.5 / 1.5 mm face offset) so the default-profile
# builders are byte-identical to before.
PICO_GENIE = ProjectorProfile(
    name="Pico Genie Impact 2.0 Plus Elite",
    body_dims_mm=(55.0, 55.0, 55.0),
    lens_diameter_mm=20.0,
    lens_length_mm=5.0,
    lens_face_offset_mm=(-6.5, 17.5, 1.5),
)

# Wintech PRO4500 (TI DLP LightCrafter 4500 optical engine). MEASURED true
# geometry: body 84 x 54 x 145 mm with the 145 mm long axis as the OPTICAL-AXIS
# DEPTH (lz); the lens exits a short end face, so the body hangs long / vertical
# and lens-down at theta=0. The wider face dim (84) is image-horizontal, matching
# the lenses' wider-than-tall FOV (e.g. 65.6 x 41, 131.2 x 82 mm). The earlier
# 210 mm depth conflated body + barrel: the real protruding optic is a 30 mm-dia
# x 65 mm barrel (145 body + 65 barrel = 210 total optical-axis reach), modeled
# as the lens mesh (lens_diameter_mm=30, lens_length_mm=65) so make_projector_lens
# auto-builds it and the SAT / cross-arm-obstruction checks track its real
# protruding extent. Lens CENTERED horizontally on the 84 mm edge (face_x=0); 20
# mm up from the bottom of the 54 mm height = 7 mm BELOW the vertical center, so
# face_vertical=-7 (body-local +Y is "up the face"; SIGN flagged for physical
# confirmation at mount per hardware_scene's face_vertical note). ~2 mm recess
# (observed indentation) is the optical-exit setback; UNCHANGED — the lens-front /
# throw cancellation (body-depth and lens-length cancel in both the body-distance
# and cone-apex consumers) keeps the readout at throw + recess.
#
# lens_options (commit 2): the two PRO4500 field-swappable lenses in the
# work-area range. 92 mm under-fills the 68 x 55 mm camera footprint (a dead
# band around the projected patch); 184 mm fully covers it — so 184 mm is the
# sane measurement default (default_lens_index=1). The brochure's 700 mm /
# 400 x 250 mm lens is out of work-area range and is omitted (docs-only).
WINTECH_PRO4500 = ProjectorProfile(
    name="Wintech PRO4500",
    body_dims_mm=(84.0, 54.0, 145.0),
    lens_diameter_mm=30.0,
    lens_length_mm=65.0,
    lens_face_offset_mm=(0.0, -7.0, 2.0),
    lens_options=(
        LensOption(92.0, 65.6, 41.0, 50.0),     # under-fills 68x55 camera (dead band)
        LensOption(184.0, 131.2, 82.0, 100.0),  # full camera coverage
    ),
    default_lens_index=1,  # 184 mm = full coverage, the sane measurement default
)

# Registry mirroring main_window.FOV_PRESETS. Order matters: the FIRST entry
# is the default/active projector (Pico Genie). The dropdown commit indexes
# into this list.
PROJECTOR_PROFILES: Tuple[ProjectorProfile, ...] = (PICO_GENIE, WINTECH_PRO4500)


def make_projector_body(
    profile: ProjectorProfile = PICO_GENIE,
) -> Tuple[np.ndarray, np.ndarray]:
    """Build a projector body box mesh from a `ProjectorProfile`.

    Defaults to `PICO_GENIE` so existing no-arg callers (HardwareScene,
    clip_detection's module-load bbox, tests) get the prior 55 x 55 x 55 mm
    Pico cube byte-identically. Pass `WINTECH_PRO4500` (or any profile) to
    build that projector's body.

    Dimensions come from `profile.body_dims_mm = (lx, ly, lz)`, centered on
    the local origin; `lz` is the optical-axis depth. Pose (translation +
    rotation into the lab/world frame) is `scene_compose.py`'s concern. For
    the Pico cube the bounding box spans [-27.5, +27.5] on every axis.

    Returns
    -------
    verts : (8, 3) float32, units mm
    faces : (12, 3) uint32
        CCW outward winding.
    """
    lx, ly, lz = profile.body_dims_mm
    return _centered_box(lx, ly, lz)


# ---------------------------------------------------------------------------
# Cylindrical primitives — used by lens builders.
# ---------------------------------------------------------------------------

def _cylinder(
    diameter_mm: float, length_mm: float, n_segments: int = 32
) -> Tuple[np.ndarray, np.ndarray]:
    """Build a closed uniform cylinder along the local +Z axis, centered.

    The cylinder spans `z in [-length/2, +length/2]` and has radius
    `diameter/2`. Both ends are capped (closed solid).

    Mesh layout (with `N = n_segments`):

    - Vertices (total `2N + 2`):
        - `verts[0 : N]`     — bottom ring at `z = -L/2`
        - `verts[N : 2N]`    — top ring at `z = +L/2`
        - `verts[2N]`        — bottom cap center
        - `verts[2N + 1]`    — top cap center

    - Faces (total `4N`):
        - Side surface: `2N` triangles. For each angular segment `i`,
          two triangles `(bot_i, bot_{i+1}, top_{i+1})` and
          `(bot_i, top_{i+1}, top_i)`. Outward normals point radially.
        - Bottom cap: `N` triangles fanning from `verts[2N]` to the
          bottom ring, wound so the outward normal is `-Z`.
        - Top cap: `N` triangles fanning from `verts[2N + 1]` to the
          top ring, wound so the outward normal is `+Z`.

    For `N = 32`: 66 verts, 128 triangles.

    Parameters
    ----------
    diameter_mm : float
        Cylinder diameter. Must be > 0.
    length_mm : float
        Cylinder length along the local +Z axis. Must be > 0.
    n_segments : int
        Number of angular subdivisions of the side surface. Must be >= 3.
        Default 32 — smooth enough for a digital-twin scene; bump for
        finer renders if needed.

    Returns
    -------
    verts : (2N + 2, 3) float32, units mm
    faces : (4N, 3) uint32
        CCW outward winding.
    """
    n = int(n_segments)
    r = float(diameter_mm) / 2.0
    half_l = float(length_mm) / 2.0

    angles = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False, dtype=np.float64)
    cos_a = np.cos(angles)
    sin_a = np.sin(angles)

    verts = np.empty((2 * n + 2, 3), dtype=np.float32)
    verts[:n, 0] = r * cos_a
    verts[:n, 1] = r * sin_a
    verts[:n, 2] = -half_l
    verts[n : 2 * n, 0] = r * cos_a
    verts[n : 2 * n, 1] = r * sin_a
    verts[n : 2 * n, 2] = +half_l
    verts[2 * n] = (0.0, 0.0, -half_l)         # bottom cap center
    verts[2 * n + 1] = (0.0, 0.0, +half_l)     # top cap center

    faces = _build_cylinder_faces(bot_offset=0, top_offset=n,
                                  bot_center=2 * n, top_center=2 * n + 1,
                                  n_segments=n)
    return verts, faces


def _stepped_cylinder(
    sections, n_segments: int = 32
) -> Tuple[np.ndarray, np.ndarray]:
    """Build a closed multi-section solid of revolution along local +Z.

    Each section is a `(d_start, d_end, length)` triple:
    - `d_start == d_end`  -> uniform cylinder section
    - `d_start != d_end`  -> conical frustum section
    Sections are concatenated along the local +Z axis from `z = -total/2`
    to `z = +total/2`. The solid is closed by end caps at the first
    section's start and the last section's end.

    Note on API
    -----------
    The original sub-task-2 prompt specified `(diameter, length)` 2-tuples,
    which cannot express a section with a non-zero-length taper between
    different diameters (a section with one diameter is a uniform
    cylinder; transitions between sections of different diameters would
    form zero-length frustum walls). The 3-tuple form `(d_start, d_end,
    length)` is the smallest extension that lets a single section
    represent either a cylinder OR a tapered frustum of finite length —
    which the camera lens needs.

    Mesh layout (with `N = n_segments` and `K = len(sections)`):

    - Ring layers along z: `K + 1` rings of `N` verts each. Ring `k`
      sits at `z = -total/2 + sum(section_lengths[:k])` and has radius
      derived from section diameters (ring 0 uses `sections[0][0]`;
      ring K uses `sections[K-1][1]`; interior ring `k` uses
      `sections[k-1][1]` which equals `sections[k][0]` for C0-continuous
      profiles).
    - Plus 2 cap centers: bottom center at `z = -total/2`,
      top center at `z = +total/2`.
    - Total verts: `(K + 1) * N + 2`.

    - Side faces: between each consecutive ring pair, `2N` triangles
      (one trapezoidal quad per angular segment, split into 2 tris).
      Total side tris: `2 K N`.
    - Cap faces: `N` tris each for bottom and top caps. Total: `2N`.
    - Total faces: `2N (K + 1)`.

    For the camera lens (K = 3, N = 32): 130 verts, 256 triangles.

    Parameters
    ----------
    sections : sequence of (float, float, float)
        Triples of `(d_start, d_end, length)` in mm. All values must be
        positive. The list must be non-empty.
    n_segments : int
        Angular subdivision count. Must be >= 3.

    Returns
    -------
    verts : ((K+1)*N + 2, 3) float32, units mm
    faces : (2N*(K+1), 3) uint32
        CCW outward winding.
    """
    n = int(n_segments)
    secs = [(float(a), float(b), float(L)) for a, b, L in sections]
    if not secs:
        raise ValueError("sections must be non-empty")
    total_length = sum(L for _, _, L in secs)
    half_l = total_length / 2.0

    # Ring radii: K+1 layers. Layer k uses the d_start of section k for
    # k < K, and the d_end of the last section for k == K. (For C0-
    # continuous profiles, sections[k-1].d_end == sections[k].d_start.)
    radii = [secs[0][0] / 2.0]
    for _, d_end, _ in secs:
        radii.append(d_end / 2.0)

    # Ring z-positions: cumulative sum of section lengths, shifted so
    # the assembly is centered on origin.
    z_positions = [-half_l]
    cumulative = 0.0
    for _, _, L in secs:
        cumulative += L
        z_positions.append(-half_l + cumulative)

    angles = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False, dtype=np.float64)
    cos_a = np.cos(angles)
    sin_a = np.sin(angles)

    n_rings = len(radii)
    verts = np.empty((n_rings * n + 2, 3), dtype=np.float32)
    for k in range(n_rings):
        r_k = radii[k]
        z_k = z_positions[k]
        verts[k * n : (k + 1) * n, 0] = r_k * cos_a
        verts[k * n : (k + 1) * n, 1] = r_k * sin_a
        verts[k * n : (k + 1) * n, 2] = z_k
    verts[n_rings * n] = (0.0, 0.0, z_positions[0])      # bottom cap center
    verts[n_rings * n + 1] = (0.0, 0.0, z_positions[-1]) # top cap center

    # Build side faces between each consecutive ring pair, plus caps at
    # the first and last rings.
    face_lists = []
    for k in range(n_rings - 1):
        face_lists.append(
            _build_side_faces(bot_offset=k * n, top_offset=(k + 1) * n, n_segments=n)
        )
    face_lists.append(
        _build_cap_faces(ring_offset=0,
                         center_index=n_rings * n,
                         n_segments=n, outward_z=-1)
    )
    face_lists.append(
        _build_cap_faces(ring_offset=(n_rings - 1) * n,
                         center_index=n_rings * n + 1,
                         n_segments=n, outward_z=+1)
    )
    faces = np.concatenate(face_lists, axis=0).astype(np.uint32, copy=False)
    return verts, faces


# --- Cylinder/frustum face-builder helpers ---------------------------------

def _build_side_faces(bot_offset: int, top_offset: int, n_segments: int) -> np.ndarray:
    """Two triangles per angular segment between bottom and top rings.

    Winding: outward normals point radially away from the z-axis.
    Concretely, for angular segment i (bottom-left to top-right pair):
        tri1 = (bot_i,     bot_{i+1}, top_{i+1})
        tri2 = (bot_i,     top_{i+1}, top_i)
    Both have `cross(e1, e2)` pointing radially outward when the bottom
    ring is below the top ring along +Z. This also produces outward
    normals for tapered frustums where bottom and top radii differ.
    """
    n = n_segments
    faces = np.empty((2 * n, 3), dtype=np.uint32)
    for i in range(n):
        i_next = (i + 1) % n
        b0, b1 = bot_offset + i, bot_offset + i_next
        t0, t1 = top_offset + i, top_offset + i_next
        faces[2 * i]     = (b0, b1, t1)
        faces[2 * i + 1] = (b0, t1, t0)
    return faces


def _build_cap_faces(
    ring_offset: int, center_index: int, n_segments: int, outward_z: int
) -> np.ndarray:
    """Fan-triangulate a cap from `center_index` out to the ring.

    `outward_z = +1` means the cap's outward normal points +Z (top cap);
    `outward_z = -1` means -Z (bottom cap). The winding flips between
    the two so `cross(e1, e2)` lands in the requested direction.
    """
    n = n_segments
    faces = np.empty((n, 3), dtype=np.uint32)
    for i in range(n):
        i_next = (i + 1) % n
        if outward_z > 0:
            # Top cap: viewed from +Z, ring vertices in CCW order.
            faces[i] = (center_index, ring_offset + i, ring_offset + i_next)
        else:
            # Bottom cap: viewed from -Z, ring vertices need CW order
            # (so the cross product points -Z).
            faces[i] = (center_index, ring_offset + i_next, ring_offset + i)
    return faces


def _build_cylinder_faces(
    bot_offset: int, top_offset: int, bot_center: int, top_center: int,
    n_segments: int
) -> np.ndarray:
    """Combined side + bottom-cap + top-cap face list for a uniform cylinder."""
    return np.concatenate(
        [
            _build_side_faces(bot_offset, top_offset, n_segments),
            _build_cap_faces(bot_offset, bot_center, n_segments, outward_z=-1),
            _build_cap_faces(top_offset, top_center, n_segments, outward_z=+1),
        ],
        axis=0,
    ).astype(np.uint32, copy=False)


# ---------------------------------------------------------------------------
# Lens builders.
# ---------------------------------------------------------------------------

def make_camera_lens() -> Tuple[np.ndarray, np.ndarray]:
    """Build the Edmund Optics #58-259 telecentric lens mesh.

    Stepped profile along local +Z (front element at +Z, rear mount at
    -Z; the rear mount is the side that meets the camera body):

        Rear cylinder:    55 mm diameter,  76 mm long   (at -Z, meets body)
        Taper:             55 mm -> 110 mm,  59 mm long (widens going +Z)
        Front cylinder:  110 mm diameter,  65 mm long   (at +Z, faces surface)
        Total length:                     200 mm

    Centered origin in lens-local frame; the bounding box spans
    [-100, +100] mm on z and [-55, +55] mm on x and y.

    The hardware values for length (65 / 59 / 76) are estimates pending
    the physical measurement called out in PROJECT_CONTEXT.md Sec 8
    item 8; the visible shape (fat front, taper, thin rear, ~200 mm
    total) is what matters for the digital-twin scene.

    Returns
    -------
    verts : (130, 3) float32, units mm
    faces : (256, 3) uint32
        CCW outward winding.
    """
    sections = [
        ( 55.0,  55.0, 76.0),   # rear mount at -Z (meets camera body)
        ( 55.0, 110.0, 59.0),   # taper widens going +Z
        (110.0, 110.0, 65.0),   # front element at +Z (faces surface)
    ]
    return _stepped_cylinder(sections)


def make_projector_lens(
    profile: ProjectorProfile = PICO_GENIE,
) -> Tuple[np.ndarray, np.ndarray]:
    """Build a projector lens stub-cylinder mesh from a `ProjectorProfile`.

    Defaults to `PICO_GENIE` -> 20 mm diameter, 5 mm long, byte-identical to
    the prior hardcoded mesh. Centered origin in lens-local frame, oriented
    along local +Z; for the Pico lens the bounding box spans [-10, +10] on
    x and y, [-2.5, +2.5] on z.

    The lens's off-center position on the body front face
    (`profile.lens_face_offset_mm`) is NOT encoded in this mesh — the lens
    mesh is a centered cylinder; the compose layer
    (`hardware_scene` / `scene_compose`) applies the offset translation when
    assembling the projector. Size comes from `profile.lens_diameter_mm` and
    `profile.lens_length_mm`.

    Returns
    -------
    verts : (66, 3) float32, units mm   (32-segment cylinder)
    faces : (128, 3) uint32
        CCW outward winding.
    """
    return _cylinder(profile.lens_diameter_mm, profile.lens_length_mm)


# ---------------------------------------------------------------------------
# Cone wireframe builders (Stage 4b task 4).
#
# These return (verts, edges) tuples — distinct from the (verts, faces)
# mesh contract above. `edges` is (M, 2) uint32: each row is a pair of
# vertex indices forming one line segment. The GUI renders these with
# pyqtgraph's GLLinePlotItem(mode='lines'); there are no faces and no
# winding convention (a wireframe has no orientable surface).
# ---------------------------------------------------------------------------

def make_projection_cone_wireframe(
    throw_distance_mm: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Wireframe of the Pico Genie projection cone.

    A rectangular pyramid: apex at the local origin (= projector
    lens-front in lens-local frame), opening along local +Z to a
    rectangular base at `z = +throw_distance_mm`.

    Pico Genie spec: 1.2:1 throw ratio, 16:9 aspect. So at throw
    distance L:

        base_width  = L / 1.2
        base_height = base_width * 9 / 16

    Unlike the telecentric viewing cone, this one genuinely diverges
    (non-telecentric consumer DLP optics) — the apex-to-base taper IS
    the perspective projection visualized.

    Vertices (5)
    ------------
        0 : apex at (0, 0, 0)
        1 : (+w/2, +h/2, L)
        2 : (-w/2, +h/2, L)
        3 : (-w/2, -h/2, L)
        4 : (+w/2, -h/2, L)

    Edges (8): 4 apex->corner slants + 4 base-perimeter segments.

    Parameters
    ----------
    throw_distance_mm : float
        Projector lens-front to projected-image-plane distance. Must
        be > 0.

    Returns
    -------
    verts : (5, 3) float32, units mm
    edges : (8, 2) uint32
    """
    L = float(throw_distance_mm)
    w = L / 1.2
    h = w * 9.0 / 16.0
    hw, hh = w / 2.0, h / 2.0

    verts = np.array(
        [
            [0.0, 0.0, 0.0],   # 0 apex
            [+hw, +hh, L],     # 1
            [-hw, +hh, L],     # 2
            [-hw, -hh, L],     # 3
            [+hw, -hh, L],     # 4
        ],
        dtype=np.float32,
    )
    edges = np.array(
        [
            [0, 1], [0, 2], [0, 3], [0, 4],   # apex -> base corners
            [1, 2], [2, 3], [3, 4], [4, 1],   # base perimeter
        ],
        dtype=np.uint32,
    )
    return verts, edges


def make_projection_cone_from_fov(
    fov_w_mm: float,
    fov_h_mm: float,
    distance_mm: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Wireframe of a projection cone whose base is a KNOWN FOV at a KNOWN distance.

    Stage 6 projector-swap commit 2 — for PRO4500-class lenses. Same rectangular
    pyramid SHAPE as `make_projection_cone_wireframe` (apex at the local origin =
    lens-front, opening along local +Z; 5 vertices, 8 edges, identical vertex
    order + edge list + dtypes), but the base is the lens's RATED FOV rectangle
    (`fov_w_mm` x `fov_h_mm`) at its RATED working distance (`distance_mm`):

        base half-width  = fov_w_mm / 2     at z = distance_mm
        base half-height = fov_h_mm / 2

    This is NOT a throw-ratio extrapolation (contrast `make_projection_cone_
    wireframe`, where the base is `L/1.2` x `(L/1.2)*9/16`). A PRO4500 lens fixes
    (working distance, FOV) as a pair, so the drawn cone is the true light cone
    from the lens to its rated image rectangle.

    Standalone by design (commit 2): the throw-ratio Pico builder is left
    byte-untouched; no shared helper is factored out, to avoid any float32 LSB
    shift on the Pico cone.

    Vertices (5)
    ------------
        0 : apex at (0, 0, 0)
        1 : (+fov_w/2, +fov_h/2, distance)
        2 : (-fov_w/2, +fov_h/2, distance)
        3 : (-fov_w/2, -fov_h/2, distance)
        4 : (+fov_w/2, -fov_h/2, distance)

    Edges (8): 4 apex->corner slants + 4 base-perimeter segments.

    Parameters
    ----------
    fov_w_mm, fov_h_mm : float
        Full field-of-view width / height covered on the surface. Must be > 0.
    distance_mm : float
        Working distance (lens-front to image plane). Must be > 0.

    Returns
    -------
    verts : (5, 3) float32, units mm
    edges : (8, 2) uint32
    """
    L = float(distance_mm)
    hw = float(fov_w_mm) / 2.0
    hh = float(fov_h_mm) / 2.0

    verts = np.array(
        [
            [0.0, 0.0, 0.0],   # 0 apex
            [+hw, +hh, L],     # 1
            [-hw, +hh, L],     # 2
            [-hw, -hh, L],     # 3
            [+hw, -hh, L],     # 4
        ],
        dtype=np.float32,
    )
    edges = np.array(
        [
            [0, 1], [0, 2], [0, 3], [0, 4],   # apex -> base corners
            [1, 2], [2, 3], [3, 4], [4, 1],   # base perimeter
        ],
        dtype=np.uint32,
    )
    return verts, edges


def make_viewing_cone_wireframe(
    working_distance_mm: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Wireframe of the Edmund #58-259 telecentric viewing volume.

    This is a rectangular PRISM, not a true cone. The Edmund #58-259
    is telecentric: the chief rays through its rear aperture stop are
    constrained parallel, so the imaged field is the same size at every
    object distance within the working range. The wireframe therefore
    has identical front and back rectangles (68 x 55 mm — the FOV on
    the test surface) connected by four parallel long edges.

    The parallel sides ARE the telecentric property visualized: a
    non-telecentric viewing cone would diverge from the lens toward
    the object; this one does not, because magnification is constant
    regardless of object distance. (Contrast the projection cone,
    which genuinely diverges — the Pico Genie is non-telecentric.)

    Front face at local z = 0 (= camera lens-front in lens-local
    frame); back face at z = +working_distance_mm (the test surface).

    Vertices (8)
    ------------
        0-3 : front rectangle at z=0     (+/-34, +/-27.5, 0)
        4-7 : back rectangle  at z=WD    (+/-34, +/-27.5, WD)

    Edges (12): 4 front-perimeter + 4 back-perimeter + 4 long parallels.

    Parameters
    ----------
    working_distance_mm : float
        Camera lens-front to test-surface distance (Edmund #58-259 WD
        range 132-182 mm). Must be > 0.

    Returns
    -------
    verts : (8, 3) float32, units mm
    edges : (12, 2) uint32
    """
    wd = float(working_distance_mm)
    # 68 x 55 mm FOV on the test surface (PROJECT_CONTEXT Sec 2).
    hx, hy = 68.0 / 2.0, 55.0 / 2.0

    verts = np.array(
        [
            [+hx, +hy, 0.0],   # 0 front
            [-hx, +hy, 0.0],   # 1
            [-hx, -hy, 0.0],   # 2
            [+hx, -hy, 0.0],   # 3
            [+hx, +hy, wd],    # 4 back
            [-hx, +hy, wd],    # 5
            [-hx, -hy, wd],    # 6
            [+hx, -hy, wd],    # 7
        ],
        dtype=np.float32,
    )
    edges = np.array(
        [
            [0, 1], [1, 2], [2, 3], [3, 0],   # front perimeter
            [4, 5], [5, 6], [6, 7], [7, 4],   # back perimeter
            [0, 4], [1, 5], [2, 6], [3, 7],   # parallel long edges
        ],
        dtype=np.uint32,
    )
    return verts, edges
