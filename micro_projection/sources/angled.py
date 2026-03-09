"""Angled (triangulation) fringe projection simulation."""

import numpy as np
from dataclasses import dataclass
from typing import Optional

from ..core.datatypes import SimulationConfig
from .simulation import SimulationSource


@dataclass
class AngledSimulationConfig:
    """Geometry configuration for angled (triangulation) projection.

    Attributes:
        baseline: Camera-projector separation distance (d).
        standoff_distance: Working distance from camera to reference plane (L).
        telecentric: If True, use linear approximation. If False, full perspective.
        shadow_enabled: If True, compute shadow mask from projector occlusion.
    """
    baseline: float = 50.0
    standoff_distance: float = 1000.0
    telecentric: bool = True
    shadow_enabled: bool = True


class AngledSimulationSource(SimulationSource):
    """Simulated fringe projection with triangulation geometry.

    Models a projector offset from the camera by a baseline distance,
    creating an angled illumination that introduces geometric sensitivity
    and shadows behind tall features.

    The projector is located to the right of the image field of view.

    Phase sensitivity:
        Telecentric:  delta_phi = 2*pi * d * h / (P * L)
        Perspective:  delta_phi = 2*pi * d * h / (P * (L - h))

    Equivalent wavelength: lambda_eq = P * L / d
    """

    def __init__(self, config: SimulationConfig | None = None,
                 angled_config: AngledSimulationConfig | None = None):
        super().__init__(config)
        self.angled_config = angled_config or AngledSimulationConfig()
        self._shadow_mask: Optional[np.ndarray] = None

    def set_surface(self, height_map: np.ndarray) -> None:
        super().set_surface(height_map)
        self._shadow_mask = None

    def set_flat_surface(self) -> None:
        super().set_flat_surface()
        self._shadow_mask = None

    def set_test_surface(self, surface_type: str = "sphere", **kwargs) -> None:
        super().set_test_surface(surface_type, **kwargs)
        self._shadow_mask = None

    def _compute_deformed_pattern(self) -> np.ndarray:
        """Compute deformed pattern with triangulation phase shift.

        Telecentric: delta_phi = (2*pi * d * h) / (P * L)
        Perspective: delta_phi = (2*pi * d * h) / (P * (L - h))
        """
        pattern_phase = self._current_pattern_phase
        period = getattr(self, '_current_period', self.config.resolution[1])

        d = self.angled_config.baseline
        L = self.angled_config.standoff_distance

        if self.angled_config.telecentric:
            phase_shift = (2.0 * np.pi * d * self._surface) / (period * L)
        else:
            effective_L = np.maximum(L - self._surface, 1e-6)
            phase_shift = (2.0 * np.pi * d * self._surface) / (period * effective_L)

        deformed_phase = pattern_phase + phase_shift
        deformed_intensity = 0.5 * (1.0 + np.cos(deformed_phase))

        if self.angled_config.shadow_enabled:
            shadow = self.get_shadow_mask()
            deformed_intensity[shadow] = 0.0

        return deformed_intensity

    def _compute_shadow_mask(self) -> np.ndarray:
        """Compute shadow mask from projector occlusion.

        Uses horizon-angle algorithm: the projector sits to the right of
        the image at x_proj = (cols-1) + d.  For every pixel we compute the
        slope h/dx from the projector.  Scanning right-to-left, any pixel
        whose slope is below the running maximum is in shadow.
        """
        if self._surface is None:
            return np.zeros(self.config.resolution, dtype=bool)

        h, w = self._surface.shape
        d = self.angled_config.baseline

        cols = np.arange(w, dtype=np.float64)
        dx = d + (w - 1 - cols)  # horizontal distance to projector

        slopes = self._surface / dx[np.newaxis, :]

        # Running max from right to left
        slopes_flipped = slopes[:, ::-1]
        cum_max_flipped = np.maximum.accumulate(slopes_flipped, axis=1)
        cum_max = cum_max_flipped[:, ::-1]

        # Max slope of pixels strictly to the right of each column
        max_right = np.full_like(slopes, -np.inf)
        max_right[:, :-1] = cum_max[:, 1:]

        return slopes < max_right

    def get_shadow_mask(self) -> np.ndarray:
        """Get the shadow mask, computing and caching on first call.

        Returns:
            Boolean array where True means the pixel is in projector shadow.
        """
        if self._shadow_mask is None:
            self._shadow_mask = self._compute_shadow_mask()
        return self._shadow_mask

    def get_quality_map(self) -> np.ndarray:
        """Get quality map: 1.0 illuminated, 0.0 in shadow.

        Returns:
            Float array with quality values.
        """
        shadow = self.get_shadow_mask()
        quality = np.ones(self.config.resolution, dtype=np.float64)
        quality[shadow] = 0.0
        return quality

    def compute_equivalent_wavelength(self, period: float) -> float:
        """Compute equivalent wavelength for a given fringe period.

        Args:
            period: Fringe period in pixels.

        Returns:
            lambda_eq = P * L / d
        """
        return period * self.angled_config.standoff_distance / self.angled_config.baseline
