"""Surface generators for multi-frequency demonstration.

Each function returns (form, roughness, combined) tuple with known
ground truth components for roughness accuracy comparison.
"""

import numpy as np


def _make_roughness(resolution: tuple[int, int], amplitude: float = 0.005) -> np.ndarray:
    """Create a repeatable roughness texture (random + periodic)."""
    h, w = resolution
    rng = np.random.default_rng(42)
    y, x = np.mgrid[0:h, 0:w].astype(np.float64)
    cx, cy = w / 2, h / 2
    x_norm = (x - cx) / cx
    y_norm = (y - cy) / cy

    rough = amplitude * rng.standard_normal((h, w))
    # Periodic micro-texture
    rough += 0.003 * np.sin(40 * np.pi * x_norm) * np.cos(40 * np.pi * y_norm)
    # Cross-hatch pattern (machining-like)
    rough += 0.002 * np.sin(25 * np.pi * (x_norm + y_norm))
    return rough


def create_smooth_surface(resolution: tuple[int, int]):
    """Smooth dome + roughness. No discontinuities (control test).

    Returns:
        (form, roughness, combined)
    """
    h, w = resolution
    y, x = np.mgrid[0:h, 0:w].astype(np.float64)
    cx, cy = w / 2, h / 2
    x_norm = (x - cx) / cx
    y_norm = (y - cy) / cy

    r = np.sqrt(x_norm**2 + y_norm**2)
    form = 0.3 * np.exp(-2 * r**2) + 0.08 * x_norm
    roughness = _make_roughness(resolution)
    return form, roughness, form + roughness


def create_simple_step_surface(resolution: tuple[int, int]):
    """Single step + roughness. One discontinuity.

    Returns:
        (form, roughness, combined)
    """
    h, w = resolution
    y, x = np.mgrid[0:h, 0:w].astype(np.float64)
    cx, cy = w / 2, h / 2
    x_norm = (x - cx) / cx

    from scipy import ndimage
    form = np.zeros((h, w), dtype=np.float64)
    form[x_norm > 0] = 0.7
    form = ndimage.gaussian_filter(form, sigma=1.0)

    roughness = _make_roughness(resolution)
    return form, roughness, form + roughness


def create_challenging_surface(resolution: tuple[int, int]):
    """Multiple steps and isolated features + roughness.

    The form has sharp discontinuities that cause phase unwrapping errors.
    Those errors propagate into the roughness after form/roughness separation,
    corrupting Sa/Sq/Sz measurements.

    Returns:
        (form, roughness, combined)
    """
    h, w = resolution
    y, x = np.mgrid[0:h, 0:w].astype(np.float64)
    cx, cy = w / 2, h / 2
    x_norm = (x - cx) / cx
    y_norm = (y - cy) / cy

    form = np.zeros((h, w), dtype=np.float64)

    # Gentle base slope
    form += 0.1 * x_norm

    # Raised rectangular plateau
    step_mask = (x_norm > -0.2) & (x_norm < 0.5) & (y_norm > -0.3) & (y_norm < 0.3)
    form[step_mask] += 0.8

    # Second step at different height (overlapping corner)
    step2_mask = (x_norm > 0.3) & (y_norm > 0.2)
    form[step2_mask] += 0.5

    # Isolated pillar
    pillar_r = np.sqrt((x_norm + 0.5)**2 + (y_norm - 0.4)**2)
    form[pillar_r < 0.1] = 1.2

    # Isolated feature
    feat_r = np.sqrt((x_norm - 0.6)**2 + (y_norm + 0.5)**2)
    form[feat_r < 0.12] = 0.9

    # Depression/pit
    pit_r = np.sqrt((x_norm + 0.6)**2 + (y_norm + 0.5)**2)
    form[pit_r < 0.08] = -0.4

    # Minimal smoothing - keep edges sharp
    from scipy import ndimage
    form = ndimage.gaussian_filter(form, sigma=1.0)

    roughness = _make_roughness(resolution)
    return form, roughness, form + roughness
