"""Sinusoidal fringe pattern generation utilities."""

import numpy as np
from typing import Sequence


def sinusoidal_pattern(
    resolution: tuple[int, int],
    period: float,
    phase_offset: float = 0.0,
    orientation: float = 0.0,
) -> np.ndarray:
    """Generate a sinusoidal fringe pattern.

    Args:
        resolution: Image resolution as (height, width)
        period: Fringe period in pixels
        phase_offset: Phase offset in radians (default 0)
        orientation: Pattern orientation in degrees (0 = vertical fringes,
                     90 = horizontal fringes)

    Returns:
        2D array with values in [0, 1] representing the pattern intensity.

    Example:
        >>> pattern = sinusoidal_pattern((512, 512), period=32, phase_offset=0)
        >>> pattern.shape
        (512, 512)
        >>> 0 <= pattern.min() and pattern.max() <= 1
        True
    """
    height, width = resolution

    # Create coordinate grids
    y, x = np.mgrid[0:height, 0:width].astype(np.float64)

    # Convert orientation to radians
    theta = np.radians(orientation)

    # Compute coordinate along fringe direction
    # For orientation=0 (vertical fringes), we use x
    # For orientation=90 (horizontal fringes), we use y
    coord = x * np.cos(theta) + y * np.sin(theta)

    # Generate sinusoidal pattern
    # I = 0.5 * (1 + cos(2*pi * coord / period + phase_offset))
    phase = 2.0 * np.pi * coord / period + phase_offset
    pattern = 0.5 * (1.0 + np.cos(phase))

    return pattern


def generate_phase_sequence(
    resolution: tuple[int, int],
    period: float,
    n_steps: int,
    orientation: float = 0.0,
) -> list[np.ndarray]:
    """Generate a sequence of phase-shifted sinusoidal patterns.

    Args:
        resolution: Image resolution as (height, width)
        period: Fringe period in pixels
        n_steps: Number of phase-shifted patterns to generate
        orientation: Pattern orientation in degrees

    Returns:
        List of n_steps patterns with evenly distributed phase offsets.
        Phase offsets are: 0, 2*pi/N, 4*pi/N, ..., 2*pi(N-1)/N

    Example:
        >>> patterns = generate_phase_sequence((512, 512), period=32, n_steps=4)
        >>> len(patterns)
        4
        >>> all(p.shape == (512, 512) for p in patterns)
        True
    """
    if n_steps < 3:
        raise ValueError("n_steps must be at least 3 for phase extraction")

    patterns = []
    for i in range(n_steps):
        phase_offset = 2.0 * np.pi * i / n_steps
        pattern = sinusoidal_pattern(
            resolution=resolution,
            period=period,
            phase_offset=phase_offset,
            orientation=orientation,
        )
        patterns.append(pattern)

    return patterns


def generate_multi_frequency_sequence(
    resolution: tuple[int, int],
    periods: Sequence[float],
    n_steps: int,
    orientation: float = 0.0,
) -> dict[float, list[np.ndarray]]:
    """Generate phase-shifted patterns for multiple frequencies.

    This is useful for multi-frequency or hierarchical phase unwrapping.

    Args:
        resolution: Image resolution as (height, width)
        periods: Sequence of fringe periods in pixels
        n_steps: Number of phase-shifted patterns per frequency
        orientation: Pattern orientation in degrees

    Returns:
        Dictionary mapping period to list of phase-shifted patterns.

    Example:
        >>> sequences = generate_multi_frequency_sequence(
        ...     (512, 512), periods=[32, 64, 128], n_steps=4
        ... )
        >>> len(sequences)
        3
        >>> all(len(patterns) == 4 for patterns in sequences.values())
        True
    """
    sequences = {}
    for period in periods:
        sequences[period] = generate_phase_sequence(
            resolution=resolution,
            period=period,
            n_steps=n_steps,
            orientation=orientation,
        )
    return sequences


def compute_carrier_phase(
    resolution: tuple[int, int],
    period: float,
    orientation: float = 0.0,
) -> np.ndarray:
    """Compute the wrapped carrier phase for a fringe pattern.

    The carrier phase is the spatial phase of the fringe pattern without
    any surface deformation or phase-shifting offset. This is useful for
    removing the carrier contribution from measured phase maps before
    temporal unwrapping.

    Args:
        resolution: Image resolution as (height, width)
        period: Fringe period in pixels
        orientation: Pattern orientation in degrees (0 = vertical fringes)

    Returns:
        2D array of carrier phase values wrapped to [-pi, pi].
    """
    height, width = resolution
    y, x = np.mgrid[0:height, 0:width].astype(np.float64)

    theta = np.radians(orientation)
    coord = x * np.cos(theta) + y * np.sin(theta)
    phase = 2.0 * np.pi * coord / period

    # Wrap to [-pi, pi]
    return np.arctan2(np.sin(phase), np.cos(phase))
