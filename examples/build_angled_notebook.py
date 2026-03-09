"""Build the angled projection notebook programmatically."""
import json

cells = []

def md(cell_id, source):
    cells.append({
        "cell_type": "markdown",
        "id": cell_id,
        "metadata": {},
        "source": [line + "\n" for line in source.strip().split("\n")]
    })

def code(cell_id, source):
    cells.append({
        "cell_type": "code",
        "id": cell_id,
        "metadata": {},
        "source": [line + "\n" for line in source.strip().split("\n")],
        "outputs": [],
        "execution_count": None
    })

# --- Cell 0: Title ---
md("cell-0", r"""# Angled (Triangulation) Fringe Projection

In standard fringe projection profilometry, the projector and camera can be
**coaxial** (shared optical axis) or separated by a baseline distance
(**triangulation**). This notebook explores the triangulation geometry where
the projector is offset at angle $\theta = \arctan(d/L)$ from the camera.

## Geometry

| Parameter | Symbol | Description |
|-----------|--------|-------------|
| Baseline | $d$ | Camera-projector separation |
| Standoff | $L$ | Working distance to reference plane |
| Period | $P$ | Projected fringe pitch (pixels) |

**Phase sensitivity** (telecentric approximation):
$$\Delta\varphi = \frac{2\pi\, d\, h}{P\, L}$$

**Equivalent wavelength**: $\lambda_\mathrm{eq} = P L / d$

The triangulation angle controls two competing effects:
1. **Sensitivity** -- larger $\theta$ gives more phase shift per unit height
2. **Shadows** -- larger $\theta$ occludes more surface area from the projector

This tradeoff is fundamental to triangulation-based measurement system design.""")

# --- Cell 1: Imports ---
code("cell-1", r"""import sys
sys.path.insert(0, '.')
sys.path.insert(0, '..')

import numpy as np
import matplotlib.pyplot as plt

from micro_projection import SimulationSource, SimulationConfig, CalibrationParams
from micro_projection.sources.angled import AngledSimulationSource, AngledSimulationConfig
from micro_projection.patterns import generate_phase_sequence, compute_carrier_phase
from micro_projection.processing import (
    extract_phase, phase_to_height, remove_plane,
    separate_surface, compute_roughness_parameters,
    temporal_unwrap, generate_multifreq_patterns,
)
from micro_projection.core.datatypes import HeightMap, PhaseMap
from micro_projection.processing.unwrap import unwrap_phase
from multifreq_surfaces import create_complex_surface

%matplotlib inline
plt.rcParams['figure.dpi'] = 120""")

# --- Cell 2: Parameters heading ---
md("cell-2", "## Parameters")

# --- Cell 3: Parameters ---
code("cell-3", r"""RESOLUTION = (512, 512)
N_STEPS = 12
NOISE = 0.005
PERIODS = [256, 64, 16]   # coarse -> fine

# Triangulation geometry
BASELINE = 200.0        # camera-projector separation (d)
STANDOFF = 500.0        # working distance (L)
SURFACE_SCALE = 50.0    # scale surface heights for triangulation sensitivity

# Derived
theta_deg = np.degrees(np.arctan2(BASELINE, STANDOFF))
print(f'Triangulation angle: {theta_deg:.1f}\u00b0')
print(f'd/L = {BASELINE/STANDOFF:.3f}')
for P in PERIODS:
    eq_wl = P * STANDOFF / BASELINE
    print(f'  P={P:>3d}: \u03bb_eq = {eq_wl:.1f}')

# Roughness pipeline
CUTOFF = 50.0
FORM_METHOD = 'morphological'
QUALITY_THRESHOLD = 0.3""")

# --- Cell 4: Test surface heading ---
md("cell-4", r"""## Test Surface

We reuse the complex surface from the multi-frequency notebook, scaled by a
factor to produce height variations appropriate for triangulation measurement.
Triangulation FPP typically measures features in the tens-to-hundreds of
micrometres range, whereas the original surface heights (~1 unit) are tuned
for the coaxial model's artificial sensitivity scale.""")

