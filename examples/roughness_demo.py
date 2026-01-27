#!/usr/bin/env python3
"""Surface roughness measurement demonstration.

Demonstrates the separation of form (low-frequency) from roughness (high-frequency)
components and computation of roughness parameters (Sa, Sq, Sz) for both simulated
and recovered surfaces.

Supports loading external 3D models (STL, OBJ, PLY) or using procedural surfaces.
"""

import argparse
import os
import time
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

from micro_projection import SimulationSource, SimulationConfig, CalibrationParams
from micro_projection.patterns import generate_phase_sequence
from micro_projection.processing import (
    extract_phase,
    unwrap_phase,
    phase_to_height,
    remove_plane,
    separate_surface,
    compute_roughness_parameters,
)
from micro_projection.core.datatypes import HeightMap
from micro_projection.utils import load_surface_from_model


def create_test_surface(resolution: tuple[int, int], roughness_amplitude: float = 0.005):
    """Create a test surface with known form and roughness components.

    Args:
        resolution: Surface resolution (height, width)
        roughness_amplitude: Standard deviation of roughness noise

    Returns:
        tuple: (form, roughness, combined) as numpy arrays
    """
    h, w = resolution
    y, x = np.mgrid[0:h, 0:w].astype(np.float64)
    cx, cy = w / 2, h / 2

    # Normalize coordinates to [-1, 1]
    x_norm = (x - cx) / cx
    y_norm = (y - cy) / cy

    # Form (h1): Smooth gaussian dome
    r2 = x_norm**2 + y_norm**2
    form = 0.1 * np.exp(-2 * r2)

    # Roughness (h2): High-frequency random noise
    rng = np.random.default_rng(42)  # For reproducibility
    roughness = roughness_amplitude * rng.standard_normal((h, w))

    # Add some periodic texture for visual interest
    periodic = 0.002 * np.sin(20 * np.pi * x_norm) * np.sin(20 * np.pi * y_norm)
    roughness = roughness + periodic

    # Combined surface
    combined = form + roughness

    return form, roughness, combined


def run_fringe_projection_recovery(
    surface: np.ndarray,
    resolution: tuple[int, int],
    period: int = 64,
    n_steps: int = 8,
):
    """Run fringe projection simulation and recover the surface.

    Args:
        surface: Input surface height map
        resolution: Image resolution
        period: Fringe period in pixels
        n_steps: Number of phase-shifting steps

    Returns:
        tuple: (recovered_surface, patterns, frames) for animation support
    """
    # Setup simulation
    config = SimulationConfig(resolution=resolution, noise_level=0.003)
    source = SimulationSource(config)
    source.set_surface(surface)

    # Generate phase-shifted patterns
    patterns = generate_phase_sequence(resolution, period=period, n_steps=n_steps)

    # Capture frames
    frames = []
    for p in patterns:
        source.project_pattern(p)
        frames.append(source.capture_frame())

    # Process phase
    phase_map = extract_phase(frames, n_steps=n_steps)
    phase_map.unwrapped = unwrap_phase(phase_map.wrapped, phase_map.quality)

    # Convert to height
    calibration = CalibrationParams(equivalent_wavelength=1.0, pixel_pitch=1.0)
    height_map = phase_to_height(phase_map, calibration)
    height_map = remove_plane(height_map)

    # Normalize recovered surface
    recovered = -height_map.data
    recovered = recovered - np.mean(recovered)

    # Scale to match input
    input_centered = surface - np.mean(surface)
    scale = np.std(input_centered) / (np.std(recovered) + 1e-10)
    recovered = recovered * scale

    return recovered, patterns, frames


def create_mesh(surface: np.ndarray, X: np.ndarray, Y: np.ndarray, z_scale: float, texture=None):
    """Create a PyVista StructuredGrid from surface data."""
    grid = pv.StructuredGrid(
        X.astype(np.float32),
        Y.astype(np.float32),
        (surface * z_scale).astype(np.float32)
    )
    if texture is not None:
        grid.point_data['texture'] = texture.flatten(order='F').astype(np.float32)
    else:
        grid.point_data['height'] = surface.flatten(order='F').astype(np.float32)
    return grid


