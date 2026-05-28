"""Hardware paper specs. Lengths in cm/mm (per constant); pixel pitch in um."""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
SURFACE_CAMERA_MODEL = "Teledyne FLIR Blackfly S BFS-U3-13Y3M-C"
SURFACE_CAMERA_SENSOR_MODEL = "Sony IMX304"
SURFACE_CAMERA_SENSOR_WIDTH_PX = 4112
SURFACE_CAMERA_SENSOR_HEIGHT_PX = 3008
SURFACE_CAMERA_PIXEL_PITCH_UM = 3.45
SURFACE_CAMERA_SENSOR_WIDTH_MM = 14.1864   # 4112 * 3.45 um
SURFACE_CAMERA_SENSOR_HEIGHT_MM = 10.3776  # 3008 * 3.45 um

# Default capture grid is a 4x downsample of the native sensor (interactive perf).
SURFACE_CAMERA_CAPTURE_WIDTH_PX = SURFACE_CAMERA_SENSOR_WIDTH_PX // 4
SURFACE_CAMERA_CAPTURE_HEIGHT_PX = SURFACE_CAMERA_SENSOR_HEIGHT_PX // 4

# ---------------------------------------------------------------------------
# Optics (telecentric front + standard rear lens on the camera)
# ---------------------------------------------------------------------------
TELECENTRIC_LENS_DIAMETER_CM = 10.0
TELECENTRIC_LENS_TO_CAMERA_LENS_CM = 4.0
SURFACE_CAMERA_REAR_LENS_DIAMETER_CM = 1.6
OPTICAL_AXIS_HEIGHT_CM = 8.1
SURFACE_CAMERA_LENS_HEIGHT_CM = OPTICAL_AXIS_HEIGHT_CM

# ---------------------------------------------------------------------------
# Projector
# ---------------------------------------------------------------------------
PROJECTOR_THROW_RATIO = 1.2
PROJECTOR_IMAGE_ASPECT = 16.0 / 9.0
PROJECTOR_ANGLE_LIMIT_DEG = 45.0
DEFAULT_PROJECTION_ANGLE_DEG = -20.0
PROJECTOR_LENS_HEIGHT_CM = OPTICAL_AXIS_HEIGHT_CM
PROJECTOR_LENS_WINDOW_WIDTH_CM = 1.4
PROJECTOR_LENS_WINDOW_HEIGHT_CM = 1.0

# ---------------------------------------------------------------------------
# Rig geometry
# ---------------------------------------------------------------------------
DEFAULT_DEVICE_SPACING_CM = 12.0   # projector-camera baseline along the rig

# Field-of-view ceiling implied by the telecentric optic: the imaged field must
# fit inside the lens aperture (a telecentric lens cannot image a field wider
# than its front element).
MAX_TELECENTRIC_FIELD_WIDTH_CM = TELECENTRIC_LENS_DIAMETER_CM


def summary() -> dict[str, object]:
    """Compact dict for inclusion in exported reports / Calibration tab."""
    return {
        "camera_model": SURFACE_CAMERA_MODEL,
        "sensor_model": SURFACE_CAMERA_SENSOR_MODEL,
        "sensor_px": (SURFACE_CAMERA_SENSOR_WIDTH_PX, SURFACE_CAMERA_SENSOR_HEIGHT_PX),
        "sensor_mm": (SURFACE_CAMERA_SENSOR_WIDTH_MM, SURFACE_CAMERA_SENSOR_HEIGHT_MM),
        "pixel_pitch_um": SURFACE_CAMERA_PIXEL_PITCH_UM,
        "telecentric_lens_diameter_cm": TELECENTRIC_LENS_DIAMETER_CM,
        "max_telecentric_field_cm": MAX_TELECENTRIC_FIELD_WIDTH_CM,
        "device_spacing_cm": DEFAULT_DEVICE_SPACING_CM,
        "optical_axis_height_cm": OPTICAL_AXIS_HEIGHT_CM,
        "projector_throw_ratio": PROJECTOR_THROW_RATIO,
        "projector_image_aspect": PROJECTOR_IMAGE_ASPECT,
    }
