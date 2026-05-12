"""unwrapping.py — Phase unwrapping wrappers.

Two functions:

- `unwrap_2d` — the operational unwrap. Reproduces notebook cells 7 and 17
  exactly: np.unwrap along axis=1 (rows / horizontal), then along axis=0
  (columns / vertical). This is what every Stage 2 regression test
  inherits from.

- `unwrap_2d_skimage` — a robust alternative based on
  scikit-image's Goldstein-branch-cut algorithm. Not yet validated against
  the operational regression fixture; kept available for Stage 5+ work
  where measurement noise may defeat the simple row-then-column unwrap.

Pure array ops — no Geometry dependency.
"""
from __future__ import annotations

import numpy as np


def unwrap_2d(wrapped: np.ndarray) -> np.ndarray:
    """Two-axis phase unwrapping via row-then-column np.unwrap.

    Operational unwrap for this project. Reproduces the notebook idiom:

        np.unwrap(np.unwrap(wrapped, axis=1), axis=0)

    Row-then-column ordering matters because the projected fringes run
    vertically in our convention, so the largest phase discontinuities
    are along x (axis=1). Unwrapping rows first removes those jumps,
    leaving only small row-to-row residuals for the axis=0 pass to
    reconcile.

    Parameters
    ----------
    wrapped : ndarray, shape (H, W)
        Wrapped phase in radians, principal value in (-pi, pi].

    Returns
    -------
    ndarray, shape (H, W), dtype float64
        Unwrapped phase. Element [0, 0] is preserved; subsequent elements
        accumulate multiples of 2*pi as needed.
    """
    return np.unwrap(np.unwrap(wrapped, axis=1), axis=0)


def unwrap_2d_skimage(wrapped: np.ndarray) -> np.ndarray:
    """Robust 2D phase unwrap via scikit-image (Goldstein branch-cut).

    Robust alternative to `unwrap_2d`, not yet validated against the
    operational regression fixture. Provided for Stage 5+ comparison work
    where real measurement noise may cause the simple row-then-column
    unwrap to fail (residue-induced 2*pi miscounts).

    Lazy-imports `skimage.restoration.unwrap_phase` so the operational
    `unwrap_2d` does not depend on scikit-image being importable at
    module load time.

    Parameters
    ----------
    wrapped : ndarray, shape (H, W)
        Wrapped phase in radians, principal value in (-pi, pi].

    Returns
    -------
    ndarray, shape (H, W), dtype float64
        Unwrapped phase.
    """
    from skimage.restoration import unwrap_phase

    return np.asarray(unwrap_phase(wrapped), dtype=np.float64)
