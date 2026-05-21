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
    """
    H, W = shape
    x_mm, y_mm = _grid_axes_mm(shape, pixel_size_mm)
    out = np.full((H, W), -np.inf, dtype=np.float64)

    inv_ps = 1.0 / pixel_size_mm
    col_off = (W - 1) / 2.0
    row_off = (H - 1) / 2.0

    for tri in triangles:
        x1, y1, z1 = tri[0]
        x2, y2, z2 = tri[1]
        x3, y3, z3 = tri[2]

        den = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
        if abs(den) < _DEGENERATE_DEN:
            continue  # vertical-wall / collinear projection: no contribution

        # Pixel-index bbox of the triangle, clamped to the image.
        cols_f = (np.array([x1, x2, x3]) * inv_ps) + col_off
        rows_f = (np.array([y1, y2, y3]) * inv_ps) + row_off
        j0 = max(0, int(np.floor(cols_f.min())))
        j1 = min(W - 1, int(np.ceil(cols_f.max())))
        i0 = max(0, int(np.floor(rows_f.min())))
        i1 = min(H - 1, int(np.ceil(rows_f.max())))
        if j0 > j1 or i0 > i1:
            continue  # triangle's footprint is entirely off-grid

        # Pixel-center world coords for the block (vectorized fill).
        bx = x_mm[j0 : j1 + 1]              # (bw,)
        by = y_mm[i0 : i1 + 1]              # (bh,)
        gx, gy = np.meshgrid(bx, by)       # (bh, bw)

        inv_den = 1.0 / den
        l1 = ((y2 - y3) * (gx - x3) + (x3 - x2) * (gy - y3)) * inv_den
        l2 = ((y3 - y1) * (gx - x3) + (x1 - x3) * (gy - y3)) * inv_den
        l3 = 1.0 - l1 - l2

        inside = (l1 >= -_BARY_EPS) & (l2 >= -_BARY_EPS) & (l3 >= -_BARY_EPS)
        if not inside.any():
            continue

        z_interp = l1 * z1 + l2 * z2 + l3 * z3
        block = out[i0 : i1 + 1, j0 : j1 + 1]
        np.maximum(block, np.where(inside, z_interp, -np.inf), out=block)

    return out


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

    The returned heightmap is lifted so the part's lowest point (its
    base — the plane it rests on in the FPP setup) is z = 0; bare-stage
    pixels with no part above them are also 0. The base is the true
    minimum-Z vertex over *all* triangles, including the camera-invisible
    bottom shell of a closed solid (which the max-z envelope discards but
    which still defines where the part contacts the stage). The 120 mm
    height cap is a downstream concern (main_window.py's bbox guard);
    this loader does not enforce it.

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

    finite = np.isfinite(acc)
    if not finite.any():
        # Non-empty mesh, but nothing covered any pixel (all-degenerate
        # or footprint entirely off-grid). Bare stage everywhere.
        return np.zeros(shape, dtype=np.float64)

    # Lift by the part's true base: the global minimum-Z vertex over all
    # triangles, including the camera-invisible bottom shell discarded by
    # the max-z envelope. That bottom is where the part rests on the
    # stage, so it (not the visible envelope's low point) is z = 0.
    z_min_mesh = tris[:, :, 2].min()
    out = np.zeros(shape, dtype=np.float64)
    out[finite] = acc[finite] - z_min_mesh
    return out


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
        Lifted by the global mesh-Z minimum (same convention as
        `load_stl_heightmap` — the part's true base, including
        the bottom shell discarded by the max-z envelope).
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

    finite = np.isfinite(acc)
    if not finite.any():
        return np.zeros((H, W), dtype=np.float64), (x_min, y_min)

    z_min_mesh = float(tris[:, :, 2].min())
    out = np.zeros((H, W), dtype=np.float64)
    out[finite] = acc[finite] - z_min_mesh
    return out, (x_min, y_min)


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
