"""Phase-to-height conversion for fringe projection profilometry."""

import numpy as np
from typing import Optional

from ..core.datatypes import PhaseMap, HeightMap, CalibrationParams
from ..core.exceptions import CalibrationError


def phase_to_height(
    phase_map: PhaseMap,
    calibration: CalibrationParams,
    use_unwrapped: bool = True,
) -> HeightMap:
    """Convert phase map to height map using calibration parameters.

    The fundamental relationship is:
        h = (lambda_eq / 2*pi) * psi

    where:
        h = height
        lambda_eq = equivalent wavelength
        psi = unwrapped phase

    Args:
        phase_map: PhaseMap containing wrapped and/or unwrapped phase
        calibration: Calibration parameters including equivalent wavelength
        use_unwrapped: If True, use unwrapped phase; otherwise use wrapped

    Returns:
        HeightMap with computed height values

    Raises:
        CalibrationError: If required calibration parameters are missing
    """
    if calibration.equivalent_wavelength <= 0:
        raise CalibrationError("Equivalent wavelength must be positive")

    # Select which phase to use
    if use_unwrapped:
        if phase_map.unwrapped is None:
            raise CalibrationError(
                "Unwrapped phase required but not available. "
                "Set use_unwrapped=False or unwrap the phase first."
            )
        phase = phase_map.unwrapped
    else:
        phase = phase_map.wrapped

    # Apply the height conversion formula: h = (lambda_eq / 2*pi) * psi
    height_data = (calibration.equivalent_wavelength / (2.0 * np.pi)) * phase

    # Build metadata
    metadata = {
        "equivalent_wavelength": calibration.equivalent_wavelength,
        "pixel_pitch": calibration.pixel_pitch,
        "unit": calibration.unit,
        "use_unwrapped": use_unwrapped,
    }

    if calibration.reference_distance is not None:
        metadata["reference_distance"] = calibration.reference_distance
    if calibration.fringe_pitch is not None:
        metadata["fringe_pitch"] = calibration.fringe_pitch

    return HeightMap(
        data=height_data,
        unit=calibration.unit,
        pixel_pitch=calibration.pixel_pitch,
        equivalent_wavelength=calibration.equivalent_wavelength,
        metadata=metadata,
    )


def compute_equivalent_wavelength(
    wavelength1: float,
    wavelength2: float,
) -> float:
    """Compute the equivalent (synthetic) wavelength for dual-frequency measurement.

    For two fringe patterns with periods P1 and P2:
        lambda_eq = (P1 * P2) / |P1 - P2|

    The equivalent wavelength is much larger than either individual wavelength,
    allowing unambiguous measurement of larger heights.

    Args:
        wavelength1: First fringe period/wavelength
        wavelength2: Second fringe period/wavelength

    Returns:
        Equivalent (synthetic) wavelength

    Raises:
        ValueError: If wavelengths are equal (would give infinite lambda_eq)
    """
    if np.isclose(wavelength1, wavelength2):
        raise ValueError("Wavelengths must be different for dual-frequency")

    return (wavelength1 * wavelength2) / abs(wavelength1 - wavelength2)


def apply_perspective_correction(
    height_map: HeightMap,
    reference_distance: float,
    projection_angle: float = 0.0,
) -> HeightMap:
    """Apply perspective correction for non-telecentric setups.

    When the projector and camera are not telecentric, the relationship
    between phase and height is not linear and depends on pixel position.

    This is a simplified correction assuming small angles.
    For more accurate correction, full geometric calibration is needed.

    Args:
        height_map: Input height map
        reference_distance: Distance from system to reference plane
        projection_angle: Angle between projector and camera optical axes (degrees)

    Returns:
        Corrected HeightMap
    """
    h, w = height_map.shape

    # Create pixel coordinate grids (centered)
    y, x = np.mgrid[0:h, 0:w]
    cx, cy = w / 2, h / 2
    x = x - cx
    y = y - cy

    # Convert to physical coordinates
    x_phys = x * height_map.pixel_pitch
    y_phys = y * height_map.pixel_pitch

    # Perspective correction factor (simplified model)
    # For telecentric systems, this factor is 1.0 everywhere
    theta = np.radians(projection_angle)

    # Correction becomes more significant for smaller reference_distance
    # Check for potential singularities in the denominator
    denominator = 1.0 - height_map.data * np.tan(theta) / reference_distance

    # Warn if values are too close to zero (potential instability)
    import warnings
    if np.any(np.abs(denominator) < 1e-10):
        warnings.warn("Perspective correction may be unstable near singularity. "
                     "Consider adjusting reference_distance or projection_angle.")

    # Apply correction with safeguard against division by zero
    correction_factor = np.where(np.abs(denominator) > 1e-10, 1.0 / denominator, np.nan)

    # Apply correction
    corrected_data = height_map.data * correction_factor

    # Update metadata
    new_metadata = height_map.metadata.copy()
    new_metadata["perspective_corrected"] = True
    new_metadata["reference_distance"] = reference_distance
    new_metadata["projection_angle"] = projection_angle

    return HeightMap(
        data=corrected_data,
        unit=height_map.unit,
        pixel_pitch=height_map.pixel_pitch,
        equivalent_wavelength=height_map.equivalent_wavelength,
        metadata=new_metadata,
    )


def remove_plane(height_map: HeightMap) -> HeightMap:
    """Remove best-fit plane from height map (tilt correction).

    Fits a plane z = ax + by + c to the height data and subtracts it.
    Useful for removing sample tilt.

    Args:
        height_map: Input height map

    Returns:
        HeightMap with plane removed
    """
    h, w = height_map.shape
    y, x = np.mgrid[0:h, 0:w]

    # Flatten for least squares
    x_flat = x.flatten()
    y_flat = y.flatten()
    z_flat = height_map.data.flatten()

    # Build design matrix for plane fit: z = ax + by + c
    A = np.column_stack([x_flat, y_flat, np.ones_like(x_flat)])

    # Solve least squares
    coeffs, _, _, _ = np.linalg.lstsq(A, z_flat, rcond=None)
    a, b, c = coeffs

    # Compute and subtract plane
    plane = a * x + b * y + c
    corrected_data = height_map.data - plane

    # Update metadata
    new_metadata = height_map.metadata.copy()
    new_metadata["plane_removed"] = True
    new_metadata["plane_coefficients"] = {"a": a, "b": b, "c": c}

    return HeightMap(
        data=corrected_data,
        unit=height_map.unit,
        pixel_pitch=height_map.pixel_pitch,
        equivalent_wavelength=height_map.equivalent_wavelength,
        metadata=new_metadata,
    )
