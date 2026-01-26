"""Integration tests for the fringe projection module.

Tests the complete pipeline: simulation -> capture -> process -> height map
"""

import numpy as np
import pytest

from micro_projection import (
    SimulationSource,
    SimulationConfig,
    CalibrationParams,
    PhaseMap,
    HeightMap,
)
from micro_projection.patterns import (
    sinusoidal_pattern,
    generate_phase_sequence,
)
from micro_projection.processing import (
    extract_phase,
    extract_phase_4step,
    unwrap_phase,
    phase_to_height,
    separate_surface,
    compute_roughness_parameters,
    remove_plane,
)


class TestPatternGeneration:
    """Tests for fringe pattern generation."""

    def test_sinusoidal_pattern_shape(self):
        """Pattern should have correct shape."""
        resolution = (512, 512)
        pattern = sinusoidal_pattern(resolution, period=32)
        assert pattern.shape == resolution

    def test_sinusoidal_pattern_range(self):
        """Pattern values should be in [0, 1]."""
        pattern = sinusoidal_pattern((256, 256), period=32)
        assert pattern.min() >= 0.0
        assert pattern.max() <= 1.0

    def test_sinusoidal_pattern_period(self):
        """Pattern should have correct period."""
        resolution = (256, 256)
        period = 32
        pattern = sinusoidal_pattern(resolution, period=period, orientation=0)

        # Check that pattern repeats with expected period along x-axis
        # Sample a row and find peaks
        row = pattern[128, :]

        # Find local maxima
        from scipy.signal import find_peaks
        peaks, _ = find_peaks(row)

        # Average distance between peaks should be close to period
        if len(peaks) > 1:
            avg_period = np.mean(np.diff(peaks))
            assert abs(avg_period - period) < 2  # Allow small tolerance

    def test_phase_sequence_length(self):
        """Phase sequence should have correct number of patterns."""
        patterns = generate_phase_sequence((256, 256), period=32, n_steps=4)
        assert len(patterns) == 4

        patterns = generate_phase_sequence((256, 256), period=32, n_steps=8)
        assert len(patterns) == 8

    def test_phase_sequence_phase_shifts(self):
        """Phase-shifted patterns should have different phases."""
        patterns = generate_phase_sequence((256, 256), period=32, n_steps=4)

        # Patterns should not be identical
        for i in range(len(patterns)):
            for j in range(i + 1, len(patterns)):
                assert not np.allclose(patterns[i], patterns[j])


class TestSimulationSource:
    """Tests for the simulation source."""

    def test_flat_surface(self):
        """Flat surface should produce undeformed fringes."""
        config = SimulationConfig(resolution=(256, 256), noise_level=0.0)
        source = SimulationSource(config)
        source.set_flat_surface()

        pattern = sinusoidal_pattern((256, 256), period=32)
        source.project_pattern(pattern)
        frame = source.capture_frame()

        assert frame.shape == (256, 256)
        assert frame.min() >= 0.0
        assert frame.max() <= 1.0

    def test_test_surface_sphere(self):
        """Sphere test surface should be created."""
        config = SimulationConfig(resolution=(256, 256))
        source = SimulationSource(config)
        source.set_test_surface("sphere", amplitude=0.1)

        surface = source.get_surface()
        assert surface is not None
        assert surface.shape == (256, 256)
        assert surface.max() > 0  # Sphere has positive height at center

    def test_noise_effect(self):
        """Noise should increase variance in captured frames."""
        resolution = (256, 256)
        pattern = sinusoidal_pattern(resolution, period=32)

        # Capture without noise
        source_clean = SimulationSource(SimulationConfig(resolution=resolution, noise_level=0.0))
        source_clean.set_flat_surface()
        source_clean.project_pattern(pattern)
        frame_clean = source_clean.capture_frame()

        # Capture with noise
        source_noisy = SimulationSource(SimulationConfig(resolution=resolution, noise_level=0.05))
        source_noisy.set_flat_surface()
        source_noisy.project_pattern(pattern)
        frame_noisy = source_noisy.capture_frame()

        # Noisy frame should have higher variance
        # (This is probabilistic but should pass almost always)
        diff = frame_noisy - frame_clean
        assert np.std(diff) > 0.01  # Should have meaningful noise


