#!/usr/bin/env python3
"""Multi-frequency vs single-frequency roughness comparison.

Applies all accuracy improvements:
  1. Temporal phase unwrapping (no spatial error propagation)
  2. Quality masking (exclude unreliable pixels near edges)
  3. Wider frequency spacing (256->64->16, coarsest has no wrapping)
  4. Morphological form removal (robust at step discontinuities)
"""

import argparse
import time
from pathlib import Path

import numpy as np

from micro_projection import SimulationSource, SimulationConfig, CalibrationParams
from micro_projection.patterns import generate_phase_sequence, compute_carrier_phase
from micro_projection.processing import (
    extract_phase,
    phase_to_height,
    remove_plane,
    separate_surface,
    compute_roughness_parameters,
    MultiFreqConfig,
    temporal_unwrap,
    generate_multifreq_patterns,
)
from micro_projection.core.datatypes import HeightMap, PhaseMap
from micro_projection.processing.unwrap import unwrap_phase

# Must match SimulationSource._compute_deformed_pattern height_scale
SIMULATION_HEIGHT_SCALE = 50.0

from multifreq_surfaces import (
    create_smooth_surface,
    create_simple_step_surface,
    create_complex_surface,
)
from multifreq_viz import visualize_3d, create_summary_figure


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

def run_single_frequency(source, resolution, period, n_steps):
    """Single-frequency: spatial unwrapping + plane removal."""
    patterns = generate_phase_sequence(resolution, period=period, n_steps=n_steps)
    frames = []
    for p in patterns:
        source.project_pattern(p)
        frames.append(source.capture_frame())

    phase_map = extract_phase(frames, n_steps=n_steps)
    phase_map.unwrapped = unwrap_phase(phase_map.wrapped, phase_map.quality)

    eq_wl = period / SIMULATION_HEIGHT_SCALE
    calib = CalibrationParams(equivalent_wavelength=eq_wl, pixel_pitch=1.0)
    height_map = phase_to_height(phase_map, calib)
    height_map = remove_plane(height_map)
    return height_map.data, phase_map.quality


def run_multi_frequency(source, resolution, periods, n_steps):
    """Multi-frequency with temporal unwrapping (no spatial propagation).

    Key fix: subtract carrier phase before temporal unwrapping so that
    the coarsest frequency is truly unambiguous (height-only phase).
    """
    all_patterns = generate_multifreq_patterns(resolution, periods, n_steps)

    # Capture and extract phase per frequency
    wrapped_phases = []
    quality_maps = []
    for i, freq_patterns in enumerate(all_patterns):
        frames = []
        for p in freq_patterns:
            source.project_pattern(p)
            frames.append(source.capture_frame())
        pm = extract_phase(frames, n_steps=n_steps)

        # Remove carrier phase so temporal unwrapping sees height-only phase.
        # PSA extracts -phi_true (negative sign convention), so:
        #   pm.wrapped = -(carrier + height_phase)
        # To isolate height_phase: -(pm.wrapped + carrier)
        carrier = compute_carrier_phase(resolution, periods[i])
        height_phase = -(pm.wrapped + carrier)
        # Re-wrap to [-pi, pi]
        height_phase = np.arctan2(np.sin(height_phase), np.cos(height_phase))

        wrapped_phases.append(height_phase)
        quality_maps.append(pm.quality)

    # Temporal unwrap on height-only phases (coarsest is now unambiguous)
    unwrapped, quality = temporal_unwrap(wrapped_phases, periods)

    # Convert phase to height using correct calibration
    finest_period = periods[-1]
    eq_wl = finest_period / SIMULATION_HEIGHT_SCALE
    combined_phase_map = PhaseMap(
        wrapped=unwrapped, unwrapped=unwrapped, quality=quality,
    )
    calib = CalibrationParams(equivalent_wavelength=eq_wl, pixel_pitch=1.0)
    height_map = phase_to_height(combined_phase_map, calib)
    return height_map.data, quality


# ---------------------------------------------------------------------------
# Roughness analysis
# ---------------------------------------------------------------------------

def extract_roughness(recovered, cutoff, method="gaussian"):
    """Separate form/roughness from recovered surface (properly calibrated)."""
    hm = HeightMap(data=recovered, unit="um", pixel_pitch=1.0, equivalent_wavelength=1.0)
    analysis = separate_surface(hm, cutoff_wavelength=cutoff, method=method)
    return analysis.finish.data