# --- Cell 5: Create surface ---
code("cell-5", r"""form_orig, roughness_orig, combined_orig = create_complex_surface(RESOLUTION)

# Scale for triangulation sensitivity
form = form_orig * SURFACE_SCALE
roughness = roughness_orig * SURFACE_SCALE
combined = combined_orig * SURFACE_SCALE

fig, axes = plt.subplots(1, 3, figsize=(14, 4))

im0 = axes[0].imshow(form, cmap='terrain')
axes[0].set_title('Form (macro shape)')
plt.colorbar(im0, ax=axes[0], fraction=0.046)

im1 = axes[1].imshow(roughness, cmap='coolwarm')
axes[1].set_title(f'Roughness (\u00d7{SURFACE_SCALE:.0f})')
plt.colorbar(im1, ax=axes[1], fraction=0.046)

im2 = axes[2].imshow(combined, cmap='terrain')
axes[2].set_title('Combined surface')
plt.colorbar(im2, ax=axes[2], fraction=0.046)

for ax in axes:
    ax.set_xticks([]); ax.set_yticks([])
plt.tight_layout()
plt.show()

true_sa = np.mean(np.abs(roughness - roughness.mean()))
print(f'Height range: {combined.min():.1f} to {combined.max():.1f}')
print(f'True roughness Sa: {true_sa:.4f}')""")

# --- Cell 6: Coaxial vs Angled ---
md("cell-6", r"""## Coaxial vs Angled: Visual Comparison

The coaxial model applies a uniform phase shift proportional to height (no
geometry). The angled model creates a geometric phase shift that depends on
the triangulation angle, plus shadows where projector light is occluded by
surface features.""")

# --- Cell 7: Side-by-side ---
code("cell-7", r"""# Coaxial source with original (unscaled) surface
coax_source = SimulationSource(SimulationConfig(resolution=RESOLUTION, noise_level=NOISE))
coax_source.set_surface(combined_orig)

# Angled source with scaled surface
angled_cfg = AngledSimulationConfig(
    baseline=BASELINE, standoff_distance=STANDOFF,
    telecentric=True, shadow_enabled=True,
)
angled_source = AngledSimulationSource(
    SimulationConfig(resolution=RESOLUTION, noise_level=NOISE), angled_cfg,
)
angled_source.set_surface(combined)

# Project finest fringe pattern (first step only, for visualization)
pattern = generate_phase_sequence(RESOLUTION, period=PERIODS[-1], n_steps=1)[0]
coax_source.project_pattern(pattern)
angled_source.project_pattern(pattern)

coax_frame = coax_source.capture_frame()
angled_frame = angled_source.capture_frame()
shadow_mask = angled_source.get_shadow_mask()

fig, axes = plt.subplots(1, 3, figsize=(14, 4))

axes[0].imshow(coax_frame, cmap='gray', vmin=0, vmax=1)
axes[0].set_title('Coaxial (no shadows)')

axes[1].imshow(angled_frame, cmap='gray', vmin=0, vmax=1)
axes[1].set_title(f'Angled (\u03b8={theta_deg:.1f}\u00b0)')

axes[2].imshow(shadow_mask, cmap='Reds', vmin=0, vmax=1)
axes[2].set_title(f'Shadow mask ({shadow_mask.mean()*100:.1f}% shadowed)')

for ax in axes:
    ax.set_xticks([]); ax.set_yticks([])
plt.tight_layout()
plt.show()""")

# --- Cell 8: Tradeoff heading ---
md("cell-8", r"""## Sensitivity-Shadow Tradeoff

Increasing the baseline improves phase sensitivity (smaller equivalent
wavelength) but also increases the shadow area. This is the fundamental
design tradeoff in triangulation-based fringe projection.""")

# --- Cell 9: Sweep baselines ---
code("cell-9", r"""baselines = [10, 25, 50, 100, 200, 400]
sensitivities = []
shadow_fractions = []

for d in baselines:
    eq_wl = PERIODS[-1] * STANDOFF / d
    sensitivities.append(1.0 / eq_wl)

    ac = AngledSimulationConfig(baseline=d, standoff_distance=STANDOFF,
                                telecentric=True, shadow_enabled=True)
    src = AngledSimulationSource(SimulationConfig(resolution=RESOLUTION), ac)
    src.set_surface(combined)
    shadow_fractions.append(src.get_shadow_mask().mean() * 100)

fig, ax1 = plt.subplots(figsize=(8, 5))

color1 = '#1f77b4'
ax1.set_xlabel('Baseline d')
ax1.set_ylabel('Phase sensitivity (1/\u03bb_eq)', color=color1)
ax1.plot(baselines, sensitivities, 'o-', color=color1, linewidth=2, markersize=8)
ax1.tick_params(axis='y', labelcolor=color1)

ax2 = ax1.twinx()
color2 = '#d62728'
ax2.set_ylabel('Shadow area (%)', color=color2)
ax2.plot(baselines, shadow_fractions, 's-', color=color2, linewidth=2, markersize=8)
ax2.tick_params(axis='y', labelcolor=color2)

ax1.set_title('Sensitivity vs Shadow Area')
ax1.grid(alpha=0.3)
fig.tight_layout()
plt.show()

for d, s, sf in zip(baselines, sensitivities, shadow_fractions):
    print(f'd={d:>4d}:  1/\u03bb_eq={s:.5f}  shadow={sf:.1f}%  \u03bb_eq={1/s:.1f}')""")

