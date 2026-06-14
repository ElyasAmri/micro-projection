---
tags: [fringe-projection, profilometry, phase-shifting, metrology, surface-measurement, telecentric-lenses, equivalent-wavelength, perspective-correction]
---

**Source:** Dr. Ayman Samara (asamara@hbku.edu.qa)

---

## Overview

In fringe projection, a grating is imaged onto a test surface using projection optics, then imaged back from a different angle onto a detector array. Fringes can also be created via interference between two plane waves inclined at a small angle.

---

## System Geometry

### Coordinate Systems

Three coordinate systems are used:
- **(x1, y1, z1)** - Grating coordinate system
- **(x2, y2, z2)** - Surface coordinate system
- **(x3, y3, z3)** - Detector array coordinate system

### Key Parameters

| Parameter  | Description                                  | Typical Value |
| ---------- | -------------------------------------------- | ------------- |
| $p$        | Grating period                               | 1 mm          |
| $\theta_1$ | Projection angle (lens L1 to surface normal) | ~15-20 deg    |
| $\theta_2$ | Viewing angle (lens L2 to surface normal)    | ~15-20 deg    |
| $a$        | Distance: grating to projection lens L1      | 110-480 mm    |
| $b$        | Distance: detector array to viewing lens L2  | 110-480 mm    |
| $l_p$      | Distance: center of L1 to surface origin     | ~80 mm        |
| $l_k$      | Distance: center of L2 to surface origin     | ~80 mm        |
| $M$        | System magnification ($M = l/b$)             | varies        |

### Symmetric System

For symmetric systems: $a = b$, $l_p = l_k = l$, $\theta_1 = \theta_2 = \theta$

---

## Core Equations

### Projection Arm Analysis

**Position on surface (x2) as function of grating position (x1):**

$$x_2 = x_2(x_1) = \frac{x_1 l_p}{a\cos\theta_1 - x_1\sin\theta_1}$$

**Fringe period on x2-axis:**

$$\lambda_{x2} = \frac{p l_p a \cos\theta_1}{(a\cos\theta_1 - x_1\sin\theta_1)^2}$$

### Viewing Arm Analysis

**Position on surface (x2) as function of detector position (x3):**

$$x_2 = x_2(x_3) = \frac{x_3 l_k}{b\cos\theta_2 + x_3\sin\theta_2}$$

**Fringe period on detector:**

$$\lambda_{x3} = \frac{\lambda_{x2} l_k a \cos\theta_2}{(l_k - x_2\sin\theta_2)^2}$$

### Symmetric System - Fringe Period on Detector

$$\lambda_{x3} = \frac{p(al\cos\theta)^2}{(la\cos\theta - 2lx_1\sin\theta)^2} = \frac{p}{\left(1 - \frac{2x_1\tan\theta}{a}\right)^2}$$

> **Important:** The fringe period is NOT constant - it varies with position $x_1$. This causes the **perspective effect**.

---

## Height Measurement

### Displacement Due to Object Height

For an object with height profile $h$ at position $x_2$:

**Displacement on camera plane:**

$$u_3 = h\frac{2lb\sin\theta}{(l - x_2\sin\theta)^2}$$

For symmetric system as function of $x_1$:

$$u_3 = h\frac{2\sin\theta}{M}\left(1 - \frac{2x_1\tan\theta}{a}\right)^{-1}$$

### Fringe Intensity Distribution

$$I = A + B\cos\left(\frac{2\pi}{\lambda_{x3}}[x_3 + u_3]\right)$$

As function of grating position $x_1$:

$$I = A + B\cos\left(\frac{2\pi}{p}\left[1 - \frac{2x_1\tan\theta}{a}\right] \times \left[x_1 + \frac{2\sin\theta}{M}h\right]\right)$$

This can be written as:

$$I = A + B\cos(\phi + \psi)$$

Where:
- **Carrier phase:** $\phi = \frac{2\pi x_1}{p}\left[1 - \frac{2x_1\tan\theta}{a}\right]$
- **Phase shift from height:** $\psi = \frac{2\pi}{p}\left[1 - \frac{2x_1\tan\theta}{a}\right]\frac{2\sin\theta}{M}h$

