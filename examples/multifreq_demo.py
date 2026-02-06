#!/usr/bin/env python3
"""Multi-frequency vs single-frequency roughness comparison.

Measures with both approaches, separates form/roughness, then compares
how well each recovers the ROUGHNESS (Sa, Sq, Sz) against ground truth.
Unwrapping errors from single-frequency leak into roughness after form removal.
"""

import argparse
import time
from pathlib import Path

import numpy as np

from micro_projection import SimulationSource, SimulationConfig, CalibrationParams
from micro_projection.patterns import generate_phase_sequence
from micro_projection.processing import (
    extract_phase,
    unwrap_phase,
    phase_to_height,
    remove_plane,
    separate_surface,
    compute_roughness_parameters,
    MultiFreqConfig,
    process_multifreq,
    generate_multifreq_patterns,
)
from micro_projection.core.datatypes import HeightMap, PhaseMap

from multifreq_surfaces import (
    create_smooth_surface,
    create_simple_step_surface,
    create_challenging_surface,
)
from multifreq_viz import visualize_3d


# ---------------------------------------------------------------------------
# Measurement helpers
# ---------------------------------------------------------------------------

def run_single_frequency(source, resolution, period, n_steps):
    """Run single-frequency measurement, return recovered height data."""
    patterns = generate_phase_sequence(resolution, period=period, n_steps=n_steps)
    frames = []
    for p in patterns:
        source.project_pattern(p)
        frames.append(source.capture_frame())

    phase_map = extract_phase(frames, n_steps=n_steps)
    phase_map.unwrapped = unwrap_phase(phase_map.wrapped, phase_map.quality)

    calib = CalibrationParams(equivalent_wavelength=1.0, pixel_pitch=1.0)
    height_map = phase_to_height(phase_map, calib)
    height_map = remove_plane(height_map)
    return -height_map.data


def run_multi_frequency(source, resolution, periods, n_steps):
    """Run multi-frequency measurement, return recovered height data."""
    config = MultiFreqConfig(periods=periods, n_steps=n_steps)
    all_patterns = generate_multifreq_patterns(resolution, periods, n_steps)

    frames_per_freq = []
    for freq_patterns in all_patterns:
        freq_frames = []
        for p in freq_patterns:
            source.project_pattern(p)
            freq_frames.append(source.capture_frame())
        frames_per_freq.append(freq_frames)

    result = process_multifreq(frames_per_freq, config)

    combined_phase_map = PhaseMap(
        wrapped=result.combined_phase,
        unwrapped=result.combined_phase,
        quality=result.quality,
    )

    calib = CalibrationParams(equivalent_wavelength=1.0, pixel_pitch=1.0)
    height_map = phase_to_height(combined_phase_map, calib)
    height_map = remove_plane(height_map)
    return -height_map.data


def normalize_to_reference(recovered, reference):
    """Normalize recovered surface to match reference scale and offset."""
    recovered = recovered - np.mean(recovered)
    reference_centered = reference - np.mean(reference)
    scale = np.std(reference_centered) / (np.std(recovered) + 1e-10)
    return recovered * scale


def extract_roughness(recovered, reference, cutoff=50.0):
    """Normalize recovered surface, then extract roughness via filtering."""
    normed = normalize_to_reference(recovered, reference)
    hm = HeightMap(data=normed, unit="um", pixel_pitch=1.0, equivalent_wavelength=1.0)
    analysis = separate_surface(hm, cutoff_wavelength=cutoff, method="gaussian")
    return analysis.finish.data


