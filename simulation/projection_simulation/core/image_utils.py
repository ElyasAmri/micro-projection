from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage


def qimage_to_rgb_array(image: QImage) -> np.ndarray:
    rgb = image.convertToFormat(QImage.Format_RGB888)
    width = rgb.width()
    height = rgb.height()
    row_stride = rgb.bytesPerLine()
    buffer = np.frombuffer(rgb.bits(), dtype=np.uint8).reshape((height, row_stride))
    return buffer[:, : width * 3].reshape((height, width, 3)).copy()


def qimage_to_luma(image: QImage) -> np.ndarray:
    pixels = qimage_to_rgb_array(image)
    return pixels.astype(np.float64).mean(axis=2) / 255.0


def even_video_frame(image: QImage) -> QImage:
    width = image.width() if image.width() % 2 == 0 else image.width() + 1
    height = image.height() if image.height() % 2 == 0 else image.height() + 1
    if width == image.width() and height == image.height():
        return image
    return image.scaled(width, height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
