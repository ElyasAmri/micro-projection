"""Write captured frames to disk.

Frames are whatever the camera produced: mono uint8/uint16 (PySpin) or RGB
uint8 (OpenCV). PNG preserves both 8- and 16-bit grayscale losslessly, which
matters for phase precision, so frames are saved as PNG via OpenCV.
"""
from __future__ import annotations

import cv2
import numpy as np


def save_png(path: str, image: np.ndarray) -> None:
    """Write an array to ``path`` as PNG, as-is. Raises on write failure."""
    if not cv2.imwrite(path, image):
        raise RuntimeError(f"Could not write {path}")


def save_frame(path: str, image: np.ndarray) -> None:
    """Save a camera frame to ``path`` as PNG.

    Mono frames (2-D) are written as-is; RGB frames (3-D) are converted to BGR
    for OpenCV.
    """
    if image.ndim == 3 and image.shape[2] == 3:
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    save_png(path, image)
