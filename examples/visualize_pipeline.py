"""Visualization of the fringe projection pipeline."""

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

from micro_projection import SimulationSource, SimulationConfig, CalibrationParams
from micro_projection.patterns import generate_phase_sequence
from micro_projection.processing import extract_phase, unwrap_phase, phase_to_height, remove_plane


def main():
    # Setup
    resolution = (256, 256)
    period = 32
    n_steps = 8

    # Create simulation with a sphere surface
    config = SimulationConfig(resolution=resolution, noise_level=0.005)
    source = SimulationSource(config)
    source.set_test_surface("sphere", amplitude=0.15, radius=0.8)

    # Get the known input surface
    input_surface = source.get_surface()

    # Generate phase-shifted patterns
    patterns = generate_phase_sequence(resolution, period=period, n_steps=n_steps)

    # Capture frames (deformed fringes)
    frames = []
    for p in patterns:
        source.project_pattern(p)
        frames.append(source.capture_frame())

    # Process: extract phase
    phase_map = extract_phase(frames, n_steps=n_steps)

    # Unwrap phase
    phase_map.unwrapped = unwrap_phase(phase_map.wrapped, phase_map.quality)

    # Convert to height
    calibration = CalibrationParams(equivalent_wavelength=1.0, pixel_pitch=1.0)
    height_map = phase_to_height(phase_map, calibration)

    # Remove plane (tilt correction)
    height_map_corrected = remove_plane(height_map)

    # Create visualization
    fig = plt.figure(figsize=(16, 12))

    # 1. Input Surface (3D)
    ax1 = fig.add_subplot(2, 3, 1, projection='3d')
    x = np.arange(resolution[1])
    y = np.arange(resolution[0])
    X, Y = np.meshgrid(x, y)
    ax1.plot_surface(X[::4, ::4], Y[::4, ::4], input_surface[::4, ::4],
                     cmap='viridis', alpha=0.8)
    ax1.set_title('Input Surface Geometry\n(What we project onto)')
    ax1.set_xlabel('X (pixels)')
    ax1.set_ylabel('Y (pixels)')
    ax1.set_zlabel('Height')

    # 2. Input Surface (2D top-down)
    ax2 = fig.add_subplot(2, 3, 2)
    im2 = ax2.imshow(input_surface, cmap='viridis')
    ax2.set_title('Input Surface (Top View)')
    plt.colorbar(im2, ax=ax2, label='Height')

    # 3. One of the projected patterns
    ax3 = fig.add_subplot(2, 3, 3)
    ax3.imshow(patterns[0], cmap='gray')
    ax3.set_title('Projected Fringe Pattern\n(One of 8 phase-shifted patterns)')

    # 4. Captured deformed fringes
    ax4 = fig.add_subplot(2, 3, 4)
    ax4.imshow(frames[0], cmap='gray')
    ax4.set_title('Captured Deformed Fringes\n(Surface modulates the pattern)')

    # 5. Wrapped Phase
    ax5 = fig.add_subplot(2, 3, 5)
    im5 = ax5.imshow(phase_map.wrapped, cmap='twilight', vmin=-np.pi, vmax=np.pi)
    ax5.set_title('Extracted Wrapped Phase\n(-pi to pi)')
    plt.colorbar(im5, ax=ax5, label='Phase (rad)')

    # 6. Output Height Map (3D)
    ax6 = fig.add_subplot(2, 3, 6, projection='3d')
    ax6.plot_surface(X[::4, ::4], Y[::4, ::4], height_map_corrected.data[::4, ::4],
                     cmap='viridis', alpha=0.8)
    ax6.set_title('Recovered Height Map\n(Output result)')
    ax6.set_xlabel('X (pixels)')
    ax6.set_ylabel('Y (pixels)')
    ax6.set_zlabel('Height')

    plt.tight_layout()
    plt.savefig('pipeline_visualization.png', dpi=150, bbox_inches='tight')
    print("Saved: pipeline_visualization.png")

    # Also create a comparison figure
    fig2, axes = plt.subplots(1, 3, figsize=(15, 5))

    # Cross-section comparison
    center_row = resolution[0] // 2

    axes[0].plot(input_surface[center_row, :], 'b-', linewidth=2, label='Input Surface')
    axes[0].set_title('Input Surface Cross-Section')
    axes[0].set_xlabel('X (pixels)')
    axes[0].set_ylabel('Height')
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()

    # Negate recovered height (sign convention in phase-height relationship)
    recovered = -height_map_corrected.data[center_row, :]
    axes[1].plot(recovered, 'r-', linewidth=2, label='Recovered (sign-corrected)')
    axes[1].set_title('Recovered Height Cross-Section')
    axes[1].set_xlabel('X (pixels)')
    axes[1].set_ylabel('Height')
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()

    # Overlay comparison (normalized for shape comparison)
    input_norm = input_surface[center_row, :] - np.mean(input_surface[center_row, :])
    input_norm = input_norm / (np.max(np.abs(input_norm)) + 1e-10)

    output_norm = recovered - np.mean(recovered)
    output_norm = output_norm / (np.max(np.abs(output_norm)) + 1e-10)

    axes[2].plot(input_norm, 'b-', linewidth=2, label='Input (normalized)')
    axes[2].plot(output_norm, 'r--', linewidth=2, label='Output (normalized)')
    axes[2].set_title('Shape Comparison (Normalized)')
    axes[2].set_xlabel('X (pixels)')
    axes[2].set_ylabel('Normalized Height')
    axes[2].grid(True, alpha=0.3)
    axes[2].legend()

    plt.tight_layout()
    plt.savefig('cross_section_comparison.png', dpi=150, bbox_inches='tight')
    print("Saved: cross_section_comparison.png")

    # Print statistics
    print("\n=== Pipeline Statistics ===")
    print(f"Input surface shape: {input_surface.shape}")
    print(f"Input surface range: [{input_surface.min():.4f}, {input_surface.max():.4f}]")
    print(f"Output height range: [{height_map_corrected.data.min():.4f}, {height_map_corrected.data.max():.4f}]")
    print(f"Wrapped phase range: [{phase_map.wrapped.min():.4f}, {phase_map.wrapped.max():.4f}]")
    print(f"Quality map range: [{phase_map.quality.min():.4f}, {phase_map.quality.max():.4f}]")


if __name__ == "__main__":
    main()