def create_flat_image(image_data: np.ndarray, X: np.ndarray, Y: np.ndarray):
    """Create a flat 2D plane for displaying captured camera image."""
    flat_z = np.zeros_like(image_data)
    grid = pv.StructuredGrid(
        X.astype(np.float32),
        Y.astype(np.float32),
        flat_z.astype(np.float32)
    )
    grid.point_data['intensity'] = image_data.flatten(order='F').astype(np.float32)
    return grid


def get_camera_position(angle_deg: float, center_x: float, center_y: float,
                       camera_distance: float, camera_height: float):
    """Get camera position for 3D view at given angle."""
    angle_rad = np.radians(angle_deg)
    cam_x = center_x + camera_distance * np.cos(angle_rad)
    cam_y = center_y + camera_distance * np.sin(angle_rad)
    return [
        (cam_x, cam_y, camera_height),
        (center_x, center_y, 0),
        (0, 0, 1)
    ]


def get_topdown_camera(center_x: float, center_y: float, height: float):
    """Get camera position for top-down 2D view."""
    return [
        (center_x, center_y, height),  # position above
        (center_x, center_y, 0),  # look at center
        (0, 1, 0)  # up vector
    ]


def create_animation(
    input_combined: np.ndarray,
    input_form: np.ndarray,
    input_roughness: np.ndarray,
    recovered_combined: np.ndarray,
    recovered_form: np.ndarray,
    recovered_roughness: np.ndarray,
    patterns: list,
    frames: list,
    input_params: dict,
    recovered_params: dict,
    output_path: str,
    resolution: tuple[int, int],
    n_steps: int,
):
    """Create PyVista animation showing roughness measurement process.

    Args:
        input_combined: Input combined surface
        input_form: Input form component
        input_roughness: Input roughness component
        recovered_combined: Recovered combined surface
        recovered_form: Recovered form component
        recovered_roughness: Recovered roughness component
        patterns: List of projected patterns
        frames: List of captured frames
        input_params: Roughness parameters for input
        recovered_params: Roughness parameters for recovered
        output_path: Path to save animation
        resolution: Surface resolution
        n_steps: Number of phase-shifting steps
    """
    if not HAS_PYVISTA:
        print("  Warning: PyVista not available. Skipping animation.")
        return

    print("  Creating animation...")
    t0 = time.time()

    # Create coordinate grids
    x_coords = np.arange(resolution[1])
    y_coords = np.arange(resolution[0])
    X, Y = np.meshgrid(x_coords, y_coords)

    # Z scale for visualization
    z_scale = resolution[0] * 2

    # Fixed camera position (no rotation)
    center_x, center_y = resolution[1] / 2, resolution[0] / 2
    camera_distance = resolution[0] * 2.5
    camera_height = resolution[0] * 1.2
    camera_pos = get_camera_position(30, center_x, center_y, camera_distance, camera_height)
    topdown_pos = get_topdown_camera(center_x, center_y, resolution[0] * 2)

    # Setup plotter for 2x4 layout (top: projection, bottom: form/roughness)
    plotter = pv.Plotter(shape=(2, 4), off_screen=True, window_size=(1800, 900))
    plotter.open_movie(str(output_path), framerate=30, quality=9)

    # Animation frames
    total_frames = n_steps + 20  # projection + hold

    for frame_num in range(total_frames):
        plotter.clear()

        step_idx = min(frame_num, n_steps - 1)
        recovery_progress = min((frame_num + 1) / n_steps, 1.0)
        pattern = patterns[step_idx]
        captured = frames[step_idx]

        # === TOP ROW: Fringe projection process ===
        # Panel (0,0): Input surface
        plotter.subplot(0, 0)
        mesh = create_mesh(input_combined, X, Y, z_scale)
        plotter.add_mesh(mesh, scalars='height', cmap='viridis',
                       show_scalar_bar=False, smooth_shading=True)
        plotter.add_title('Input Surface', font_size=10)
        plotter.camera_position = camera_pos

        # Panel (0,1): Projected fringes
        plotter.subplot(0, 1)
        mesh = create_mesh(input_combined, X, Y, z_scale, texture=pattern)
        plotter.add_mesh(mesh, scalars='texture', cmap='gray',
                       show_scalar_bar=False, smooth_shading=True)
        plotter.add_title(f'Projected {step_idx+1}/{n_steps}', font_size=10)
        plotter.camera_position = camera_pos

        # Panel (0,2): Camera view (2D)
        plotter.subplot(0, 2)
        flat_image = create_flat_image(captured, X, Y)
        plotter.add_mesh(flat_image, scalars='intensity', cmap='gray',
                       show_scalar_bar=False)
        plotter.add_title('Camera View', font_size=10)
        plotter.camera_position = topdown_pos

        # Panel (0,3): Recovered surface emerging
        plotter.subplot(0, 3)
        flat_level = np.mean(recovered_combined)
        emerging = flat_level + (recovered_combined - flat_level) * recovery_progress
        mesh = create_mesh(emerging, X, Y, z_scale)
        plotter.add_mesh(mesh, scalars='height', cmap='plasma',
                       show_scalar_bar=False, smooth_shading=True)
        plotter.add_title(f'Recovered {int(recovery_progress*100)}%', font_size=10)
        plotter.camera_position = camera_pos

        # === BOTTOM ROW: Form/Roughness separation ===
        # Panel (1,0): Input form
        plotter.subplot(1, 0)
        mesh = create_mesh(input_form, X, Y, z_scale)
        plotter.add_mesh(mesh, scalars='height', cmap='viridis',
                       show_scalar_bar=False, smooth_shading=True)
        plotter.add_title('Input Form', font_size=10)
        plotter.camera_position = camera_pos

        # Panel (1,1): Input roughness (exaggerated)
        plotter.subplot(1, 1)
        mesh = create_mesh(input_roughness, X, Y, z_scale * 10)
        plotter.add_mesh(mesh, scalars='height', cmap='RdBu_r',
                       show_scalar_bar=False, smooth_shading=True)
        plotter.add_title('Input Roughness', font_size=10)
        plotter.camera_position = camera_pos

        # Panel (1,2): Recovered form (emerging)
        plotter.subplot(1, 2)
        form_flat = np.mean(recovered_form)
        emerging_form = form_flat + (recovered_form - form_flat) * recovery_progress
        mesh = create_mesh(emerging_form, X, Y, z_scale)
        plotter.add_mesh(mesh, scalars='height', cmap='plasma',
                       show_scalar_bar=False, smooth_shading=True)
        plotter.add_title(f'Recovered Form', font_size=10)
        plotter.camera_position = camera_pos

        # Panel (1,3): Recovered roughness (emerging, exaggerated)
        plotter.subplot(1, 3)
        rough_flat = np.mean(recovered_roughness)
        emerging_rough = rough_flat + (recovered_roughness - rough_flat) * recovery_progress
        mesh = create_mesh(emerging_rough, X, Y, z_scale * 10)
        plotter.add_mesh(mesh, scalars='height', cmap='RdBu_r',
                       show_scalar_bar=False, smooth_shading=True)
        plotter.add_title(f'Recovered Roughness', font_size=10)
        plotter.camera_position = camera_pos

        plotter.write_frame()

        if (frame_num + 1) % 10 == 0:
            print(f"    Frame {frame_num + 1}/{total_frames}")

    plotter.close()
    print(f"  Animation time: {time.time() - t0:.2f}s")


