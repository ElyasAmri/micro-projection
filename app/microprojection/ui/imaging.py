"""Convert numpy arrays into QImages for painting into the canvas."""
from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage


def gray_to_qimage(array: np.ndarray) -> QImage:
    """An (H, W) uint8 array to a grayscale QImage that owns its own pixels."""
    arr = np.ascontiguousarray(array, dtype=np.uint8)
    height, width = arr.shape
    buffer = arr.tobytes()
    image = QImage(buffer, width, height, width, QImage.Format_Grayscale8)
    return image.copy()  # detach from `buffer`, which is about to go out of scope
