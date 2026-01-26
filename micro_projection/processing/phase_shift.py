"""N-step phase shifting algorithm for fringe pattern analysis."""

import numpy as np
from typing import Sequence

from ..core.datatypes import PhaseMap
from ..core.exceptions import ProcessingError, InvalidPatternError


def extract_phase(
    frames: Sequence[np.ndarray],
    n_steps: int | None = None,
) -> PhaseMap:
    """Extract phase from a sequence of phase-shifted fringe images.

    Uses the N-step phase shifting algorithm:
    phi = atan2(sum(In*sin(delta_n)), sum(In*cos(delta_n)))

    where delta_n = 2*pi*n/N is the phase shift for frame n.

    Args:
        frames: Sequence of N phase-shifted images (must be at least 3)
        n_steps: Number of steps (default: len(frames))

    Returns:
        PhaseMap with wrapped phase in (-pi, pi]

    Raises:
        InvalidPatternError: If frames have inconsistent shapes
        ProcessingError: If fewer than 3 frames provided

    Example:
        >>> # With 4 phase-shifted images
        >>> phase_map = extract_phase(frames, n_steps=4)
        >>> phase_map.wrapped.shape == frames[0].shape
        True
    """
    if len(frames) < 3:
        raise ProcessingError("At least 3 phase-shifted frames required")

    if n_steps is None:
        n_steps = len(frames)

    if len(frames) != n_steps:
        raise ProcessingError(f"Expected {n_steps} frames, got {len(frames)}")

    # Validate frame shapes
    shape = frames[0].shape
    for i, frame in enumerate(frames):
        if frame.shape != shape:
            raise InvalidPatternError(
                f"Frame {i} has shape {frame.shape}, expected {shape}"
            )

    # Convert to float64 for precision
    frames = [np.asarray(f, dtype=np.float64) for f in frames]

    # Compute numerator and denominator for atan2
    # phi = atan2(sum(In*sin(2*pi*n/N)), sum(In*cos(2*pi*n/N)))
    sin_sum = np.zeros(shape, dtype=np.float64)
    cos_sum = np.zeros(shape, dtype=np.float64)
    intensity_sum = np.zeros(shape, dtype=np.float64)

    for n, frame in enumerate(frames):
        delta_n = 2.0 * np.pi * n / n_steps
        sin_sum += frame * np.sin(delta_n)
        cos_sum += frame * np.cos(delta_n)
        intensity_sum += frame

    # Calculate wrapped phase
    wrapped_phase = np.arctan2(sin_sum, cos_sum)

    # Calculate modulation/quality map (reuse computed sums)
    # Quality based on fringe contrast (modulation depth)
    avg_intensity = intensity_sum / n_steps
    amplitude = 2.0 * np.sqrt(sin_sum**2 + cos_sum**2) / n_steps

    with np.errstate(divide='ignore', invalid='ignore'):
        quality = np.where(
            avg_intensity > 1e-10,
            amplitude / avg_intensity,
            0.0
        )
    quality = np.clip(quality, 0.0, 1.0)

    return PhaseMap(wrapped=wrapped_phase, quality=quality)


def compute_modulation(
    frames: Sequence[np.ndarray],
    n_steps: int,
) -> np.ndarray:
    """Compute fringe modulation (contrast) as a quality metric.

    Modulation gamma = 2 * sqrt(sin_sum^2 + cos_sum^2) / (N * I_avg)

    High modulation indicates good fringe visibility.
    Low modulation indicates noise, saturation, or poor contrast.

    Args:
        frames: Sequence of phase-shifted images
        n_steps: Number of phase steps

    Returns:
        2D array of modulation values, normalized to [0, 1]
    """
    frames = [np.asarray(f, dtype=np.float64) for f in frames]
    shape = frames[0].shape

    sin_sum = np.zeros(shape, dtype=np.float64)
    cos_sum = np.zeros(shape, dtype=np.float64)
    intensity_sum = np.zeros(shape, dtype=np.float64)

    for n, frame in enumerate(frames):
        delta_n = 2.0 * np.pi * n / n_steps
        sin_sum += frame * np.sin(delta_n)
        cos_sum += frame * np.cos(delta_n)
        intensity_sum += frame

    # Average intensity
    avg_intensity = intensity_sum / n_steps

    # Modulation amplitude
    amplitude = 2.0 * np.sqrt(sin_sum**2 + cos_sum**2) / n_steps

    # Normalized modulation (avoid division by zero)
    with np.errstate(divide='ignore', invalid='ignore'):
        modulation = np.where(
            avg_intensity > 1e-10,
            amplitude / avg_intensity,
            0.0
        )

    # Clip to [0, 1] range
    return np.clip(modulation, 0.0, 1.0)


def extract_phase_4step(frames: Sequence[np.ndarray]) -> PhaseMap:
    """Specialized 4-step phase extraction (common case).

    Uses the optimized formula for 4-step with 90 degree shifts:
    phi = atan2(I4 - I2, I1 - I3)

    Args:
        frames: Exactly 4 phase-shifted images (0, 90, 180, 270 degrees)

    Returns:
        PhaseMap with wrapped phase
    """
    if len(frames) != 4:
        raise ProcessingError("4-step extraction requires exactly 4 frames")

    I1, I2, I3, I4 = [np.asarray(f, dtype=np.float64) for f in frames]

    # Optimized 4-step formula
    wrapped_phase = np.arctan2(I4 - I2, I1 - I3)

    # Quality from modulation
    numerator = I4 - I2
    denominator = I1 - I3
    amplitude = np.sqrt(numerator**2 + denominator**2)
    avg_intensity = (I1 + I2 + I3 + I4) / 4.0

    with np.errstate(divide='ignore', invalid='ignore'):
        quality = np.where(
            avg_intensity > 1e-10,
            amplitude / (2.0 * avg_intensity),
            0.0
        )
    quality = np.clip(quality, 0.0, 1.0)

    return PhaseMap(wrapped=wrapped_phase, quality=quality)
