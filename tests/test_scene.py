"""Unit tests for src/scene.py — Stage 4b hardware-body mesh builders.

Coverage
--------
Six universal checks parametrized over eight builders -> 48 cases:

  1. test_return_contract             — verts (N, 3) float32; faces (M, 3) uint32
  2. test_vertex_and_face_counts      — exact N and M per builder
  3. test_bounding_box                 — min == -dim/2, max == +dim/2 per axis
  4. test_face_indices_in_range       — all indices in [0, N)
  5. test_no_degenerate_triangles     — each face has 3 distinct vertex indices
  6. test_winding_outward              — cross(e1, e2) for every face points
                                         away from the body center (origin)

Parametrized builders
---------------------
- `make_camera_body`         — 29 x 29 x 30 mm box
- `make_projector_body`      — 55 mm cube (default PICO_GENIE profile)
- `make_projector_body(PRO4500)` — 84 x 54 x 210 mm box (PRO4500 profile)
- `_cylinder` reference      — 40 x 40 x 100 mm uniform cylinder (n_segments=32)
- `_stepped_cylinder` ref    — 30 mm dia x 60 mm long (2 uniform sections)
- `make_camera_lens`         — 110 mm front / 55 mm rear stepped lens, 200 mm
- `make_projector_lens`      — 20 x 20 x 5 mm uniform cylinder (default PICO)
- `make_projector_lens(PRO4500)` — 20 x 20 x 5 mm uniform cylinder (PRO4500)

Projector-profile tests (Stage 6 projector-swap commit 1) live at the bottom:
the default-is-Pico byte-identity guard and the profile/registry sanity checks.

The reference cylinder/stepped builders use different parameters from the
public lens builders to cover the helper code paths with distinct inputs.

Tolerances
----------
- Bounding box: `atol=1e-6` mm (worst-case float32 round-off for the largest
  coordinate (110 mm) is ~7e-6 mm; the test tolerance is set at "ULP-scale
  on the largest dimension" which the camera lens just barely passes —
  see test_bounding_box's atol if it ever needs to widen).
- The cylinder builders rely on `n_segments = 32` producing exact ±r
  extents on x and y because the angle grid `np.linspace(0, 2 pi, 32,
  endpoint=False)` includes 0, pi/2, pi, 3 pi/2 — placing one vertex
  per quadrant axis. Any n_segments divisible by 4 has the same property;
  non-multiples-of-4 would shrink the bounding box slightly.
"""
from __future__ import annotations

import numpy as np
import pytest

from scene import (
    PICO_GENIE,
    PROJECTOR_PROFILES,
    WINTECH_PRO4500,
    LensOption,
    ProjectorProfile,
    _centered_box,
    _cylinder,
    _stepped_cylinder,
    make_camera_body,
    make_camera_lens,
    make_projection_cone_from_fov,
    make_projection_cone_wireframe,
    make_projector_body,
    make_projector_lens,
    make_viewing_cone_wireframe,
)


