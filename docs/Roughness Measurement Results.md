---
tags: [roughness, metrology, simulation, surface-measurement, iso-25178]
---

**Date:** 2026-01-26

---

## Overview

Simulation demonstrating surface roughness measurement using fringe projection profilometry. The system separates form (h1) from roughness (h2) and computes ISO 25178 roughness parameters.

---

## Test Configuration

| Parameter | Value |
|-----------|-------|
| Resolution | 512 x 512 pixels |
| Phase-shifting steps | 8 |
| Fringe period | 64 pixels |
| Noise level | 0.003 (Gaussian) |
| Cutoff wavelength | 30 pixels |
| Filter method | Gaussian low-pass |

### Test Surface Components

- **Form (h1):** Gaussian dome, amplitude = 0.1
- **Roughness (h2):** Random noise ($\sigma$ = 0.005) + periodic texture (amplitude = 0.002)

---

## Roughness Parameters Comparison

| Parameter | Description | Input | Recovered | Error |
|-----------|-------------|-------|-----------|-------|
| $S_a$ | Arithmetical mean height | 0.004012 | 0.004034 | 0.53% |
| $S_q$ | Root mean square height | 0.005029 | 0.005055 | 0.52% |
| $S_p$ | Maximum peak height | 0.021841 | 0.022332 | 2.25% |
| $S_v$ | Maximum valley depth | 0.022752 | 0.022443 | 1.36% |
| $S_z$ | Maximum height ($S_p + S_v$) | 0.044593 | 0.044775 | 0.41% |
| $S_{sk}$ | Skewness | -0.006173 | -0.005858 | 5.11% |
| $S_{ku}$ | Kurtosis | 2.996897 | 2.996160 | 0.02% |

---

## Error Analysis

### Error Sources in Simulation

| Source | Contribution | Notes |
|--------|--------------|-------|
| Sensor noise | ~0.35% | Dominant factor, Gaussian noise added to frames |
| Filter rolloff | ~0.10% | Gaussian filter has gradual transition, not brick-wall |
| Phase quantization | ~0.02% | 8 steps = $\pi/4$ resolution |
| Discretization | ~0.01% | Pixel sampling of continuous surface |

### Noise Impact Test

| Noise Level | $S_a$ Error | $S_q$ Error |
|-------------|-------------|-------------|
| 0.003 (realistic) | 0.48% | 0.47% |
| 0.0 (ideal) | 0.13% | 0.13% |

**Key Finding:** Noise contributes approximately 3x more error than algorithmic sources combined.

---

## Filtering Theory

The surface separation uses the relationship:

$$H = h_1 + h_2$$

Where:
- $H$ = Total measured height
- $h_1$ = Form/waviness (low-frequency)
- $h_2$ = Roughness/finish (high-frequency)

### Gaussian Filter Transfer Function

The cutoff wavelength $\lambda_c$ relates to Gaussian sigma by:

$$\sigma = \frac{\lambda_c}{2\pi}$$

The filter response at cutoff is -3dB (50% amplitude), meaning some energy from both form and roughness appears in the opposite component near the cutoff frequency.

---

## Conclusions

1. **High Accuracy:** The system achieves <1% error for primary roughness parameters ($S_a$, $S_q$, $S_z$) even with realistic noise levels.

2. **Noise Dominant:** Sensor noise is the primary error source (~70% of total error).

3. **Robust Separation:** The Gaussian filtering effectively separates form from roughness despite imperfect frequency response.

4. **Practical Viability:** Results demonstrate the fringe projection method is suitable for quantitative roughness measurement.

---

## References

- ISO 25178: Geometrical product specifications - Surface texture: Areal
- See also: [[Fringe Projection System - Complete Analysis]]

---