class TestPhaseExtraction:
    """Tests for phase extraction algorithms."""

    def test_extract_phase_4step(self):
        """4-step phase extraction should produce valid phase map."""
        resolution = (256, 256)
        patterns = generate_phase_sequence(resolution, period=32, n_steps=4)

        # Use patterns directly (ideal case)
        phase_map = extract_phase_4step(patterns)

        assert phase_map.wrapped.shape == resolution
        assert phase_map.wrapped.min() >= -np.pi
        assert phase_map.wrapped.max() <= np.pi
        assert phase_map.quality is not None

    def test_extract_phase_n_step(self):
        """N-step phase extraction should work for various N."""
        resolution = (256, 256)

        for n_steps in [4, 6, 8]:
            patterns = generate_phase_sequence(resolution, period=32, n_steps=n_steps)
            phase_map = extract_phase(patterns, n_steps=n_steps)

            assert phase_map.wrapped.shape == resolution
            assert phase_map.wrapped.min() >= -np.pi
            assert phase_map.wrapped.max() <= np.pi

    def test_extract_phase_requires_minimum_frames(self):
        """Phase extraction should require at least 3 frames."""
        # generate_phase_sequence validates n_steps >= 3
        with pytest.raises(ValueError):
            generate_phase_sequence((256, 256), period=32, n_steps=2)

        # Also test extract_phase directly with manually created 2-frame list
        patterns = generate_phase_sequence((256, 256), period=32, n_steps=4)
        with pytest.raises(Exception):  # ProcessingError
            extract_phase(patterns[:2], n_steps=2)


class TestPhaseUnwrapping:
    """Tests for phase unwrapping."""

    def test_unwrap_smooth_phase(self):
        """Unwrapping smooth phase should be continuous."""
        # Create a known wrapped phase
        x = np.linspace(0, 6 * np.pi, 256)
        y = np.linspace(0, 6 * np.pi, 256)
        X, Y = np.meshgrid(x, y)
        true_phase = X  # Linear phase ramp
        wrapped = np.angle(np.exp(1j * true_phase))

        unwrapped = unwrap_phase(wrapped)

        # Unwrapped should be continuous (no jumps > pi)
        dx = np.diff(unwrapped, axis=1)
        dy = np.diff(unwrapped, axis=0)

        assert np.abs(dx).max() < np.pi + 0.1  # Allow small tolerance
        assert np.abs(dy).max() < np.pi + 0.1

    def test_unwrap_with_quality(self):
        """Quality-guided unwrapping should use quality map."""
        # Create wrapped phase with known quality
        wrapped = np.random.uniform(-np.pi, np.pi, (128, 128))
        quality = np.ones_like(wrapped)
        quality[50:70, 50:70] = 0.1  # Low quality region

        unwrapped = unwrap_phase(wrapped, quality, method="quality_guided")

        assert unwrapped.shape == wrapped.shape


class TestHeightConversion:
    """Tests for phase-to-height conversion."""

    def test_height_conversion_basic(self):
        """Height conversion should apply correct formula."""
        # Create simple phase map
        unwrapped_phase = np.ones((100, 100)) * 2 * np.pi  # One full cycle
        phase_map = PhaseMap(
            wrapped=np.zeros((100, 100)),
            unwrapped=unwrapped_phase,
        )

        # Calibration: lambda_eq = 1.0 means h = (1/2pi) * psi = 1.0 for psi = 2pi
        calibration = CalibrationParams(equivalent_wavelength=1.0)

        height_map = phase_to_height(phase_map, calibration)

        # h = (lambda_eq / 2pi) * psi = (1.0 / 2pi) * 2pi = 1.0
        assert np.allclose(height_map.data, 1.0)

    def test_plane_removal(self):
        """Plane removal should flatten tilted surface."""
        # Create tilted plane
        y, x = np.mgrid[0:100, 0:100]
        tilt = 0.01 * x + 0.005 * y + 5.0  # Tilted plane

        height_map = HeightMap(data=tilt, unit="mm", pixel_pitch=0.1)

        corrected = remove_plane(height_map)

        # After plane removal, mean should be ~0 and tilt should be removed
        assert abs(np.mean(corrected.data)) < 0.01
        assert np.std(corrected.data) < 0.01  # Should be nearly flat