# Each builder entry: (callable, bbox_dims_mm, expected_verts, expected_faces, id)
# bbox_dims_mm is (Lx, Ly, Lz); the bounding box is [-Lx/2, +Lx/2] etc.
BUILDERS = [
    (make_camera_body,    (29.0, 29.0, 30.0),    8,  12, "camera_body"),
    (make_projector_body, (55.0, 55.0, 55.0),    8,  12, "projector_body"),
    # PRO4500 body via its profile: 84 x 54 x 210 mm box (lz=210 optical-axis
    # depth). Constructible + universally checked, but NOT displayed (commit 1).
    (lambda: make_projector_body(WINTECH_PRO4500),
                          (84.0, 54.0, 210.0),   8,  12, "projector_body_pro4500"),
    # PRO4500 lens via its profile: 20 x 5 mm stub cylinder (same as Pico).
    (lambda: make_projector_lens(WINTECH_PRO4500),
                          (20.0, 20.0, 5.0),     66, 128, "projector_lens_pro4500"),
    # _cylinder reference: 40 dia x 100 long, n=32 -> 2*32+2=66 verts, 4*32=128 tris
    (lambda: _cylinder(40.0, 100.0),
                          (40.0, 40.0, 100.0),   66, 128, "cylinder_ref"),
    # _stepped_cylinder reference: K=2 uniform-diameter sections of 30 dia.
    # Lengths 20 + 40 = 60 total. (K+1)*N + 2 = 3*32+2 = 98 verts.
    # 2*N*(K+1) = 2*32*3 = 192 faces.
    (lambda: _stepped_cylinder(
        [(30.0, 30.0, 20.0), (30.0, 30.0, 40.0)]),
                          (30.0, 30.0, 60.0),    98, 192, "stepped_cylinder_ref"),
    # camera lens: 3 sections (65 + 59 + 76 = 200). Max diameter 110 in the
    # front cylinder section. (K=3, N=32) -> 4*32+2=130 verts, 2*32*4=256 faces.
    (make_camera_lens,    (110.0, 110.0, 200.0), 130, 256, "camera_lens"),
    # projector lens: _cylinder(20, 5). 66 verts, 128 faces.
    (make_projector_lens, (20.0, 20.0, 5.0),     66, 128, "projector_lens"),
]
BUILDER_IDS = [b[4] for b in BUILDERS]
# Trim entries for tests that don't need every field — keep parametrize concise.
BUILDER_PARAMS = [(b[0], b[1], b[2], b[3]) for b in BUILDERS]


# ---------------------------------------------------------------------------
# Check 1 — Return contract: shapes and dtypes.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("builder,dims,n_verts,n_faces", BUILDER_PARAMS, ids=BUILDER_IDS)
def test_return_contract(builder, dims, n_verts, n_faces):
    verts, faces = builder()

    assert isinstance(verts, np.ndarray), "verts is not an ndarray"
    assert verts.ndim == 2 and verts.shape[1] == 3, f"verts shape {verts.shape}"
    assert verts.dtype == np.float32, f"verts dtype {verts.dtype}"

    assert isinstance(faces, np.ndarray), "faces is not an ndarray"
    assert faces.ndim == 2 and faces.shape[1] == 3, f"faces shape {faces.shape}"
    assert faces.dtype == np.uint32, f"faces dtype {faces.dtype}"


# ---------------------------------------------------------------------------
# Check 2 — Exact vertex and face counts per builder.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("builder,dims,n_verts,n_faces", BUILDER_PARAMS, ids=BUILDER_IDS)
def test_vertex_and_face_counts(builder, dims, n_verts, n_faces):
    verts, faces = builder()
    assert verts.shape[0] == n_verts, (
        f"expected {n_verts} vertices, got {verts.shape[0]}"
    )
    assert faces.shape[0] == n_faces, (
        f"expected {n_faces} faces, got {faces.shape[0]}"
    )


# ---------------------------------------------------------------------------
# Check 3 — Bounding box: dimensions correct and centered on origin.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("builder,dims,n_verts,n_faces", BUILDER_PARAMS, ids=BUILDER_IDS)
def test_bounding_box(builder, dims, n_verts, n_faces):
    verts, _ = builder()
    lx, ly, lz = dims
    expected_min = np.array([-lx / 2.0, -ly / 2.0, -lz / 2.0], dtype=np.float64)
    expected_max = np.array([+lx / 2.0, +ly / 2.0, +lz / 2.0], dtype=np.float64)
    actual_min = verts.min(axis=0).astype(np.float64)
    actual_max = verts.max(axis=0).astype(np.float64)
    # 1e-5 mm tolerance accommodates float32 round-off on the largest coord
    # (110 mm * float32_eps ~= 7e-6 mm worst case).
    np.testing.assert_allclose(actual_min, expected_min, atol=1e-5)
    np.testing.assert_allclose(actual_max, expected_max, atol=1e-5)


# ---------------------------------------------------------------------------
# Check 4 — Every face index addresses a real vertex.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("builder,dims,n_verts,n_faces", BUILDER_PARAMS, ids=BUILDER_IDS)
def test_face_indices_in_range(builder, dims, n_verts, n_faces):
    verts, faces = builder()
    n = verts.shape[0]
    assert faces.min() >= 0, f"negative face index: min={faces.min()}"
    assert faces.max() < n, f"face index out of range: max={faces.max()}, N={n}"


