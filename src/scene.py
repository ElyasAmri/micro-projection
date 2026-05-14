"""scene.py — Pure-NumPy mesh-builder functions for the unified 3D scene.

Stage 4b adds the lab apparatus (camera body, projector body, lens
cylinders, projection / viewing cones) into the same 3D scene that
already shows the recovered surface. This module produces the raw
geometry primitives; the GUI layer wraps each `(verts, faces)` tuple
into a `pyqtgraph.opengl.GLMeshItem` separately.

Scope (sub-task 1)
------------------
- `make_camera_body()`   — FLIR Blackfly S body, 29 x 29 x 30 mm.
- `make_projector_body()`— Pico Genie Impact 2.0 Plus Elite cube,
                           55 x 55 x 55 mm.

Both bodies are centered on the origin of the scene frame. Pose
(translation + rotation into the lab frame) is sub-task 2's concern;
this module just produces geometrically correct boxes.

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

from typing import Tuple

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


def make_projector_body() -> Tuple[np.ndarray, np.ndarray]:
    """Build the Pico Genie Impact 2.0 Plus Elite projector body mesh.

    Dimensions: 55 x 55 x 55 mm cube (per PROJECT_CONTEXT Sec 2).

    Centered origin in scene frame. The corner-origin convention in
    Projector_Geometry_Summary.docx is a measurement convention; see
    sub-task 2 for the conversion when placing the lens.

    The bounding box spans [-27.5, +27.5] on every axis.

    Returns
    -------
    verts : (8, 3) float32, units mm
    faces : (12, 3) uint32
        CCW outward winding.
    """
    return _centered_box(55.0, 55.0, 55.0)
