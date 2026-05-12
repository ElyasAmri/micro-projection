"""calibration.py — Tilt-flip / inverse-grating calibration from flat reference.

Stub for Stage 2 Task 7. Will house:
- Linear tilt fit and bias extraction from `phi1_unwrapped`.
- `phi2` generation via the tilt-flip trick (Ch.4 §4.3.1, Eq. 4-2 to 4-7):
      phi2 = 2 * tilt - phi1_unwrapped
- Optional load/save of an empirically calibrated lambda_eq
  (Ch.4 §4.3.1 step-height path) consumed by `geometry.HybridGeometry`.
"""