# ---------------------------------------------------------------------------
# Check 5 — No triangle reuses the same vertex index (no degenerate face).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("builder,dims,n_verts,n_faces", BUILDER_PARAMS, ids=BUILDER_IDS)
def test_no_degenerate_triangles(builder, dims, n_verts, n_faces):
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
@pytest.mark.parametrize("builder,dims,n_verts,n_faces", BUILDER_PARAMS, ids=BUILDER_IDS)
def test_winding_outward(builder, dims, n_verts, n_faces):
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


# ===========================================================================
# Stage 4b task 4 — cone WIREFRAME builders.
#
# These return (verts, edges) instead of (verts, faces). The winding
# check above does NOT apply (wireframes have no orientable surface),
# so they are intentionally NOT in BUILDERS — they get their own
# parametrize list and a reduced set of universal checks (5, not 6).
#
# Each entry: (builder, arg, expected_dims, n_verts, n_edges, id).
# `arg` is the single throw / WD argument; expected_dims is the
# (full-x, full-y, full-z) extent of the wireframe bounding box (NOT
# centered — cones run z in [0, length] with apex / front face at the
# origin).
# ===========================================================================
WIREFRAME_BUILDERS = [
    # Projection cone at throw=150: width = 150/1.2 = 125,
    # height = 125 * 9/16 = 70.3125, length = 150. 5 verts, 8 edges.
    (
        make_projection_cone_wireframe, 150.0,
        (125.0, 70.3125, 150.0), 5, 8, "projection_cone",
    ),
    # Viewing cone at WD=157: 68 x 55 mm prism, length 157.
    # 8 verts, 12 edges.
    (
        make_viewing_cone_wireframe, 157.0,
        (68.0, 55.0, 157.0), 8, 12, "viewing_cone",
    ),
]
WIREFRAME_IDS = [b[5] for b in WIREFRAME_BUILDERS]
WIREFRAME_PARAMS = [(b[0], b[1], b[2], b[3], b[4]) for b in WIREFRAME_BUILDERS]


@pytest.mark.parametrize(
    "builder,arg,dims,n_verts,n_edges", WIREFRAME_PARAMS, ids=WIREFRAME_IDS
)
def test_wireframe_return_contract(builder, arg, dims, n_verts, n_edges):
    verts, edges = builder(arg)
    assert isinstance(verts, np.ndarray) and verts.shape == (n_verts, 3)
    assert verts.dtype == np.float32, f"verts dtype {verts.dtype}"
    assert isinstance(edges, np.ndarray) and edges.shape == (n_edges, 2)
    assert edges.dtype == np.uint32, f"edges dtype {edges.dtype}"


@pytest.mark.parametrize(
    "builder,arg,dims,n_verts,n_edges", WIREFRAME_PARAMS, ids=WIREFRAME_IDS
)
def test_wireframe_vertex_and_edge_counts(builder, arg, dims, n_verts, n_edges):
    verts, edges = builder(arg)
    assert verts.shape[0] == n_verts, (
        f"expected {n_verts} verts, got {verts.shape[0]}"
    )
    assert edges.shape[0] == n_edges, (
        f"expected {n_edges} edges, got {edges.shape[0]}"
    )


@pytest.mark.parametrize(
    "builder,arg,dims,n_verts,n_edges", WIREFRAME_PARAMS, ids=WIREFRAME_IDS
)
def test_wireframe_bounding_box(builder, arg, dims, n_verts, n_edges):
    """Cones are NOT centered: x/y span +/-dim/2 but z runs [0, length].

    The apex (projection) / front face (viewing) sits at the local
    origin; the cone opens toward +Z.
    """
    verts, _ = builder(arg)
    dx, dy, dz = dims
    mn = verts.min(axis=0).astype(np.float64)
    mx = verts.max(axis=0).astype(np.float64)
    np.testing.assert_allclose(mn, [-dx / 2.0, -dy / 2.0, 0.0], atol=1e-4)
    np.testing.assert_allclose(mx, [+dx / 2.0, +dy / 2.0, dz], atol=1e-4)


