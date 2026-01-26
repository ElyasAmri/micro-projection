"""Data types for fringe projection results."""

from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class PhaseMap:
    """Represents extracted phase information from fringe patterns.

    Attributes:
        wrapped: Wrapped phase values in range (-pi, pi]
        unwrapped: Unwrapped continuous phase values
        quality: Quality/confidence map (0-1, higher is better)
    """
    wrapped: np.ndarray
    unwrapped: Optional[np.ndarray] = None
    quality: Optional[np.ndarray] = None

    def __post_init__(self):
        if self.quality is None:
            self.quality = np.ones_like(self.wrapped)

    def __repr__(self) -> str:
        has_unwrapped = self.unwrapped is not None
        return f"PhaseMap(shape={self.wrapped.shape}, unwrapped={has_unwrapped})"


@dataclass
class HeightMap:
    """Represents computed height/depth information.

    Attributes:
        data: Height values as 2D array
        unit: Physical unit of height values ("mm", "um", "nm")
        pixel_pitch: Physical size per pixel in the same unit
        equivalent_wavelength: lambda_eq used for computation
        metadata: Additional algorithm parameters, timestamps, etc.
    """
    data: np.ndarray
    unit: str = "mm"
    pixel_pitch: float = 1.0
    equivalent_wavelength: float = 1.0
    metadata: dict = field(default_factory=dict)

    @property
    def shape(self) -> tuple[int, int]:
        """Return the shape of the height map."""
        return self.data.shape

    @property
    def physical_size(self) -> tuple[float, float]:
        """Return physical dimensions (height, width) in the specified unit."""
        h, w = self.shape
        return (h * self.pixel_pitch, w * self.pixel_pitch)

    def __repr__(self) -> str:
        return f"HeightMap(shape={self.shape}, unit='{self.unit}', pixel_pitch={self.pixel_pitch})"


@dataclass
class SurfaceAnalysis:
    """Represents separated surface components.

    Attributes:
        total: Full surface measurement (h1 + h2)
        form: Low-frequency waviness/form component (h1)
        finish: High-frequency roughness/finish component (h2)
    """
    total: HeightMap
    form: Optional[HeightMap] = None
    finish: Optional[HeightMap] = None

    def __repr__(self) -> str:
        has_form = self.form is not None
        has_finish = self.finish is not None
        return f"SurfaceAnalysis(total={self.total.shape}, form={has_form}, finish={has_finish})"


@dataclass
class SimulationConfig:
    """Configuration for simulation source.

    Attributes:
        resolution: Image resolution (height, width)
        noise_level: Standard deviation of Gaussian noise (0-1 scale)
        perspective_effect: Enable perspective distortion simulation
        gamma: Camera gamma response (1.0 = linear)
        bit_depth: Simulated camera bit depth (8, 10, 12, 16)
        exposure_variation: Random exposure variation factor
    """
    resolution: tuple[int, int] = (512, 512)
    noise_level: float = 0.01
    perspective_effect: bool = False
    gamma: float = 1.0
    bit_depth: int = 8
    exposure_variation: float = 0.0


@dataclass
class CalibrationParams:
    """Calibration parameters for phase-to-height conversion.

    Attributes:
        equivalent_wavelength: lambda_eq for height calculation
        pixel_pitch: Physical size per pixel
        reference_distance: Distance from projector to reference plane
        fringe_pitch: Physical pitch of projected fringes
        unit: Physical unit for measurements
    """
    equivalent_wavelength: float
    pixel_pitch: float = 1.0
    reference_distance: Optional[float] = None
    fringe_pitch: Optional[float] = None
    unit: str = "mm"
