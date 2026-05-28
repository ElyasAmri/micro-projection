from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None


@dataclass(frozen=True)
class PhaseShiftResult:
    wrapped_phase: np.ndarray
    modulation: np.ndarray
    average: np.ndarray


@dataclass(frozen=True)
class HeightCalibration:
    phase_scale: float
    height_offset: float
    x_scale: float = 0.0
    y_scale: float = 0.0

    @property
    def equivalent_wavelength(self) -> float:
        return self.phase_scale * (2.0 * np.pi)


@dataclass(frozen=True)
class SimilarityMetrics:
    count: int
    rmse: float
    mae: float
    max_abs: float
    correlation: float
    r2: float

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)


def phase_shift_sequence(
    frames: np.ndarray,
    *,
    phase_steps_rad: np.ndarray | None = None,
) -> PhaseShiftResult:
    sequence = np.asarray(frames, dtype=np.float64)
    if sequence.ndim != 3:
        raise ValueError("frames must have shape (steps, height, width).")
    step_count = sequence.shape[0]
    if step_count < 3:
        raise ValueError("At least three phase-shifted frames are required.")

    if phase_steps_rad is None:
        phase_steps = np.linspace(0.0, 2.0 * np.pi, step_count, endpoint=False)
    else:
        phase_steps = np.asarray(phase_steps_rad, dtype=np.float64)
        if phase_steps.shape != (step_count,):
            raise ValueError("phase_steps_rad must contain one phase per frame.")

    sin_sum = np.tensordot(np.sin(phase_steps), sequence, axes=(0, 0))
    cos_sum = np.tensordot(np.cos(phase_steps), sequence, axes=(0, 0))
    # The generated fringe is sine-based, so atan2(cos, sin) recovers its phase convention.
    wrapped_phase = np.arctan2(cos_sum, sin_sum)
    modulation = (2.0 / step_count) * np.hypot(sin_sum, cos_sum)
    average = np.mean(sequence, axis=0)
    return PhaseShiftResult(wrapped_phase, modulation, average)


def wrapped_phase_delta(phase: np.ndarray, reference_phase: np.ndarray) -> np.ndarray:
    return np.angle(np.exp(1j * (phase - reference_phase)))


def available_unwrap_backends() -> tuple[str, ...]:
    backends = ["numpy"]
    if cv2 is not None and hasattr(cv2, "phase_unwrapping"):
        backends.insert(0, "opencv")
    return tuple(backends)


def resolve_unwrap_backend(preferred: str = "auto") -> str:
    if preferred == "auto":
        return available_unwrap_backends()[0]
    if preferred not in available_unwrap_backends():
        options = ", ".join(available_unwrap_backends())
        raise ValueError(f"Unsupported unwrap backend '{preferred}'. Available backends: {options}.")
    return preferred


def _opencv_unwrap_phase_2d(wrapped_phase: np.ndarray) -> np.ndarray:
    if cv2 is None or not hasattr(cv2, "phase_unwrapping"):
        raise RuntimeError("OpenCV phase unwrapping is not available.")
    wrapped = np.asarray(wrapped_phase, dtype=np.float32)
    height, width = wrapped.shape
    params = cv2.phase_unwrapping_HistogramPhaseUnwrapping_Params()
    params.width = width
    params.height = height
    unwrapper = cv2.phase_unwrapping.HistogramPhaseUnwrapping_create(params)
    return np.asarray(unwrapper.unwrapPhaseMap(wrapped), dtype=np.float64)


def unwrap_phase_2d(wrapped_phase: np.ndarray, *, backend: str = "auto") -> np.ndarray:
    selected_backend = resolve_unwrap_backend(backend)
    if selected_backend == "opencv":
        return _opencv_unwrap_phase_2d(wrapped_phase)
    return np.unwrap(np.unwrap(wrapped_phase, axis=1), axis=0)


