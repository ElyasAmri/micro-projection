import math

from PySide6.QtGui import QImage


def generate_fringe_image(
    width: int,
    height: int,
    *,
    period_px: float,
    phase_deg: float,
    orientation: str,
    contrast: float,
    bias: float,
) -> QImage:
    if width <= 0 or height <= 0:
        raise ValueError("Fringe size must be positive.")
    if period_px <= 0:
        raise ValueError("Fringe period must be > 0.")
    if not (0.0 <= contrast <= 1.0):
        raise ValueError("Fringe contrast must be in [0, 1].")
    if not (0.0 <= bias <= 1.0):
        raise ValueError("Fringe bias must be in [0, 1].")

    image = QImage(width, height, QImage.Format_Grayscale8)
    phase = math.radians(phase_deg)
    two_pi_over_period = (2.0 * math.pi) / period_px

    for y in range(height):
        for x in range(width):
            axis = x if orientation == "vertical" else y
            wave = math.sin(two_pi_over_period * axis + phase)
            value = bias + 0.5 * contrast * wave
            level = int(max(0, min(255, round(value * 255))))
            image.setPixel(x, y, level)
    return image
