"""stl_loader.py — STL mesh -> heightmap, pure NumPy (no GUI).

Peer of `src/test_surfaces.py` in the surface-library role: where
`make_flat` / `make_gaussian` synthesize analytic heightmaps, this module
rasterizes an arbitrary STL solid into the *same* contract —
`(shape, pixel_size_mm) -> (H, W) float64 mm` — so an imported part drops
into the existing pipeline with zero math-layer changes.

Rasterization is projected-barycentric with a per-pixel max-z upper
envelope: each triangle is projected to the XY plane and its covered
pixels take its barycentrically interpolated z; the pixel keeps the
maximum z over all covering triangles. For a closed solid this yields the
camera-visible top surface (the bottom shell is discarded), which is what
fringe projection actually sees.

Module scope
------------
- No GUI imports. Pure NumPy + numpy-stl.
- mm is assumed for STL coordinates (no unit metadata exists in STL; mm
  is the CAD default). No unit parameter — a wrong-unit file is caught
  by the downstream bbox check in main_window.py's _load_stl_from_path,
  not here.
- The 120 mm height cap and any per-part working-volume policy are
  downstream concerns (main_window.py's bbox guard); this loader does
  not enforce them.
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple, Union

import numpy as np
from stl import mesh as _stl_mesh

# Inclusive barycentric edge tolerance: a pixel center exactly on a shared
# triangle edge counts as inside for both triangles, so no hairline gaps
# appear along internal edges. The two triangles interpolate the same z
# there, so the max-z envelope is unaffected.
_BARY_EPS = 1e-9

# XY-projected triangle area denominator below which the triangle is
# treated as degenerate (vertical-wall triangles of a closed solid project
# to a line — exactly zero area). Absolute, in mm**2; vertical walls are
# exactly degenerate, not merely small, so an absolute floor is correct.
_DEGENERATE_DEN = 1e-12

PathLike = Union[str, Path]


def _load_mesh(path: PathLike) -> "_stl_mesh.Mesh":
    """Load an STL into a numpy-stl Mesh.

    Raises
    ------
    ValueError
        If the file contains zero triangles. An empty mesh is a malformed
        input, not a valid flat surface; surfacing it lets the eventual
        GUI import path reject the file instead of silently showing a
        flat heightmap indistinguishable from a real flat part.
    """
    m = _stl_mesh.Mesh.from_file(str(path))
    if m.vectors.shape[0] == 0:
        raise ValueError(f"STL contains no triangles: {path}")
    return m


def _grid_axes_mm(
    shape: Tuple[int, int], pixel_size_mm: float
) -> Tuple[np.ndarray, np.ndarray]:
    """Per-column X and per-row Y pixel-center coordinates, in mm.

    `output[i, j]` samples world `x = x_mm[j]`, `y = y_mm[i]`.
    """
    # Coordinate convention mirrors src/test_surfaces._centered_grid_mm
    # (kept in sync by convention; the 4-line formula is too small to
    # warrant cross-module coupling).
    H, W = shape
    x_mm = (np.arange(W, dtype=np.float64) - (W - 1) / 2.0) * pixel_size_mm
    y_mm = (np.arange(H, dtype=np.float64) - (H - 1) / 2.0) * pixel_size_mm
    return x_mm, y_mm


# Row-band pixel cap for the rasterizer's vectorized inner block. A triangle
# whose clamped pixel bbox exceeds this many pixels is processed in horizontal
# row-bands so the transient 2D arrays stay bounded — a single 450 mm baseplate
# triangle would otherwise build full-grid (4500x4501 ~ 20 M-pixel) temporaries
# at once (the ~610 MB peak). Banding is byte-identical to a single block: the
# per-pixel arithmetic is unchanged and the max-z envelope is order-independent
# across bands, so only peak memory changes, never the output.
_RASTER_BAND_PX = 1_000_000


def _rasterize_triangles(
    triangles: np.ndarray,
    shape: Tuple[int, int],
    pixel_size_mm: float,
) -> np.ndarray:
    """Projected-barycentric rasterization with per-pixel max-z.

    Parameters
    ----------
    triangles : (N, 3, 3) float64
        XY-centered triangle vertices; last axis is (x, y, z) in mm.
    shape : (H, W)
    pixel_size_mm : float

    Returns
    -------
    (H, W) float64 with -inf in never-covered pixels (the caller lifts).

    Implementation note (Stage 6 B.3b-perf.1)
    -----------------------------------------
    Vectorized + row-banded rewrite of the original per-triangle Python loop,
    BYTE-IDENTICAL to it (pinned by tests/test_rasterizer_fixture.py against the
    perf.0 baseline, including the cube's ~1.78e-15 sub-ULP residual). Three
    changes, none of which alter per-pixel arithmetic:

    1. Per-triangle setup (`den`, the floor/ceil/clamp pixel bbox, the
       degenerate + off-grid skip masks) is computed for all triangles at once;
       the loop runs only over survivors. The two coordinate paths stay separate
       exactly as before — bbox via `coord * inv_ps + offset`, inside-test via
       the `x_mm`/`y_mm` pixel CENTERS — because unifying them drifts by ULPs.
    2. The inside-test uses the SEPARABLE barycentric form: `l1`/`l2` are affine,
       so `((y2-y3)*(gx-x3) + (x3-x2)*(gy-y3)) * inv_den` factors into
       `(tx[col] + ty[row]) * inv_den` via one broadcast-add. Each element is a
       single IEEE add of the SAME two operands the fused 2D form adds (no
       regrouping, so non-associativity cannot bite) — proven equal by the
       perf.0 gate. This drops the `meshgrid` and the two 2D coordinate-diff
       products.
    3. Triangles whose bbox exceeds `_RASTER_BAND_PX` are processed in row-bands
       to cap transient memory.
    """
    H, W = shape
    x_mm, y_mm = _grid_axes_mm(shape, pixel_size_mm)
    out = np.full((H, W), -np.inf, dtype=np.float64)

    tris = np.asarray(triangles, dtype=np.float64)
    if tris.shape[0] == 0:
        return out

    inv_ps = 1.0 / pixel_size_mm
    col_off = (W - 1) / 2.0
    row_off = (H - 1) / 2.0

    # --- Per-triangle setup, vectorized (byte-identical scalars; no per-tri
    # Python-loop overhead for the skip tests + bbox arithmetic). ---
    x1 = tris[:, 0, 0]; y1 = tris[:, 0, 1]; z1 = tris[:, 0, 2]
    x2 = tris[:, 1, 0]; y2 = tris[:, 1, 1]; z2 = tris[:, 1, 2]
    x3 = tris[:, 2, 0]; y3 = tris[:, 2, 1]; z3 = tris[:, 2, 2]

    # Signed projected-area denominator, same form as the scalar code.
    den = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)

    # Pixel-index bbox per triangle (same floor/ceil/clamp arithmetic).
    cols_f = np.stack((x1, x2, x3), axis=1) * inv_ps + col_off
    rows_f = np.stack((y1, y2, y3), axis=1) * inv_ps + row_off
    j0 = np.maximum(0, np.floor(cols_f.min(axis=1)).astype(np.int64))
    j1 = np.minimum(W - 1, np.ceil(cols_f.max(axis=1)).astype(np.int64))
    i0 = np.maximum(0, np.floor(rows_f.min(axis=1)).astype(np.int64))
    i1 = np.minimum(H - 1, np.ceil(rows_f.max(axis=1)).astype(np.int64))

    # Skip the same triangles the scalar code skips: degenerate projection
    # (|den| < tol) and footprint entirely off-grid. Survivors run in ascending
    # index order (the max-z envelope is order-independent regardless).
    active = np.nonzero(
        (np.abs(den) >= _DEGENERATE_DEN) & (j0 <= j1) & (i0 <= i1)
    )[0]

    for t in active:
        inv_den = 1.0 / den[t]
        jj0 = int(j0[t]); jj1 = int(j1[t])
        ii0 = int(i0[t]); ii1 = int(i1[t])

        bx = x_mm[jj0:jj1 + 1]            # (bw,) pixel-center X
        by_full = y_mm[ii0:ii1 + 1]      # (bh,) pixel-center Y
        bw = bx.shape[0]
        bh = by_full.shape[0]

        x3t = x3[t]; y3t = y3[t]
        z1t = z1[t]; z2t = z2[t]; z3t = z3[t]

        # Separable column terms (row-independent) — reused across bands. These
        # equal the fused form's (y2-y3)*(gx-x3) / (y3-y1)*(gx-x3) row-for-row.
        dxx = bx - x3t
        tx1 = (y2[t] - y3t) * dxx
        tx2 = (y3t - y1[t]) * dxx

        rows_per_band = max(1, _RASTER_BAND_PX // bw)
        for rs in range(0, bh, rows_per_band):
            by = by_full[rs:rs + rows_per_band]
            dyy = by - y3t
            ty1 = (x3t - x2[t]) * dyy
            ty2 = (x1[t] - x3t) * dyy

            # Barycentric coords (separable broadcast-add == fused 2D add of the
            # same two operands, bit-for-bit; see the docstring note).
            l1 = (tx1[None, :] + ty1[:, None]) * inv_den
            l2 = (tx2[None, :] + ty2[:, None]) * inv_den
            l3 = 1.0 - l1 - l2

            inside = (l1 >= -_BARY_EPS) & (l2 >= -_BARY_EPS) & (l3 >= -_BARY_EPS)
            if not inside.any():
                continue

            z_interp = l1 * z1t + l2 * z2t + l3 * z3t
            block = out[ii0 + rs:ii0 + rs + by.shape[0], jj0:jj1 + 1]
            np.maximum(block, np.where(inside, z_interp, -np.inf), out=block)

    return out


def _lift_to_zero(acc: np.ndarray, shape: Tuple[int, int]) -> np.ndarray:
    """Lift a rasterizer envelope so its lowest camera-visible point is z = 0.

    Shared by both loaders (Stage 6 B.3b-perf.1b). `acc` is the
    `_rasterize_triangles` output: finite max-z on covered pixels, `-inf` on
    never-covered (bare-stage) pixels. Returns an (H, W) mm heightmap whose
    minimum covered height is 0 and whose bare-stage pixels are 0.

    Byte-identical to the prior `out = zeros; out[finite] = acc[finite] - zmin`
    form (pinned by tests/test_rasterizer_fixture.py, the cube's ~1.78e-15
    residual included), but done IN PLACE on `acc` to drop the ~160 MB
    boolean-index copies and the separate output allocation. `acc` is the
    rasterizer's private array and is dead in both callers after this returns,
    so mutating it is safe.

    Two invariants the perf.0 gate guards exactly:
    - Finite pixels end at `acc[finite] - z_min_visible` (same per-element
      subtract; `np.min(..., where=finite)` selects the SAME minimum value as
      `acc[finite].min()` — min is pure selection, no arithmetic).
    - Non-finite (`-inf`) pixels MUST be explicitly zeroed. The masked subtract
      (`where=finite`) leaves them bit-unchanged at `-inf`; the
      `acc[~finite] = 0.0` write turns them into the 0.0 bare stage. A
      whole-array `acc -= zmin` would leave `-inf` and leak — never do that.
    """
    finite = np.isfinite(acc)
    if not finite.any():
        # Nothing covered any pixel (all-degenerate or footprint off-grid):
        # bare stage everywhere.
        return np.zeros(shape, dtype=np.float64)

    # Lift by the lowest camera-VISIBLE point: the minimum of the max-z upper
    # envelope, not the global mesh minimum. FPP only measures the visible top
    # surface, so the visible base (not the discarded bottom shell of a closed
    # solid) defines z = 0.
    z_min_visible = np.min(acc, where=finite, initial=np.inf)
    np.subtract(acc, z_min_visible, out=acc, where=finite)
    acc[~finite] = 0.0
    return acc


def load_stl_heightmap(
    path: PathLike,
    shape: Tuple[int, int],
    pixel_size_mm: float,
) -> np.ndarray:
    """Load an STL file and rasterize it to a heightmap.

    Returns a (H, W) float64 array in mm, matching the existing surface
    contract used by make_flat / make_gaussian.

    Units
    -----
    STL coordinates are assumed to be millimeters. STL files have no unit
    metadata; mm is the de-facto CAD convention (SolidWorks / Fusion /
    Onshape default). Files authored in inches will trip the bbox check
    in main_window.py's _load_stl_from_path on normally-sized parts.

    Rasterization
    -------------
    Projected-barycentric: each triangle is projected to the XY plane,
    rasterized over the pixels its bbox covers, with z interpolated
    barycentrically. Pixel value is the MAXIMUM z across all triangles
    covering that pixel (upper-envelope). This matches the
    camera-visible surface for fringe projection: a closed solid's
    bottom is discarded, only the top surface contributes.

    The mesh is centered in XY (its XY bounding-box center moves to the
    grid origin) before rasterization, mirroring how Flat / Gaussian sit
    on a centered grid; the input STL's world origin need not be at the
    part centroid.

    The returned heightmap is lifted so the part's lowest camera-visible
    point (the minimum of the max-z upper envelope) is z = 0; bare-stage
    pixels with no part above them are also 0. This matches what fringe
    projection actually measures — only the visible top surface exists in
    the data, so the visible base (not the camera-invisible bottom shell
    of a closed solid) defines z = 0. A closed solid on the stage renders
    with its visible base at z = 0: a sphere's visible equator at 0 and
    apex at the radius; a flat-topped box, whose entire visible surface is
    one height, collapses to a single z = 0 plane (zero relief). The
    120 mm height cap is a downstream concern (main_window.py's bbox
    guard); this loader does not enforce it.

    Empty mesh (zero triangles) raises ValueError. A non-empty mesh whose
    triangles all project degenerately, or whose footprint misses the
    grid entirely, is not an error: it returns an all-zero heightmap.

    Raises
    ------
    ValueError
        If the STL contains zero triangles.
    """
    m = _load_mesh(path)
    tris = np.asarray(m.vectors, dtype=np.float64)  # (N, 3, 3)

    # Center the part in XY by its XY bbox center (translation-invariant:
    # the same part offset anywhere in X/Y yields the same heightmap).
    pts = tris.reshape(-1, 3)
    x_min, y_min = pts[:, 0].min(), pts[:, 1].min()
    x_max, y_max = pts[:, 0].max(), pts[:, 1].max()
    tris[:, :, 0] -= (x_min + x_max) / 2.0
    tris[:, :, 1] -= (y_min + y_max) / 2.0

    acc = _rasterize_triangles(tris, shape, pixel_size_mm)
    # Lift the visible base to z = 0 (shared, in-place; see _lift_to_zero).
    return _lift_to_zero(acc, shape)


def load_stl_heightmap_full_scale(
    path: PathLike,
    pixel_size_mm: float,
) -> Tuple[np.ndarray, Tuple[float, float]]:
    """Rasterize an STL at native scale (no FOV-clipping).

    Peer of `load_stl_heightmap` but for the Stage 4d Browser path:
    the output shape is chosen to fit the part's XY bbox at the
    requested pitch, with `ceil` rounding so the part is never
    clipped. The (0, 0) pixel maps to the part's `(x_min, y_min)`
    in part-local coordinates (up to a half-pixel offset absorbed
    by integer pixel-index rounding at the slice-extraction site).

    Returns
    -------
    heightmap : (H, W) float64 mm
        H = ceil((y_max - y_min) / pixel_size_mm)
        W = ceil((x_max - x_min) / pixel_size_mm)
        Lifted by the lowest camera-visible point (the minimum of the
        max-z upper envelope), same convention as `load_stl_heightmap`
        — the visible base sits at z = 0, not the discarded bottom shell.
    origin_mm : (x_min_mm, y_min_mm)
        Part-local origin of the heightmap's (0, 0) pixel. Used by
        callers to convert part-local FOV positions to pixel
        indices when extracting a windowed slice.

    Raises
    ------
    ValueError
        If the STL contains zero triangles.
    """
    m = _load_mesh(path)
    tris = np.asarray(m.vectors, dtype=np.float64).copy()  # (N, 3, 3)

    pts = tris.reshape(-1, 3)
    x_min = float(pts[:, 0].min())
    y_min = float(pts[:, 1].min())
    x_max = float(pts[:, 0].max())
    y_max = float(pts[:, 1].max())

    W = int(np.ceil((x_max - x_min) / pixel_size_mm))
    H = int(np.ceil((y_max - y_min) / pixel_size_mm))
    # Zero-extent edge case (degenerate flat STL with no XY footprint):
    # return a 1x1 zero heightmap rather than a (0, 0) shape that
    # downstream NumPy would choke on.
    if W <= 0 or H <= 0:
        return np.zeros((max(H, 1), max(W, 1)), dtype=np.float64), (x_min, y_min)

    # Center the triangles to use the existing centered `_rasterize_triangles`.
    # The half-pixel offset between "(0,0) of the centered grid" and
    # "part-local (x_min, y_min)" is at most pixel_size_mm/2 and is
    # absorbed by integer pixel-index rounding at the slice-extraction
    # site (MainWindow._extract_fov_slice).
    tris[:, :, 0] -= (x_min + x_max) / 2.0
    tris[:, :, 1] -= (y_min + y_max) / 2.0

    acc = _rasterize_triangles(tris, (H, W), pixel_size_mm)
    # Lift the visible base to z = 0 (shared, in-place; see _lift_to_zero).
    return _lift_to_zero(acc, (H, W)), (x_min, y_min)


def get_stl_bbox_mm(path: PathLike) -> Tuple[float, float, float]:
    """Return the (X, Y, Z) bounding-box extents of an STL in mm.

    Used by the import-time bbox check in main_window.py. Cheap — does
    not rasterize, just reads the mesh and computes max - min per axis.

    Raises
    ------
    ValueError
        If the STL contains zero triangles.
    """
    m = _load_mesh(path)
    pts = np.asarray(m.vectors, dtype=np.float64).reshape(-1, 3)
    ext = pts.max(axis=0) - pts.min(axis=0)
    return (float(ext[0]), float(ext[1]), float(ext[2]))
