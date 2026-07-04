# Hardware integration (projector + camera)

The app drives the rig through a `Backend` (see `app/backend/base.py`). Two
implementations satisfy the same interface, so the UI is identical either way:

- **`SimulationBackend`** — renders the capture stack with Blender and scores
  the reconstruction against a known ground-truth surface.
- **`HardwareBackend`** — projects the fringe on a real projector and grabs
  frames from a real camera. A live target has no ground truth, so it produces
  a height map only.

Swapping between them is a launch-time choice, not a code change.

## Choosing the backend

`MP_BACKEND` selects it:

| value        | behaviour                                                        |
|--------------|------------------------------------------------------------------|
| `sim` (default) | Blender + scored reconstruction                               |
| `hardware`   | real projector + camera                                          |
| `auto`       | hardware **iff** a FLIR camera is attached, else sim             |

```sh
python app/main.py                 # simulation
MP_BACKEND=hardware python app/main.py
MP_BACKEND=auto    python app/main.py   # go live just by plugging the camera in
```

## The projector (used as a second screen)

The projector is driven as an ordinary external display: connect it over HDMI,
extend the desktop (do **not** mirror), and the app puts a borderless,
black-background fullscreen window on the non-primary screen. No projector SDK
is involved — see `app/hardware/projector.py`.

- With no second display attached, projection falls back to a small windowed
  preview on the primary screen so you can still bench-test. Connect the
  projector as a second screen for real use.
- Patterns are generated at the projector screen's native resolution and shown
  pixel-for-pixel (no smoothing), so the sinusoid the camera images is exactly
  the one generated. Press **Esc** on the projection to dismiss it.

macOS note: this is the same "extend, then fullscreen a window on it" approach
the Windows rig used — QScreen exposes the external display identically.

## The camera

`MP_CAMERA` selects the driver (`app/hardware/camera.py`):

| value            | camera                                                        |
|------------------|---------------------------------------------------------------|
| `auto` (default) | FLIR if attached, else the **synthetic** camera               |
| `spinnaker`      | FLIR / Teledyne via PySpin (Mono8)                            |
| `opencv`         | any USB / UVC webcam (bench stand-in)                        |
| `dummy`          | synthetic phase-stepped fringe (no device; tests + demos)    |

