"""Custom exceptions for the fringe projection module."""


class FringeProjectionError(Exception):
    """Base exception for all fringe projection errors."""
    pass


class CalibrationError(FringeProjectionError):
    """Raised when calibration parameters are invalid or missing."""
    pass


class AcquisitionError(FringeProjectionError):
    """Raised when image acquisition fails."""
    pass


class ProcessingError(FringeProjectionError):
    """Raised when phase processing encounters an error."""
    pass


class UnwrapError(ProcessingError):
    """Raised when phase unwrapping fails."""
    pass


class InvalidPatternError(FringeProjectionError):
    """Raised when fringe pattern is invalid or corrupted."""
    pass


class ConfigurationError(FringeProjectionError):
    """Raised when configuration is invalid."""
    pass
