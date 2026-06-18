"""Camera temporal-noise characterization.

Projects a static pattern and captures many frames of it (default 1000),
accumulating the per-pixel temporal variance online (Welford) so memory stays
flat regardless of frame count. Each frame is saved.

The pattern is a uniform gray flat field by default. Set ``pattern_kind`` to
pick the condition:

* "flat" - uniform gray at ``level``; every pixel sits at the same mean.
* "fringe" - a sinusoid at ``period``/``orientation``, the phase-shifting
  operating condition, where the std varies with local intensity (low at the
  troughs, higher at the crests).
* "dark" - projector black (level 0), so no projected light reaches the sensor.
  This isolates the camera's own read noise / dark current from any projector
  contribution (a flat or fringe field at mid-gray is dominated by DLP PWM
  dithering, not the sensor), giving a clean sensor-noise baseline.

The temporal std is per-pixel-over-time in every mode, so spatial structure does
not enter it; only the spread across pixels changes.

At the end it evaluates the per-pixel intensity deviation against three
thresholds and writes a report:

* per-pixel std limit (in intensity counts): the fraction of pixels whose
  temporal std exceeds the limit must stay under an allowed fraction;
* percentile of std: the chosen percentile of the std distribution must stay
  under a limit (catches a noisy tail of pixels);
* mean std ceiling: the mean per-pixel std across the sensor must stay under a
  ceiling.

The overall verdict passes only if all three pass. A std heatmap and a mask of
the pixels that exceed the per-pixel limit are saved for inspection. The
thresholds are constructor arguments; the defaults are starting points to tune
per camera.
"""
from __future__ import annotations

import os

import cv2
import numpy as np

from microprojection.patterns import flat_field, fringe
from microprojection.pipelines.base import CapturePipeline
from microprojection.pipelines.frame_io import save_frame, save_png


def _full_scale(dtype) -> float:
    """Saturation count for the camera's pixel mode: 255 for Mono8 (uint8),
    65535 for Mono16 (uint16). The std thresholds are defined on the 0..255
    scale, so the measured std is normalised by this before they are applied -
    otherwise a 16-bit run reads ~256x larger and fails every threshold purely
    on units."""
    if dtype == np.uint8:
        return 255.0
    if dtype == np.uint16:
        return 65535.0
    return 255.0


