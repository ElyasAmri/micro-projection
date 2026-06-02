"""sampling.py — Pixel-area sensor sampling model (Stage 6 A.0.2).

A real camera pixel integrates incident light over its finite light-sensitive
area; it does NOT point-sample a continuous sinusoid at the pixel center. When
the fringe period shrinks toward the pixel size, that area-integration averages
over a growing fraction of a fringe cycle and the recorded contrast fades. This
is the physical wall that the project's inverse-FPP claim is meant to beat: a
straight fringe finer than ~2 px loses contrast the way a sensor would, rather
than aliasing silently.

Physics
-------
Integrating a sinusoid of local spatial frequency `f` (cycles per pixel) over a
box of width `w` pixels multiplies its amplitude by

    |sinc(w * f)|        with sinc(z) = sin(pi z) / (pi z)   (np.sinc convention)

Here `w` is the fill factor (fraction of the pixel pitch that is photosensitive,
default 1.0 -> the box spans the whole pixel). The local frequency is read from
the LOCAL phase gradient, not the scalar carrier period, so height-warped /
steep regions — where the observed fringe density genuinely rises — fade while
flat regions stay full-contrast:

    f_local = |grad(phase)| / (2 * pi)        [cycles / pixel]

`|grad(phase)|` is the full 2D gradient magnitude (both axes): a steep object
slope across rows raises the observed frequency just as a steep slope across
columns does, and both must fade contrast.

Unit discipline
---------------
Everything here is in cycles/pixel — dimensionless. This module reads NOTHING
from the object-space scale-bridge constants in geometry.py; microns never
enter the math path. The fill factor is a fraction of a pixel, not a length.
This keeps the simulation core sealed in pixel-space. (The no-leak guard test
enforces this by forbidding those constant names from appearing here at all.)

The honest wall
---------------
At fill_factor = 1.0 the first sinc null is at f = 1 cycle/pixel (a 1-px period).
At the 2-px Nyquist period (f = 0.5) the envelope is still |sinc(0.5)| ~ 0.637 —
substantial contrast, not zero. The roll-off is a monotone suppression toward the
1-px limit, NOT a hard cliff at Nyquist.
"""
from __future__ import annotations

import numpy as np


def contrast_envelope(phase_2d: np.ndarray, fill_factor: float = 1.0) -> np.ndarray:
    """Local-frequency pixel-area contrast envelope of a phase map.

    Parameters
    ----------
    phase_2d : ndarray, shape (H, W)
        Phase map in radians (the exact phase the cos() will be evaluated at,
        carrier + any height-induced component already summed in).
    fill_factor : float, default 1.0
        Fraction of the pixel pitch that is light-sensitive (the box width, in
        pixels, over which intensity is integrated). 1.0 -> first contrast null
        at a 1-px fringe period. Must be > 0.

    Returns
    -------
    ndarray, shape (H, W), dtype float64
        Contrast multiplier in [0, 1]:  |sinc(fill_factor * f_local)|, with
        f_local = |grad(phase_2d)| / (2*pi) in cycles/pixel. Multiply the cos
        amplitude (B) by this to model area-averaging contrast loss.

    Notes
    -----
    Pure NumPy, headless. Reads nothing from the scale-bridge constants — the
    envelope is purely cycles/pixel.
    """
    if fill_factor <= 0.0:
        raise ValueError(f"fill_factor must be > 0; got {fill_factor}")

    phase = np.asarray(phase_2d, dtype=np.float64)
    if phase.ndim != 2:
        raise ValueError(f"phase_2d must be 2D (H, W); got shape {phase.shape}")

    # np.gradient returns [d/d(axis0=rows=y), d/d(axis1=cols=x)] on a unit grid
    # (pixel spacing = 1), so the components are already in rad/pixel.
    grad_y, grad_x = np.gradient(phase)
    grad_mag = np.hypot(grad_x, grad_y)               # rad/pixel
    f_local = grad_mag / (2.0 * np.pi)                # cycles/pixel

    # np.sinc(z) = sin(pi z)/(pi z): the pi is built in.
    return np.abs(np.sinc(fill_factor * f_local))
