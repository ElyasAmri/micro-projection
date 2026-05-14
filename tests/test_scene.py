"""Unit tests for src/scene.py — Stage 4b hardware-body mesh builders.

Coverage (Stage 4b sub-task 1)
------------------------------
Six parametrized checks per builder, two builders -> 12 cases:

  1. test_return_contract             — verts (N, 3) float32; faces (M, 3) uint32
  2. test_vertex_and_face_counts      — exactly 8 verts and 12 faces (closed box)
  3. test_bounding_box                 — min == -dim/2, max == +dim/2 per axis
  4. test_face_indices_in_range       — all indices in [0, N)
  5. test_no_degenerate_triangles     — each face has 3 distinct vertex indices
  6. test_winding_outward              — cross(e1, e2) for every face points
                                         away from the body center (origin),
                                         catching inverted CCW winding which
                                         would render as dark / inside-out
                                         under pyqtgraph's 'shaded' shader.

The bounding box is tested at `atol=1e-6` (mm). The dimensions are
encoded as Python floats, the box is constructed in float32, so the
worst-case round-trip error is ~`max(dim) * float32_eps` ~ 55 * 6e-8
~ 3e-6 mm. The 1e-6 tolerance is set with the convention that we'd
notice anything substantially worse than a single ULP of round-off.
"""
from __future__ import annotations

import numpy as np
import pytest

from scene import make_camera_body, make_projector_body


# (builder, dimensions, id) tuples for parametrization.
BUILDERS = [
    (make_camera_body, (29.0, 29.0, 30.0), "camera"),
    (make_projector_body, (55.0, 55.0, 55.0), "projector"),
]
BUILDER_IDS = [b[2] for b in BUILDERS]
BUILDER_PARAMS = [(b, d) for b, d, _ in BUILDERS]


# ---------------------------------------------------------------------------
# Check 1 — Return contract: shapes and dtypes.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("builder,dims", BUILDER_PARAMS, ids=BUILDER_IDS)
def test_return_contract(builder, dims):
    verts, faces = builder()

    assert isinstance(verts, np.ndarray), "verts is not an ndarray"
    assert verts.ndim == 2 and verts.shape[1] == 3, f"verts shape {verts.shape}"
    assert verts.dtype == np.float32, f"verts dtype {verts.dtype}"

    assert isinstance(faces, np.ndarray), "faces is not an ndarray"
    assert faces.ndim == 2 and faces.shape[1] == 3, f"faces shape {faces.shape}"
    assert faces.dtype == np.uint32, f"faces dtype {faces.dtype}"


# ---------------------------------------------------------------------------
# Check 2 — Exactly 8 vertices and 12 triangle faces (a closed box).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("builder,dims", BUILDER_PARAMS, ids=BUILDER_IDS)
def test_vertex_and_face_counts(builder, dims):
    verts, faces = builder()
    assert verts.shape[0] == 8, f"expected 8 vertices, got {verts.shape[0]}"
    assert faces.shape[0] == 12, f"expected 12 faces, got {faces.shape[0]}"


# ---------------------------------------------------------------------------
# Check 3 — Bounding box: dimensions correct and centered on origin.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("builder,dims", BUILDER_PARAMS, ids=BUILDER_IDS)
def test_bounding_box(builder, dims):
    verts, _ = builder()
    lx, ly, lz = dims
    expected_min = np.array([-lx / 2.0, -ly / 2.0, -lz / 2.0], dtype=np.float64)
    expected_max = np.array([+lx / 2.0, +ly / 2.0, +lz / 2.0], dtype=np.float64)
    actual_min = verts.min(axis=0).astype(np.float64)
    actual_max = verts.max(axis=0).astype(np.float64)
    np.testing.assert_allclose(actual_min, expected_min, atol=1e-6)
    np.testing.assert_allclose(actual_max, expected_max, atol=1e-6)


# ---------------------------------------------------------------------------
# Check 4 — Every face index addresses a real vertex.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("builder,dims", BUILDER_PARAMS, ids=BUILDER_IDS)
def test_face_indices_in_range(builder, dims):
    verts, faces = builder()
    n = verts.shape[0]
    assert faces.min() >= 0, f"negative face index: min={faces.min()}"
    assert faces.max() < n, f"face index out of range: max={faces.max()}, N={n}"


# ---------------------------------------------------------------------------
# Check 5 — No triangle reuses the same vertex index (no degenerate face).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("builder,dims", BUILDER_PARAMS, ids=BUILDER_IDS)
def test_no_degenerate_triangles(builder, dims):
    _, faces = builder()
    for k, face in enumerate(faces):
        assert len(set(face.tolist())) == 3, (
            f"face {k} has repeated vertex index: {face.tolist()}"
        )


# ---------------------------------------------------------------------------
# Check 6 — CCW outward winding on every face.
#
# For face (a, b, c): cross(verts[b] - verts[a], verts[c] - verts[a])
# is the face normal up to a sign. CCW-from-outside winding makes this
# normal point AWAY from the body center (here, the origin). We check
# the dot product of the normal with the face centroid (which is also
# the centroid-from-origin vector for a centered body) is strictly
# positive on every face.
#
# Edge-order note: the cross product is `cross(e1, e2)` with
# `e1 = v[b] - v[a]` and `e2 = v[c] - v[a]`. Swapping e1/e2 flips the
# sign and makes every face fail — loud failure, but worth being
# deliberate about the order so a future reader doesn't misread it
# as a subtle bug.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("builder,dims", BUILDER_PARAMS, ids=BUILDER_IDS)
def test_winding_outward(builder, dims):
    verts, faces = builder()
    body_center = np.zeros(3, dtype=np.float64)  # bodies are centered

    for k, (a, b, c) in enumerate(faces):
        v0 = verts[a].astype(np.float64)
        v1 = verts[b].astype(np.float64)
        v2 = verts[c].astype(np.float64)
        e1 = v1 - v0
        e2 = v2 - v0
        normal = np.cross(e1, e2)
        centroid = (v0 + v1 + v2) / 3.0
        outward_dir = centroid - body_center
        dot = float(np.dot(normal, outward_dir))
        assert dot > 0.0, (
            f"face {k} (verts {[int(a), int(b), int(c)]}) has inverted winding: "
            f"normal . outward = {dot:.3e}"
        )