### Height Calculation

$$h = \frac{\lambda_{eq}}{2\pi}\psi$$

---

## Equivalent Wavelength

### General Formula

$$\lambda_{eq} = \frac{Mp}{2\sin\theta}\left[1 - \frac{2x_1\tan\theta}{a}\right]^{-1}$$

### For Telecentric Systems (constant)

$$\lambda_{eq} = \frac{Mp}{2\tan\theta}$$

### For Custom Grating Correction

$$\lambda_{eq} = \frac{Mp}{2\sin\theta}$$

> **Key Insight:** The equivalent wavelength is the conversion factor from phase to height. It can be determined by calibration using a standard step height artifact.

---

## Perspective Effect

### The Problem

When projecting onto a flat plane, the measured fringe period $\lambda_{x3}$ varies with position $x_1$. This makes a flat reference surface appear non-planar (cylindrical curvature).

### Simulation Parameters (Example)

- $l_p = l_k = 128$ mm
- $\theta_1 = \theta_2 = 20^\circ$
- $p = 1$ mm
- Field of view = 12 mm

### Impact

The curvature of the apparent non-planar surface **increases with increasing field of view**.

---

## Solutions for Perspective Effect

### Method 1: Telecentric Lenses

**Principle:** In telecentric systems, magnification is constant regardless of object distance. An aperture stop is placed at the rear principal focal plane of the lens.

**Key Property:** Chief rays are always parallel to the lens principal axis.

**Result:** Fringe period is constant over the entire field of view.

**Equations for Telecentric System:**

Fringe displacement on object plane:
$$U = h(\tan\theta_1 + \tan\theta_2)$$

Displacement on camera plane:
$$u = \frac{U}{M} = \frac{h(\tan\theta_1 + \tan\theta_2)}{M}$$

Phase shift:
$$\psi = \frac{2\pi}{p}u = \frac{2\pi h(\tan\theta_1 + \tan\theta_2)}{Mp}$$

Height calculation:
$$h = \lambda_{eq} \times \frac{\psi}{2\pi} = \frac{Mp}{\tan\theta_1 + \tan\theta_2} \times \frac{\psi}{2\pi}$$

For symmetric system ($\theta_1 = \theta_2 = \theta$):
$$h = \frac{Mp}{2\tan\theta} \times \frac{\psi}{2\pi}$$

### Method 2: Custom Pre-Deformed Grating

**Principle:** Project a grating with variable period $p_2(x_1)$ that compensates for perspective distortion.

**Variable Period Formula:**
$$p_2 = p \times \left(1 - \frac{2x_1\tan\theta}{a}\right)$$

**Resulting Intensity Distribution:**
$$I = A + B\cos\left(\frac{2\pi}{p} \times \left[x_1 + \frac{2\sin\theta}{M}h\right]\right)$$

**Phase shift due to height:**
$$\psi = \frac{2\pi}{p} \times \frac{2\sin\theta}{M}h$$

**Height calculation:**
$$h = \frac{\psi}{2\pi} \times \frac{Mp}{2\sin\theta} = \frac{\psi}{2\pi} \times \lambda_{eq}$$

---

## Phase Shifting Algorithm

### N-Step Phase Shifting

Standard algorithm with configurable steps (4, 5, 6, or 8 frames typical).

**Intensity equation for each frame:**
$$I_n = A + B\cos(\phi + \delta_n)$$

Where $\delta_n$ = phase shift for frame n (typically $\pi/2$ increments for 4-step)

**Phase extraction:**
$$\phi = \arctan\left(\frac{\sum I_n \sin(\delta_n)}{\sum I_n \cos(\delta_n)}\right)$$

### 8-Step Algorithm Details

- Each frame phase-shifted by $\pi/2$
- Matrix size: 640 x 480 x 8 pixels
- Resolution: 640 x 480 pixels per frame

---

## Software Implementation

### Basic Algorithm (projecting_function)

1. Define fringe period $p$ in millimeters
2. Create 640x480 intensity matrix: $I = 1 + \sin\left(\frac{2\pi}{p}x\right)$
3. Display fringe pattern on screen
4. Capture frame and store in 3D matrix
5. Apply phase shift (add $\pi/2$ to phase)
6. Repeat steps 3-5 until all frames captured

