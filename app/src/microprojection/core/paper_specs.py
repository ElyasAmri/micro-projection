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
# Projector hardware: Wintech PRO4500 (TI DLP LightCrafter 4500 / DLPC350)
# Numbers from the PRO4500 brochure (.local/PRO4500_Brochure.pdf), 3D-measurement
# configuration (700 mm working-distance lens).
# ---------------------------------------------------------------------------
PROJECTOR_MODEL = "Wintech PRO4500"
PROJECTOR_OPTICAL_ENGINE = "TI DLP LightCrafter 4500"
PROJECTOR_CONTROLLER = "TI DLPC350"
PROJECTOR_USB_VID = 0x0451          # DLPC350 USB descriptor
PROJECTOR_USB_PID = 0x6401

# 0.45" WXGA diamond-pixel DMD.
PROJECTOR_DMD_WIDTH_PX = 912
PROJECTOR_DMD_HEIGHT_PX = 1140
PROJECTOR_DMD_DIAGONAL_IN = 0.45

# All-glass 0% offset optics; coatings optimized for this band.
PROJECTOR_OPTICS_BAND_NM = (381, 650)
# Dominant LED wavelength selected for 3D measurement (blue, within coating band).
PROJECTOR_LED_WAVELENGTH_NM = 460

# Measurement lens (700 mm working distance) field on the plane.
PROJECTOR_WORKING_DISTANCE_MM = 700.0
PROJECTOR_FOV_WIDTH_MM = 400.0
PROJECTOR_FOV_HEIGHT_MM = 250.0
PROJECTOR_PROJECTED_PIXEL_SIZE_UM = 305.0   # projected DMD pixel on the plane
PROJECTOR_DISTORTION_PCT = 0.5

# Streaming rates (DLPC350): HDMI grayscale vs. HDMI/flash binary.
PROJECTOR_HDMI_GRAYSCALE_FPS = 120
PROJECTOR_HDMI_BINARY_FPS = 2880
PROJECTOR_FLASH_BINARY_FPS = 4255

# Projected pixel pitch on the measurement plane, in mm.
PROJECTOR_PIXEL_SIZE_MM = PROJECTOR_PROJECTED_PIXEL_SIZE_UM / 1000.0

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
        "projector_model": f"{PROJECTOR_MODEL} ({PROJECTOR_OPTICAL_ENGINE})",
        "projector_controller": PROJECTOR_CONTROLLER,
        "projector_dmd_px": (PROJECTOR_DMD_WIDTH_PX, PROJECTOR_DMD_HEIGHT_PX),
        "projector_led_nm": PROJECTOR_LED_WAVELENGTH_NM,
        "projector_working_distance_mm": PROJECTOR_WORKING_DISTANCE_MM,
        "projector_fov_mm": (PROJECTOR_FOV_WIDTH_MM, PROJECTOR_FOV_HEIGHT_MM),
        "projector_pixel_size_mm": PROJECTOR_PIXEL_SIZE_MM,
    }