@pytest.mark.parametrize(
    "builder,arg,dims,n_verts,n_edges", WIREFRAME_PARAMS, ids=WIREFRAME_IDS
)
def test_wireframe_edge_indices_in_range(builder, arg, dims, n_verts, n_edges):
    verts, edges = builder(arg)
    n = verts.shape[0]
    assert edges.min() >= 0, f"negative edge index: {edges.min()}"
    assert edges.max() < n, f"edge index out of range: {edges.max()}, N={n}"


@pytest.mark.parametrize(
    "builder,arg,dims,n_verts,n_edges", WIREFRAME_PARAMS, ids=WIREFRAME_IDS
)
def test_wireframe_no_degenerate_edges(builder, arg, dims, n_verts, n_edges):
    _, edges = builder(arg)
    for k, (a, b) in enumerate(edges):
        assert a != b, f"edge {k} connects a vertex to itself: ({a}, {b})"


# --- Cone-specific dimension checks at typical pose values. ---------------

def test_projection_cone_obeys_throw_ratio_and_aspect():
    """1.2:1 throw, 16:9 aspect at throw=150 -> base 125 x 70.3125."""
    verts, _ = make_projection_cone_wireframe(150.0)
    apex = verts[0]
    np.testing.assert_allclose(apex, [0.0, 0.0, 0.0], atol=1e-6)
    base = verts[1:]
    base_w = float(base[:, 0].max() - base[:, 0].min())
    base_h = float(base[:, 1].max() - base[:, 1].min())
    assert base_w == pytest.approx(150.0 / 1.2, abs=1e-4)        # 125.0
    assert base_h == pytest.approx((150.0 / 1.2) * 9 / 16, abs=1e-4)  # 70.3125
    assert float(base[:, 2].min()) == pytest.approx(150.0, abs=1e-4)


def test_viewing_cone_is_parallel_prism():
    """Telecentric: front and back rectangles are identical (68 x 55).

    The defining check — a non-telecentric cone would have a
    different-sized back face. Here front (z=0) and back (z=WD)
    rectangles must match exactly in x/y extent.
    """
    verts, _ = make_viewing_cone_wireframe(157.0)
    front = verts[verts[:, 2] == 0.0]
    back = verts[verts[:, 2] == 157.0]
    assert front.shape[0] == 4 and back.shape[0] == 4
    for arr in (front, back):
        assert float(arr[:, 0].max() - arr[:, 0].min()) == pytest.approx(
            68.0, abs=1e-4
        )
        assert float(arr[:, 1].max() - arr[:, 1].min()) == pytest.approx(
            55.0, abs=1e-4
        )


# ===========================================================================
# Projector profiles (Stage 6 projector-swap commit 1).
#
# The profile spine makes the projector mesh builders profile-driven without
# changing the default (Pico Genie) output. PRO4500 is constructible + checked
# above via BUILDERS, but NOT displayed — HardwareScene still builds Pico.
# These tests pin (a) the default-is-Pico byte-identity and (b) the profile /
# registry data.
# ===========================================================================
def test_make_projector_default_is_pico_byte_identical():
    """No-arg builders == explicit PICO_GENIE == the prior hardcoded mesh.

    Guards the byte-identity the whole Option-A swap depends on: every existing
    no-arg caller (HardwareScene, clip_detection's module-load bbox) must get
    the exact prior Pico mesh, so nothing visible changes this commit.
    """
    # Body: default == PICO_GENIE == _centered_box(55, 55, 55).
    dv, dfa = make_projector_body()
    pv, pfa = make_projector_body(PICO_GENIE)
    bv, bfa = _centered_box(55.0, 55.0, 55.0)
    np.testing.assert_array_equal(dv, pv)
    np.testing.assert_array_equal(dfa, pfa)
    np.testing.assert_array_equal(dv, bv)
    np.testing.assert_array_equal(dfa, bfa)

    # Lens: default == PICO_GENIE == _cylinder(20, 5).
    dlv, dlf = make_projector_lens()
    plv, plf = make_projector_lens(PICO_GENIE)
    clv, clf = _cylinder(20.0, 5.0)
    np.testing.assert_array_equal(dlv, plv)
    np.testing.assert_array_equal(dlf, plf)
    np.testing.assert_array_equal(dlv, clv)
    np.testing.assert_array_equal(dlf, clf)