### Vision Software Settings

| Setting | Value | Notes |
|---------|-------|-------|
| Wavelength | 2 nm | Each fringe = 1 wave |
| FOV | 640 x 480 um | 1 um = 1 pixel |
| Phase Algorithm | 4/5/6/8 frames | Selectable |
| Phase Unwrapping | Enhanced2 | Best for complex interferograms |

---

## Waviness Filtering

### Surface Components

Total height profile:
$$H = h_1 + h_2$$

Where:
- $h_1$ = Low-frequency large form (waviness)
- $h_2$ = High-frequency surface finish (roughness)

### Dual-Frequency Measurement Approach

**Step 1: Measure Low-Frequency Profile ($h_1$)**

Project low-frequency fringes (large period $p_1$):
$$I = A + B\cos\left(\frac{2\pi}{p_1}\left[1 - \frac{2x_1\tan\theta}{a}\right] \times [x_1 + Kh_1]\right)$$

Where $K = \frac{2\sin\theta}{M}$

**Step 2: Filter Out Low-Frequency Profile**

Project custom grating with variable period $p_3(x_1)$:
$$\frac{1}{p_3(x_1)} = \frac{x_1}{p_1\left[1 - \frac{2x_1\tan\theta}{a}\right] \times [x_1 + Kh_1]}$$

**Step 3: Measure High-Frequency Profile ($h_2$)**

Multiply the correction phase $\phi_3$ by the frequency ratio:
- For 10x higher frequency: new phase = $10 \times \phi_3$

### Phase Correction Method

To generate corrected phase $\phi_2$ from measured phase $\phi_1$:
1. Subtract tilt from $\phi_1$
2. Multiply result by -1
3. Add tilt back

---

## Calibration

### Equivalent Wavelength Calibration

Use standard VLSI step height artifact with known height.

**Procedure:**
1. Measure phase map of step height
2. Calculate: $\lambda_{eq} = \frac{h_{known}}{\psi_{measured}/2\pi}$

### Lateral Calibration

Use lateral calibration artifact to determine pixel-to-micrometer conversion factor.

---

## Bias Correction Workflow

### Real-Time Bias Correction

**Step 1:** Project straight fringes (period $p_1$) onto flat reference surface

**Step 2:** Measure phase map $\phi_1$:
$$\phi_1 = \frac{2\pi}{p_1}\left[x_1 - \frac{2x_1^2\tan\theta}{ap_1}\right]$$

**Step 3:** Calculate corrected projection phase $\phi_2$:
$$\phi_2 = \frac{2\pi}{p_1}x_1 + \frac{2x_1^2\tan\theta}{ap_1}$$

(Same tilt, opposite curvature)

**Step 4:** Project corrected fringes onto test surface

**Step 5:** Extract height from measured phase:
$$H = \lambda_{eq} \times \phi_3$$

---

## Key Relationships Summary

| Quantity | Formula | Notes |
|----------|---------|-------|
| Height from phase | $h = \frac{\lambda_{eq}}{2\pi}\psi$ | Fundamental relationship |
| Equivalent wavelength (general) | $\lambda_{eq} = \frac{Mp}{2\sin\theta}\left[1 - \frac{2x_1\tan\theta}{a}\right]^{-1}$ | Position-dependent |
| Equivalent wavelength (telecentric) | $\lambda_{eq} = \frac{Mp}{2\tan\theta}$ | Constant |
| Equivalent wavelength (custom grating) | $\lambda_{eq} = \frac{Mp}{2\sin\theta}$ | Constant after correction |
| Phase sensitivity | $K = \frac{2\sin\theta}{M}$ | Height-to-phase factor |
| Perspective correction | $p_2 = p\left(1 - \frac{2x_1\tan\theta}{a}\right)$ | Variable grating period |

---

## References from Document

Key references cited: 17, 31, 34, 46, 49, 50, 71, 79-91

Topics covered:
- Telecentric lenses: refs 86-88
- Fringe projection theory: refs 31, 34, 17, 79-85
- Custom grating methods: refs 71, 89-91

---
