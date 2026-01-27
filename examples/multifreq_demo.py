#!/usr/bin/env python3
"""Multi-frequency fringe projection demonstration.

Creates a complex surface with features that challenge single-frequency
measurement, then compares single vs multi-frequency approaches.
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
    MultiFreqConfig,
    process_multifreq,
    generate_multifreq_patterns,
    compute_equivalent_period,
)


def create_complex_surface(resolution: tuple[int, int]) -> np.ndarray:
    """Create a complex surface with multiple challenging features.

    Features:
        - Large central plateau (step discontinuity)
        - Smaller raised features (bumps)
        - Sloped region
        - Fine surface texture
        - Depression/valley

    This surface is designed to challenge single-frequency measurement
    due to height variations spanning multiple fringe periods.
    """
    h, w = resolution
    y, x = np.mgrid[0:h, 0:w].astype(np.float64)
    cx, cy = w / 2, h / 2

    # Normalize to [-1, 1]
    x_norm = (x - cx) / cx
    y_norm = (y - cy) / cy
    r = np.sqrt(x_norm**2 + y_norm**2)

    surface = np.zeros((h, w), dtype=np.float64)

    # 1. Central raised plateau (large step - spans multiple fringes)
    plateau_mask = r < 0.3
    surface[plateau_mask] = 0.25

    # Smooth the plateau edges slightly
    from scipy import ndimage
    surface = ndimage.gaussian_filter(surface, sigma=3)

    # 2. Raised bump on the plateau
    bump1_r = np.sqrt((x_norm - 0.1)**2 + (y_norm + 0.05)**2)
    surface += 0.08 * np.exp(-50 * bump1_r**2)

    # 3. Another bump off the plateau
    bump2_r = np.sqrt((x_norm + 0.5)**2 + (y_norm - 0.3)**2)
    surface += 0.12 * np.exp(-30 * bump2_r**2)

    # 4. Sloped ramp region
    ramp_mask = (x_norm > 0.3) & (x_norm < 0.7) & (np.abs(y_norm) < 0.3)
    ramp_values = 0.15 * (x_norm - 0.3) / 0.4
    surface[ramp_mask] += ramp_values[ramp_mask]

    # 5. Depression/valley
    valley_r = np.sqrt((x_norm + 0.4)**2 + (y_norm + 0.5)**2)
    surface -= 0.1 * np.exp(-40 * valley_r**2)

    # 6. Fine periodic texture (high frequency detail)
    texture = 0.01 * np.sin(30 * np.pi * x_norm) * np.sin(30 * np.pi * y_norm)
    texture *= np.exp(-2 * r**2)  # Fade towards edges
    surface += texture

    # 7. Small step feature
    small_step_mask = (x_norm > -0.7) & (x_norm < -0.5) & (y_norm > 0.2) & (y_norm < 0.5)
    surface[small_step_mask] += 0.08

    # Normalize so minimum is 0
    surface = surface - surface.min()

    return surface


def create_challenging_surface(resolution: tuple[int, int]) -> np.ndarray:
    """Create a surface with discontinuities that cause phase unwrapping failures.

    This surface is specifically designed to show where multi-frequency
    outperforms single-frequency:
    - Sharp step discontinuities
    - Isolated tall features
    - Height range that causes multiple fringe wraps at fine period

    The key insight: fine period (16 pixels) with height_scale=50 causes
    one full wrap per 0.32 units of height. A 1.0 unit step = ~3 wraps,
    which single-frequency unwrapping cannot reliably resolve.
    """
    h, w = resolution
    y, x = np.mgrid[0:h, 0:w].astype(np.float64)
    cx, cy = w / 2, h / 2

    # Normalize to [-1, 1]
    x_norm = (x - cx) / cx
    y_norm = (y - cy) / cy

    surface = np.zeros((h, w), dtype=np.float64)

    # Base: gentle slope (no problem for either method)
    surface += 0.1 * x_norm

    # 1. Sharp step - height = 0.8 causes ~2.5 wraps at period=16
    # This is the "Goldilocks zone" - single-freq fails, multi-freq succeeds
    step_mask = (x_norm > -0.2) & (x_norm < 0.5) & (y_norm > -0.3) & (y_norm < 0.3)
    surface[step_mask] += 0.8

    # 2. Second step at different height
    step2_mask = (x_norm > 0.3) & (y_norm > 0.2)
    surface[step2_mask] += 0.5

    # 3. Isolated pillar - surrounded by low area, causes path-following to fail
    pillar_r = np.sqrt((x_norm + 0.5)**2 + (y_norm - 0.4)**2)
    pillar_mask = pillar_r < 0.1
    surface[pillar_mask] = 1.2

    # 4. Another isolated feature (bottom right)
    feature_r = np.sqrt((x_norm - 0.6)**2 + (y_norm + 0.5)**2)
    feature_mask = feature_r < 0.12
    surface[feature_mask] = 0.9

    # 5. Depression/pit in bottom left
    pit_r = np.sqrt((x_norm + 0.6)**2 + (y_norm + 0.5)**2)
    pit_mask = pit_r < 0.08
    surface[pit_mask] = -0.4

    # Very minimal smoothing - keep discontinuities sharp
    from scipy import ndimage
    surface = ndimage.gaussian_filter(surface, sigma=1.0)

    return surface


def create_simple_step_surface(resolution: tuple[int, int]) -> np.ndarray:
    """Create the SIMPLEST possible test case: a single step.

    Just one clean step from 0 to step_height.
    If multi-freq helps here, we know the algorithm is working correctly.
    """
    h, w = resolution
    y, x = np.mgrid[0:h, 0:w].astype(np.float64)
    cx, cy = w / 2, h / 2

    x_norm = (x - cx) / cx

    surface = np.zeros((h, w), dtype=np.float64)

    # Single step at x=0: left half = 0, right half = step_height
    # Height of 0.7 should cause ~2 fringe wraps at period=16
    step_height = 0.7
    surface[x_norm > 0] = step_height

    # Minimal smoothing for the edge (1-2 pixels)
    from scipy import ndimage
    surface = ndimage.gaussian_filter(surface, sigma=1.0)

    return surface


def create_smooth_surface(resolution: tuple[int, int]) -> np.ndarray:
    """Create a SMOOTH surface with NO discontinuities.

    Both methods should perform equally well on this surface.
    This verifies there's no bug favoring multi-frequency.
    """
    h, w = resolution
    y, x = np.mgrid[0:h, 0:w].astype(np.float64)
    cx, cy = w / 2, h / 2

    x_norm = (x - cx) / cx
    y_norm = (y - cy) / cy

    surface = np.zeros((h, w), dtype=np.float64)

    # Smooth dome/hill - no discontinuities
    r = np.sqrt(x_norm**2 + y_norm**2)
    surface = 0.5 * np.exp(-2 * r**2)

    # Add gentle slope
    surface += 0.1 * x_norm

    # Add smooth sinusoidal variation
    surface += 0.05 * np.sin(3 * np.pi * x_norm) * np.cos(3 * np.pi * y_norm)

    return surface


def run_single_frequency(
    source: SimulationSource,
    resolution: tuple[int, int],
    period: int,
    n_steps: int,
) -> tuple[np.ndarray, float]:
    """Run single-frequency measurement."""
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

    return -height_map.data, n_steps


def run_multi_frequency(
    source: SimulationSource,
    resolution: tuple[int, int],
    periods: list[int],
    n_steps: int,
) -> tuple[np.ndarray, int]:
    """Run multi-frequency measurement."""
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

    # Convert combined phase to height using phase_to_height
    # Create a PhaseMap-compatible object
    from micro_projection.core.datatypes import PhaseMap
    combined_phase_map = PhaseMap(
        wrapped=result.combined_phase,
        unwrapped=result.combined_phase,  # Already hierarchically unwrapped
        quality=result.quality,
    )

    calib = CalibrationParams(equivalent_wavelength=1.0, pixel_pitch=1.0)
    height_map = phase_to_height(combined_phase_map, calib)
    height_map = remove_plane(height_map)

    total_patterns = len(periods) * n_steps
    return -height_map.data, total_patterns


def normalize_to_reference(recovered: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Normalize recovered surface to match reference scale and offset."""
    recovered = recovered - np.mean(recovered)
    reference_centered = reference - np.mean(reference)

    scale = np.std(reference_centered) / (np.std(recovered) + 1e-10)
    return recovered * scale