def test_pro4500_body_differs_from_pico():
    """The PRO4500 body is genuinely a different (oriented) box, not the cube.

    Sanity that the profile actually drives the mesh: same vert/face counts,
    but the bounding box is the 84 x 54 x 210 mm oriented box (lz=210 is the
    optical-axis depth) — distinct from Pico's 55^3 cube.
    """
    pico_v, _ = make_projector_body(PICO_GENIE)
    pro_v, _ = make_projector_body(WINTECH_PRO4500)
    assert pro_v.shape == pico_v.shape  # both 8-vertex boxes
    assert not np.array_equal(pro_v, pico_v)
    span = (pro_v.max(axis=0) - pro_v.min(axis=0)).astype(np.float64)
    np.testing.assert_allclose(span, [84.0, 54.0, 210.0], atol=1e-4)


def test_projector_registry_order_and_membership():
    """Registry mirrors FOV_PRESETS: Pico first (default/active), PRO4500 next."""
    assert isinstance(PROJECTOR_PROFILES, tuple)
    assert len(PROJECTOR_PROFILES) == 2
    assert PROJECTOR_PROFILES[0] is PICO_GENIE  # first == default/active
    assert PROJECTOR_PROFILES[1] is WINTECH_PRO4500
    assert all(isinstance(p, ProjectorProfile) for p in PROJECTOR_PROFILES)
    names = [p.name for p in PROJECTOR_PROFILES]
    assert names == ["Pico Genie Impact 2.0 Plus Elite", "Wintech PRO4500"]


def test_profile_field_values():
    """The two profiles carry the agreed visual specs, slots empty this commit."""
    # Pico exactly reproduces the prior hardcoded values.
    assert PICO_GENIE.body_dims_mm == (55.0, 55.0, 55.0)
    assert PICO_GENIE.lens_diameter_mm == 20.0
    assert PICO_GENIE.lens_length_mm == 5.0
    assert PICO_GENIE.lens_face_offset_mm == (-6.5, 17.5, 1.5)

    # PRO4500: 84 x 54 x 210 body (lz=210 optical-axis depth), centered lens
    # (0% offset) with ~2 mm recess.
    assert WINTECH_PRO4500.body_dims_mm == (84.0, 54.0, 210.0)
    assert WINTECH_PRO4500.lens_diameter_mm == 20.0
    assert WINTECH_PRO4500.lens_length_mm == 5.0
    assert WINTECH_PRO4500.lens_face_offset_mm == (0.0, 0.0, 2.0)

    # cone_params slot stays None this commit for both.
    for prof in (PICO_GENIE, WINTECH_PRO4500):
        assert prof.cone_params is None