# --- Cell 10: Full pipeline heading ---
md("cell-10", r"""## Full Multi-Frequency Pipeline with Angled Projection

We run the same multi-frequency temporal unwrapping pipeline as the coaxial
notebook, but using the angled simulation source. Key differences:

1. Phase-to-height uses $\lambda_\mathrm{eq} = P L / d$ instead of $P / h_\mathrm{scale}$
2. Shadow pixels are masked out using the quality map
3. Carrier removal is identical (PSA sign convention is geometry-independent)""")

# --- Cell 11: Multi-freq capture ---
code("cell-11", r"""angled_source.set_surface(combined)
shadow_quality = angled_source.get_quality_map()

all_patterns = generate_multifreq_patterns(RESOLUTION, PERIODS, N_STEPS)
wrapped_phases = []
quality_maps = []

for i, freq_patterns in enumerate(all_patterns):
    freq_frames = []
    for p in freq_patterns:
        angled_source.project_pattern(p)
        freq_frames.append(angled_source.capture_frame())

    pm = extract_phase(freq_frames, n_steps=N_STEPS)

    # Remove carrier: height_phase = -(psa_output + carrier)
    carrier = compute_carrier_phase(RESOLUTION, PERIODS[i])
    height_phase = -(pm.wrapped + carrier)
    height_phase = np.arctan2(np.sin(height_phase), np.cos(height_phase))

    # Combine fringe quality with shadow quality
    combined_quality = pm.quality * shadow_quality

    wrapped_phases.append(height_phase)
    quality_maps.append(combined_quality)

print(f'Captured {sum(len(p) for p in all_patterns)} frames '
      f'across {len(PERIODS)} frequencies')
print(f'Shadow area: {(1 - shadow_quality.mean()) * 100:.1f}%')""")

# --- Cell 12: Temporal unwrap + height ---
code("cell-12", r"""multi_unwrapped, multi_quality = temporal_unwrap(wrapped_phases, PERIODS)

# Combine temporal quality with shadow quality
final_quality = multi_quality * shadow_quality

finest_period = PERIODS[-1]
eq_wl = finest_period * STANDOFF / BASELINE
print(f'Equivalent wavelength (finest): {eq_wl:.1f}')

combined_pm = PhaseMap(
    wrapped=multi_unwrapped, unwrapped=multi_unwrapped, quality=final_quality,
)
calib = CalibrationParams(equivalent_wavelength=eq_wl, pixel_pitch=1.0)
multi_height_map = phase_to_height(combined_pm, calib)
multi_height = multi_height_map.data

print(f'Recovered height range: {multi_height.min():.1f} to {multi_height.max():.1f}')
print(f'Ground truth range:     {combined.min():.1f} to {combined.max():.1f}')""")

# --- Cell 13: Display ---
code("cell-13", r"""fig, axes = plt.subplots(2, 2, figsize=(12, 10))

im0 = axes[0, 0].imshow(multi_unwrapped, cmap='viridis')
axes[0, 0].set_title('Unwrapped Phase')
plt.colorbar(im0, ax=axes[0, 0], fraction=0.046, label='rad')

im1 = axes[0, 1].imshow(final_quality, cmap='viridis', vmin=0, vmax=1)
axes[0, 1].set_title('Combined Quality (fringe \u00d7 shadow)')
plt.colorbar(im1, ax=axes[0, 1], fraction=0.046)

im2 = axes[1, 0].imshow(multi_height, cmap='terrain')
axes[1, 0].set_title('Recovered Height')
plt.colorbar(im2, ax=axes[1, 0], fraction=0.046)

# Shadow overlay on height map
height_display = multi_height.copy()
height_display[shadow_mask] = np.nan
im3 = axes[1, 1].imshow(height_display, cmap='terrain')
axes[1, 1].set_title('Height with Shadow Overlay')
plt.colorbar(im3, ax=axes[1, 1], fraction=0.046)

for ax in axes.flat:
    ax.set_xticks([]); ax.set_yticks([])
plt.tight_layout()
plt.show()""")

