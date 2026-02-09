"""Multi-frequency phase measurement for extended range and improved accuracy.

Multi-frequency (temporal) phase unwrapping uses patterns with different fringe
periods to eliminate phase ambiguity and improve measurement accuracy.

Key concepts:
    - Coarse frequency: Long period, unambiguous over large range, lower precision
    - Fine frequency: Short period, high precision, but ambiguous (wraps frequently)
    - Hierarchical unwrapping: Coarse guides fine, eliminating ambiguity
"""

import numpy as np
from dataclasses import dataclass
from typing import Sequence

from ..core.datatypes import PhaseMap, HeightMap
from ..core.exceptions import ProcessingError
from .phase_shift import extract_phase
from .unwrap import unwrap_phase


@dataclass
class MultiFreqConfig:
    """Configuration for multi-frequency measurement.

    Attributes:
        periods: List of fringe periods in pixels, from coarse to fine.
                 Example: [160, 40, 10] for 3-frequency measurement.
        n_steps: Number of phase-shifting steps per frequency.
        use_equivalent_wavelength: If True, compute equivalent wavelength
                                   for each frequency pair to extend range.
    """
    periods: list[float]
    n_steps: int = 8
    use_equivalent_wavelength: bool = True

    def __post_init__(self):
        if len(self.periods) < 2:
            raise ValueError("Multi-frequency requires at least 2 periods")
        # Ensure periods are sorted from coarse (large) to fine (small)
        if self.periods != sorted(self.periods, reverse=True):
            raise ValueError("Periods must be ordered from coarse (large) to fine (small)")


@dataclass
class MultiFreqResult:
    """Result of multi-frequency phase measurement.

    Attributes:
        phase_maps: List of PhaseMap for each frequency (coarse to fine)
        combined_phase: Final unwrapped phase combining all frequencies
        equivalent_periods: Equivalent periods for each frequency pair
        quality: Combined quality map
    """
    phase_maps: list[PhaseMap]
    combined_phase: np.ndarray
    equivalent_periods: list[float]
    quality: np.ndarray


def compute_equivalent_period(period1: float, period2: float) -> float:
    """Compute equivalent period from two fringe periods.

    The equivalent period extends the unambiguous measurement range.
    When two frequencies beat together, the equivalent period is:
        P_eq = P1 * P2 / |P1 - P2|

    Args:
        period1: First fringe period (pixels)
        period2: Second fringe period (pixels)

    Returns:
        Equivalent period (pixels)

    Example:
        >>> compute_equivalent_period(160, 128)
        640.0  # Extends range 4x beyond single frequency
    """
    if period1 == period2:
        raise ValueError("Periods must be different for equivalent wavelength")
    return abs(period1 * period2 / (period1 - period2))


def hierarchical_unwrap(
    wrapped_phases: list[np.ndarray],
    periods: list[float],
    quality_maps: list[np.ndarray] | None = None,
) -> np.ndarray:
    """Perform hierarchical phase unwrapping from coarse to fine.

    Uses coarse frequency phase to guide unwrapping of finer frequencies,
    eliminating 2*pi ambiguities.

    Algorithm:
        1. Unwrap coarsest frequency conventionally
        2. For each finer frequency:
           a. Scale coarse unwrapped phase to fine frequency
           b. Use scaled phase to determine fringe order
           c. Add fringe order * 2*pi to wrapped fine phase

    Args:
        wrapped_phases: List of wrapped phase maps, coarse to fine
        periods: Corresponding fringe periods, coarse to fine
        quality_maps: Optional quality maps for each frequency

    Returns:
        Final unwrapped phase at finest frequency resolution
    """
    if len(wrapped_phases) != len(periods):
        raise ValueError("Number of phases must match number of periods")

    n_freqs = len(wrapped_phases)

    # Start with coarsest frequency - conventional unwrapping
    if quality_maps is not None:
        coarse_unwrapped = unwrap_phase(wrapped_phases[0], quality_maps[0])
    else:
        coarse_unwrapped = unwrap_phase(wrapped_phases[0])

    if n_freqs == 1:
        return coarse_unwrapped

    # Hierarchically unwrap each finer frequency
    current_unwrapped = coarse_unwrapped
    current_period = periods[0]

    for i in range(1, n_freqs):
        fine_wrapped = wrapped_phases[i]
        fine_period = periods[i]

        # Scale current unwrapped phase to fine frequency
        # Phase scales inversely with period: phi_fine = phi_coarse * (P_coarse / P_fine)
        scaled_phase = current_unwrapped * (current_period / fine_period)

        # Compute fringe order: k = round((scaled_phase - fine_wrapped) / (2*pi))
        fringe_order = np.round((scaled_phase - fine_wrapped) / (2 * np.pi))

        # Unwrap fine phase using fringe order
        fine_unwrapped = fine_wrapped + fringe_order * 2 * np.pi

        # Update for next iteration
        current_unwrapped = fine_unwrapped
        current_period = fine_period

    return current_unwrapped


