"""Camera temporal-noise qualification (ported from the original hardware app).

Projects one static pattern and grabs many frames of it, accumulating the
per-pixel temporal variance online (Welford) so memory stays flat regardless
of frame count. Three pattern modes probe different noise sources:

* "flat"   -- uniform gray at a chosen level: system noise at a controlled
  operating point.
* "fringe" -- a sinusoid at the measurement period/orientation: noise under
  the actual phase-shift condition (std varies with local intensity).
* "dark"   -- projector black: no projected light reaches the sensor, so this
  isolates the camera's own read noise / dark current. A flat or fringe field
  at mid-gray is dominated by DLP PWM dithering, not the sensor.

The temporal std is per-pixel-over-time in every mode, so spatial structure
does not enter it; only the spread across pixels changes.

The std map is checked against three thresholds, all defined on an
8-bit-equivalent 0..255 scale (a Mono16 run is normalised by its 65535 full
scale first, so the same thresholds hold for both pixel formats):

* per-pixel std limit: the fraction of pixels whose std exceeds `std_dn`
  must stay under `max_fail_fraction`;
* percentile cap: the `percentile` of the std distribution must stay under
  `percentile_limit` (catches a noisy tail);
* mean ceiling: the mean std across the sensor must stay under `mean_ceiling`.

The verdict passes only if all three pass. The defaults are per-camera
starting points to tune against a known-good run -- not vendor truth.
This is camera *qualification*; the reconstruction-domain error analysis
(backend.estimate_noise) answers a different question and complements it.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PySide6.QtCore import QThread, Signal


def full_scale_for(dtype) -> float:
    """Saturation count for the camera's pixel mode: 255 for Mono8 (uint8),
    65535 for Mono16 (uint16). Thresholds are defined on the 0..255 scale, so
    a measured std is normalised by this before checks -- otherwise a 16-bit
    run reads ~256x larger and fails every threshold purely on units."""
    if dtype == np.uint16:
        return 65535.0
    return 255.0


class WelfordStats:
    """Online per-pixel mean/variance over a frame stream, O(1) memory."""

    def __init__(self) -> None:
        self.count = 0
        self._mean: np.ndarray | None = None
        self._m2: np.ndarray | None = None
        self.full_scale: float | None = None

    def update(self, frame: np.ndarray) -> None:
        image = np.asarray(frame)
        if self.full_scale is None:
            # Record the mode's full scale from the native dtype, before any
            # float conversion.
            self.full_scale = full_scale_for(image.dtype)
        if image.ndim == 3:  # reduce colour to luminance, single-channel std
            image = image.mean(axis=2)
        value = image.astype(np.float64)
        if self._mean is None:
            self._mean = np.zeros_like(value)
            self._m2 = np.zeros_like(value)
        self.count += 1
        delta = value - self._mean
        self._mean += delta / self.count
        self._m2 += delta * (value - self._mean)

    def variance(self) -> np.ndarray:
        if self._m2 is None or self.count < 2:
            return np.zeros((1, 1))
        return self._m2 / (self.count - 1)

    def std(self) -> np.ndarray:
        return np.sqrt(self.variance())  # raw counts, native scale

    def std_8bit(self) -> np.ndarray:
        return self.std() * (255.0 / (self.full_scale or 255.0))


@dataclass
class NoiseThresholds:
    """8-bit-equivalent counts; starting points, tune per camera."""
    std_dn: float = 2.0
    max_fail_fraction: float = 0.01
    percentile: float = 99.0
    percentile_limit: float = 3.0
    mean_ceiling: float = 1.5


def evaluate(std_norm: np.ndarray, t: NoiseThresholds) -> dict:
    """The three threshold checks on an 8-bit-equivalent std map."""
    fail_mask = std_norm > t.std_dn
    fail_fraction = float(fail_mask.mean()) if std_norm.size else 0.0
    pct_value = float(np.percentile(std_norm, t.percentile))
    mean_std = float(std_norm.mean())
    checks = {
        "fail_fraction": fail_fraction,
        "per_pixel_pass": fail_fraction <= t.max_fail_fraction,
        "pct_value": pct_value,
        "percentile_pass": pct_value <= t.percentile_limit,
        "mean_std": mean_std,
        "mean_pass": mean_std <= t.mean_ceiling,
    }
    checks["overall_pass"] = (checks["per_pixel_pass"]
                              and checks["percentile_pass"]
                              and checks["mean_pass"])
    return checks


def write_outputs(out_dir: Path, stats: WelfordStats, t: NoiseThresholds,
                  pattern_desc: str) -> tuple[Path, bool]:
    """variance_map.npy (raw counts), std heatmap, over-threshold mask, and a
    plain-text report; returns (report_path, overall_pass)."""
    import cv2

    out_dir.mkdir(parents=True, exist_ok=True)
    std = stats.std()
    std_norm = stats.std_8bit()
    full = int(stats.full_scale or 255.0)
    np.save(out_dir / "variance_map.npy", stats.variance())

    peak = float(std.max()) or 1.0
    heat = cv2.applyColorMap(
        np.clip(std / peak * 255.0, 0, 255).astype(np.uint8), cv2.COLORMAP_JET)
    cv2.imwrite(str(out_dir / "std_heatmap.png"), heat)
    cv2.imwrite(str(out_dir / "over_threshold_mask.png"),
                (std_norm > t.std_dn).astype(np.uint8) * 255)

    c = evaluate(std_norm, t)
    verdict = lambda ok: "pass" if ok else "FAIL"  # noqa: E731
    lines = [
        "Camera temporal-noise test",
        f"frames: {stats.count}",
        pattern_desc,
        f"full scale: {full} counts (std below is 8-bit-equivalent, 0..255)",
        "",
        f"per-pixel std: mean {float(std_norm.mean()):.4f}  "
        f"median {float(np.median(std_norm)):.4f}  "
        f"max {float(std_norm.max()):.4f}",
        "",
        f"pixels over {t.std_dn} DN: {c['fail_fraction']:.4%} "
        f"(allowed {t.max_fail_fraction:.2%}) -> {verdict(c['per_pixel_pass'])}",
        f"p{t.percentile:g} std: {c['pct_value']:.4f} "
        f"(limit {t.percentile_limit}) -> {verdict(c['percentile_pass'])}",
        f"mean std: {c['mean_std']:.4f} "
        f"(ceiling {t.mean_ceiling}) -> {verdict(c['mean_pass'])}",
        "",
        f"overall: {verdict(c['overall_pass'])}",
    ]
    report = out_dir / "noise_test.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report, c["overall_pass"]


class NoiseWorker(QThread):
    """Project one static pattern, then grab `n_frames` freshly exposed frames
    from the camera service, folding each into the Welford accumulator. Frames
    are not written to disk (1000 PNGs at full resolution was the old app's
    behaviour and is pure I/O drag; the accumulator keeps everything needed)."""

    line = Signal(str)
    failed = Signal(str)
    finished_ok = Signal(bool)  # overall pass/fail
    show_pattern = Signal(object)  # -> projector.show_pattern (blocking, GUI thread)

    def __init__(self, pattern, camera_service, out_dir: Path, *,
                 n_frames: int = 200, settle_ms: int = 200,
                 thresholds: NoiseThresholds | None = None,
                 pattern_desc: str = "pattern: flat field", parent=None) -> None:
        super().__init__(parent)
        self._pattern = pattern
        self._service = camera_service
        self._out_dir = out_dir
        self._n_frames = max(2, int(n_frames))
        self._settle_ms = settle_ms
        self._thresholds = thresholds or NoiseThresholds()
        self._pattern_desc = pattern_desc

    def run(self) -> None:
        stats = WelfordStats()
        try:
            self._service.acquire_step(self._n_frames)
        except Exception as exc:  # noqa: BLE001 - camera never became available
            self.failed.emit(f"camera unavailable: {exc}")
            return
        try:
            self.show_pattern.emit(self._pattern)  # blocks until on screen
            self.msleep(self._settle_ms)
            for k in range(self._n_frames):
                if self.isInterruptionRequested():
                    raise RuntimeError("aborted (app closing)")
                stats.update(self._service.grab_step())
                if (k + 1) % 50 == 0:
                    self.line.emit(f"[noise] frame {k + 1}/{self._n_frames}")
        except Exception as exc:  # noqa: BLE001 - surface any capture failure
            self.failed.emit(f"noise test failed: {exc}")
            return
        finally:
            self._service.release_step()
        report, passed = write_outputs(self._out_dir, stats, self._thresholds,
                                       self._pattern_desc)
        self.line.emit(f"[noise] report: {report}")
        self.finished_ok.emit(passed)