def compute_error_metrics(recovered: np.ndarray, reference: np.ndarray) -> dict:
    """Compute error metrics between recovered and reference surfaces."""
    reference_centered = reference - np.mean(reference)
    recovered_centered = recovered - np.mean(recovered)

    # Scale recovered to match reference
    scale = np.std(reference_centered) / (np.std(recovered_centered) + 1e-10)
    recovered_scaled = recovered_centered * scale

    error = recovered_scaled - reference_centered

    return {
        "rms": np.sqrt(np.mean(error**2)),
        "max": np.abs(error).max(),
        "mean": np.mean(np.abs(error)),
        "error_map": error,
    }


def run_single_surface_test(
    surface: np.ndarray,
    surface_name: str,
    surface_description: str,
    resolution: tuple[int, int],
    n_steps: int,
    noise_level: float,
    single_period: int,
    multi_periods: list[int],
    output_dir: Path,
) -> dict:
    """Run single vs multi-frequency comparison on one surface."""
    print(f"\n{'='*60}")
    print(f"Testing: {surface_name}")
    print(f"{'='*60}")

    print(f"\n  Surface: {surface_description}")
    print(f"  Height range: {surface.min():.4f} to {surface.max():.4f}")

    # Setup simulation
    config = SimulationConfig(resolution=resolution, noise_level=noise_level)
    source = SimulationSource(config)
    source.set_surface(surface)

    # Single frequency measurement
    print(f"\n  Running single-frequency (period={single_period})...")
    single_result, _ = run_single_frequency(source, resolution, single_period, n_steps)

    # Multi-frequency measurement
    print(f"  Running multi-frequency (periods={multi_periods})...")
    multi_result, _ = run_multi_frequency(source, resolution, multi_periods, n_steps)

    # Compute metrics
    single_metrics = compute_error_metrics(single_result, surface)
    multi_metrics = compute_error_metrics(multi_result, surface)

    print(f"\n  Results:")
    print(f"    Single-freq RMS: {single_metrics['rms']:.4f}, Max: {single_metrics['max']:.4f}")
    print(f"    Multi-freq  RMS: {multi_metrics['rms']:.4f}, Max: {multi_metrics['max']:.4f}")

    if multi_metrics['rms'] < single_metrics['rms'] * 0.95:
        improvement = (1 - multi_metrics['rms'] / single_metrics['rms']) * 100
        print(f"    --> Multi-freq {improvement:.1f}% better")
    else:
        print(f"    --> Both methods equal (no discontinuities)")

    # Create visualizations
    print(f"\n  Creating visualizations...")

    # 3D visualization
    visualize_3d(
        surface, single_result, multi_result,
        single_metrics, multi_metrics,
        output_dir / surface_name,
    )

    return {
        "name": surface_name,
        "single_rms": single_metrics['rms'],
        "single_max": single_metrics['max'],
        "multi_rms": multi_metrics['rms'],
        "multi_max": multi_metrics['max'],
    }