# --- Cell 14: Error heatmap heading ---
md("cell-14", r"""## Reconstruction Error

Error heatmap comparing the angled reconstruction against the ground truth.
Shadowed regions are excluded from the comparison.""")

# --- Cell 15: Error heatmap ---
code("cell-15", r"""error = multi_height - combined
error[shadow_mask] = np.nan

elim = np.nanpercentile(np.abs(error), 99)

fig, ax = plt.subplots(figsize=(8, 6))
im = ax.imshow(error, cmap='RdBu_r', vmin=-elim, vmax=elim)
ax.set_title('Reconstruction Error (angled \u2212 truth)')
plt.colorbar(im, ax=ax, fraction=0.046)
ax.set_xticks([]); ax.set_yticks([])
plt.tight_layout()
plt.show()

valid = error[~np.isnan(error)]
print(f'MAE:      {np.mean(np.abs(valid)):.4f}')
print(f'Max|err|: {np.max(np.abs(valid)):.4f}')
print(f'Valid pixels: {len(valid):,} / {error.size:,} '
      f'({100 * len(valid) / error.size:.1f}%)')""")

# --- Cell 16: Roughness heading ---
md("cell-16", r"""## Roughness Comparison

Extract roughness from the angled reconstruction using morphological form
removal. Quality masking excludes shadowed and low-quality pixels, and
MAD-based outlier removal cleans residual spikes.""")

# --- Cell 17: Roughness ---
code("cell-17", r"""def extract_roughness_from_height(height_data, cutoff, method):
    hm = HeightMap(data=height_data, unit='um', pixel_pitch=1.0,
                   equivalent_wavelength=1.0)
    analysis = separate_surface(hm, cutoff_wavelength=cutoff, method=method)
    return analysis.finish.data

def apply_quality_mask(rough, quality, threshold):
    masked = rough.copy()
    masked[quality < threshold] = np.nan
    return masked

def remove_outliers(rough, sigma=5.0):
    valid = rough[~np.isnan(rough)]
    if len(valid) == 0:
        return rough
    median = np.median(valid)
    mad = np.median(np.abs(valid - median))
    robust_std = 1.4826 * mad
    cleaned = rough.copy()
    cleaned[np.abs(rough - median) > sigma * robust_std] = np.nan
    return cleaned

rec_rough = extract_roughness_from_height(multi_height, CUTOFF, FORM_METHOD)
rec_rough_masked = apply_quality_mask(rec_rough, final_quality, QUALITY_THRESHOLD)
rec_rough_masked = remove_outliers(rec_rough_masked)

# Ground truth masked identically
true_rough_masked = roughness.copy()
true_rough_masked[final_quality < QUALITY_THRESHOLD] = np.nan
true_rough_masked[np.isnan(rec_rough_masked)] = np.nan

def roughness_params(data):
    hm = HeightMap(data=data, unit='um', pixel_pitch=1.0,
                   equivalent_wavelength=1.0)
    return compute_roughness_parameters(hm)

true_p = roughness_params(true_rough_masked)
rec_p = roughness_params(rec_rough_masked)

print(f'{"Param":<6} {"True":>10} {"Angled":>10} {"Error%":>8}')
print('-' * 40)
for key in ('Sa', 'Sq', 'Sz'):
    tv, rv = true_p[key], rec_p[key]
    err = abs(rv - tv) / (tv + 1e-12) * 100
    print(f'{key:<6} {tv:>10.4f} {rv:>10.4f} {err:>7.1f}%')

n_masked = np.isnan(rec_rough_masked).sum()
print(f'\nMasked pixels: {n_masked:,} / {rec_rough_masked.size:,} '
      f'({100 * n_masked / rec_rough_masked.size:.1f}%)')""")

# --- Cell 18: Telecentric vs perspective ---
md("cell-18", r"""## Telecentric vs Perspective Approximation

The telecentric (linear) model assumes $h \ll L$:
$$\Delta\varphi = \frac{2\pi\, d\, h}{P\, L}$$

The perspective model accounts for height-dependent effective distance:
$$\Delta\varphi = \frac{2\pi\, d\, h}{P\, (L - h)}$$

The difference grows as $h/L$ increases. We compare both on a tall surface
where $h$ is a significant fraction of $L$.""")

