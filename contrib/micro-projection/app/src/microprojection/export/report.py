"""Write `results.json` (canonical), `height.png`, `roughness.png` for a measurement."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

from microprojection.core import paper_specs
from microprojection.core.datatypes import PipelineResult


def _normalize_to_uint8(values: np.ndarray) -> np.ndarray:
    data = np.asarray(values, dtype=np.float64)
    finite = np.isfinite(data)
    if not np.any(finite):
        return np.zeros(data.shape, dtype=np.uint8)
    lo, hi = np.percentile(data[finite], [1.0, 99.0])
    if hi <= lo:
        return np.full(data.shape, 127, dtype=np.uint8)
    normalized = np.clip((data - lo) / (hi - lo), 0.0, 1.0)
    return np.round(normalized * 255.0).astype(np.uint8)


def save_report(
    out_dir: Path | str,
    result: PipelineResult,
    *,
    calibration: Mapping[str, object] | None = None,
    parameters: Mapping[str, object] | None = None,
    notes: str | None = None,
) -> Path:
    """Save a measurement report to `out_dir`.

    Returns the path to the written results.json. Creates `out_dir` if needed.
    """
    if cv2 is None:
        raise RuntimeError("opencv-python is required to write PNG previews.")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out / "height.png"), _normalize_to_uint8(result.height_map))
    cv2.imwrite(str(out / "roughness.png"), _normalize_to_uint8(result.roughness_map))
    document = {
        "schema": "micro-projection.report.v1",
        "saved_utc": datetime.now(timezone.utc).isoformat(),
        "device": paper_specs.summary(),
        "calibration": dict(calibration) if calibration else None,
        "parameters": dict(parameters) if parameters else None,
        "roughness": dict(result.roughness),
        "processing_time_s": float(result.processing_time),
        "height_map_shape": list(result.height_map.shape),
        "notes": notes,
    }
    results_path = out / "results.json"
    # allow_nan=False + a recursive sanitiser so non-finite floats become null
    # (RFC 8259 forbids bare NaN/Infinity literals; emit valid JSON).
    sanitised = _sanitise_for_json(document)
    results_path.write_text(
        json.dumps(sanitised, indent=2, allow_nan=False, default=_json_default),
        encoding="utf-8",
    )
    return results_path


def _sanitise_for_json(value: object) -> object:
    if isinstance(value, dict):
        return {str(k): _sanitise_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitise_for_json(v) for v in value]
    if isinstance(value, (np.floating, float)):
        f = float(value)
        return f if np.isfinite(f) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.ndarray):
        return _sanitise_for_json(value.tolist())
    return value


def _json_default(value: object) -> object:
    if isinstance(value, np.floating):
        f = float(value)
        return f if np.isfinite(f) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"Cannot serialise {type(value).__name__}")