def apply_quality_mask(roughness, quality, threshold=0.5):
    """NaN-out pixels where quality is below threshold."""
    masked = roughness.copy()
    masked[quality < threshold] = np.nan
    return masked


def remove_outliers(roughness, sigma=5.0):
    """NaN-out isolated outlier pixels in roughness (measurement artifacts).

    At sharp discontinuities, temporal unwrapping can produce isolated spikes
    that don't represent real roughness. These outliers are identified as
    pixels exceeding sigma * robust_std from the median.
    """
    valid = roughness[~np.isnan(roughness)]
    if len(valid) == 0:
        return roughness
    median = np.median(valid)
    mad = np.median(np.abs(valid - median))
    robust_std = 1.4826 * mad  # MAD to std conversion for normal distribution
    limit = sigma * robust_std
    cleaned = roughness.copy()
    cleaned[np.abs(roughness - median) > limit] = np.nan
    return cleaned


def roughness_error(rec_roughness, true_roughness):
    """Compare roughness parameters. Ignores NaN pixels (masked)."""
    rec_hm = HeightMap(data=rec_roughness, unit="um",
                       pixel_pitch=1.0, equivalent_wavelength=1.0)
    true_hm = HeightMap(data=true_roughness, unit="um",
                        pixel_pitch=1.0, equivalent_wavelength=1.0)
    rec_params = compute_roughness_parameters(rec_hm)
    true_params = compute_roughness_parameters(true_hm)

    errors = {}
    for key in ("Sa", "Sq", "Sz"):
        tv = true_params[key]
        rv = rec_params[key]
        errors[f"{key}_true"] = tv
        errors[f"{key}_recovered"] = rv
        errors[f"{key}_error_pct"] = abs(rv - tv) / (tv + 1e-12) * 100
    errors["roughness_map"] = rec_roughness
    return errors


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_test(form, roughness, combined, name, desc, resolution,
             n_steps, noise, single_period, multi_periods,
             cutoff, form_method, output_dir):
    """Run comparison with all improvements applied."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"{'='*60}")
    print(f"\n  Surface: {desc}")
    print(f"  Height range: {combined.min():.4f} to {combined.max():.4f}")
    true_sa = np.mean(np.abs(roughness - roughness.mean()))
    print(f"  True roughness Sa: {true_sa:.6f}")

    config = SimulationConfig(resolution=resolution, noise_level=noise)
    source = SimulationSource(config)
    source.set_surface(combined)

    # --- Single-frequency ---
    print(f"\n  Single-freq (period={single_period})...")
    single_height, single_qual = run_single_frequency(
        source, resolution, single_period, n_steps)

    # --- Multi-frequency (temporal unwrap) ---
    print(f"  Multi-freq temporal (periods={multi_periods})...")
    multi_height, multi_qual = run_multi_frequency(
        source, resolution, multi_periods, n_steps)

    # --- Form/roughness separation (morphological or gaussian) ---
    print(f"  Separating form/roughness (method={form_method}, cutoff={cutoff})...")
    single_rough = extract_roughness(single_height, cutoff, form_method)
    multi_rough = extract_roughness(multi_height, cutoff, form_method)

    # --- Quality masking + outlier removal ---
    quality_threshold = 0.5
    print(f"  Applying quality mask (threshold={quality_threshold}) + outlier removal...")
    multi_rough_masked = apply_quality_mask(multi_rough, multi_qual, threshold=quality_threshold)
    multi_rough_masked = remove_outliers(multi_rough_masked)

    # Mask ground truth the same way for fair comparison
    true_rough_masked = roughness.copy()
    true_rough_masked[multi_qual < quality_threshold] = np.nan
    true_rough_masked[np.isnan(multi_rough_masked)] = np.nan

    single_err = roughness_error(single_rough, roughness)
    multi_err = roughness_error(multi_rough, roughness)
    multi_masked_err = roughness_error(multi_rough_masked, true_rough_masked)

    print(f"\n  Roughness comparison:")
    hdr = f"    {'Param':<6} {'True':>10} {'Single':>10} {'Multi':>10} {'M+Mask':>10}  {'S.Err%':>7} {'M.Err%':>7} {'MM.Err%':>7}"
    print(hdr)
    print(f"    {'-'*76}")
    for key in ("Sa", "Sq", "Sz"):
        tv = single_err[f"{key}_true"]
        sv = single_err[f"{key}_recovered"]
        mv = multi_err[f"{key}_recovered"]
        mmv = multi_masked_err[f"{key}_recovered"]
        se = single_err[f"{key}_error_pct"]
        me = multi_err[f"{key}_error_pct"]
        mme = multi_masked_err[f"{key}_error_pct"]
        print(f"    {key:<6} {tv:>10.6f} {sv:>10.6f} {mv:>10.6f} {mmv:>10.6f}  {se:>6.1f}% {me:>6.1f}% {mme:>6.1f}%")

    print(f"\n  Creating 3D visualization...")
    visualize_3d(combined, roughness, single_rough, multi_rough_masked,
                 single_err, multi_masked_err, output_dir / name)

    return {
        "name": name,
        "desc": desc,
        "single_Sa": single_err["Sa_error_pct"],
        "multi_Sa": multi_err["Sa_error_pct"],
        "masked_Sa": multi_masked_err["Sa_error_pct"],
        "single_Sq": single_err["Sq_error_pct"],
        "multi_Sq": multi_err["Sq_error_pct"],
        "masked_Sq": multi_masked_err["Sq_error_pct"],
        "single_Sz": single_err["Sz_error_pct"],
        "multi_Sz": multi_err["Sz_error_pct"],
        "masked_Sz": multi_masked_err["Sz_error_pct"],
        # Arrays for summary figure
        "surface": combined,
        "true_roughness": roughness,
        "single_roughness": single_rough,
        "multi_roughness": multi_rough_masked,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Multi-freq roughness comparison with all improvements")
    parser.add_argument("-o", "--output", default="output")
    parser.add_argument("-r", "--resolution", type=int, default=512)
    parser.add_argument("-n", "--n-steps", type=int, default=12)
    parser.add_argument("--noise", type=float, default=0.005)
    parser.add_argument("--cutoff", type=float, default=50.0)
    parser.add_argument("--form-method", default="morphological",
                        choices=["gaussian", "morphological", "butterworth"])
    args = parser.parse_args()

    print("=" * 60)
    print("IMPROVED Multi-Freq vs Single-Freq: ROUGHNESS Comparison")
    print("=" * 60)
    print(f"\nImprovements applied:")
    print(f"  1. Temporal phase unwrapping (no spatial propagation)")
    print(f"  2. Quality masking (exclude unreliable edge pixels)")
    print(f"  3. Wider frequency spacing [256, 64, 16]")
    print(f"  4. {args.form_method} form removal")
    print(f"  5. {args.n_steps} phase steps (higher SNR)")

    total_start = time.time()
    resolution = (args.resolution, args.resolution)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    single_period = 16
    multi_periods = [256, 64, 16]  # Wider spacing - coarsest has no wrapping

    surfaces = [
        ("smooth", "Smooth dome (CONTROL)", create_smooth_surface(resolution)),
        ("simple_step", "Single step + roughness", create_simple_step_surface(resolution)),
        ("complex", "Steps, pillar, pit + roughness", create_complex_surface(resolution)),
    ]

    results = []
    for name, desc, (form, roughness, combined) in surfaces:
        results.append(run_test(
            form, roughness, combined, name, desc,
            resolution, args.n_steps, args.noise,
            single_period, multi_periods,
            args.cutoff, args.form_method, output_dir,
        ))

    # Summary
    print(f"\n{'='*60}")
    print("ROUGHNESS ACCURACY SUMMARY")
    print("=" * 60)
    print(f"\n{'Surface':<15} {'Sa(S)':>8} {'Sa(M)':>8} {'Sa(M+Q)':>8}  "
          f"{'Sq(S)':>8} {'Sq(M)':>8} {'Sq(M+Q)':>8}  "
          f"{'Sz(S)':>8} {'Sz(M)':>8} {'Sz(M+Q)':>8}")
    print("-" * 100)
    for r in results:
        print(f"{r['name']:<15} "
              f"{r['single_Sa']:>7.1f}% {r['multi_Sa']:>7.1f}% {r['masked_Sa']:>7.1f}%  "
              f"{r['single_Sq']:>7.1f}% {r['multi_Sq']:>7.1f}% {r['masked_Sq']:>7.1f}%  "
              f"{r['single_Sz']:>7.1f}% {r['multi_Sz']:>7.1f}% {r['masked_Sz']:>7.1f}%")
    print(f"\n(S)=Single  (M)=Multi+temporal  (M+Q)=Multi+temporal+quality mask")
    print(f"Lower % = better roughness recovery\n")

    # Generate combined summary figure
    print("Creating summary illustration...")
    create_summary_figure(results, output_dir / "summary.png")

    print(f"Total time: {time.time() - total_start:.2f}s")


if __name__ == "__main__":
    main()
