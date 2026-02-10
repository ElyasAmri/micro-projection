"""Physical calibration routines for fringe projection systems.

Provides step-height calibration (the gold standard for determining
equivalent wavelength), fringe period estimation via FFT, and
pixel pitch calibration from known distances.
"""

import numpy as np
from typing import Optional

from ..core.datatypes import CalibrationParams, PhaseMap
from ..core.exceptions import CalibrationError
from ..processing.phase_shift import extract_phase
from ..processing.unwrap import unwrap_phase


def calibrate_from_step_height(
    frames: list[np.ndarray],
    known_height: float,
    roi_high: tuple[int, int, int, int],
    roi_low: tuple[int, int, int, int],
    pixel_pitch: float = 1.0,
    unit: str = "mm",
) -> CalibrationParams:
    """Calibrate equivalent wavelength using a step-height standard.

    Projects phase-shifted patterns onto a step standard with known height
    difference. Measures the phase difference between high and low regions
    to determine the equivalent wavelength.

    Args:
        frames: List of captured phase-shifted frames
        known_height: Known height difference of the step standard
        roi_high: Region on the high step as (row_start, row_end, col_start, col_end)
        roi_low: Region on the low step as (row_start, row_end, col_start, col_end)
        pixel_pitch: Physical size per pixel
        unit: Physical unit for measurements

    Returns:
        CalibrationParams with computed equivalent_wavelength

    Raises:
        CalibrationError: If calibration computation fails
    """
    # Extract phase from the captured frames
    phase_map = extract_phase(frames)

    # Spatially unwrap the phase
    unwrapped = unwrap_phase(phase_map.wrapped, phase_map.quality)

    # Extract mean phase in each ROI
    r1s, r1e, c1s, c1e = roi_high
    r2s, r2e, c2s, c2e = roi_low

    phase_high = np.mean(unwrapped[r1s:r1e, c1s:c1e])
    phase_low = np.mean(unwrapped[r2s:r2e, c2s:c2e])

    delta_phase = abs(phase_high - phase_low)

    if delta_phase < 0.01:
        raise CalibrationError(
            "Phase difference between ROIs is too small for calibration. "
            "Check ROI placement or step height."
        )

    # lambda_eq = known_height * 2*pi / delta_phase
    equivalent_wavelength = known_height * 2.0 * np.pi / delta_phase

    return CalibrationParams(
        equivalent_wavelength=equivalent_wavelength,
        pixel_pitch=pixel_pitch,
        unit=unit,
    )


def estimate_fringe_period(
    frame: np.ndarray,
    axis: int = 1,
) -> float:
    """Estimate the fringe period in a captured frame using FFT.

    Analyzes the spatial frequency content along the specified axis
    to find the dominant fringe period in camera pixels.

    Args:
        frame: 2D grayscale image containing fringes
        axis: Axis along which fringes vary (1 = vertical fringes, 0 = horizontal)

    Returns:
        Estimated fringe period in pixels

    Raises:
        CalibrationError: If no clear fringe frequency is detected
    """
    # Average along the perpendicular axis for a clean 1D profile
    if axis == 1:
        profile = np.mean(frame, axis=0)
    else:
        profile = np.mean(frame, axis=1)

    # Remove DC component
    profile = profile - np.mean(profile)

    # Compute FFT
    spectrum = np.abs(np.fft.rfft(profile))
    freqs = np.fft.rfftfreq(len(profile))

    # Ignore DC (index 0) and very low frequencies
    min_idx = max(1, len(spectrum) // 100)

    # Find peak frequency
    peak_idx = min_idx + np.argmax(spectrum[min_idx:])
    peak_freq = freqs[peak_idx]

    if peak_freq < 1e-10:
        raise CalibrationError("No clear fringe frequency detected")

    period = 1.0 / peak_freq
    return period


def calibrate_pixel_pitch(
    known_distance_mm: float,
    point1_px: tuple[float, float],
    point2_px: tuple[float, float],
) -> float:
    """Calibrate pixel pitch from a known physical distance.

    Given two points with known physical distance between them,
    computes the pixel pitch (mm/pixel).

    Args:
        known_distance_mm: Known physical distance between the two points
        point1_px: First point as (row, col) in pixels
        point2_px: Second point as (row, col) in pixels

    Returns:
        Pixel pitch in mm/pixel
    """
    dy = point2_px[0] - point1_px[0]
    dx = point2_px[1] - point1_px[1]
    pixel_distance = np.sqrt(dx**2 + dy**2)

    if pixel_distance < 1.0:
        raise CalibrationError("Points are too close together for calibration")

    return known_distance_mm / pixel_distance
