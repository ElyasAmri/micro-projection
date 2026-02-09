"""Pattern generation utilities for fringe projection."""

from .generator import (
    sinusoidal_pattern,
    generate_phase_sequence,
    generate_multi_frequency_sequence,
    compute_carrier_phase,
)

__all__ = [
    "sinusoidal_pattern",
    "generate_phase_sequence",
    "generate_multi_frequency_sequence",
    "compute_carrier_phase",
]