def process_multifreq(
    frames_per_freq: list[list[np.ndarray]],
    config: MultiFreqConfig,
) -> MultiFreqResult:
    """Process multi-frequency fringe projection measurement.

    Args:
        frames_per_freq: List of frame lists, one per frequency.
                        frames_per_freq[i] contains n_steps frames for frequency i.
        config: Multi-frequency configuration.

    Returns:
        MultiFreqResult with combined phase and individual frequency data.

    Example:
        >>> config = MultiFreqConfig(periods=[160, 40, 10], n_steps=8)
        >>> # Capture frames for each frequency
        >>> frames = [capture_sequence(period, n_steps) for period in config.periods]
        >>> result = process_multifreq(frames, config)
    """
    if len(frames_per_freq) != len(config.periods):
        raise ProcessingError(
            f"Expected {len(config.periods)} frame sequences, got {len(frames_per_freq)}"
        )

    # Extract phase for each frequency
    phase_maps = []
    wrapped_phases = []
    quality_maps = []

    for i, frames in enumerate(frames_per_freq):
        if len(frames) != config.n_steps:
            raise ProcessingError(
                f"Frequency {i}: expected {config.n_steps} frames, got {len(frames)}"
            )

        phase_map = extract_phase(frames, n_steps=config.n_steps)
        phase_maps.append(phase_map)
        wrapped_phases.append(phase_map.wrapped)
        quality_maps.append(phase_map.quality)

    # Compute equivalent periods
    equivalent_periods = []
    if config.use_equivalent_wavelength:
        for i in range(len(config.periods) - 1):
            eq_period = compute_equivalent_period(config.periods[i], config.periods[i + 1])
            equivalent_periods.append(eq_period)

    # Hierarchical unwrapping
    combined_phase = hierarchical_unwrap(
        wrapped_phases,
        config.periods,
        quality_maps
    )

    # Combined quality: product of all quality maps (normalized)
    combined_quality = np.ones_like(quality_maps[0])
    for q in quality_maps:
        combined_quality *= q / q.max()
    combined_quality = combined_quality / combined_quality.max()

    return MultiFreqResult(
        phase_maps=phase_maps,
        combined_phase=combined_phase,
        equivalent_periods=equivalent_periods,
        quality=combined_quality,
    )


