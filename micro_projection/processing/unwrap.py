"""Phase unwrapping algorithms for continuous phase recovery."""

import numpy as np
from typing import Literal

from ..core.exceptions import UnwrapError


def unwrap_phase(
    wrapped: np.ndarray,
    quality: np.ndarray | None = None,
    method: Literal["path", "quality_guided", "flood"] = "quality_guided",
) -> np.ndarray:
    """Unwrap 2D wrapped phase to continuous phase.

    Args:
        wrapped: 2D array of wrapped phase values in (-pi, pi]
        quality: Optional quality map for guided unwrapping
        method: Unwrapping method to use:
            - "path": Simple path-following (fast, less robust)
            - "quality_guided": Quality-guided (recommended)
            - "flood": Flood-fill from best quality point

    Returns:
        2D array of unwrapped continuous phase

    Raises:
        UnwrapError: If unwrapping fails
    """
    if method == "path":
        return _unwrap_path_following(wrapped)
    elif method == "quality_guided":
        if quality is None:
            quality = np.ones_like(wrapped)
        return _unwrap_quality_guided(wrapped, quality)
    elif method == "flood":
        if quality is None:
            quality = np.ones_like(wrapped)
        return _unwrap_flood_fill(wrapped, quality)
    else:
        raise ValueError(f"Unknown unwrapping method: {method}")


def _unwrap_path_following(wrapped: np.ndarray) -> np.ndarray:
    """Simple row-by-row, column-by-column path following unwrap.

    Fast but can propagate errors. Best for high-quality data.
    """
    unwrapped = wrapped.copy()

    # Unwrap along rows first
    for i in range(unwrapped.shape[0]):
        unwrapped[i, :] = np.unwrap(unwrapped[i, :])

    # Then unwrap along columns
    for j in range(unwrapped.shape[1]):
        unwrapped[:, j] = np.unwrap(unwrapped[:, j])

    return unwrapped


def _unwrap_quality_guided(
    wrapped: np.ndarray,
    quality: np.ndarray,
) -> np.ndarray:
    """Quality-guided phase unwrapping.

    Processes pixels in order of decreasing quality, propagating
    from high-quality regions to low-quality regions.
    """
    height, width = wrapped.shape
    unwrapped = np.zeros_like(wrapped)
    processed = np.zeros((height, width), dtype=bool)

    # Edge quality: minimum quality of neighboring pixels
    edge_quality = _compute_edge_quality(quality)

    # Create list of edges sorted by quality (descending)
    edges = []
    for i in range(height):
        for j in range(width):
            # Horizontal edge (i,j) -> (i,j+1)
            if j < width - 1:
                eq = edge_quality[i, j, 0]
                edges.append((eq, i, j, i, j + 1))
            # Vertical edge (i,j) -> (i+1,j)
            if i < height - 1:
                eq = edge_quality[i, j, 1]
                edges.append((eq, i, j, i + 1, j))

    # Sort edges by quality (highest first)
    edges.sort(reverse=True, key=lambda x: x[0])

    # Start from the highest quality pixel
    flat_quality = quality.flatten()
    start_idx = np.argmax(flat_quality)
    start_i, start_j = divmod(start_idx, width)

    unwrapped[start_i, start_j] = wrapped[start_i, start_j]
    processed[start_i, start_j] = True

    # Process edges in quality order
    for _, i1, j1, i2, j2 in edges:
        p1_done = processed[i1, j1]
        p2_done = processed[i2, j2]

        if p1_done and not p2_done:
            # Unwrap p2 relative to p1
            diff = wrapped[i2, j2] - wrapped[i1, j1]
            diff = _wrap_to_pi(diff)
            unwrapped[i2, j2] = unwrapped[i1, j1] + diff
            processed[i2, j2] = True
        elif p2_done and not p1_done:
            # Unwrap p1 relative to p2
            diff = wrapped[i1, j1] - wrapped[i2, j2]
            diff = _wrap_to_pi(diff)
            unwrapped[i1, j1] = unwrapped[i2, j2] + diff
            processed[i1, j1] = True

    # Handle any remaining unprocessed pixels with simple unwrap
    if not np.all(processed):
        # Fall back to path following for disconnected regions
        mask = ~processed
        unwrapped[mask] = _unwrap_path_following(wrapped)[mask]

    return unwrapped


def _unwrap_flood_fill(
    wrapped: np.ndarray,
    quality: np.ndarray,
) -> np.ndarray:
    """Flood-fill unwrapping starting from the best quality pixel.

    Uses breadth-first search to propagate phase values outward.
    """
    from collections import deque

    height, width = wrapped.shape
    unwrapped = np.zeros_like(wrapped)
    processed = np.zeros((height, width), dtype=bool)

    # Start from highest quality pixel
    flat_quality = quality.flatten()
    start_idx = np.argmax(flat_quality)
    start_i, start_j = divmod(start_idx, width)

    unwrapped[start_i, start_j] = wrapped[start_i, start_j]
    processed[start_i, start_j] = True

    # BFS queue: (row, col)
    queue = deque([(start_i, start_j)])

    # 4-connected neighbors
    neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    while queue:
        i, j = queue.popleft()

        for di, dj in neighbors:
            ni, nj = i + di, j + dj

            if 0 <= ni < height and 0 <= nj < width and not processed[ni, nj]:
                # Unwrap neighbor relative to current pixel
                diff = wrapped[ni, nj] - wrapped[i, j]
                diff = _wrap_to_pi(diff)
                unwrapped[ni, nj] = unwrapped[i, j] + diff
                processed[ni, nj] = True
                queue.append((ni, nj))

    return unwrapped


def _compute_edge_quality(quality: np.ndarray) -> np.ndarray:
    """Compute quality for edges between adjacent pixels.

    Returns array of shape (H, W, 2) where:
        [i, j, 0] = quality of horizontal edge (i,j) -> (i,j+1)
        [i, j, 1] = quality of vertical edge (i,j) -> (i+1,j)
    """
    height, width = quality.shape
    edge_quality = np.zeros((height, width, 2), dtype=quality.dtype)

    # Horizontal edges: min of adjacent pixels
    edge_quality[:, :-1, 0] = np.minimum(quality[:, :-1], quality[:, 1:])

    # Vertical edges: min of adjacent pixels
    edge_quality[:-1, :, 1] = np.minimum(quality[:-1, :], quality[1:, :])

    return edge_quality


def _wrap_to_pi(phase: float | np.ndarray) -> float | np.ndarray:
    """Wrap phase values to (-pi, pi] range.

    This function wraps phase values to the principal value range of (-pi, pi].
    This is the standard range for wrapped phase in interferometry and fringe projection.

    The mathematical operation is:
        wrapped = ((phase + pi) mod 2*pi) - pi

    This ensures that phase differences are normalized to the smallest equivalent angle,
    which is essential for phase unwrapping algorithms to correctly detect 2*pi jumps.

    Args:
        phase: Phase value(s) in radians (scalar or array)

    Returns:
        Phase value(s) wrapped to (-pi, pi] range

    Example:
        >>> _wrap_to_pi(3.5 * np.pi)  # Returns ~-0.5*pi
        >>> _wrap_to_pi(np.array([0, np.pi, 2*np.pi]))  # [0, pi, 0]
    """
    return np.mod(phase + np.pi, 2 * np.pi) - np.pi