class TestFiltering:
    """Tests for surface filtering."""

    def test_separate_surface(self):
        """Surface separation should split into form and finish."""
        # Create surface with form (low freq) and finish (high freq)
        y, x = np.mgrid[0:256, 0:256]
        form = 0.1 * np.sin(2 * np.pi * x / 200)  # Low frequency
        finish = 0.01 * np.sin(2 * np.pi * x / 10)  # High frequency
        total = form + finish

        height_map = HeightMap(data=total, unit="mm", pixel_pitch=1.0)

        analysis = separate_surface(height_map, cutoff_wavelength=50.0)

        assert analysis.total is not None
        assert analysis.form is not None
        assert analysis.finish is not None

        # Form should have lower frequency content
        # Finish should have higher frequency content
        assert np.std(analysis.form.data) > np.std(analysis.finish.data)

    def test_roughness_parameters(self):
        """Roughness parameters should be computed correctly."""
        # Create random surface
        np.random.seed(42)
        data = np.random.randn(100, 100) * 0.1

        height_map = HeightMap(data=data, unit="um", pixel_pitch=1.0)

        params = compute_roughness_parameters(height_map)

        assert "Sa" in params  # Arithmetical mean height
        assert "Sq" in params  # RMS height
        assert "Sz" in params  # Maximum height
        assert params["Sa"] > 0
        assert params["Sq"] > 0


class TestEndToEndPipeline:
    """End-to-end integration tests."""

    def test_full_pipeline_flat_surface(self):
        """Full pipeline should recover flat surface."""
        resolution = (256, 256)
        period = 32
        n_steps = 4

        # Setup simulation with flat surface
        config = SimulationConfig(resolution=resolution, noise_level=0.001)
        source = SimulationSource(config)
        source.set_flat_surface()

        # Generate and capture patterns
        patterns = generate_phase_sequence(resolution, period=period, n_steps=n_steps)
        frames = []
        for p in patterns:
            source.project_pattern(p)
            frames.append(source.capture_frame())

        # Extract phase
        phase_map = extract_phase(frames, n_steps=n_steps)

        # Unwrap phase
        phase_map.unwrapped = unwrap_phase(phase_map.wrapped, phase_map.quality)

        # Convert to height
        calibration = CalibrationParams(equivalent_wavelength=1.0, pixel_pitch=1.0)
        height_map = phase_to_height(phase_map, calibration)

        # Remove plane (to handle any systematic offset)
        height_map = remove_plane(height_map)

        # Flat surface should have very low height variation
        assert np.std(height_map.data) < 0.1

    def test_full_pipeline_known_surface(self):
        """Full pipeline should produce valid output for known surface."""
        resolution = (256, 256)
        period = 32
        n_steps = 8

        # Setup simulation with sphere surface
        config = SimulationConfig(resolution=resolution, noise_level=0.005)
        source = SimulationSource(config)
        source.set_test_surface("sphere", amplitude=0.1)

        known_surface = source.get_surface()

        # Generate and capture patterns
        patterns = generate_phase_sequence(resolution, period=period, n_steps=n_steps)
        frames = []
        for p in patterns:
            source.project_pattern(p)
            frames.append(source.capture_frame())

        # Extract and unwrap phase
        phase_map = extract_phase(frames, n_steps=n_steps)
        phase_map.unwrapped = unwrap_phase(phase_map.wrapped, phase_map.quality)

        # Convert to height
        calibration = CalibrationParams(equivalent_wavelength=1.0, pixel_pitch=1.0)
        height_map = phase_to_height(phase_map, calibration)

        # Verify the pipeline produces valid results:
        # 1. Output shape matches input
        assert height_map.shape == resolution

        # 2. Height values are finite (no NaN/Inf)
        assert np.all(np.isfinite(height_map.data))

        # 3. Height map has spatial structure (not constant)
        assert np.std(height_map.data) > 0

        # 4. Known surface had structure, recovered should too
        # The center region where sphere is should differ from edges
        center = height_map.data[100:156, 100:156]
        edge = height_map.data[:50, :50]
        assert np.mean(center) != np.mean(edge)  # Center differs from edge


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
