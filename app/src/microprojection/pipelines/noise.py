"""Flat-field camera noise characterization.

Projects a uniform gray field (so every pixel sits at the same mean intensity,
isolating camera temporal noise rather than scene structure) and captures many
frames of it (default 1000). Each frame is saved, and the per-pixel temporal
variance is accumulated online (Welford) so memory stays flat regardless of
frame count.

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

from microprojection.patterns import flat_field
from microprojection.pipelines.base import CapturePipeline
from microprojection.pipelines.frame_io import save_frame, save_png


class NoisePipeline(CapturePipeline):
    def __init__(self, camera, projector_window, settings, output_dir, *,
                 num_frames: int = 1000, level: int = 128,
                 std_dn_threshold: float = 2.0, max_fail_fraction: float = 0.01,
                 percentile: float = 99.0, percentile_limit: float = 3.0,
                 mean_ceiling: float = 1.5, parent=None):
        super().__init__(camera, projector_window, settings, output_dir,
                         parent=parent)
        self._num_frames = max(1, int(num_frames))
        self._level = level
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

    @property
    def total(self) -> int:
        return self._num_frames

    def pattern_for(self, i: int):
        # Project the uniform field once (frame 0); hold it for the rest.
        if i == 0:
            return flat_field(self.width, self.height, level=self._level)
        return None

    def handle_frame(self, i: int, frame) -> None:
        image = np.asarray(frame.image)
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
        std = np.sqrt(variance)

        np.save(os.path.join(self._output_dir, "variance_map.npy"), variance)
        self._save_heatmap(std)
        self._save_fail_mask(std)
        self._write_report(std)

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

    def _write_report(self, std: np.ndarray) -> None:
        c = self._checks(std)
        overall = c["per_pixel_pass"] and c["percentile_pass"] and c["mean_pass"]
        lines = [
            "Flat-field camera noise test",
            f"frames captured: {self._count}",
            f"flat-field level (0..255): {self._level}",
            "",
            "Per-pixel temporal std (intensity counts):",
            f"  mean:   {float(std.mean()):.4f}",
            f"  median: {float(np.median(std)):.4f}",
            f"  min:    {float(std.min()):.4f}",
            f"  max:    {float(std.max()):.4f}",
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
