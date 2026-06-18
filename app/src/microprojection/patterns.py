"""Real-time generated projection patterns for setup and focus calibration.

Each generator returns a HxW ``uint8`` grayscale array ready for the projector
window. Patterns are produced at the projector's native resolution so a pixel
maps one-to-one onto the display.

The fringe is sin-based to match the phase-extraction convention in
``processing/steps.py``.
"""
from __future__ import annotations

import numpy as np


def fringe(width: int, height: int, period: float = 32.0,
           orientation: str = "vertical", phase: float = 0.0) -> np.ndarray:
    """Sinusoidal fringe. "vertical" stripes vary along x, "horizontal" along y.

    ``phase`` (radians) shifts the sine, for phase-stepping acquisition.
    """
    period = max(2.0, float(period))
    if orientation == "horizontal":
        coord = np.arange(height, dtype=np.float64)[:, None]
    else:
        coord = np.arange(width, dtype=np.float64)[None, :]
    val = 0.5 * (1.0 + np.sin(2.0 * np.pi * coord / period + float(phase)))
    img = np.broadcast_to(val, (height, width))
    return (img * 255.0).astype(np.uint8)


def flat_field(width: int, height: int, level: int = 128) -> np.ndarray:
    """Uniform gray field at ``level`` (0..255). Used for camera noise tests so
    every pixel sits at the same mean intensity."""
    level = int(np.clip(level, 0, 255))
    return np.full((height, width), level, dtype=np.uint8)


def solid_box(width: int, height: int, box, level: int = 255) -> np.ndarray:
    """Filled bright rectangle at ``box`` = (x0, y0, x1, y1) in projector pixels,
    ``level`` inside and 0 outside. Used by the FOV pipeline to project a box the
    camera can locate. Coordinates are clamped to the projector bounds."""
    img = np.zeros((height, width), dtype=np.uint8)
    x0, y0, x1, y1 = _clamp_box(box, width, height)
    if x1 > x0 and y1 > y0:
        img[y0:y1, x0:x1] = int(np.clip(level, 0, 255))
    return img


def box_outline(width: int, height: int, box, level: int = 255,
                thickness: int = 4) -> np.ndarray:
    """Hollow rectangle outline at ``box`` = (x0, y0, x1, y1), ``thickness`` px
    wide. Used to show the matched camera FOV on the projector at the end of the
    FOV pipeline without flooding the scene with light."""
    img = np.zeros((height, width), dtype=np.uint8)
    x0, y0, x1, y1 = _clamp_box(box, width, height)
    if x1 <= x0 or y1 <= y0:
        return img
    t = max(1, int(thickness))
    val = int(np.clip(level, 0, 255))
    img[y0:y1, x0:min(x0 + t, x1)] = val
    img[y0:y1, max(x1 - t, x0):x1] = val
    img[y0:min(y0 + t, y1), x0:x1] = val
    img[max(y1 - t, y0):y1, x0:x1] = val
    return img


def _clamp_box(box, width: int, height: int):
    """Clamp (x0, y0, x1, y1) to the projector bounds and integer pixels."""
    x0, y0, x1, y1 = box
    x0 = int(np.clip(round(x0), 0, width))
    x1 = int(np.clip(round(x1), 0, width))
    y0 = int(np.clip(round(y0), 0, height))
    y1 = int(np.clip(round(y1), 0, height))
    return x0, y0, x1, y1


def siemens_star(width: int, height: int, spokes: int = 36) -> np.ndarray:
    """Siemens star: alternating wedges inside a centered disk, a classic focus
    target. The fine detail toward the center reveals when focus is sharp."""
    cx, cy = width / 2.0, height / 2.0
    y, x = np.ogrid[:height, :width]
    theta = np.arctan2(y - cy, x - cx)
    wedges = np.cos(theta * spokes) >= 0.0
    radius = np.hypot(x - cx, y - cy)
    disk = radius <= 0.95 * min(cx, cy)
    return np.where(disk & wedges, 255, 0).astype(np.uint8)


def crosshair(width: int, height: int, thickness: int | None = None) -> np.ndarray:
    """Center cross plus a reference box, for aligning the optical axis."""
    img = np.zeros((height, width), dtype=np.uint8)
    t = thickness or max(2, min(width, height) // 240)
    cx, cy = width // 2, height // 2
    img[cy - t // 2: cy + t // 2 + 1, :] = 255
    img[:, cx - t // 2: cx + t // 2 + 1] = 255
    box = min(width, height) // 8
    y0, y1 = cy - box, cy + box
    x0, x1 = cx - box, cx + box
    img[y0:y1, x0:x0 + t] = 255
    img[y0:y1, x1 - t:x1] = 255
    img[y0:y0 + t, x0:x1] = 255
    img[y1 - t:y1, x0:x1] = 255
    return img


def generate_pattern(kind: str, width: int, height: int, *,
                     period: float = 32.0,
                     orientation: str = "vertical",
                     phase: float = 0.0) -> np.ndarray:
    """Dispatch by pattern key ("fringe", "star", "crosshair")."""
    if kind == "fringe":
        return fringe(width, height, period=period, orientation=orientation,
                      phase=phase)
    if kind == "star":
        return siemens_star(width, height)
    if kind == "crosshair":
        return crosshair(width, height)
    raise ValueError(f"Unknown pattern: {kind}")
