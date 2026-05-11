from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class PhaseShiftResult:
    wrapped_phase: np.ndarray
    modulation: np.ndarray
    average: np.ndarray


@dataclass(frozen=True)
class HeightCalibration:
    phase_scale: float
    height_offset: float

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
    wrapped_phase = np.arctan2(cos_sum, sin_sum)
    modulation = (2.0 / step_count) * np.hypot(sin_sum, cos_sum)
    average = np.mean(sequence, axis=0)
    return PhaseShiftResult(wrapped_phase, modulation, average)


def wrapped_phase_delta(phase: np.ndarray, reference_phase: np.ndarray) -> np.ndarray:
    return np.angle(np.exp(1j * (phase - reference_phase)))


def unwrap_phase_2d(wrapped_phase: np.ndarray) -> np.ndarray:
    return np.unwrap(np.unwrap(wrapped_phase, axis=1), axis=0)


def fit_height_calibration(
    phase_delta: np.ndarray,
    truth_height: np.ndarray,
    mask: np.ndarray,
) -> HeightCalibration:
    valid_phase = np.asarray(phase_delta, dtype=np.float64)[mask]
    valid_truth = np.asarray(truth_height, dtype=np.float64)[mask]
    if valid_phase.size < 2:
        raise ValueError("At least two valid samples are required for calibration.")
    design = np.column_stack([valid_phase, np.ones_like(valid_phase)])
    phase_scale, height_offset = np.linalg.lstsq(design, valid_truth, rcond=None)[0]
    return HeightCalibration(float(phase_scale), float(height_offset))


def apply_height_calibration(
    phase_delta: np.ndarray,
    calibration: HeightCalibration,
) -> np.ndarray:
    return phase_delta * calibration.phase_scale + calibration.height_offset


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
