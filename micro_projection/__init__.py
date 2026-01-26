"""Fringe Projection Profilometry Module.

A Python module for fringe projection profilometry that is environment-agnostic -
works with simulation, real cameras, or microscope setups without code changes.

Example:
    >>> from micro_projection import SimulationSource, SimulationConfig
    >>> from micro_projection.patterns import generate_phase_sequence
    >>> from micro_projection.processing import extract_phase, unwrap_phase, phase_to_height
    >>>
    >>> # Setup simulation
    >>> config = SimulationConfig(resolution=(512, 512), noise_level=0.01)
    >>> source = SimulationSource(config)
    >>> source.set_test_surface("sphere", amplitude=0.1)
    >>>
    >>> # Generate and capture phase-shifted patterns
    >>> patterns = generate_phase_sequence((512, 512), period=32, n_steps=4)
    >>> frames = []
    >>> for p in patterns:
    ...     source.project_pattern(p)
    ...     frames.append(source.capture_frame())
    >>>
    >>> # Process to get height map
    >>> phase_map = extract_phase(frames)
    >>> phase_map.unwrapped = unwrap_phase(phase_map.wrapped, phase_map.quality)
    >>> height = phase_to_height(phase_map, calibration)
"""

from .core.datatypes import (
    PhaseMap,
    HeightMap,
    SurfaceAnalysis,
    SimulationConfig,
    CalibrationParams,
)
from .core.exceptions import (
    FringeProjectionError,
    CalibrationError,
    AcquisitionError,
    ProcessingError,
    UnwrapError,
    InvalidPatternError,
    ConfigurationError,
)
from .sources.simulation import SimulationSource
from .sources.file import FileSource
from .sources.camera import CameraSource

__version__ = "0.1.0"
__all__ = [
    # Data types
    "PhaseMap",
    "HeightMap",
    "SurfaceAnalysis",
    "SimulationConfig",
    "CalibrationParams",
    # Exceptions
    "FringeProjectionError",
    "CalibrationError",
    "AcquisitionError",
    "ProcessingError",
    "UnwrapError",
    "InvalidPatternError",
    "ConfigurationError",
    # Sources
    "SimulationSource",
    "FileSource",
    "CameraSource",
]