# ===========================================================================
# PRO4500 lens table + FOV-driven projection cone (Stage 6 projector-swap
# commit 2). The PRO4500 cone is constructible + checked here, but NOT drawn —
# HardwareScene still calls the Pico throw-ratio builder (verified headless in
# the commit's verification, not in this pure-mesh test module).
# ===========================================================================
@pytest.mark.parametrize(
    "fov_w,fov_h,dist,hw,hh",
    [
        (65.6, 41.0, 92.0, 32.8, 20.5),     # PRO4500 92 mm lens
        (131.2, 82.0, 184.0, 65.6, 41.0),   # PRO4500 184 mm lens
    ],
    ids=["lens_92mm", "lens_184mm"],
)
def test_projection_cone_from_fov(fov_w, fov_h, dist, hw, hh):
    """The FOV cone's base is the rated FOV rectangle at the rated WD.

    Apex at the origin; base corners at +/-fov_w/2, +/-fov_h/2, z=distance —
    the lens's true light cone, NOT a throw-ratio extrapolation. Same 5-vert /
    8-edge shape + dtypes + edge convention as the Pico builder.
    """
    verts, edges = make_projection_cone_from_fov(fov_w, fov_h, dist)
    assert verts.shape == (5, 3) and verts.dtype == np.float32
    assert edges.shape == (8, 2) and edges.dtype == np.uint32

    # Apex at origin.
    np.testing.assert_allclose(verts[0], [0.0, 0.0, 0.0], atol=1e-6)
    # Base = rated FOV rectangle at z = distance.
    base = verts[1:]
    np.testing.assert_allclose(base[:, 0].max(), +hw, atol=1e-4)
    np.testing.assert_allclose(base[:, 0].min(), -hw, atol=1e-4)
    np.testing.assert_allclose(base[:, 1].max(), +hh, atol=1e-4)
    np.testing.assert_allclose(base[:, 1].min(), -hh, atol=1e-4)
    np.testing.assert_allclose(base[:, 2], dist, atol=1e-4)

    # Edge convention identical to the Pico cone builder (same apex/base wiring).
    _, pico_edges = make_projection_cone_wireframe(100.0)
    np.testing.assert_array_equal(edges, pico_edges)

    # It is genuinely FOV-driven, not the throw-ratio cone: at the same
    # distance the Pico builder would give a different base width (dist/1.2).
    pico_v, _ = make_projection_cone_wireframe(dist)
    pico_base_w = float(pico_v[1:, 0].max() - pico_v[1:, 0].min())
    assert abs(pico_base_w - 2.0 * hw) > 1.0  # different base => not a throw-ratio


def test_pico_cone_byte_unchanged_guard():
    """Pico throw-ratio cone at throw=150 is literally unchanged: base 125 x
    70.3125 (corners +/-62.5, +/-35.15625) at z=150, apex at origin.

    Guards the commit promise that make_projection_cone_wireframe's body was
    not touched. The added FOV builder is separate; this pins the Pico bytes.
    """
    verts, edges = make_projection_cone_wireframe(150.0)
    expected_verts = np.array(
        [
            [0.0, 0.0, 0.0],
            [+62.5, +35.15625, 150.0],
            [-62.5, +35.15625, 150.0],
            [-62.5, -35.15625, 150.0],
            [+62.5, -35.15625, 150.0],
        ],
        dtype=np.float32,
    )
    np.testing.assert_array_equal(verts, expected_verts)
    expected_edges = np.array(
        [[0, 1], [0, 2], [0, 3], [0, 4], [1, 2], [2, 3], [3, 4], [4, 1]],
        dtype=np.uint32,
    )
    np.testing.assert_array_equal(edges, expected_edges)


def test_pro4500_lens_table_and_default_index():
    """PRO4500 carries the 2 lenses in WD order; default index resolves to 184 mm.

    Pico keeps an empty table (default index moot).
    """
    opts = WINTECH_PRO4500.lens_options
    assert len(opts) == 2
    assert [o.working_distance_mm for o in opts] == [92.0, 184.0]  # ascending WD
    assert WINTECH_PRO4500.default_lens_index == 1
    chosen = opts[WINTECH_PRO4500.default_lens_index]
    assert chosen.working_distance_mm == 184.0
    assert (chosen.fov_w_mm, chosen.fov_h_mm) == (131.2, 82.0)  # full 68x55 coverage

    # Pico: single-lens / throw-ratio projector — empty table, index 0 (moot).
    assert PICO_GENIE.lens_options == ()
    assert PICO_GENIE.default_lens_index == 0


def test_lens_option_field_values():
    """Both PRO4500 lens rows carry the settled rated specs (named access)."""
    near, far = WINTECH_PRO4500.lens_options
    assert near == LensOption(92.0, 65.6, 41.0, 50.0)
    assert far == LensOption(184.0, 131.2, 82.0, 100.0)
    assert near.working_distance_mm == 92.0
    assert (near.fov_w_mm, near.fov_h_mm) == (65.6, 41.0)
    assert near.projected_pixel_um == 50.0
    assert far.projected_pixel_um == 100.0
