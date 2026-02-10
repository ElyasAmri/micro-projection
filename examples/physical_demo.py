"""Physical fringe projection measurement demo.

Interactive workflow:
1. Connect camera + open projector
2. Live preview to position part
3. Optional step-height calibration
4. Capture phase-shifted pattern sequence
5. Process: phase extraction -> unwrap -> plane removal -> height
6. Surface separation + roughness parameters
7. Display results and save data

Usage:
    python examples/physical_demo.py --camera 0 --period 64 --n-steps 8
    python examples/physical_demo.py --camera 0 --period 64 --n-steps 8 --step-height 0.1
"""

import argparse
import sys
import os
import time
from pathlib import Path

import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(
        description="Physical fringe projection measurement"
    )
    parser.add_argument(
        "--camera", type=int, default=0, help="Camera device index (default: 0)"
    )
    parser.add_argument(
        "--screen", type=int, default=0, help="Projector screen index (default: 0)"
    )
    parser.add_argument(
        "--period", type=float, default=64, help="Fringe period in projector pixels (default: 64)"
    )
    parser.add_argument(
        "--n-steps", type=int, default=8, help="Number of phase steps (default: 8)"
    )
    parser.add_argument(
        "--settle-ms", type=float, default=300, help="Settle time after pattern display in ms (default: 300)"
    )
    parser.add_argument(
        "--n-avg", type=int, default=3, help="Frames to average per capture (default: 3)"
    )
    parser.add_argument(
        "--n-discard", type=int, default=2, help="Frames to discard after pattern change (default: 2)"
    )
    parser.add_argument(
        "--proj-width", type=int, default=1920, help="Projector width in pixels (default: 1920)"
    )
    parser.add_argument(
        "--proj-height", type=int, default=1080, help="Projector height in pixels (default: 1080)"
    )
    parser.add_argument(
        "--step-height", type=float, default=None,
        help="Known step height for calibration (mm). If provided, runs calibration."
    )
    parser.add_argument(
        "--lambda-eq", type=float, default=1.0,
        help="Equivalent wavelength if no calibration (default: 1.0, arbitrary units)"
    )
    parser.add_argument(
        "--cutoff", type=float, default=50.0,
        help="Cutoff wavelength for surface separation in pixels (default: 50)"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output directory for saving results"
    )
    parser.add_argument(
        "--gamma", type=float, default=1.0,
        help="Projector gamma correction (default: 1.0)"
    )
    return parser.parse_args()


def live_preview(camera_backend):
    """Show live camera feed until user presses 'q'."""
    import cv2

    print("\n--- Live Preview ---")
    print("Position the part under the projector.")
    print("Press 'q' to continue to measurement.")
    print()

    while True:
        frame = camera_backend.grab_frame()
        # Convert to uint8 for display
        display = (frame * 255).astype(np.uint8)
        cv2.imshow("Camera Preview", display)

        key = cv2.waitKey(30) & 0xFF
        if key == ord("q"):
            break

    cv2.destroyWindow("Camera Preview")
    cv2.waitKey(1)


def select_roi_interactive(frame: np.ndarray, label: str) -> tuple[int, int, int, int]:
    """Let user select a rectangular ROI on the image.

    Returns (row_start, row_end, col_start, col_end).
    """
    import cv2

    display = (frame * 255).astype(np.uint8)
    print(f"\nSelect ROI for '{label}': click and drag, then press Enter/Space.")
    roi = cv2.selectROI(f"Select {label}", display, fromCenter=False)
    cv2.destroyWindow(f"Select {label}")
    cv2.waitKey(1)

    x, y, w, h = roi
    return (y, y + h, x, x + w)


def run_calibration(source, args):
    """Run step-height calibration interactively."""
    from micro_projection.patterns import generate_phase_sequence
    from micro_projection.calibration import calibrate_from_step_height

    print("\n--- Step-Height Calibration ---")
    print(f"Place the step standard (height = {args.step_height} mm) under the projector.")
    input("Press Enter when ready...")

    proj_res = (args.proj_height, args.proj_width)
    patterns = generate_phase_sequence(proj_res, period=args.period, n_steps=args.n_steps)

    print(f"Capturing {args.n_steps} calibration frames...")
    frames = source.capture_sequence(
        patterns,
        progress_callback=lambda i, n: print(f"  Frame {i+1}/{n}", end="\r"),
    )
    print()

    # Capture a single frame for ROI selection
    print("Select ROIs on the captured frame...")
    source.project_pattern(patterns[0])
    ref_frame = source.capture_frame()

    roi_high = select_roi_interactive(ref_frame, "HIGH step")
    roi_low = select_roi_interactive(ref_frame, "LOW step")

    cal = calibrate_from_step_height(
        frames=frames,
        known_height=args.step_height,
        roi_high=roi_high,
        roi_low=roi_low,
        unit="mm",
    )

    print(f"Calibration complete: lambda_eq = {cal.equivalent_wavelength:.4f} mm")
    return cal


def capture_measurement(source, args):
    """Capture the measurement pattern sequence."""
    from micro_projection.patterns import generate_phase_sequence

    proj_res = (args.proj_height, args.proj_width)
    patterns = generate_phase_sequence(proj_res, period=args.period, n_steps=args.n_steps)

    print(f"\nCapturing {args.n_steps} measurement frames (period={args.period})...")
    frames = source.capture_sequence(
        patterns,
        progress_callback=lambda i, n: print(f"  Frame {i+1}/{n}", end="\r"),
    )
    print()
    return frames