def visualize_results(
    input_form: np.ndarray,
    input_roughness: np.ndarray,
    input_combined: np.ndarray,
    recovered_form: np.ndarray,
    recovered_roughness: np.ndarray,
    recovered_combined: np.ndarray,
    input_params: dict,
    recovered_params: dict,
    output_path: str,
    has_ground_truth: bool = True,
):
    """Create visualization of form/roughness separation and comparison.

    Args:
        input_form: Input form component
        input_roughness: Input roughness component
        input_combined: Input combined surface
        recovered_form: Recovered form component
        recovered_roughness: Recovered roughness component
        recovered_combined: Recovered combined surface
        input_params: Roughness parameters for input
        recovered_params: Roughness parameters for recovered
        output_path: Path to save the figure
        has_ground_truth: Whether we have ground-truth form/roughness separation
    """
    fig = plt.figure(figsize=(15, 10))

    # Create 3x3 grid
    # Row 1: Input components
    # Row 2: Recovered components
    # Row 3: Difference maps (only if ground truth available)

    # Common colormap limits
    vmin_form = min(input_form.min(), recovered_form.min())
    vmax_form = max(input_form.max(), recovered_form.max())

    vmin_rough = min(input_roughness.min(), recovered_roughness.min())
    vmax_rough = max(input_roughness.max(), recovered_roughness.max())

    vmin_combined = min(input_combined.min(), recovered_combined.min())
    vmax_combined = max(input_combined.max(), recovered_combined.max())

    # Adjust titles based on whether we have ground truth
    if has_ground_truth:
        input_title_prefix = "Input"
        recovered_title_prefix = "Recovered"
    else:
        input_title_prefix = "Input Total"
        recovered_title_prefix = "Recovered Total"

    # Row 1: Input
    ax1 = plt.subplot(3, 3, 1)
    im1 = ax1.imshow(input_form, cmap='viridis', vmin=vmin_form, vmax=vmax_form)
    ax1.set_title(f'{input_title_prefix} Form (h1)', fontsize=12, fontweight='bold')
    ax1.axis('off')
    plt.colorbar(im1, ax=ax1, fraction=0.046, pad=0.04)

    ax2 = plt.subplot(3, 3, 2)
    im2 = ax2.imshow(input_roughness, cmap='RdBu_r', vmin=vmin_rough, vmax=vmax_rough)
    ax2.set_title(f'{input_title_prefix} Roughness (h2)', fontsize=12, fontweight='bold')
    ax2.axis('off')
    plt.colorbar(im2, ax=ax2, fraction=0.046, pad=0.04)

    ax3 = plt.subplot(3, 3, 3)
    im3 = ax3.imshow(input_combined, cmap='plasma', vmin=vmin_combined, vmax=vmax_combined)
    ax3.set_title(f'{input_title_prefix} Combined (h1 + h2)', fontsize=12, fontweight='bold')
    ax3.axis('off')
    plt.colorbar(im3, ax=ax3, fraction=0.046, pad=0.04)

    # Row 2: Recovered
    ax4 = plt.subplot(3, 3, 4)
    im4 = ax4.imshow(recovered_form, cmap='viridis', vmin=vmin_form, vmax=vmax_form)
    ax4.set_title(f'{recovered_title_prefix} Form (h1)', fontsize=12, fontweight='bold')
    ax4.axis('off')
    plt.colorbar(im4, ax=ax4, fraction=0.046, pad=0.04)

    ax5 = plt.subplot(3, 3, 5)
    im5 = ax5.imshow(recovered_roughness, cmap='RdBu_r', vmin=vmin_rough, vmax=vmax_rough)
    ax5.set_title(f'{recovered_title_prefix} Roughness (h2)', fontsize=12, fontweight='bold')
    ax5.axis('off')
    plt.colorbar(im5, ax=ax5, fraction=0.046, pad=0.04)

    ax6 = plt.subplot(3, 3, 6)
    im6 = ax6.imshow(recovered_combined, cmap='plasma', vmin=vmin_combined, vmax=vmax_combined)
    ax6.set_title(f'{recovered_title_prefix} Combined (h1 + h2)', fontsize=12, fontweight='bold')
    ax6.axis('off')
    plt.colorbar(im6, ax=ax6, fraction=0.046, pad=0.04)

    # Row 3: Differences (only meaningful if we have ground truth)
    if has_ground_truth:
        diff_form = recovered_form - input_form
        diff_roughness = recovered_roughness - input_roughness
        diff_combined = recovered_combined - input_combined

        vmax_diff = max(abs(diff_form).max(), abs(diff_roughness).max(), abs(diff_combined).max())
        vmax_diff = max(vmax_diff, 1e-10)  # Avoid zero range

        ax7 = plt.subplot(3, 3, 7)
        im7 = ax7.imshow(diff_form, cmap='RdBu_r', vmin=-vmax_diff, vmax=vmax_diff)
        ax7.set_title('Form Difference', fontsize=12, fontweight='bold')
        ax7.axis('off')
        plt.colorbar(im7, ax=ax7, fraction=0.046, pad=0.04)

        ax8 = plt.subplot(3, 3, 8)
        im8 = ax8.imshow(diff_roughness, cmap='RdBu_r', vmin=-vmax_diff, vmax=vmax_diff)
        ax8.set_title('Roughness Difference', fontsize=12, fontweight='bold')
        ax8.axis('off')
        plt.colorbar(im8, ax=ax8, fraction=0.046, pad=0.04)

        ax9 = plt.subplot(3, 3, 9)
        im9 = ax9.imshow(diff_combined, cmap='RdBu_r', vmin=-vmax_diff, vmax=vmax_diff)
        ax9.set_title('Combined Difference', fontsize=12, fontweight='bold')
        ax9.axis('off')
        plt.colorbar(im9, ax=ax9, fraction=0.046, pad=0.04)
    else:
        # For external models, show histograms of roughness distributions
        ax7 = plt.subplot(3, 3, 7)
        ax7.hist(input_roughness.flatten(), bins=50, alpha=0.7, label='Input', color='blue')
        ax7.set_title('Input Roughness Distribution', fontsize=12, fontweight='bold')
        ax7.set_xlabel('Height')
        ax7.set_ylabel('Frequency')
        ax7.legend()
        ax7.grid(True, alpha=0.3)

        ax8 = plt.subplot(3, 3, 8)
        ax8.hist(recovered_roughness.flatten(), bins=50, alpha=0.7, label='Recovered', color='orange')
        ax8.set_title('Recovered Roughness Distribution', fontsize=12, fontweight='bold')
        ax8.set_xlabel('Height')
        ax8.set_ylabel('Frequency')
        ax8.legend()
        ax8.grid(True, alpha=0.3)

        ax9 = plt.subplot(3, 3, 9)
        ax9.hist(input_roughness.flatten(), bins=50, alpha=0.5, label='Input', color='blue')
        ax9.hist(recovered_roughness.flatten(), bins=50, alpha=0.5, label='Recovered', color='orange')
        ax9.set_title('Roughness Comparison', fontsize=12, fontweight='bold')
        ax9.set_xlabel('Height')
        ax9.set_ylabel('Frequency')
        ax9.legend()
        ax9.grid(True, alpha=0.3)

    # Add text box with roughness parameters comparison
    if has_ground_truth:
        textstr = 'Roughness Parameters Comparison\n' + '=' * 50 + '\n\n'
        textstr += f"{'Parameter':<12} {'Input':>12} {'Recovered':>12} {'Error %':>12}\n"
        textstr += '-' * 50 + '\n'

        for param in ['Sa', 'Sq', 'Sz']:
            inp_val = input_params.get(param, 0)
            rec_val = recovered_params.get(param, 0)
            error = abs(rec_val - inp_val) / (abs(inp_val) + 1e-10) * 100

            textstr += f"{param:<12} {inp_val:>12.6f} {rec_val:>12.6f} {error:>11.2f}%\n"
    else:
        textstr = 'Roughness Parameters Comparison (No Ground Truth)\n' + '=' * 50 + '\n\n'
        textstr += f"{'Parameter':<12} {'Input':>12} {'Recovered':>12}\n"
        textstr += '-' * 50 + '\n'

        for param in ['Sa', 'Sq', 'Sz']:
            inp_val = input_params.get(param, 0)
            rec_val = recovered_params.get(param, 0)

            textstr += f"{param:<12} {inp_val:>12.6f} {rec_val:>12.6f}\n"

    plt.figtext(0.5, 0.02, textstr, ha='center', fontsize=9, family='monospace',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))

    title_suffix = ' (Procedural)' if has_ground_truth else ' (External Model)'
    plt.suptitle(f'Surface Roughness Measurement: Form/Roughness Separation{title_suffix}',
                 fontsize=14, fontweight='bold', y=0.98)

    plt.tight_layout(rect=[0, 0.08, 1, 0.96])
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"  Saved: {output_path}")
    plt.close()