class NoisePipeline(CapturePipeline):
    def __init__(self, camera, projector_window, settings, output_dir, *,
                 num_frames: int = 1000, level: int = 128,
                 pattern_kind: str = "flat", period: float = 32.0,
                 orientation: str = "vertical",
                 std_dn_threshold: float = 2.0, max_fail_fraction: float = 0.01,
                 percentile: float = 99.0, percentile_limit: float = 3.0,
                 mean_ceiling: float = 1.5, parent=None):
        super().__init__(camera, projector_window, settings, output_dir,
                         parent=parent)
        self._num_frames = max(1, int(num_frames))
        self._level = level
        # Static pattern to characterize over: "flat" (uniform gray at level) or
        # "fringe" (sinusoid at period/orientation, the phase-shift condition).
        self._pattern_kind = pattern_kind
        self._period = period
        self._orientation = orientation
        # Thresholds are in 8-bit-equivalent counts (a 0..255 scale); the std is
        # normalised to that scale before they are checked, so they hold for
        # both Mono8 and Mono16.
        self._std_dn_threshold = std_dn_threshold
        self._max_fail_fraction = max_fail_fraction
        self._percentile = percentile
        self._percentile_limit = percentile_limit
        self._mean_ceiling = mean_ceiling
        # Welford accumulators (allocated on the first frame, once the shape is
        # known): count, running mean, sum of squared deviations.
        self._count = 0
        self._mean: np.ndarray | None = None
        self._m2: np.ndarray | None = None
        # Saturation count of the camera mode, set from the first frame's dtype.
        self._full_scale: float | None = None

    @property
    def total(self) -> int:
        return self._num_frames

    def pattern_for(self, i: int):
        # Project the static pattern once (frame 0); hold it for the rest.
        if i == 0:
            if self._pattern_kind == "fringe":
                return fringe(self.width, self.height, period=self._period,
                              orientation=self._orientation)
            if self._pattern_kind == "dark":
                # Projector black: read noise / dark current with no projected
                # light (so it isolates the sensor, not the projector).
                return flat_field(self.width, self.height, level=0)
            return flat_field(self.width, self.height, level=self._level)
        return None

    def handle_frame(self, i: int, frame) -> None:
        image = np.asarray(frame.image)
        # Record the mode's full scale from the native dtype, before any float
        # conversion, so the std can be normalised to the 8-bit threshold scale.
        if self._full_scale is None:
            self._full_scale = _full_scale(image.dtype)
        # Reduce colour frames to luminance so deviation is single-channel.
        if image.ndim == 3:
            image = image.mean(axis=2)
        value = image.astype(np.float64)

        if self._mean is None:
            self._mean = np.zeros_like(value)
            self._m2 = np.zeros_like(value)
        # Welford online update for per-pixel mean and variance.
        self._count += 1
        delta = value - self._mean
        self._mean += delta / self._count
        self._m2 += delta * (value - self._mean)

        save_frame(os.path.join(self._output_dir, f"frame_{i:04d}.png"),
                   np.asarray(frame.image))

    def finalize(self) -> None:
        if self._m2 is None or self._count < 2:
            variance = np.zeros((1, 1))
        else:
            variance = self._m2 / (self._count - 1)
        std = np.sqrt(variance)  # raw counts, in the camera's native scale

        # Normalise to 8-bit-equivalent counts so the thresholds apply to both
        # Mono8 and Mono16. variance_map.npy stays in raw counts.
        full_scale = self._full_scale or 255.0
        std_norm = std * (255.0 / full_scale)

        np.save(os.path.join(self._output_dir, "variance_map.npy"), variance)
        self._save_heatmap(std)  # heatmap self-normalises, so raw is fine
        self._save_fail_mask(std_norm)
        self._write_report(std, std_norm, full_scale)

    # Threshold evaluation and outputs.

    def _checks(self, std: np.ndarray) -> dict:
        fail_mask = std > self._std_dn_threshold
        fail_count = int(fail_mask.sum())
        total_px = int(std.size)
        fail_fraction = fail_count / total_px if total_px else 0.0
        pct_value = float(np.percentile(std, self._percentile))
        mean_std = float(std.mean())
        return {
            "fail_count": fail_count,
            "total_px": total_px,
            "fail_fraction": fail_fraction,
            "per_pixel_pass": fail_fraction <= self._max_fail_fraction,
            "pct_value": pct_value,
            "percentile_pass": pct_value <= self._percentile_limit,
            "mean_std": mean_std,
            "mean_pass": mean_std <= self._mean_ceiling,
        }

    def _save_heatmap(self, std: np.ndarray) -> None:
        peak = float(std.max()) or 1.0
        norm = np.clip(std / peak * 255.0, 0, 255).astype(np.uint8)
        heat = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
        save_png(os.path.join(self._output_dir, "std_heatmap.png"), heat)

    def _save_fail_mask(self, std: np.ndarray) -> None:
        mask = (std > self._std_dn_threshold).astype(np.uint8) * 255
        save_png(os.path.join(self._output_dir, "over_threshold_mask.png"), mask)

    def _verdict(self, ok: bool) -> str:
        return "pass" if ok else "fail"

    def _write_report(self, std: np.ndarray, std_norm: np.ndarray,
                      full_scale: float) -> None:
        c = self._checks(std_norm)
        overall = c["per_pixel_pass"] and c["percentile_pass"] and c["mean_pass"]
        mode = getattr(self._settings, "pixel_format", "unknown")
        if self._pattern_kind == "fringe":
            pattern_desc = (f"pattern: fringe (period {self._period:.0f} px, "
                            f"{self._orientation})")
        elif self._pattern_kind == "dark":
            pattern_desc = "pattern: dark frame (projector black)"
        else:
            pattern_desc = f"pattern: flat field (level {self._level}, 0..255)"
        lines = [
            "Camera temporal-noise test",
            f"frames captured: {self._count}",
            pattern_desc,
            f"pixel format: {mode} (full scale {int(full_scale)} counts)",
            "",
            "Per-pixel temporal std (8-bit-equivalent counts, 0..255 scale):",
            f"  mean:   {float(std_norm.mean()):.4f}",
            f"  median: {float(np.median(std_norm)):.4f}",
            f"  min:    {float(std_norm.min()):.4f}",
            f"  max:    {float(std_norm.max()):.4f}",
            f"  (raw mean {float(std.mean()):.1f} counts on the native "
            f"{int(full_scale)} scale)",
            "",
            "Threshold checks:",
            f"  per-pixel std limit {self._std_dn_threshold:.2f} counts: "
            f"{c['fail_count']}/{c['total_px']} pixels over "
            f"({100.0 * c['fail_fraction']:.3f}%), "
            f"allowed {100.0 * self._max_fail_fraction:.3f}% -> "
            f"{self._verdict(c['per_pixel_pass'])}",
            f"  {self._percentile:.0f}th percentile std {c['pct_value']:.4f} "
            f"vs limit {self._percentile_limit:.2f} -> "
            f"{self._verdict(c['percentile_pass'])}",
            f"  mean std {c['mean_std']:.4f} vs ceiling "
            f"{self._mean_ceiling:.2f} -> {self._verdict(c['mean_pass'])}",
            "",
            f"overall: {self._verdict(overall)}",
            "",
            "Files: variance_map.npy (per-pixel variance), std_heatmap.png, "
            "over_threshold_mask.png (white = over the per-pixel limit).",
        ]
        path = os.path.join(self._output_dir, "noise_variance.txt")
        with open(path, "w", encoding="ascii") as handle:
            handle.write("\n".join(lines) + "\n")