# --- Cell 19: Telecentric vs perspective code ---
code("cell-19", r"""# Use a taller surface to amplify the perspective effect
tall_scale = 200.0
combined_tall = combined_orig * tall_scale
print(f'Max height: {combined_tall.max():.1f}  (h/L = {combined_tall.max() / STANDOFF:.3f})')

# No noise, no shadows -- isolate the telecentric/perspective difference
sim_cfg = SimulationConfig(resolution=RESOLUTION, noise_level=0)

tele_source = AngledSimulationSource(sim_cfg, AngledSimulationConfig(
    baseline=BASELINE, standoff_distance=STANDOFF,
    telecentric=True, shadow_enabled=False))
tele_source.set_surface(combined_tall)

persp_source = AngledSimulationSource(sim_cfg, AngledSimulationConfig(
    baseline=BASELINE, standoff_distance=STANDOFF,
    telecentric=False, shadow_enabled=False))
persp_source.set_surface(combined_tall)

# Capture at finest frequency
patterns_finest = generate_phase_sequence(RESOLUTION, period=PERIODS[-1], n_steps=N_STEPS)
tele_frames, persp_frames = [], []
for p in patterns_finest:
    tele_source.project_pattern(p)
    tele_frames.append(tele_source.capture_frame())
    persp_source.project_pattern(p)
    persp_frames.append(persp_source.capture_frame())

# Extract phase, remove carrier, unwrap
tele_pm = extract_phase(tele_frames, n_steps=N_STEPS)
persp_pm = extract_phase(persp_frames, n_steps=N_STEPS)

carrier = compute_carrier_phase(RESOLUTION, PERIODS[-1])
tele_hp = -(tele_pm.wrapped + carrier)
persp_hp = -(persp_pm.wrapped + carrier)

tele_unwrapped = unwrap_phase(tele_hp)
persp_unwrapped = unwrap_phase(persp_hp)

# Convert to height using telecentric calibration for both
eq_wl_cmp = PERIODS[-1] * STANDOFF / BASELINE
tele_height = (eq_wl_cmp / (2 * np.pi)) * tele_unwrapped
persp_height = (eq_wl_cmp / (2 * np.pi)) * persp_unwrapped

diff = persp_height - tele_height

fig, axes = plt.subplots(1, 3, figsize=(14, 4))

im0 = axes[0].imshow(tele_height, cmap='terrain')
axes[0].set_title('Telecentric reconstruction')
plt.colorbar(im0, ax=axes[0], fraction=0.046)

im1 = axes[1].imshow(persp_height, cmap='terrain')
axes[1].set_title('Perspective reconstruction')
plt.colorbar(im1, ax=axes[1], fraction=0.046)

dlim = np.percentile(np.abs(diff), 99)
im2 = axes[2].imshow(diff, cmap='RdBu_r', vmin=-dlim, vmax=dlim)
axes[2].set_title('Perspective \u2212 Telecentric')
plt.colorbar(im2, ax=axes[2], fraction=0.046)

for ax in axes:
    ax.set_xticks([]); ax.set_yticks([])
plt.tight_layout()
plt.show()

print(f'Max |difference|: {np.max(np.abs(diff)):.4f}')
print(f'Mean |difference|: {np.mean(np.abs(diff)):.4f}')
print(f'Relative to height range: '
      f'{np.max(np.abs(diff)) / (combined_tall.max() - combined_tall.min()) * 100:.2f}%')""")

# --- Cell 20: Summary ---
md("cell-20", r"""## Key Takeaways

1. **Triangulation geometry** introduces a physical sensitivity $d/L$ that
   replaces the coaxial model's artificial height scale.

2. **Shadows** are an inherent consequence of off-axis illumination. They
   grow with baseline but are handled by quality masking in the pipeline.

3. **Sensitivity-shadow tradeoff**: increasing baseline improves measurement
   precision but reduces the usable surface area. System design must balance
   both.

4. **Telecentric vs perspective**: for $h \ll L$ the linear approximation is
   excellent. Perspective corrections matter when surface heights approach a
   significant fraction of the standoff distance.

5. The existing multi-frequency temporal unwrapping pipeline (carrier removal,
   PSA, temporal unwrap) works unchanged -- only the phase-to-height
   calibration constant changes.""")

# --- Assemble notebook ---
notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3"
        },
        "language_info": {
            "name": "python",
            "version": "3.12.0"
        }
    },
    "nbformat": 4,
    "nbformat_minor": 5
}

# Fix: remove trailing newline from last line of each cell's source
for cell in notebook["cells"]:
    if cell["source"]:
        cell["source"][-1] = cell["source"][-1].rstrip("\n")

with open("examples/angled_projection_notebook.ipynb", "w", encoding="utf-8") as f:
    json.dump(notebook, f, indent=1, ensure_ascii=False)

print(f"Created notebook with {len(cells)} cells")