def temporal_unwrap(
    wrapped_phases: list[np.ndarray],
    periods: list[float],
) -> tuple[np.ndarray, np.ndarray]:
    """Purely temporal (pixel-by-pixel) phase unwrapping.

    Unlike hierarchical_unwrap which uses spatial unwrapping on the coarsest
    frequency, this method works entirely per-pixel using the relationship
    between frequencies. No spatial error propagation.

    Algorithm per pixel:
        1. Coarsest frequency: phase is assumed unambiguous (period large enough)
        2. For each finer frequency: use coarser phase to determine fringe order

    Args:
        wrapped_phases: List of wrapped phase maps, coarse to fine
        periods: Corresponding fringe periods, coarse to fine

    Returns:
        (unwrapped_phase, quality_map) tuple.
        Quality map indicates reliability (0-1) based on consistency between
        frequency levels.
    """
    if len(wrapped_phases) != len(periods):
        raise ValueError("Number of phases must match number of periods")

    # Start with coarsest frequency - assume unambiguous (no spatial unwrap)
    current_unwrapped = wrapped_phases[0].copy()
    current_period = periods[0]

    # Quality: track consistency between levels
    quality = np.ones_like(wrapped_phases[0])

    for i in range(1, len(wrapped_phases)):
        fine_wrapped = wrapped_phases[i]
        fine_period = periods[i]

        # Scale current unwrapped phase to fine frequency
        scaled_phase = current_unwrapped * (current_period / fine_period)

        # Compute fringe order per pixel
        fringe_order = np.round((scaled_phase - fine_wrapped) / (2 * np.pi))

        # Unwrap fine phase
        fine_unwrapped = fine_wrapped + fringe_order * 2 * np.pi

        # Quality: measure consistency (fractional part of fringe order)
        # Perfect consistency = integer fringe order, poor = 0.5 fractional
        fractional = np.abs((scaled_phase - fine_wrapped) / (2 * np.pi) - fringe_order)
        quality *= (1.0 - 2.0 * fractional)  # 1.0 = perfect, 0.0 = ambiguous

        current_unwrapped = fine_unwrapped
        current_period = fine_period

    quality = np.clip(quality, 0, 1)
    return current_unwrapped, quality


def generate_multifreq_patterns(
    resolution: tuple[int, int],
    periods: list[float],
    n_steps: int = 8,
) -> list[list[np.ndarray]]:
    """Generate pattern sequences for multi-frequency measurement.

    Convenience function to generate all patterns needed for multi-frequency
    measurement.

    Args:
        resolution: Pattern resolution (height, width)
        periods: List of fringe periods, coarse to fine
        n_steps: Number of phase-shifting steps per frequency

    Returns:
        List of pattern sequences, one per frequency.
        patterns[i][j] is the j-th phase-shifted pattern for frequency i.
    """
    from ..patterns import generate_phase_sequence

    all_patterns = []
    for period in periods:
        patterns = generate_phase_sequence(resolution, period=period, n_steps=n_steps)
        all_patterns.append(patterns)

    return all_patterns


def estimate_optimal_periods(
    height_range: float,
    pixel_pitch: float,
    resolution: tuple[int, int],
    n_frequencies: int = 3,
    min_period_pixels: int = 8,
) -> list[float]:
    """Estimate optimal fringe periods for a given measurement range.

    Suggests periods that provide good coverage from coarse (full range)
    to fine (maximum resolution).

    Args:
        height_range: Expected height range to measure (same units as pixel_pitch)
        pixel_pitch: Physical size per pixel
        resolution: Image resolution (height, width)
        n_frequencies: Number of frequencies to use (2-4 recommended)
        min_period_pixels: Minimum period in pixels (limited by camera resolution)

    Returns:
        List of suggested periods from coarse to fine.

    Example:
        >>> periods = estimate_optimal_periods(
        ...     height_range=10.0,  # mm
        ...     pixel_pitch=0.01,   # mm/pixel
        ...     resolution=(1024, 1024),
        ...     n_frequencies=3
        ... )
    """
    if n_frequencies < 2:
        raise ValueError("Need at least 2 frequencies")

    # Coarsest period should cover the full height range unambiguously
    # For safety, use 2x the expected range
    max_period = min(resolution[0], resolution[1]) // 2

    # Finest period is limited by pixel resolution (need ~8+ pixels per fringe)
    min_period = max(min_period_pixels, 8)

    # Generate geometrically spaced periods
    # This gives roughly equal information contribution from each frequency
    ratio = (max_period / min_period) ** (1.0 / (n_frequencies - 1))

    periods = []
    current = max_period
    for _ in range(n_frequencies):
        periods.append(round(current))
        current /= ratio

    # Ensure minimum period constraint
    periods[-1] = max(periods[-1], min_period)

    return periods