def main():
    """Run the roughness measurement demonstration."""
    parser = argparse.ArgumentParser(
        description="Surface Roughness Measurement with Form/Roughness Separation"
    )
    parser.add_argument(
        "-i", "--input",
        help="Input 3D model file (STL, OBJ, PLY). If not provided, uses procedural surface."
    )
    parser.add_argument(
        "-o", "--output",
        default="output",
        help="Output directory for results (default: output)"
    )
    parser.add_argument(
        "-r", "--resolution",
        type=int,
        default=512,
        help="Resolution (square, default: 512)"
    )
    parser.add_argument(
        "-c", "--cutoff",
        type=float,
        default=30.0,
        help="Cutoff wavelength for filtering in pixels (default: 30)"
    )
    parser.add_argument(
        "-a", "--animate",
        action="store_true",
        help="Generate animation video (requires PyVista, increases processing time)"
    )
    parser.add_argument(
        "-n", "--n-steps",
        type=int,
        default=256,
        help="Number of phase-shifting steps (default: 256)"
    )
    parser.add_argument(
        "-f", "--filter",
        choices=["gaussian", "butterworth", "ideal"],
        default="gaussian",
        help="Filter method for form/roughness separation (default: gaussian). "
             "WARNING: 'ideal' causes ringing artifacts."
    )
    parser.add_argument(
        "--filter-order",
        type=int,
        default=2,
        help="Butterworth filter order (default: 2). Higher = sharper cutoff."
    )

    args = parser.parse_args()

    print("Surface Roughness Measurement Demonstration")
    print("=" * 60)

    total_start = time.time()

    # Configuration
    resolution = (args.resolution, args.resolution)
    period = 64
    n_steps = args.n_steps
    cutoff_wavelength = args.cutoff
    roughness_amplitude = 0.005

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine if we're using external model or procedural surface
    use_external_model = args.input and os.path.exists(args.input)
    has_ground_truth = not use_external_model

    # Step 1: Load or create test surface
    if use_external_model:
        print(f"\n1. Loading external 3D model: {args.input}")
        t0 = time.time()
        input_combined = load_surface_from_model(args.input, resolution)
        # For external models, we don't have separate form/roughness components
        # We'll compute them from the filtering step
        input_form = None
        input_roughness = None
        print(f"   Surface range: {input_combined.min():.6f} to {input_combined.max():.6f}")
        print(f"   Time: {time.time() - t0:.2f}s")
    else:
        print("\n1. Creating procedural test surface with known components...")
        if args.input:
            print(f"   Warning: Model file not found: {args.input}")
            print("   Using procedural surface instead.")
        t0 = time.time()
        input_form, input_roughness, input_combined = create_test_surface(
            resolution, roughness_amplitude=roughness_amplitude
        )
        print(f"   Form amplitude: {input_form.max():.6f}")
        print(f"   Roughness std: {np.std(input_roughness):.6f}")
        print(f"   Time: {time.time() - t0:.2f}s")

    # Step 2: Run fringe projection simulation
    print("\n2. Running fringe projection simulation...")
    t0 = time.time()
    recovered_combined, patterns, frames = run_fringe_projection_recovery(
        input_combined, resolution, period=period, n_steps=n_steps
    )
    print(f"   Time: {time.time() - t0:.2f}s")

    # Step 3: Separate surfaces into form and roughness
    print("\n3. Separating form and roughness components...")
    t0 = time.time()

    # Create HeightMap objects for filtering
    input_height_map = HeightMap(
        data=input_combined,
        unit="mm",
        pixel_pitch=1.0,
        equivalent_wavelength=1.0,
    )

    recovered_height_map = HeightMap(
        data=recovered_combined,
        unit="mm",
        pixel_pitch=1.0,
        equivalent_wavelength=1.0,
    )

    # Apply filtering
    filter_method = args.filter
    filter_order = args.filter_order
    input_analysis = separate_surface(
        input_height_map, cutoff_wavelength, method=filter_method, order=filter_order
    )
    recovered_analysis = separate_surface(
        recovered_height_map, cutoff_wavelength, method=filter_method, order=filter_order
    )

    # For external models, we now have the separated components
    if use_external_model:
        input_form = input_analysis.form.data
        input_roughness = input_analysis.finish.data

    filter_info = f"{filter_method}"
    if filter_method == "butterworth":
        filter_info += f" (order={filter_order})"
    print(f"   Filter method: {filter_info}")
    print(f"   Cutoff wavelength: {cutoff_wavelength} pixels")
    print(f"   Time: {time.time() - t0:.2f}s")

    # Step 4: Compute roughness parameters
    print("\n4. Computing roughness parameters...")
    t0 = time.time()

    input_params = compute_roughness_parameters(input_analysis.finish)
    recovered_params = compute_roughness_parameters(recovered_analysis.finish)

    print(f"   Time: {time.time() - t0:.2f}s")

    # Step 5: Display results
    print("\n5. Roughness Parameters Comparison:")
    print("   " + "=" * 56)
    if has_ground_truth:
        print(f"   {'Parameter':<12} {'Input':>12} {'Recovered':>12} {'Error %':>12}")
        print("   " + "-" * 56)

        for param in ['Sa', 'Sq', 'Sp', 'Sv', 'Sz', 'Ssk', 'Sku']:
            inp_val = input_params.get(param, 0)
            rec_val = recovered_params.get(param, 0)
            error = abs(rec_val - inp_val) / (abs(inp_val) + 1e-10) * 100

            print(f"   {param:<12} {inp_val:>12.6f} {rec_val:>12.6f} {error:>11.2f}%")
    else:
        print(f"   {'Parameter':<12} {'Input':>12} {'Recovered':>12}")
        print("   " + "-" * 56)

        for param in ['Sa', 'Sq', 'Sp', 'Sv', 'Sz', 'Ssk', 'Sku']:
            inp_val = input_params.get(param, 0)
            rec_val = recovered_params.get(param, 0)

            print(f"   {param:<12} {inp_val:>12.6f} {rec_val:>12.6f}")

    print("   " + "=" * 56)

    # Step 6: Create visualization
    print("\n6. Creating visualization...")
    t0 = time.time()

    png_output_path = output_dir / "roughness_comparison.png"
    visualize_results(
        input_form=input_form,
        input_roughness=input_roughness,
        input_combined=input_combined,
        recovered_form=recovered_analysis.form.data,
        recovered_roughness=recovered_analysis.finish.data,
        recovered_combined=recovered_combined,
        input_params=input_params,
        recovered_params=recovered_params,
        output_path=str(png_output_path),
        has_ground_truth=has_ground_truth,
    )
    print(f"   Time: {time.time() - t0:.2f}s")

    # Step 7: Create animation (if requested)
    if args.animate:
        if not HAS_PYVISTA:
            print("\n7. Animation requested but PyVista not installed.")
            print("   Install with: pip install pyvista")
        else:
            print("\n7. Creating animation...")
            video_output_path = output_dir / "roughness_animation.mp4"
            create_animation(
                input_combined=input_combined,
                input_form=input_form,
                input_roughness=input_roughness,
                recovered_combined=recovered_combined,
                recovered_form=recovered_analysis.form.data,
                recovered_roughness=recovered_analysis.finish.data,
                patterns=patterns,
                frames=frames,
                input_params=input_params,
                recovered_params=recovered_params,
                output_path=str(video_output_path),
                resolution=resolution,
                n_steps=n_steps,
            )

    print(f"\n{'='*60}")
    print(f"Total time: {time.time() - total_start:.2f}s")
    print(f"\nOutput files:")
    print(f"  - {png_output_path}")
    if args.animate and HAS_PYVISTA:
        video_output_path = output_dir / "roughness_animation.mp4"
        print(f"  - {video_output_path}")
    if use_external_model:
        print(f"\nNote: External model loaded from: {args.input}")
        print("      Comparison based on filtered components (no ground-truth separation)")
    print("\nDemonstration complete!")


if __name__ == "__main__":
    main()
