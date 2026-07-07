"""Projectable patterns beyond the measurement fringe -- a small library for
rig work: alignment (grid, crosshair), focus (checkerboard), brightness and
linearity checks (solids, ramp), plus fringes at either orientation and any
image file (letterboxed to the projector's aspect).

Every generator returns the same shape the fringe does -- an (H, W) uint8
grayscale array at the projector's resolution -- so a custom pattern flows
through the exact `project()` path the measurement fringe uses. Qt-free, like
the rest of `backend`; the Patterns pane (ui.patterns) is just a picker over
this registry.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from backend.base import fringe_pattern

# Default pattern resolution -- matches the fringe / PRO4500 defaults.
DEFAULT_WIDTH = 1140
DEFAULT_HEIGHT = 912


@dataclass(frozen=True)
class Pattern:
    """One selectable pattern: its registry key, list label, and which of the
    pane's knobs apply to it ('n_periods' and/or 'pitch_px')."""

    key: str
    label: str
    uses: tuple[str, ...] = ()
    description: str = ""


PATTERNS: list[Pattern] = [
    Pattern("fringe_v", "Vertical fringe", ("n_periods",),
            "The measurement sinusoid (phase 0)."),
    Pattern("fringe_h", "Horizontal fringe", ("n_periods",),
            "The same sinusoid, rotated 90°: phase runs down the height."),
    Pattern("checkerboard", "Checkerboard", ("pitch_px",),
            "High-contrast squares; the classic focus target."),
    Pattern("grid", "Grid", ("pitch_px",),
            "White lines on black; projector/camera alignment."),
    Pattern("crosshair", "Crosshair", (),
            "Center lines; optical-axis alignment."),
    Pattern("solid_white", "Solid white", (),
            "Full-field illumination; brightness/exposure setup."),
    Pattern("solid_gray", "Solid 50% gray", (),
            "Half-level field; quick linearity sanity check."),
    Pattern("solid_black", "Solid black", (),
            "Dark field; black level / stray light check."),
    Pattern("ramp_h", "Horizontal ramp", (),
            "0 -> 255 across the width; gamma/linearity check."),
]

IMAGE_KEY = "image"  # file-backed pattern; `path` selects the file


def pattern_label(key: str) -> str:
    for p in PATTERNS:
        if p.key == key:
            return p.label
    return key


# -- generators ---------------------------------------------------------------

def _fringe_h(n_periods: float, width: int, height: int) -> np.ndarray:
    # The vertical fringe generated across the *height*, then broadcast wide.
    column = fringe_pattern(n_periods, width=height, height=1)[0]
    return np.broadcast_to(column[:, None], (height, width)).copy()


def _checkerboard(pitch_px: int, width: int, height: int) -> np.ndarray:
    y = np.arange(height)[:, None] // pitch_px
    x = np.arange(width)[None, :] // pitch_px
    return np.where((x + y) % 2 == 0, 255, 0).astype(np.uint8)


def _grid(pitch_px: int, width: int, height: int, line_px: int = 2) -> np.ndarray:
    image = np.zeros((height, width), dtype=np.uint8)
    image[:, ::pitch_px] = 255
    image[::pitch_px, :] = 255
    for extra in range(1, line_px):  # thicken so the camera actually sees them
        image[:, extra::pitch_px] = 255
        image[extra::pitch_px, :] = 255
    return image


def _crosshair(width: int, height: int, line_px: int = 3) -> np.ndarray:
    image = np.zeros((height, width), dtype=np.uint8)
    cy, cx = height // 2, width // 2
    half = line_px // 2
    image[max(0, cy - half):cy + half + 1, :] = 255
    image[:, max(0, cx - half):cx + half + 1] = 255
    return image


def _solid(level: int, width: int, height: int) -> np.ndarray:
    return np.full((height, width), level, dtype=np.uint8)


def _ramp_h(width: int, height: int) -> np.ndarray:
    row = np.linspace(0.0, 255.0, width)
    return np.broadcast_to(row, (height, width)).astype(np.uint8)


def load_image_pattern(path: str | Path, width: int, height: int) -> np.ndarray:
    """An image file as a pattern: grayscale, aspect-preserving resize,
    letterboxed with black to exactly (height, width)."""
    import cv2

    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"could not read image: {path}")
    scale = min(width / image.shape[1], height / image.shape[0])
    new_w = max(1, round(image.shape[1] * scale))
    new_h = max(1, round(image.shape[0] * scale))
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((height, width), dtype=np.uint8)
    y0 = (height - new_h) // 2
    x0 = (width - new_w) // 2
    canvas[y0:y0 + new_h, x0:x0 + new_w] = resized
    return canvas


def generate(
    key: str,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    n_periods: float = 8.0,
    pitch_px: int = 64,
    path: str | Path | None = None,
) -> np.ndarray:
    """The pattern named by `key` as an (H, W) uint8 array. Knobs a pattern
    doesn't use are ignored; the 'image' key requires `path`."""
    if key == IMAGE_KEY:
        if path is None:
            raise ValueError("the 'image' pattern needs a file path")
        return load_image_pattern(path, width, height)
    if key == "fringe_v":
        return fringe_pattern(n_periods, width=width, height=height)
    if key == "fringe_h":
        return _fringe_h(n_periods, width, height)
    if key == "checkerboard":
        return _checkerboard(max(1, int(pitch_px)), width, height)
    if key == "grid":
        return _grid(max(2, int(pitch_px)), width, height)
    if key == "crosshair":
        return _crosshair(width, height)
    if key == "solid_white":
        return _solid(255, width, height)
    if key == "solid_gray":
        return _solid(128, width, height)
    if key == "solid_black":
        return _solid(0, width, height)
    if key == "ramp_h":
        return _ramp_h(width, height)
    raise ValueError(f"unknown pattern: {key!r}")
