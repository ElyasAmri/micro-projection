"""Simulated camera/projector source for testing and development."""

import numpy as np
from typing import Optional

from ..core.datatypes import SimulationConfig
from ..core.exceptions import ConfigurationError, AcquisitionError


class SimulationSource:
    """Simulated fringe projection system for testing algorithms.

    This class simulates a fringe projection setup by:
    1. Accepting a virtual test surface (height map)
    2. Simulating the projection of fringe patterns onto the surface
    3. Simulating camera capture of the deformed fringes

    The simulation can include realistic effects like:
    - Gaussian noise
    - Perspective distortion
    - Camera gamma response
    - Bit depth quantization
    - Exposure variation

    Example:
        >>> config = SimulationConfig(resolution=(512, 512), noise_level=0.02)
        >>> source = SimulationSource(config)
        >>> source.set_surface(height_map)
        >>> pattern = sinusoidal_pattern((512, 512), period=32)
        >>> source.project_pattern(pattern)
        >>> frame = source.capture_frame()
    """

    def __init__(self, config: SimulationConfig | None = None):
        """Initialize the simulation source.

        Args:
            config: Simulation configuration. If None, uses defaults.
        """
        self.config = config or SimulationConfig()
        self._surface: Optional[np.ndarray] = None
        self._current_pattern: Optional[np.ndarray] = None
        self._current_pattern_phase: Optional[np.ndarray] = None  # Store phase directly
        self._rng = np.random.default_rng()
        # Height sensitivity: 1 unit of height produces 1 fringe cycle (2*pi radians of phase)
        self.height_sensitivity = 2.0 * np.pi  # radians per unit height

    def set_surface(self, height_map: np.ndarray) -> None:
        """Set the virtual test surface.

        Args:
            height_map: 2D array of height values. Will be resized to match
                        the configured resolution if needed.
        """
        height, width = self.config.resolution

        if height_map.shape != (height, width):
            # Resize using interpolation
            from scipy import ndimage
            zoom_factors = (height / height_map.shape[0], width / height_map.shape[1])
            self._surface = ndimage.zoom(height_map, zoom_factors, order=3)
        else:
            self._surface = height_map.copy()

    def set_flat_surface(self) -> None:
        """Set a perfectly flat reference surface (height = 0)."""
        height, width = self.config.resolution
        self._surface = np.zeros((height, width), dtype=np.float64)

    def set_test_surface(self, surface_type: str = "sphere", **kwargs) -> None:
        """Set a predefined test surface.

        Args:
            surface_type: Type of test surface:
                - "sphere": Spherical cap
                - "plane": Tilted plane
                - "step": Step function
                - "sinusoid": Sinusoidal surface
                - "random": Random smooth surface
            **kwargs: Parameters for the surface type
        """
        height, width = self.config.resolution
        y, x = np.mgrid[0:height, 0:width].astype(np.float64)

        # Normalize coordinates to [-1, 1]
        x_norm = 2.0 * (x - width / 2) / width
        y_norm = 2.0 * (y - height / 2) / height

        if surface_type == "sphere":
            radius = kwargs.get("radius", 0.5)
            amplitude = kwargs.get("amplitude", 0.1)
            r2 = x_norm**2 + y_norm**2
            self._surface = amplitude * np.sqrt(np.maximum(0, radius**2 - r2))

        elif surface_type == "plane":
            tilt_x = kwargs.get("tilt_x", 0.1)
            tilt_y = kwargs.get("tilt_y", 0.05)
            self._surface = tilt_x * x_norm + tilt_y * y_norm

        elif surface_type == "step":
            step_height = kwargs.get("step_height", 0.2)
            self._surface = np.where(x_norm > 0, step_height, 0.0)

        elif surface_type == "sinusoid":
            amplitude = kwargs.get("amplitude", 0.1)
            periods = kwargs.get("periods", 3)
            self._surface = amplitude * np.sin(2.0 * np.pi * periods * x_norm)

        elif surface_type == "random":
            amplitude = kwargs.get("amplitude", 0.1)
            smoothness = kwargs.get("smoothness", 20.0)
            from scipy import ndimage
            random_surface = self._rng.standard_normal((height, width))
            self._surface = amplitude * ndimage.gaussian_filter(random_surface, sigma=smoothness)

        else:
            raise ConfigurationError(f"Unknown surface type: {surface_type}")

    def project_pattern(self, pattern: np.ndarray) -> None:
        """Project a pattern onto the virtual surface.

        Args:
            pattern: 2D array with values in [0, 1] representing the pattern.
        """
        if pattern.shape != self.config.resolution:
            raise ConfigurationError(
                f"Pattern shape {pattern.shape} doesn't match "
                f"resolution {self.config.resolution}"
            )
        if pattern.min() < 0 or pattern.max() > 1:
            raise ConfigurationError("Pattern values must be in [0, 1] range")
        self._current_pattern = pattern.copy()

        # Extract phase from the pattern: I = 0.5 * (1 + cos(phi))
        # So cos(phi) = 2*I - 1, and phi = arccos(2*I - 1)
        # But arccos only gives [0, pi], we need to determine sign from gradient
        cos_phi = np.clip(2.0 * pattern - 1.0, -1.0, 1.0)
        phase = np.arccos(cos_phi)

        # Use gradient to determine sign: where pattern is increasing, phase is negative
        grad_x = np.gradient(pattern, axis=1)
        phase = np.where(grad_x > 0, -phase, phase)

        self._current_pattern_phase = phase

    def capture_frame(self) -> np.ndarray:
        """Capture a simulated frame of the deformed fringes.

        Returns:
            2D array representing the captured image with all
            configured realistic effects applied.

        Raises:
            AcquisitionError: If no pattern has been projected or no surface set.
        """
        if self._current_pattern is None:
            raise AcquisitionError("No pattern has been projected")

        if self._surface is None:
            # Default to flat surface
            self.set_flat_surface()

        # Compute the deformed fringe pattern
        frame = self._compute_deformed_pattern()

        # Apply realistic effects
        frame = self._apply_camera_effects(frame)

        return frame

    def _compute_deformed_pattern(self) -> np.ndarray:
        """Compute the deformed fringe pattern based on surface height.

        The surface height causes a phase shift in the observed fringes.
        For a surface height h, the phase shift is:
            Delta_phi = height_sensitivity * h

        The height_sensitivity parameter controls the relationship between
        surface height and phase shift. For proper reconstruction, it should
        match the calibration's equivalent_wavelength.
        """
        # Use the pre-computed pattern phase
        pattern_phase = self._current_pattern_phase

        # Add phase shift from surface height: Delta_phi = sensitivity * h
        deformed_phase = pattern_phase + self.height_sensitivity * self._surface

        # Convert back to intensity: I = 0.5 * (1 + cos(phi))
        deformed_intensity = 0.5 * (1.0 + np.cos(deformed_phase))

        return deformed_intensity

    def _apply_camera_effects(self, frame: np.ndarray) -> np.ndarray:
        """Apply simulated camera effects to the frame."""
        result = frame.copy()

        # Exposure variation
        if self.config.exposure_variation > 0:
            exposure_factor = 1.0 + self._rng.uniform(
                -self.config.exposure_variation,
                self.config.exposure_variation
            )
            result *= exposure_factor

        # Add Gaussian noise
        if self.config.noise_level > 0:
            noise = self._rng.normal(0, self.config.noise_level, result.shape)
            result += noise

        # Apply gamma correction
        if self.config.gamma != 1.0:
            result = np.clip(result, 0, 1)
            result = np.power(result, 1.0 / self.config.gamma)

        # Clip to valid range
        result = np.clip(result, 0.0, 1.0)

        # Quantize to bit depth
        if self.config.bit_depth < 16:
            max_val = 2**self.config.bit_depth - 1
            result = np.round(result * max_val) / max_val

        return result

    def get_resolution(self) -> tuple[int, int]:
        """Get the configured resolution.

        Returns:
            Tuple of (height, width) in pixels.
        """
        return self.config.resolution

    def get_surface(self) -> Optional[np.ndarray]:
        """Get the current virtual surface.

        Returns:
            The current surface height map, or None if not set.
        """
        return self._surface.copy() if self._surface is not None else None

    def reset(self) -> None:
        """Reset the simulation state."""
        self._surface = None
        self._current_pattern = None
        self._current_pattern_phase = None