The synthetic camera lets the whole project → capture → reconstruct loop run
with no hardware at all (it's what the tests use). `auto` never silently grabs a
laptop webcam — it uses the synthetic camera unless a FLIR is present.

### Installing PySpin (the FLIR SDK)

PySpin ships as a platform-specific wheel from Teledyne, not PyPI. The Windows
build is vendored under `.archive/spinnaker_python-*`; install the matching
wheel for your platform + Python version into the venv:

```sh
pip install <spinnaker_python-4.3.0.189-cp310-...>.whl
```

The app runs fine without it — PySpin is imported lazily and its absence just
means the FLIR backend isn't offered.

## Tuning knobs

| env var                 | default | meaning                                       |
|-------------------------|---------|-----------------------------------------------|
| `MP_CAM_EXPOSURE_US`    | (auto)  | fix the FLIR exposure in µs (recommended for phase-shifting, so every step is imaged at identical brightness) |
| `MP_CAPTURE_SETTLE_MS`  | `200`   | wait per step after the pattern is shown, before grabbing (projector refresh + exposure settle) |
| `MP_BLENDER`            | (auto)  | path to the Blender executable (simulation capture) |

## Auto-exposure and the phase-shift scan

The N-step phase-shifting algorithm assumes every frame in the stack is imaged
at the *same* exposure. **Leave auto-exposure off.** If it's on, the camera
re-meters between frames, and because the fringe pattern shifts each step the
metered brightness swings -- so each frame picks up a different gain. That is
*not* random noise; it's a systematic per-frame weighting that biases the
recovered phase and prints a periodic ripple into the height map. In simulation,
a 5% brightness swing inflates the reconstruction RMSE from a few µm to ~45 µm.

Two layers of defense:

1. **Lock the exposure** -- set `MP_CAM_EXPOSURE_US` so the FLIR camera runs at a
   fixed exposure (`SpinnakerCamera` turns `ExposureAuto` off when it's set).
   This is the real fix.
2. **Gain normalization** (on by default) -- the reconstruction estimates any
   residual per-frame gain from each frame's brightness and divides it out
   before the PSA. It's a no-op on a steady stack, so it only ever helps. See
   `simulation/exposure.py`.

The **Error Analysis** panel quantifies both this and random noise: it reports
the measured brightness swing, and (in simulation, against a known injected
swing) the reconstruction RMSE with and without the correction -- so you can see
the swing's cost directly.

## Multi-frequency scanning (toward roughness)

Roughness measurement needs a small equivalent wavelength (dense fringes) for
vertical resolution, but a dense map alone wraps ambiguously on anything taller
than λ_eq/2. **Run Multi-Freq** captures a coarse→fine *ladder* of frequencies
(`geometry_constants.N_PERIODS_LADDER`, default n = 8 → 24 → 80, λ_eq 13.6 → 1.4 mm)
and reconstructs by temporal phase unwrapping: the coarse rung fixes the range,
each finer rung's 2π ambiguity is resolved by the running (coarser) estimate.
The result is the finest rung's resolution (~10× the coarse rung) without its
ambiguity — the basis for separating a large *form* from the fine *roughness*
on top (the Chapter 3 multi-frequency method).

- Mechanically it's just N ordinary captures: each rung lands in
  `out/app/<surface>/capture_f<i>`, then `reconstruct_multifreq` unwraps them.
  Identical on simulation (a Blender render per rung) and hardware (a
  project-and-grab per rung) — same as the single-frequency pipeline, repeated.
- A pixel is trusted only where **every** rung is well modulated (the per-rung
  masks are intersected), so a dim or washed-out region drops out of all of them
  at once rather than contributing a mis-unwrapped height.
- Maestro: `run_multifreq` (capture + reconstruct) and `reconstruct_multifreq`
  (re-unwrap an already-captured ladder without re-capturing).

**Run Multi-Freq** ends with a **roughness** readout in the Roughness view: the
form (waviness) is removed with an ISO 25178 Gaussian filter (cutoff 10 mm by
default) and the residual is reported as areal **Sa / Sq / Sz**, with a noise
floor and a noise-corrected Sq from the finest rung's height uncertainty (so a
near-1 SNR flags a roughness that's mostly noise). For a known simulation
specimen the parameters are scored against ground truth. Maestro:
`measure_roughness` (`cutoff_mm` overrides the form/roughness cutoff) runs it off
the latest reconstruction. This rig targets Sa/Sq in the tens-of-µm band (mid-
spatial waviness, not sub-micron finish). Tested against a real Blender camera
render, the texture is recovered faithfully in amplitude and shape, but the
roughness *map* is laterally mis-registered ~0.5 mm by the nominal geometry
(correlation 0.73 → 0.92 once that offset is removed) — so the limit is geometry
**calibration**, not fringe density or noise (a denser rung was tried and did
nothing). See `report/math.tex` §"Roughness under a real camera".

## Geometry calibration

The reconstruction otherwise trusts the **nominal** geometry
(`simulation/geometry_constants.py`: a constant λ_eq, the analytic carrier).
`simulation/calibration.py` replaces that with a **measured** phase-to-height
map: image a flat plane at several known heights z (a z-stage; in sim,
`capture_pipeline --z-offset`) and fit, per pixel, `psi = c0 + k·z`, then
reconstruct via `z = (psi − c0)/k`. `k(p) = dpsi/dz` is a per-pixel λ_eq that
absorbs the projector's perspective, which a single nominal λ_eq misses.

```sh
# render z-planes, then:
python simulation/calibration.py --plane-dirs out/cal/z-0.5 out/cal/z0 out/cal/z0.5 \
    --z-values -0.5 0.0 0.5 --n-periods 80 --out out/cal/calib.npz
```

A **lateral** pixel→world map is calibrated separately from a dot-grid target
(`capture_pipeline --target-dots`, dots at known world positions): detect the
centroids, fit an affine. That fit *confirmed the nominal map is already correct*
(to ~0.05 mm) — so the ~0.5 mm offset isn't a mapping error, it's **parallax**
(the tilted camera images a point at height h shifted by `h·tanθ` in x). Adding
that analytic correction (`reconstruct_calibrated(parallax=True)`) closes it.

Validated against a Blender camera render (known true geometry), the three
corrections compound — `rough` height RMSE **134 → 24 → 8.4 µm** (nominal →
vertical → vertical+lateral+parallax, R² 0.85 → 0.995 → 0.9994), roughness-map
registration 0.73 → 0.99. The only measured inputs are a z-plane sweep and one
dot-grid frame — the exact procedure a real rig runs. See `report/math.tex`
§"Geometry calibration". On hardware these replace the nominal constants;
capturing and reconstruction work today, calibration makes the map accurate.
