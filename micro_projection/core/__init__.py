"""Core types, protocols, and exceptions for fringe projection."""

from .datatypes import (
    PhaseMap,
    HeightMap,
    SurfaceAnalysis,
    SimulationConfig,
    CalibrationParams,
)
from .exceptions import (
    FringeProjectionError,
    CalibrationError,
    AcquisitionError,
    ProcessingError,
    UnwrapError,
    InvalidPatternError,
    ConfigurationError,
)
from .protocols import (
    ImageSource,
    FringeProcessor,
    PhaseUnwrapper,
    SurfaceFilter,
)

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
    # Protocols
    "ImageSource",
    "FringeProcessor",
    "PhaseUnwrapper",
    "SurfaceFilter",
]
