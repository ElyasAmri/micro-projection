from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from projection_simulation.scanning.synthetic_surfaces import SURFACE_KINDS

IMPROVEMENT_ORDER: tuple[str, ...] = (
    "truth-render-alignment",
    "absolute-correspondence",
    "solver-refinement",
    "reference-normalization",
    "measurement-fidelity",
    "verifier-cleanup",
)

DEFAULT_SURFACES: tuple[str, ...] = (
    "dome-ridge",
    "saddle-ripple",
    "ring-crater",
    "folded-sheet",
    "cross-groove",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark Blender reconstruction improvements separately and cumulatively.")
    parser.add_argument(
        "--verify-script",
        default=str(Path(__file__).with_name("verify_blender_reconstruction.py")),
        help="Path to the Blender verification script.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / ".artifacts" / "blender_reconstruction_improvements"),
        help="Directory for benchmark outputs.",
    )
    parser.add_argument(
        "--surfaces",
        nargs="+",
        default=list(DEFAULT_SURFACES),
        choices=SURFACE_KINDS,
        help="Surface set to benchmark.",
    )
    return parser.parse_args()


def _configurations() -> list[dict[str, object]]:
    configs: list[dict[str, object]] = [{"label": "baseline", "mode": "baseline", "enabled": []}]
    cumulative: list[str] = []
    for improvement in IMPROVEMENT_ORDER:
        configs.append(
            {
                "label": f"solo-{improvement}",
                "mode": "solo",
                "improvement": improvement,
                "enabled": [improvement],
            }
        )
        cumulative.append(improvement)
        configs.append(
            {
                "label": f"cumulative-{improvement}",
                "mode": "cumulative",
                "improvement": improvement,
                "enabled": list(cumulative),
            }
        )
    return configs


def _run_configuration(
    verify_script: Path,
    output_root: Path,
    surface: str,
    config: dict[str, object],
) -> dict[str, object]:
    run_dir = output_root / surface / str(config["label"])
    command = [
        sys.executable,
        str(verify_script),
        "--surface-kind",
        surface,
        "--output-dir",
        str(run_dir),
        "--skip-thresholds",
    ]
    enabled = list(config["enabled"])
    if enabled:
        command.extend(["--enabled-improvements", *enabled])
    completed = subprocess.run(command, check=False, capture_output=True, text=True)

    metrics_path = run_dir / "reconstruction_metrics.json"
    metrics_payload = None
    if metrics_path.exists():
        metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    return {
        "surface": surface,
        "label": config["label"],
        "mode": config["mode"],
        "improvement": config.get("improvement"),
        "enabled_improvements": enabled,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "metrics": None if metrics_payload is None else metrics_payload.get("metrics"),
        "solver": None
        if metrics_payload is None
        else {
            key: value
            for key, value in metrics_payload.items()
            if key not in {"capture_dir", "surface_kind", "metrics"}
        },
    }


def main() -> int:
    args = _parse_args()
    verify_script = Path(args.verify_script)
    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    results = []
    for surface in args.surfaces:
        for config in _configurations():
            results.append(_run_configuration(verify_script, output_root, surface, config))

    summary = {
        "surfaces": list(args.surfaces),
        "improvement_order": list(IMPROVEMENT_ORDER),
        "results": results,
    }
    (output_root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