def process_frames(frames, calibration):
    """Process captured frames through the full pipeline."""
    from micro_projection.processing import (
        extract_phase,
        unwrap_phase,
        remove_plane,
        phase_to_height,
    )

    print("Processing...")

    # Phase extraction
    phase_map = extract_phase(frames)
    print(f"  Phase extracted (wrapped range: [{phase_map.wrapped.min():.2f}, {phase_map.wrapped.max():.2f}])")

    # Phase unwrapping
    phase_map.unwrapped = unwrap_phase(phase_map.wrapped, phase_map.quality)
    print(f"  Phase unwrapped (range: [{phase_map.unwrapped.min():.2f}, {phase_map.unwrapped.max():.2f}])")

    # Phase to height
    height = phase_to_height(phase_map, calibration)
    print(f"  Height computed (range: [{height.data.min():.4f}, {height.data.max():.4f}] {height.unit})")

    # Remove tilt plane
    height = remove_plane(height)
    print(f"  Plane removed (range: [{height.data.min():.4f}, {height.data.max():.4f}] {height.unit})")

    return height


def analyze_roughness(height, cutoff):
    """Separate surface and compute roughness parameters."""
    from micro_projection.processing import separate_surface, compute_roughness_parameters

    print(f"\nSurface separation (cutoff = {cutoff} pixels)...")
    analysis = separate_surface(height, cutoff_wavelength=cutoff, method="gaussian")

    params = compute_roughness_parameters(analysis.finish)

    print("\n--- Roughness Parameters ---")
    for name, value in params.items():
        if name == "unit":
            continue
        unit = params.get("unit", "")
        print(f"  {name}: {value:.6f} {unit}")

    return analysis, params


def display_results(height, analysis):
    """Display height map and roughness map using matplotlib."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("\nInstall matplotlib for visual display: pip install matplotlib")
        return

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    im0 = axes[0].imshow(height.data, cmap="viridis")
    axes[0].set_title("Height Map (plane removed)")
    plt.colorbar(im0, ax=axes[0], label=height.unit)

    if analysis.form is not None:
        im1 = axes[1].imshow(analysis.form.data, cmap="viridis")
        axes[1].set_title("Form (low-freq)")
        plt.colorbar(im1, ax=axes[1], label=height.unit)

    if analysis.finish is not None:
        im2 = axes[2].imshow(analysis.finish.data, cmap="RdBu_r")
        axes[2].set_title("Roughness (high-freq)")
        plt.colorbar(im2, ax=axes[2], label=height.unit)

    plt.tight_layout()
    plt.show()


def save_results(frames, height, analysis, params, output_dir):
    """Save all results to the output directory."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Save captured frames
    frames_dir = out / "frames"
    frames_dir.mkdir(exist_ok=True)
    for i, frame in enumerate(frames):
        np.save(frames_dir / f"frame_{i:03d}.npy", frame)

    # Save height map
    np.save(out / "height_map.npy", height.data)

    # Save roughness data
    if analysis.finish is not None:
        np.save(out / "roughness_map.npy", analysis.finish.data)

    # Save parameters as text
    with open(out / "roughness_params.txt", "w") as f:
        for name, value in params.items():
            f.write(f"{name}: {value}\n")

    print(f"\nResults saved to: {out.resolve()}")


def main():
    args = parse_args()

    # Lazy imports (need opencv-python installed)
    try:
        import cv2
    except ImportError:
        print("Error: opencv-python is required.")
        print("Install with: pip install opencv-python")
        sys.exit(1)

    from micro_projection.sources.opencv_backend import OpenCVBackend
    from micro_projection.sources.projector import CVProjector, ProjectorConfig
    from micro_projection.sources.physical import PhysicalSource, PhysicalConfig
    from micro_projection.core.datatypes import CalibrationParams

    # Setup camera
    camera = OpenCVBackend(device_index=args.camera)

    # Setup projector
    proj_config = ProjectorConfig(
        screen_index=args.screen,
        resolution=(args.proj_height, args.proj_width),
        settle_time_ms=args.settle_ms,
        gamma=args.gamma,
    )
    projector = CVProjector(proj_config)

    # Setup physical source
    phys_config = PhysicalConfig(
        settle_time_ms=args.settle_ms,
        n_avg_frames=args.n_avg,
        n_discard_frames=args.n_discard,
        pattern_resolution=(args.proj_height, args.proj_width),
    )
    source = PhysicalSource(camera, projector, phys_config)

    print("=== Physical Fringe Projection Measurement ===")
    print(f"Camera: index {args.camera}")
    print(f"Projector: screen {args.screen} ({args.proj_width}x{args.proj_height})")
    print(f"Period: {args.period} px, Steps: {args.n_steps}")
    print(f"Settle: {args.settle_ms} ms, Avg: {args.n_avg}, Discard: {args.n_discard}")

    with source:
        # 1. Live preview
        live_preview(camera)

        # 2. Optional calibration
        if args.step_height is not None:
            calibration = run_calibration(source, args)
        else:
            calibration = CalibrationParams(
                equivalent_wavelength=args.lambda_eq,
                unit="au" if args.lambda_eq == 1.0 else "mm",
            )
            print(f"\nUsing uncalibrated lambda_eq = {args.lambda_eq} (arbitrary units)")

        # 3. Capture measurement
        input("\nPosition the measurement target. Press Enter to capture...")
        frames = capture_measurement(source, args)

    # 4. Process (projector can be closed now)
    height = process_frames(frames, calibration)

    # 5. Roughness analysis
    analysis, params = analyze_roughness(height, args.cutoff)

    # 6. Display results
    display_results(height, analysis)

    # 7. Save results
    if args.output is not None:
        save_results(frames, height, analysis, params, args.output)


if __name__ == "__main__":
    main()