def normalized_image_coordinates(shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    height, width = shape
    rows, columns = np.indices((height, width), dtype=np.float64)
    if width > 1:
        x_coords = (columns / (width - 1)) * 2.0 - 1.0
    else:
        x_coords = np.zeros_like(columns)
    if height > 1:
        y_coords = (rows / (height - 1)) * 2.0 - 1.0
    else:
        y_coords = np.zeros_like(rows)
    return x_coords, y_coords


def fit_height_calibration(
    phase_delta: np.ndarray,
    truth_height: np.ndarray,
    mask: np.ndarray,
    *,
    include_spatial_terms: bool = False,
) -> HeightCalibration:
    phase = np.asarray(phase_delta, dtype=np.float64)
    valid_phase = phase[mask]
    valid_truth = np.asarray(truth_height, dtype=np.float64)[mask]
    if valid_phase.size < 2:
        raise ValueError("At least two valid samples are required for calibration.")
    if include_spatial_terms:
        x_coords, y_coords = normalized_image_coordinates(phase.shape)
        design = np.column_stack([valid_phase, x_coords[mask], y_coords[mask], np.ones_like(valid_phase)])
        phase_scale, x_scale, y_scale, height_offset = np.linalg.lstsq(design, valid_truth, rcond=None)[0]
        return HeightCalibration(
            phase_scale=float(phase_scale),
            height_offset=float(height_offset),
            x_scale=float(x_scale),
            y_scale=float(y_scale),
        )
    design = np.column_stack([valid_phase, np.ones_like(valid_phase)])
    phase_scale, height_offset = np.linalg.lstsq(design, valid_truth, rcond=None)[0]
    return HeightCalibration(float(phase_scale), float(height_offset))


def apply_height_calibration(
    phase_delta: np.ndarray,
    calibration: HeightCalibration,
) -> np.ndarray:
    height = phase_delta * calibration.phase_scale + calibration.height_offset
    if calibration.x_scale != 0.0 or calibration.y_scale != 0.0:
        x_coords, y_coords = normalized_image_coordinates(np.asarray(phase_delta).shape)
        height = height + x_coords * calibration.x_scale + y_coords * calibration.y_scale
    return height


def similarity_metrics(
    prediction: np.ndarray,
    truth: np.ndarray,
    mask: np.ndarray,
) -> SimilarityMetrics:
    pred = np.asarray(prediction, dtype=np.float64)[mask]
    actual = np.asarray(truth, dtype=np.float64)[mask]
    if pred.size == 0:
        raise ValueError("Cannot compute similarity without valid samples.")
    error = pred - actual
    rmse = float(np.sqrt(np.mean(error * error)))
    mae = float(np.mean(np.abs(error)))
    max_abs = float(np.max(np.abs(error)))
    pred_centered = pred - np.mean(pred)
    actual_centered = actual - np.mean(actual)
    denom = float(np.sqrt(np.sum(pred_centered * pred_centered) * np.sum(actual_centered * actual_centered)))
    correlation = float(np.sum(pred_centered * actual_centered) / denom) if denom > 0.0 else 0.0
    ss_res = float(np.sum(error * error))
    ss_tot = float(np.sum(actual_centered * actual_centered))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0.0 else 0.0
    return SimilarityMetrics(int(pred.size), rmse, mae, max_abs, correlation, float(r2))


def robust_modulation_mask(
    *modulations: np.ndarray,
    percentile: float = 20.0,
) -> np.ndarray:
    if not modulations:
        raise ValueError("At least one modulation map is required.")
    mask = np.ones_like(modulations[0], dtype=bool)
    for modulation in modulations:
        values = np.asarray(modulation, dtype=np.float64)
        threshold = np.percentile(values, percentile)
        mask &= values > threshold
    return mask


def normalize_to_uint8(values: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    data = np.asarray(values, dtype=np.float64)
    valid = np.isfinite(data) if mask is None else (mask & np.isfinite(data))
    output = np.zeros(data.shape, dtype=np.uint8)
    if not np.any(valid):
        return output
    lo, hi = np.percentile(data[valid], [1.0, 99.0])
    if hi <= lo:
        output[valid] = 127
        return output
    normalized = np.clip((data - lo) / (hi - lo), 0.0, 1.0)
    output[valid] = np.round(normalized[valid] * 255.0).astype(np.uint8)
    return output


# ---------------------------------------------------------------------------
# Form / roughness separation and ISO 25178 areal roughness parameters
# ---------------------------------------------------------------------------

def gaussian_form_filter(
    height: np.ndarray,
    mask: np.ndarray,
    sigma_pixels: float,
) -> np.ndarray:
    """Normalized Gaussian low-pass filter, ignoring masked-out pixels.

    Returns the smoothed *form* component. The roughness residual is
    `height - gaussian_form_filter(height, mask, sigma)` on the same mask.

    Uses the standard ISO 16610-21 Gaussian S-filter idea: convolve both the
    masked height and the mask, then normalize. This prevents masked-out edges
    from biasing the smoothing toward zero.
    """
    if cv2 is None:
        raise RuntimeError("cv2 is required for gaussian_form_filter.")
    z = np.where(mask, np.asarray(height, dtype=np.float64), 0.0)
    w = mask.astype(np.float64)
    z_blur = cv2.GaussianBlur(z, ksize=(0, 0), sigmaX=float(sigma_pixels), sigmaY=float(sigma_pixels))
    w_blur = cv2.GaussianBlur(w, ksize=(0, 0), sigmaX=float(sigma_pixels), sigmaY=float(sigma_pixels))
    return np.where(w_blur > 1e-6, z_blur / w_blur, 0.0)


def sigma_pixels_for_cutoff(cutoff_wavelength: float, pixel_pitch: float) -> float:
    """Standard-deviation sigma (in pixels) for a Gaussian low-pass that has 50%
    transmission at the cutoff wavelength `lambda_c` (ISO 16610-21 convention).

    The ISO impulse response is s(x) = (1/(alpha*lambda_c)) * exp(-pi (x/(alpha*lambda_c))^2)
    with alpha = sqrt(ln(2)/pi). Matching that to the standard Gaussian
    g(x) = (1/(sigma*sqrt(2*pi))) * exp(-x^2/(2 sigma^2)) gives
    sigma = alpha * lambda_c / sqrt(2*pi) = sqrt(ln(2) / (2*pi^2)) * lambda_c ~= 0.1874 * lambda_c.
    cv2.GaussianBlur takes this same sigma, so divide by the pixel pitch.
    """
    sigma_phys = float(np.sqrt(np.log(2.0) / (2.0 * np.pi ** 2))) * float(cutoff_wavelength)
    return sigma_phys / float(pixel_pitch)


def sa_roughness(residual: np.ndarray, mask: np.ndarray) -> float:
    """Sa (ISO 25178) on the roughness residual: arithmetic mean absolute height."""
    valid = mask & np.isfinite(residual)
    if not np.any(valid):
        return float("nan")
    return float(np.mean(np.abs(residual[valid])))


def sz_roughness(residual: np.ndarray, mask: np.ndarray) -> float:
    """Sz (ISO 25178) on the roughness residual: max-peak minus max-valley."""
    valid = mask & np.isfinite(residual)
    if not np.any(valid):
        return float("nan")
    values = residual[valid]
    return float(values.max() - values.min())
