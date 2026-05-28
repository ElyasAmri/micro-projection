"""Capture / ground-truth loaders, percentile-normalised PNG writer, turbo colormap."""
from __future__ import annotations

from pathlib import Path

import cv2
import imageio.v2 as imageio
import numpy as np

from reconstruction import normalize_to_uint8


def period_label(period_px: float) -> str:
    """Subdirectory label for a fringe period, e.g. 48.0 -> 'period_48p0'."""
    return str(period_px).replace(".", "p")


def load_sequence(directory: Path, prefix: str) -> np.ndarray:
    """Load a phase-shifted capture sequence as (N, H, W) float64 in [0, 1]."""
    frames: list[np.ndarray] = []
    for path in sorted(directory.glob(f"{prefix}_phase_*.png")):
        image = imageio.imread(path)
        if image.ndim == 3:
            image = image[..., :3].mean(axis=2)
        data = np.asarray(image)
        if np.issubdtype(data.dtype, np.integer):
            scale = float(np.iinfo(data.dtype).max)
            frames.append(data.astype(np.float64) / scale)
        else:
            frames.append(data.astype(np.float64))
    if len(frames) < 3:
        raise ValueError(f"Expected at least three {prefix} frames in {directory}.")
    return np.stack(frames, axis=0)


def load_ground_truth(output_dir: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (truth, valid_mask, object_mask) from <dir>/ground_truth.npz."""
    truth_data = np.load(output_dir / "ground_truth.npz")
    return (
        np.asarray(truth_data["truth"], dtype=np.float64),
        np.asarray(truth_data["valid_mask"], dtype=bool),
        np.asarray(truth_data["object_mask"], dtype=bool),
    )


def write_uint8(path: Path, values: np.ndarray, mask: np.ndarray | None = None) -> None:
    """Save a height/error map as a percentile-normalised 8-bit PNG."""
    path.parent.mkdir(parents=True, exist_ok=True)
    imageio.imwrite(path, normalize_to_uint8(values, mask))


def colorize_scalar_map(
    values: np.ndarray,
    mask: np.ndarray,
    *,
    lo: float,
    hi: float,
    invalid_rgb: tuple[int, int, int] = (10, 12, 16),
    colormap: int = cv2.COLORMAP_TURBO,
) -> np.ndarray:
    """Colormap a masked scalar map to HxWx3 uint8 RGB."""
    valid = mask & np.isfinite(values)
    rgb = np.zeros((*values.shape, 3), dtype=np.uint8)
    rgb[...] = np.asarray(invalid_rgb, dtype=np.uint8)
    if not np.any(valid):
        return rgb
    if hi <= lo:
        scaled = np.full(values.shape, 127, dtype=np.uint8)
    else:
        normalized = np.clip((values - lo) / (hi - lo), 0.0, 1.0)
        scaled = np.round(normalized * 255.0).astype(np.uint8)
    colored = cv2.applyColorMap(scaled, colormap)
    colored = cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)
    rgb[valid] = colored[valid]
    return rgb