def roughness_error(recovered_roughness, true_roughness):
    """Compare recovered roughness to ground truth using ISO 25178 parameters."""
    rec_hm = HeightMap(data=recovered_roughness, unit="um",
                       pixel_pitch=1.0, equivalent_wavelength=1.0)
    true_hm = HeightMap(data=true_roughness, unit="um",
                        pixel_pitch=1.0, equivalent_wavelength=1.0)

    rec_params = compute_roughness_parameters(rec_hm)
    true_params = compute_roughness_parameters(true_hm)

    errors = {}
    for key in ("Sa", "Sq", "Sz"):
        true_val = true_params[key]
        rec_val = rec_params[key]
        errors[f"{key}_true"] = true_val
        errors[f"{key}_recovered"] = rec_val
        errors[f"{key}_error_pct"] = abs(rec_val - true_val) / (true_val + 1e-12) * 100

    errors["roughness_map"] = recovered_roughness
    return errors


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_test(form, roughness, combined, name, desc, resolution,
             n_steps, noise, single_period, multi_periods, cutoff, output_dir):
    """Run single vs multi-frequency comparison on one surface."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"{'='*60}")
    print(f"\n  Surface: {desc}")
    print(f"  Height range: {combined.min():.4f} to {combined.max():.4f}")
    print(f"  True roughness Sa: {np.mean(np.abs(roughness - roughness.mean())):.6f}")

    config = SimulationConfig(resolution=resolution, noise_level=noise)
    source = SimulationSource(config)
    source.set_surface(combined)

    print(f"\n  Running single-frequency (period={single_period})...")
    single_result = run_single_frequency(source, resolution, single_period, n_steps)

    print(f"  Running multi-frequency (periods={multi_periods})...")
    multi_result = run_multi_frequency(source, resolution, multi_periods, n_steps)

    print(f"  Separating form/roughness (cutoff={cutoff} px)...")
    single_rough = extract_roughness(single_result, combined, cutoff)
    multi_rough = extract_roughness(multi_result, combined, cutoff)

    single_err = roughness_error(single_rough, roughness)
    multi_err = roughness_error(multi_rough, roughness)

    print(f"\n  Roughness comparison:")
    print(f"    {'Param':<6} {'True':>10} {'Single':>10} {'Multi':>10}  {'S.Err%':>8} {'M.Err%':>8}")
    print(f"    {'-'*58}")
    for key in ("Sa", "Sq", "Sz"):
        tv = single_err[f"{key}_true"]
        sv = single_err[f"{key}_recovered"]
        mv = multi_err[f"{key}_recovered"]
        se = single_err[f"{key}_error_pct"]
        me = multi_err[f"{key}_error_pct"]
        print(f"    {key:<6} {tv:>10.6f} {sv:>10.6f} {mv:>10.6f}  {se:>7.1f}% {me:>7.1f}%")

    print(f"\n  Creating 3D visualization...")
    visualize_3d(roughness, single_rough, multi_rough,
                 single_err, multi_err, output_dir / name)

    return {
        "name": name,
        "single_Sa_err": single_err["Sa_error_pct"],
        "multi_Sa_err": multi_err["Sa_error_pct"],
        "single_Sq_err": single_err["Sq_error_pct"],
        "multi_Sq_err": multi_err["Sq_error_pct"],
        "single_Sz_err": single_err["Sz_error_pct"],
        "multi_Sz_err": multi_err["Sz_error_pct"],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Multi-frequency vs single-frequency roughness comparison"
    )
    parser.add_argument("-o", "--output", default="output")
    parser.add_argument("-r", "--resolution", type=int, default=512)
    parser.add_argument("-n", "--n-steps", type=int, default=8)
    parser.add_argument("--noise", type=float, default=0.005)
    parser.add_argument("--cutoff", type=float, default=50.0,
                        help="Form/roughness cutoff wavelength in pixels (default: 50)")
    args = parser.parse_args()

    print("=" * 60)
    print("Multi-Frequency vs Single-Frequency: ROUGHNESS Comparison")
    print("=" * 60)
    print("\nCompares roughness recovery (Sa, Sq, Sz) after form removal.")
    print("Unwrapping errors from single-freq leak into roughness.")

    total_start = time.time()
    resolution = (args.resolution, args.resolution)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    single_period = 16
    multi_periods = [128, 32, 16]

    surfaces = [
        ("smooth", "Smooth dome (CONTROL)", create_smooth_surface(resolution)),
        ("simple_step", "Single step + roughness", create_simple_step_surface(resolution)),
        ("challenging", "Steps, pillar, pit + roughness", create_challenging_surface(resolution)),
    ]

    results = []
    for name, desc, (form, roughness, combined) in surfaces:
        results.append(run_test(
            form, roughness, combined, name, desc,
            resolution, args.n_steps, args.noise,
            single_period, multi_periods, args.cutoff, output_dir,
        ))

    # Summary
    print(f"\n{'='*60}")
    print("ROUGHNESS ACCURACY SUMMARY")
    print("=" * 60)
    hdr = (f"{'Surface':<15} {'Sa err(S)':>10} {'Sa err(M)':>10}  "
           f"{'Sq err(S)':>10} {'Sq err(M)':>10}  "
           f"{'Sz err(S)':>10} {'Sz err(M)':>10}")
    print(f"\n{hdr}")
    print("-" * 85)
    for r in results:
        print(f"{r['name']:<15} "
              f"{r['single_Sa_err']:>9.1f}% {r['multi_Sa_err']:>9.1f}%  "
              f"{r['single_Sq_err']:>9.1f}% {r['multi_Sq_err']:>9.1f}%  "
              f"{r['single_Sz_err']:>9.1f}% {r['multi_Sz_err']:>9.1f}%")
    print(f"\n(S) = Single-frequency,  (M) = Multi-frequency")
    print(f"Lower % = better roughness recovery\n")
    print(f"Total time: {time.time() - total_start:.2f}s")


if __name__ == "__main__":
    main()
