"""Processing algorithms for fringe projection profilometry."""

from .phase_shift import (
    extract_phase,
    extract_phase_4step,
    compute_modulation,
)
from .unwrap import (
    unwrap_phase,
)
from .height import (
    phase_to_height,
    compute_equivalent_wavelength,
    apply_perspective_correction,
    remove_plane,
)
from .filtering import (
    separate_surface,
    compute_roughness_parameters,
    apply_bandpass_filter,
)
from .multifreq import (
    MultiFreqConfig,
    MultiFreqResult,
    process_multifreq,
    hierarchical_unwrap,
    temporal_unwrap,
    generate_multifreq_patterns,
    compute_equivalent_period,
    estimate_optimal_periods,
)

__all__ = [
    # Phase extraction
    "extract_phase",
    "extract_phase_4step",
    "compute_modulation",
    # Phase unwrapping
    "unwrap_phase",
    # Height conversion
    "phase_to_height",
    "compute_equivalent_wavelength",
    "apply_perspective_correction",
    "remove_plane",
    # Filtering
    "separate_surface",
    "compute_roughness_parameters",
    "apply_bandpass_filter",
    # Multi-frequency
    "MultiFreqConfig",
    "MultiFreqResult",
    "process_multifreq",
    "hierarchical_unwrap",
    "temporal_unwrap",
    "generate_multifreq_patterns",
    "compute_equivalent_period",
    "estimate_optimal_periods",
]