def visualize_3d(
    surface: np.ndarray,
    single_result: np.ndarray,
    multi_result: np.ndarray,
    single_metrics: dict,
    multi_metrics: dict,
    output_dir: Path,
):
    """Create 3D PyVista visualization comparing single vs multi-frequency."""
    import pyvista as pv

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Normalize results for display
    surface_centered = surface - np.mean(surface)
    single_norm = normalize_to_reference(single_result, surface)
    multi_norm = normalize_to_reference(multi_result, surface)

    h, w = surface.shape

    # Create coordinate grids
    x = np.arange(w)
    y = np.arange(h)
    x_grid, y_grid = np.meshgrid(x, y)

    # Height scale for better visualization
    z_scale = 100.0

    def create_mesh(height_data, name):
        grid = pv.StructuredGrid(x_grid, y_grid, height_data * z_scale)
        grid[name] = height_data.flatten(order='F')
        return grid

    mesh_truth = create_mesh(surface_centered, "height")
    mesh_single = create_mesh(single_norm, "height")
    mesh_multi = create_mesh(multi_norm, "height")

    vmin, vmax = surface_centered.min(), surface_centered.max()

    # Setup plotter
    pv.global_theme.background = 'white'
    pv.global_theme.font.color = 'black'

    plotter = pv.Plotter(shape=(1, 3), off_screen=True, window_size=(1800, 600))

    plotter.subplot(0, 0)
    plotter.add_mesh(mesh_truth, scalars="height", cmap="viridis",
                     clim=[vmin, vmax], show_scalar_bar=False)
    plotter.add_text("Ground Truth", font_size=12, position="upper_edge")

    plotter.subplot(0, 1)
    plotter.add_mesh(mesh_single, scalars="height", cmap="viridis",
                     clim=[vmin, vmax], show_scalar_bar=False)
    plotter.add_text(f"Single Freq (RMS={single_metrics['rms']:.3f})",
                     font_size=12, position="upper_edge")

    plotter.subplot(0, 2)
    plotter.add_mesh(mesh_multi, scalars="height", cmap="viridis",
                     clim=[vmin, vmax], show_scalar_bar=False)
    plotter.add_text(f"Multi Freq (RMS={multi_metrics['rms']:.3f})",
                     font_size=12, position="upper_edge")

    plotter.link_views()
    plotter.camera_position = 'iso'
    plotter.camera.zoom(0.85)

    # Save static image
    output_path = output_dir / "comparison_3d.png"
    plotter.screenshot(str(output_path))
    print(f"    Saved: {output_path}")
    plotter.close()

    # Create animation
    plotter = pv.Plotter(shape=(1, 3), off_screen=True, window_size=(1800, 600))

    plotter.subplot(0, 0)
    plotter.add_mesh(mesh_truth, scalars="height", cmap="viridis",
                     clim=[vmin, vmax], show_scalar_bar=False)
    plotter.add_text("Ground Truth", font_size=12, position="upper_edge")

    plotter.subplot(0, 1)
    plotter.add_mesh(mesh_single, scalars="height", cmap="viridis",
                     clim=[vmin, vmax], show_scalar_bar=False)
    plotter.add_text(f"Single Freq (RMS={single_metrics['rms']:.3f})",
                     font_size=12, position="upper_edge")

    plotter.subplot(0, 2)
    plotter.add_mesh(mesh_multi, scalars="height", cmap="viridis",
                     clim=[vmin, vmax], show_scalar_bar=False)
    plotter.add_text(f"Multi Freq (RMS={multi_metrics['rms']:.3f})",
                     font_size=12, position="upper_edge")

    plotter.link_views()
    plotter.camera_position = 'iso'
    plotter.camera.zoom(0.85)

    n_frames = 90
    video_path = output_dir / "comparison_3d.mp4"
    plotter.open_movie(str(video_path), framerate=30, quality=8)

    for i in range(n_frames):
        angle = 360 * i / n_frames
        for j in range(3):
            plotter.subplot(0, j)
            plotter.camera.azimuth = angle
            plotter.camera.elevation = 25
        plotter.write_frame()

    plotter.close()
    print(f"    Saved: {video_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Multi-frequency fringe projection demonstration"
    )
    parser.add_argument(
        "-o", "--output",
        default="output",
        help="Output directory (default: output)"
    )
    parser.add_argument(
        "-r", "--resolution",
        type=int,
        default=512,
        help="Resolution (default: 512)"
    )
    parser.add_argument(
        "-n", "--n-steps",
        type=int,
        default=8,
        help="Phase steps per frequency (default: 8)"
    )
    parser.add_argument(
        "--noise",
        type=float,
        default=0.005,
        help="Simulation noise level (default: 0.005)"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Multi-Frequency vs Single-Frequency Comparison Demo")
    print("=" * 60)
    print("\nThis demo runs THREE test surfaces to verify multi-frequency")
    print("advantage on discontinuities while showing equal performance")
    print("on smooth surfaces.")

    total_start = time.time()
    resolution = (args.resolution, args.resolution)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    single_period = 16
    multi_periods = [128, 32, 16]

    results = []

    # Test 1: Smooth surface (control - no discontinuities)
    smooth = create_smooth_surface(resolution)
    results.append(run_single_surface_test(
        smooth, "smooth",
        "Smooth dome with gentle variations (CONTROL - no discontinuities)",
        resolution, args.n_steps, args.noise,
        single_period, multi_periods, output_dir,
    ))

    # Test 2: Simple step surface
    step = create_simple_step_surface(resolution)
    results.append(run_single_surface_test(
        step, "simple_step",
        "Single step (height=0.7, causes ~2 fringe wraps)",
        resolution, args.n_steps, args.noise,
        single_period, multi_periods, output_dir,
    ))

    # Test 3: Challenging surface with multiple discontinuities
    challenging = create_challenging_surface(resolution)
    results.append(run_single_surface_test(
        challenging, "challenging",
        "Multiple steps, isolated pillar, pit (complex discontinuities)",
        resolution, args.n_steps, args.noise,
        single_period, multi_periods, output_dir,
    ))

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print("=" * 60)
    print(f"\n{'Surface':<15} {'Single RMS':>12} {'Multi RMS':>12} {'Improvement':>12}")
    print("-" * 55)
    for r in results:
        if r['multi_rms'] < r['single_rms'] * 0.95:
            improvement = f"{(1 - r['multi_rms']/r['single_rms'])*100:.1f}%"
        else:
            improvement = "equal"
        print(f"{r['name']:<15} {r['single_rms']:>12.4f} {r['multi_rms']:>12.4f} {improvement:>12}")

    print(f"\n{'='*60}")
    print(f"Total time: {time.time() - total_start:.2f}s")
    print(f"\nOutputs in: {output_dir}/")
    print("  - smooth/comparison_3d.png, comparison_3d.mp4")
    print("  - simple_step/comparison_3d.png, comparison_3d.mp4")
    print("  - challenging/comparison_3d.png, comparison_3d.mp4")


if __name__ == "__main__":
    main()
