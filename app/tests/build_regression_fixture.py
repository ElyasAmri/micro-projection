"""Build/refresh the frozen DSP regression fixture (regression_data.npz).

Records the numeric output of every pure DSP-core stage on a small, seeded,
deterministic input set (the exact forward model reconstruct.py inverts:
I_k = a + b*cos(carrier + h*2pi/lambda_eq + delta_k) plus seeded noise).
test_regression.py re-runs each stage on the frozen inputs and compares
against these golden arrays with tiered tolerances -- silent numeric drift
in the core, whether from a code edit, a dependency bump, or a geometry
constant, fails loudly.

Rebuild ONLY after an INTENTIONAL numerics/geometry change:

    .venv/bin/python app/tests/build_regression_fixture.py

then review the printed summary drift and commit the new npz alongside the
change that caused it. (Methodology from the fringe-projection-3d suite;
data regenerated for this pipeline's mm/world-space conventions.)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "simulation"))

import occlusion  # noqa: E402
import reconstruct  # noqa: E402
import roughness  # noqa: E402
import surfaces  # noqa: E402
from geometry_constants import N_PERIODS_LADDER, THETA_DEG  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "regression_data.npz"
SHAPE = (48, 64)
N_STEPS = 8
SIGMA = 2.0 / 255.0  # keeps arctan2/unwrap off exact gridpoints
CUTOFF_MM = 10.0
SEED = 20260711


def build() -> dict:
    rng = np.random.default_rng(SEED)
    data: dict = {"theta_deg": np.float64(THETA_DEG),
                  "ladder": np.asarray(N_PERIODS_LADDER, dtype=float),
                  "sigma": np.float64(SIGMA), "cutoff_mm": np.float64(CUTOFF_MM)}

    world_x, world_y = reconstruct.pixel_to_world(SHAPE, THETA_DEG)
    height_true = surfaces.SURFACES["rough"](world_x, world_y)
    data.update(world_x=world_x, world_y=world_y, height_true=height_true)

    data["wrap_in"] = rng.uniform(-12.0, 12.0, SHAPE)
    data["wrap_out"] = reconstruct.wrap_to_pi(data["wrap_in"])

    psis, lambdas = [], []
    for n in N_PERIODS_LADDER:
        lam = reconstruct.equivalent_wavelength_mm(n, THETA_DEG)
        carrier = reconstruct.carrier_phase(world_x, n)
        phi = carrier + height_true * 2.0 * np.pi / lam
        deltas = 2.0 * np.pi * np.arange(N_STEPS) / N_STEPS
        frames = np.stack([0.5 + 0.45 * np.cos(phi + d) for d in deltas])
        frames = frames + rng.normal(0.0, SIGMA, frames.shape)
        psi, mod = reconstruct.psi_from_frames(frames, n, world_x)
        tag = f"n{n:g}"
        data[f"frames_{tag}"] = frames
        data[f"carrier_{tag}"] = carrier
        data[f"lambda_{tag}"] = np.float64(lam)
        data[f"psi_{tag}"] = psi
        data[f"mod_{tag}"] = mod
        psis.append(psi)
        lambdas.append(lam)

    data["height_multifreq"] = reconstruct.unwrap_multifreq(psis, lambdas)
    dx, dy = reconstruct.pixel_pitch_mm(SHAPE, THETA_DEG)
    data["pixel_pitch"] = np.array([dx, dy])

    valid = np.ones(SHAPE, dtype=bool)
    rough, form = roughness.gaussian_highpass(
        data["height_multifreq"], valid, dx, dy, CUTOFF_MM)
    data["rough"] = rough
    data["form"] = form
    params = roughness.areal_parameters(rough, valid)
    data["areal_keys"] = np.array(sorted(params))
    data["areal_values"] = np.array([params[k] for k in sorted(params)])

    data["hidden"] = occlusion.camera_hidden_mask(height_true, world_x, dx)
    return data


def main() -> None:
    data = build()
    np.savez_compressed(FIXTURE, **data)
    rms = float(np.sqrt(np.mean(
        (data["height_multifreq"] - data["height_true"]) ** 2)))
    sa = dict(zip(data["areal_keys"].tolist(), data["areal_values"]))["Sa_um"]
    print(f"wrote {FIXTURE.name} ({FIXTURE.stat().st_size / 1024:.0f} KiB): "
          f"{len(data)} arrays, shape {SHAPE}, ladder {N_PERIODS_LADDER}")
    print(f"recovery bar: height rms {rms * 1000:.2f} um vs truth; "
          f"texture Sa {sa:.2f} um")


if __name__ == "__main__":
    main()
