# GUI Simulation Analysis — Fringe Projection Digital Twin

> **Phase 2 reference doc — GUI STATE, not direction.** This file describes *what the
> GUI simulation does and the math behind it*, as-built. It carries **no roadmap and no
> future tasks** — that is the separate `handoff` doc's job. Read this to understand the
> system cold; read the handoff to know what to do next.
>
> **As-of:** commit `b957ed9` (Projector swap 5c) · **442 tests passing** ·
> `[pipeline] std_err` byte-identical **1.764505e-05** · doc dated 2026-06-09.
>
> **Frozen / append-mostly.** This doc grows only when the simulation gains real new
> capability; re-stamp the header (commit + test count + date) when it does. Citations are
> `file:line` against the tree at `b957ed9`; thesis equations are Samara Ch.2/4. Code is the
> source of truth — where this doc and the frozen `PROJECT_CONTEXT.md`/`CONVERSATION_SUMMARY.md`
> disagree, the code wins.

## 0. Orientation — what the whole system is

A **fringe-projection (FPP) 3D-measurement digital twin**: a PyQt6 GUI wrapped around a
pure-NumPy math core that simulates the full measurement chain — project sinusoidal fringes,
phase-shift, capture, recover a height map — and the project's headline contribution, the
**inverse-FPP correction** (a pre-distorted "inverse grating" that nulls the non-telecentric
projector's perspective bias and turns reconstruction into golden-part defect detection). The
twin runs **forward** (height → fringes → recovered height) and **inverse** (reference →
inverse grating → project → recover deviation). The GUI lets a user pose the camera and
projector arms at arbitrary angles, swap the projector (Pico Genie ⇄ Wintech PRO4500), browse
full-scale STL specimens, and compare recovered surfaces against ground truth. The math core is
sealed in pixel-space and validated by a byte-identical regression seal (`std_err
1.764505e-05`); the visualization/geometry layer sits strictly downstream of it.

The thesis basis is **Ayman Samara, Ch.2 (theory) + Ch.4 (practical)**. The operative equations
are **Eq. 2-44** (projector perspective bias), **Eq. 2-46/2-47** (phase↔height), **Eq. 2-51**
(two-angle equivalent wavelength), and **Eq. 4-2…4-7** (the tilt-flip inverse-grating
calibration).

---

## 1. Architecture map — the sealed core and the downstream viz layer

**Summary.** Two layers with a strict one-way dependency. The **math core** is pure NumPy,
pixel-space, headless, and never imports anything GUI/geometry. The **visualization/GUI layer**
(PyQt6 + pyqtgraph + the mesh/collision modules) imports *from* the core but the core never
imports *from* it. This is the §7.11 invariant — visualization is decoupled from the math
pipeline — and it is what lets every body/mesh/collision change be proven harmless to the sealed
`std_err`.

### 1.1 The sealed math core (`src/*.py`, no GUI imports)

| Module | Role |
|---|---|
| `pipeline.py` | Orchestration: `run_pipeline` (forward), `run_inverse_fpp` (corrected), `run_straight_fringe` (uncorrected baseline). |
| `geometry.py` | `HybridGeometry`/`SymmetricGeometry`: λ_eq (Eq. 2-51), `height_to_phase`/`phase_to_height` (Eq. 2-46/47), the pixel↔µm scale-bridge constants (labeling-only). |
| `synthetic_fringes.py` | Forward model: `project()` (Eq. 2-44 bias, taylor/exact) + `synthesize_psi_stack()` (the N-step intensity stack + fade/noise). |
| `phase_shifting.py` | `extract_phase()` — the N-step arctan2 wrapped-phase solve. |
| `unwrapping.py` | `unwrap_2d()` — row-then-column `np.unwrap`. |
| `calibration.py` | `fit_tilt_plane`/`fit_tilt_line_1d` (self-cal) + `compute_inverse_phase` (the tilt-flip, Eq. 4-7). |
| `pattern_generator.py` | `inverse_grating_phase()` — projector-side framing over `compute_inverse_phase`. |
| `reconstruction.py` | `recover_object_height()` — extract→unwrap→detrend→height. |
| `sampling.py` | `contrast_envelope()` — the sinc pixel-area fade. |
| `showcase_metrics.py`, `test_surfaces.py`, `io_utils.py` | Headline ratios, test surfaces/defect, the B.4 serializable reference. |

`pipeline.py:41-46` shows the core's entire import surface: `calibration`, `pattern_generator`,
`phase_shifting`, `reconstruction`, `synthetic_fringes`, `unwrapping` — all pure-NumPy siblings.
No `gui`, no `scene`, no `clip_detection`.

### 1.2 The downstream visualization / geometry layer

- **GUI** (`src/gui/`): `main_window.py` (the window + the central `_refresh_surface_preview`
  slot), `stages_view.py`, `comparison_view.py`, `stl_browser.py`, `surface_preview.py`,
  `surface_render.py`, `coordinate_grid.py`, `app.py` (entry point).
- **Hardware twin geometry** (pure NumPy, but downstream of the core conceptually):
  `scene.py` (mesh builders + `ProjectorProfile`), `scene_compose.py` (arm transforms),
  `hardware_scene.py` (pose composition + `HardwareScene`), `clip_detection.py` (collision/coverage advisories).

These import *from* the core (e.g. `main_window.py` imports `geometry`, `pipeline`,
`pattern_generator`, `calibration`, `synthetic_fringes`, `showcase_metrics`).

### 1.3 The one-way dependency — proven

A grep for any import of `gui`, `scene`, `clip_detection`, or `hardware_scene` across **all**
core modules (`pipeline, calibration, pattern_generator, phase_shifting, reconstruction,
synthetic_fringes, unwrapping, geometry, sampling, scene_compose, showcase_metrics,
test_surfaces, io_utils, stl_loader`) returns **zero matches**. The core is reachable from the
viz layer but never reaches back. Consequence: **no mesh/profile/collision constant is on any
path to `std_err`** — the basis for the sealed-core seal (§6.1). Reinforced by an explicit
no-leak guard test (`tests/test_no_leak_scale_bridge.py`) that forbids the scale-bridge constant
names from appearing in the sampling path (`sampling.py:35-36`).

---

## 2. The math — full derivations

### 2a. Forward FPP — fringe → phase-shift → wrapped phase → unwrap

**Summary.** A vertical sinusoidal carrier `(2π/p)·x` is summed with the height-induced phase
`h/λ_eq`, optionally biased by the projector model, then sampled into N phase-shifted intensity
frames `I_k = A + B·cos(φ + δ_k)`. The wrapped phase is recovered by an N-step least-squares
arctan2 in which **both the DC offset A and the contrast B drop out**; row-then-column
`np.unwrap` lifts it to a continuous phase; multiplying by λ_eq returns height.

**Carrier + object phase.** The carrier is `(2π/p)·x` with `x = arange(W)` in pixels
(`pipeline.py:111-113`; the base pattern `0.5·(1+cos(2πx/p + δ))` lives at `geometry.py:154-157`).
Height enters via `height_to_phase`: `ψ = h / λ_eq` (`geometry.py:268`), so
`φ_object = carrier + h/λ_eq` (`pipeline.py:114`).

**Phase-shift synthesis.** For evenly spaced `δ_k = 2πk/N` (`pipeline.py:107`),
`I_k = A + B·cos(φ + δ_k)` (`synthetic_fringes.py:196`, defaults `A=1.0, B=0.9`). The
stages-view caption states it as `I = A + B·cos[2π·x/p + h/λ_eq + δ_k]` (`stages_view.py:124`).

**Wrapped-phase extraction (the arctan combination).** `extract_phase` computes
(`phase_shifting.py:17-18, 62-66`):

```
φ_wrapped = arctan2( −Σ_k I_k·sin δ_k ,  +Σ_k I_k·cos δ_k )
```

*Derivation (why A and B divide out).* Expand `I_k = A + B(cos φ·cos δ_k − sin φ·sin δ_k)`. For N
shifts uniformly spaced on `[0, 2π)`, `Σ cos δ_k = Σ sin δ_k = 0` and
`Σ cos²δ_k = Σ sin²δ_k = N/2`, `Σ sin δ_k cos δ_k = 0`. Therefore
`Σ I_k cos δ_k = (BN/2)·cos φ` and `−Σ I_k sin δ_k = (BN/2)·sin φ`. The DC term A vanishes (it
multiplies `Σ cos δ_k = 0`); the contrast B survives only as a **common positive scale** `BN/2`
that `arctan2` is invariant to. So `arctan2 → φ`, independent of A and of the value of B. This
is the algebraic root of two later facts: (i) the **contrast envelope** `B·env` divides out
losslessly when `env > 0` (§3.1), and (ii) the canonical 4-step case reduces to
`arctan2(I_4 − I_2, I_1 − I_3)` (`phase_shifting.py:39-43`).

**Unwrapping.** `unwrap_2d` = `np.unwrap(np.unwrap(wrapped, axis=1), axis=0)` — rows (x) first
because the fringes run vertically and the largest jumps are along x, then columns
(`unwrapping.py:22-46`; `stages_view.py:139`).

**Phase → height.** `phase_to_height`: `h = ψ · λ_eq` (`geometry.py:286`) — a bare multiply, no
explicit `/(2π)`, because the 2π is folded into λ_eq (see §2b and the naming note below).

### 2b. The two-angle equivalent wavelength λ_eq (Eq. 2-51)

**Summary.** λ_eq converts phase to height. The general non-telecentric two-angle form sums the
tangents of *both* arm tilts. The crucial, often-misread fact: the **telecentric camera adds no
perspective bias when tilted** — `θ_camera` enters only as a triangulation angle in λ_eq, while
the **non-telecentric projector arm is the sole source of the perspective bias** that the inverse
grating corrects.

**The formula** (`geometry.py:187, 230-251`):

```
λ_eq = M · p / ( 2π · ( tan θ_projector + tan θ_camera ) )      (Eq. 2-51)
```

Both arm angles are independent inputs; they contribute **additively through their tangents**.
`equivalent_wavelength()` returns this, or a `lambda_eq_override` when the empirical
calibration path is used (Ch.4 §4.3.1; `geometry.py:246-247`).

**Why the camera adds no bias.** A telecentric lens locks magnification M independent of object
distance; it does **not** imply the camera body is vertical. The earlier single-angle form
`M·p/(2π·tan θ_projector)` silently assumed `θ_camera = 0` by conflating "telecentric lens" with
"vertical mount" — corrected in Stage 3.5 to the two-angle form (`geometry.py:58-66, 185-192`).
So `θ_camera` is a *triangulation* angle (it changes height sensitivity via λ_eq), **not** a
bias term; the projector's `project()` is the only place a perspective bias is injected, and it
reads only `θ_projector` (`synthetic_fringes.py:14-16, 93-94`).

**Degenerate case.** When `tan θ_projector + tan θ_camera = 0` (both arms vertical, or
equal-and-opposite), triangulation has no angular separation and λ_eq → `inf`
(`geometry.py:248-251`); the GUI surfaces a "no height sensitivity" condition via `math.isinf`.

**Special/superseded forms.** Symmetric `θ_proj = θ_cam` collapses to Eq. 2-52,
`M·p/(4π·tan θ)` (`geometry.py:48-49, 352-355`). The old Eq. 4-11 **sin** form
`M·p/(4π·sin θ)` (notebook cell 14) was replaced by the **tan** form in Stage 3.5
(`geometry.py:50-52`).

**Two convention gotchas to carry:**
- **λ_eq naming.** The displayed/textbook Eq. 2-51 has an explicit `× ψ/(2π)`; the code folds
  that 2π into `equivalent_wavelength()`, so it returns `λ_textbook/(2π)` and `phase_to_height`
  is a plain multiply (`main_window.py:1047-1053`; PROJECT_CONTEXT §9 "λ_eq naming convention").
  The stages-view caption shows the textbook `h = λ_eq·(ψ−ψ_cal)/(2π)` form (`stages_view.py:146`).
- **Magnification convention.** Modern `M = sensor/object = 0.09` (Edmund #58-259); the thesis
  uses the inverse `M_chapter = 1/M ≈ 11.1`. Conversion happens at equation boundaries
  (`geometry.py:10-15`). The *operational* pipeline runs `M = 1.0` in sealed pixel-space; the
  real 0.09 lives only as the labeling-only scale bridge (§2e).

### 2c. Inverse FPP / adaptive nulling — the inverse grating

**Summary.** Given a reference measurement's phase, project a **pre-distorted** grating
`φ_inverse = 2·P − φ_ref` (keep the linear carrier `P`, flip the curvature). When that pattern
is projected through the *same* biased projector, the projector's quadratic bias and the
reference's flipped curvature cancel **exactly** (because the bias is affine in the phase
argument), leaving a clean carrier the self-cal removes. With a flat reference this nulls the
projector bias; with a **golden part** reference, recovery reduces to `C[object − golden]` — the
**curvature of the deviation**, i.e. defect detection.

**The tilt-flip (single source of truth).** `compute_inverse_phase` (Ch.4 §4.3.1, Eq. 4-7;
`calibration.py:147-173`):

```
φ_inverse(x,y) = 2·P(x,y) − φ_ref(x,y) ,   P = fit_tilt_plane(φ_ref)
```

`pattern_generator.inverse_grating_phase` is a thin projector-side wrapper over it
(`pattern_generator.py:11-16, 44-65`) — one definition of the inverse phase.

**The closed pass** (`run_inverse_fpp`, `pipeline.py:162-166, 259-289`):

```
1. ref_phase = project(carrier, geom) + h_ref/λ_eq
2. φ_proj    = inverse_grating_phase(ref_phase)   = 2P − ref_phase
3. obj_phase = project(φ_proj, geom) + h_obj/λ_eq
4. recover obj_phase via PSI + self-cal           (§2a, §2e)
5. DC-align to h_obj.mean()
```

*Derivation (why the bias cancels exactly).* `project` is **affine** in its phase argument — it
subtracts a bias `b(x)` that does not depend on the phase (`synthetic_fringes.py:96`). Take the
flat reference `h_ref = 0`: `ref_phase = project(carrier) = carrier − b`. Then
`φ_proj = 2P − carrier + b`, and
`project(φ_proj) = φ_proj − b = 2P − carrier + b − b = 2P − carrier`. The bias term `b`
(the quadratic `(4π/p)·x²·tan θ/a`) is gone **exactly**; `2P − carrier` is purely linear, so the
1D self-cal detrend removes it and the recovered height is flat (`pipeline.py:168-176`). For a
**golden** reference the same algebra generalizes to `obj_phase = 2P − carrier + (h_obj − h_ref)/λ_eq`,
so the recovered quantity is `C[h_obj − h_ref]` — a matching part nulls to the carrier; a defect
shows as residual (`pipeline.py:238-249`). The inverse grating is non-identity whenever the
projector is biased and collapses to the plain carrier in the telecentric limit
(`pipeline.py:174-176`).

**The "before" baseline.** `run_straight_fringe` projects the plain carrier with **no** inverse
grating, so the bias lands uncorrected and a 1D self-cal cannot remove the quadratic residual —
recovery is contaminated by ~6 orders of magnitude (`pipeline.py:301-314`). This is the genuine
failing baseline the showcase compares against.

### 2d. The exact vs Taylor projector models

**Summary.** Two interchangeable forms of the projector perspective bias (Eq. 2-44). `taylor` is
the first-order approximation (a subtracted quadratic); `exact` is the full closed form (a
substituted carrier). Both read only `(p, θ_projector, a)` and produce the same `std_err` on the
synthetic showcase — the seal is reported for *both*.

- **taylor** (`synthetic_fringes.py:88-96`; Ch.4 Eq. 4-7, Taylor of Eq. 2-44):
  `bias(x) = (4π/p)·x²·tan θ_projector / a`, then `φ − bias`.
- **exact** (`synthetic_fringes.py:97-120`; Ch.2 Eq. 2-44):
  `carrier_exact(x) = (2π/p)·x / (1 + 2·x·tan θ_projector / a)`, substituted for the carrier.
  Raises `ValueError` if `1 + 2x·tan θ/a ≤ 0` anywhere (small-angle/short-throw assumption
  violated, `synthetic_fringes.py:104-112`).
- **Sign convention.** The `+u` denominator matches the Taylor branch; the thesis Eq. 4-6 prints
  `−u`, which the notebook treats as a sign typo (akin to the missing 2π in Eq. 4-2) — with
  `−u` the Taylor expansion would disagree at leading order (`synthetic_fringes.py:80-86`).

In `run_pipeline` the `model` argument is currently a **no-op** in the object leg (it synthesizes
from `carrier + height_phase` with no `project()` call — `pipeline.py:29-33, 109-117`); the
exact/taylor distinction bites in `run_inverse_fpp`/`run_straight_fringe`, which *do* route
through `project()`. The seal line prints `model=taylor` and `model=exact`, both
`std_err=1.764505e-05` (§6.1).

### 2e. Reconstruction — phase → height, self-cal, the scale bridge, units

**Summary.** `recover_object_height` runs extract → unwrap → subtract a tilt-detrend
(`phi_calibration`) → mean-center → multiply by λ_eq. The detrend is **self-calibration** (fit
the object's *own* row-mean tilt), not a separate flat reference. All math is in pixel-space; the
pixel→µm scale bridge is a display-only label that no math path reads.

**The recovery chain** (`reconstruction.py:72-127`):

```
1. wrapped    = extract_phase(stack, deltas)
2. unwrapped  = unwrap_2d(wrapped)
3. φ_height   = unwrapped − φ_calibration
4. φ_height  −= φ_height.mean()
5. height     = geometry.phase_to_height(φ_height)   ( = φ_height · λ_eq )
```

**Self-cal vs cross-cal.** `phi_calibration` is caller-chosen. The operational/notebook path is
`fit_tilt_line_1d` — a 1D `polyfit` on the **object's own** row-mean phase, tiled to 2D
(`calibration.py:97-144`). `m_y = 0` is **intentional**: a 2D plane fit would let an off-center
bump bleed into a y-slope and contaminate the residual (`calibration.py:108-118`). For a
**golden-part** reference with genuine 2D structure, pass `fit_tilt_plane` (2D lstsq,
`calibration.py:46-94`) instead — the 1D fit cannot remove a real y-tilt
(`pipeline.py:222-231`). The two fits diverge ~4e-5 on the fixture (`calibration.py:32-37`),
which is why the regression test must use `fit_tilt_line_1d`.

**The scale bridge (§7.12, labeling-only).** `OBJECT_SPACE_UM_PER_PIXEL = CAMERA_PIXEL_PITCH_UM /
CAMERA_MAGNIFICATION = 4.8 / 0.09` (`geometry.py:102-104`). These constants exist **only** to
label pixel counts as microns for human display (e.g. "the ~2-px wall sits at ~107 µm
object-space"). They are read by **no** math path — not the carrier, not λ_eq, not `project()`,
not `synthesize_psi_stack` (`geometry.py:86-100`), enforced by a no-leak guard test. The
operational pipeline runs `M = 1.0` in sealed pixel-space; the real 0.09× lives only here as a
display fact (`geometry.py:96-100`).

**DC alignment.** `recover_object_height` returns a mean-centered height; the pipeline re-adds
the input mean (`h_rec − h_rec.mean() + heightmap.mean()`, `pipeline.py:130`) — a synthetic-test
convenience that needs ground truth, not part of the operational chain
(`reconstruction.py:110-118`).

---

## 3. What the sim proves — and its honest limits

**Summary.** The simulation proves the inverse-FPP **consistency** chain end-to-end (composition,
sign, unwrap, self-cal, the bias cancellation) and demonstrates the headline dynamic-range win.
It is explicit about four limits: the beyond-Nyquist wall needs **both** a sampling fade and
read noise to bite; only the **curvature** of a deviation is recovered (not linear tilt, not full
amplitude past Nyquist); end-to-end closure is a **tautology** that cannot catch a 2π-scaling
bug; and the perfect null is an artifact of the same model building *and* correcting.

### 3.1 The beyond-Nyquist wall (fade × read noise)

The wall has **two parts, both required** (`PROJECT_CONTEXT.md:429-431`):

- **The fade.** `contrast_envelope(phase, fill_factor) = |sinc(fill_factor · f_local)|` with
  `f_local = |∇φ|/(2π)` in cycles/pixel from the **local** phase gradient
  (`sampling.py:50-89`). It attenuates frame **contrast** `B·env`, broadcast identically across
  all N shifts (`synthetic_fringes.py:197-199`). Soft, not a cliff: at the 2-px Nyquist period
  (`f=0.5`) the envelope is still `|sinc(0.5)| ≈ 0.637` (`sampling.py:40-43`).
- **Why the fade alone is transparent.** `B·env` is a contrast factor common to all N frames, so
  it **divides straight out** of `extract_phase`'s arctan2 (the same A/B-cancellation as §2a) —
  recovered height is *unchanged* by the envelope on well-sampled data (`pipeline.py:201-206`;
  pinned by `tests/test_inverse_fpp.py:212-226`). The only exception is the singular `env → 0`
  sinc null (`arctan2(0,0)`), a hard degenerate point, not a roll-off
  (`tests/test_inverse_fpp.py:229-248`).
- **The read noise that gives it teeth.** Additive Gaussian noise is applied **after** the
  envelope, `size = (H,W,N)` — **independent per frame** (`synthetic_fringes.py:204-215`).
  Because it is per-frame-independent while `B·env` is common, it does **not** cancel: low
  contrast (faded region) + fixed σ = low SNR = phase error growing `~ σ/(B·env·√N)`
  (`synthetic_fringes.py:173-179`; `pipeline.py:216-218`). An `(H,W)` map broadcast across N
  would cancel like `B·env` and silently defeat the mechanism — pinned by
  `tests/test_inverse_fpp.py:315-342`; the wall biting only the faded region by
  `tests/test_inverse_fpp.py:345-378`; the `√N` averaging by `tests/test_inverse_fpp.py:381-402`.

### 3.2 The two pinned honest bounds

- **(a) A defect whose OWN gradient exceeds Nyquist recovers only ~61%.** When the *deviation
  itself* is steeper than the sampling limit, the inverse grating (built from the reference)
  cannot rescue it — the defect's own fringes fade. The measured recon is ~61% at own-frequency
  0.81 (`PROJECT_CONTEXT.md:441`; convention note `test_surfaces.py:183-185`); the pinning test
  asserts the degraded bound `|dev|.max() < 0.8·steepdef.max()`
  (`tests/test_inverse_fpp.py:573-586`), with the gentle sub-Nyquist defect surviving
  (`tests/test_inverse_fpp.py:552-570`).
- **(b) Pure linear tilt differences are NOT recovered.** The recovered quantity is the
  **curvature** of `object − golden`; a purely linear tilt difference is removed by the self-cal
  detrend (`pipeline.py:245-249`; mirrored in the GUI at `main_window.py:1270-1273`; mechanism at
  `reconstruction.py:122-127`). Fine for local-defect detection (bumps, dents, cracks); not for
  absolute global-tilt metrology.

### 3.3 The validation-tautology limit

The **same** affine `project` model creates the capture and is inverted by the inverse grating
derived from that same model's output, so a passing end-to-end closure proves **CONSISTENCY**
(composition, sign, unwrap, self-cal wired correctly), **not physics**
(`pipeline.py:253-257`; `tests/test_inverse_fpp.py:4-16`; `tests/test_synthetic_fringes.py:240-246`).
A self-consistent *wrong* bias (e.g. a factor-2 or 2π scaling error) would cancel in the loop and
never be caught by end-to-end tests. The antidote is a **different-logic route**:
`tests/test_calibration.py:101-139` builds the expectation from the *geometric definition* of the
tilt-flip (a known curvature `project()` can never emit), so it fails if `2P − φ` is wrong,
independent of `project()`'s bias formula. Physics validation proper is deferred to the
hardware oracle (D.3-vs-B.4 — a real projector whose bias is not the analytic Taylor model).

### 3.4 The perfect-null caveat

A matching golden nulls to ~1e-13 / machine precision (`tests/test_inverse_fpp.py:453-460, 95-99`)
**because the same analytic model is on both sides of the cancellation**. Real hardware will
leave residual; the sim's perfect null must not be over-claimed as a hardware result. The B.4
serializable reference is the designated hardware-phase validation target.

### 3.5 The headline dynamic-range ratios

`showcase_metrics.steep_region_ratios` computes two convention-agnostic ratios over the steep
region (`f_straight > 0.5`): **decoupling** = mean straight-fringe frequency / mean inverse-FPP
frequency (how far below the sampling wall the inverse grating pulls the observed fringe), and
**error_ratio** = steep-region RMS recovery error, straight / inverse (`showcase_metrics.py:23-108`).
The seeded B.3a reference freezes **decoupling = 219**, **error_ratio = 37691** — pinned exactly
as integers (the `.0f` display mirror absorbs ULP) with floats/arrays at `atol 1e-8`
(`tests/test_b4_reference.py`). The headline surface is the steep dome (amp 6000 / σ 60 px, the
only convention that crosses Nyquist; `test_surfaces.py:118-165`).

---

## 4. The GUI — what each view/tab does

**Summary.** One `MainWindow` (`main_window.py:332`) with a left control panel and a right
4-tab pane (3D Scene, Pipeline Stages, STL Browser, Recovered Surface). A single slot,
`_refresh_surface_preview` (`main_window.py:1176`), runs the math and fans results to whichever
tab is current; it re-runs on slider/tab changes.

### 4.1 3D Scene / lab view (`surface_preview.py`, `hardware_scene.py`)

Renders the recovered surface plus the honest-scale hardware bodies (camera + projector + lens
cones) at the live pose. Capabilities:
- **Arbitrary arm angles** `(θ_camera, θ_projector)` via pose sliders → `_on_pose_changed`
  (`main_window.py:1468`), composed by `compute_arm_transforms` (`hardware_scene.py:163`).
- **Projector swap (Pico ⇄ PRO4500)**: dropdown built `main_window.py:714-723`, handler
  `_on_projector_changed` (`:1505`) sets `self._projector_profile` (`:1516`) and rebuilds meshes
  via `SurfacePreview.set_projector_profile` → `HardwareScene.set_projector_profile`
  (`surface_preview.py:254`; `hardware_scene.py:430`).
- **Lens selector** (PRO4500 only): combo `main_window.py:730-737`, `_on_lens_changed` (`:1592`)
  re-locks the throw slider to the chosen lens WD; hidden for the single-lens Pico
  (`_populate_lens_combo`, `:1569`).
- **Projection cone + viewing prism**, **clip / coverage / cross-arm-obstruction advisories**
  (the `ClipState` from `detect_clips`, §5.3), and the **hardware-coordinate readout**
  (`arm_lens_front_world`, surfaced at `main_window.py:1495-1503`).
- **FOV presets + custom ROI**: single source `self._fov_shape` (`main_window.py:368`); preset
  and "Custom…" H×W paths both converge on `_apply_fov_shape` (`:2225`); height-first,
  0.1 mm/px grid, browser-only (§6).
- **Angle-invariant recovered surface**: the lab view's recovered leg and the Recovered Surface
  tab both call the shared `_recover_part_surface` producer (`:1372`) — the lab view forcing
  `inverse_on=True` and a clean `part=golden` (`:1353-1357`); this is why the rendered surface
  does **not** change shape under projector tilt (the §7.18 angle-invariant nulling, made
  visible). Note: one refresh runs `run_pipeline` (`:1235`) **and** `run_inverse_fpp` (via
  `_recover_part_surface`, `:1405`) — the ~2× pipeline cost per refresh.
- **Honest scale**: `Z_EXAGGERATION = 1.0` (`surface_preview.py:78`) — bodies, cones, and surface
  share one frame (§6.9).

### 4.2 Pipeline-Stages view (`stages_view.py`)

A 2×3 grid of 2D `ImageView` panels showing the pipeline intermediates with equation captions —
ground truth, projected fringe frame, wrapped phase, unwrapped phase, recovered height
(`stages_view.py:96, 160`). Pure sink: fed by `run_pipeline(..., return_stages=True)`
(`main_window.py:1247-1257`). The captions are the in-GUI statement of §2a's algebra
(`stages_view.py:117-146`).

### 4.3 STL Browser mode (`stl_browser.py`)

FOV-by-FOV navigation of oversized STLs via a three-panel layout: whole-STL 3D context with a
cyan FOV highlight, a top-down minimap with a **draggable** FOV rectangle, and a windowed 3D
slice (`stl_browser.py:167, 336, 386, 415`). A "Commit FOV" button promotes the windowed slice
into the measurement (`commit_fov_requested` → `main_window.py:2134` → refresh). Display strides
cap vertex/pixel counts for large meshes (`stl_browser.py:84, 360-363`).

### 4.4 Recovered Surface tab (`comparison_view.py`)

A `GLViewWidget` drawing the opaque recovered surface and the translucent ground-truth surface
over a labeled coordinate grid, each show/hide-able, with an optional **color-by-error** mode
(`comparison_view.py:43, 105, 154`). Inputs come from the Recovered branch of
`_refresh_surface_preview`: `tab_recovered = _recover_part_surface(...)`, `error = recovered −
heightmap` (`main_window.py:1299-1327`). Capabilities exposed there: the **sensor-noise toggle**
(`main_window.py:957`, fresh-seeded per call at `:1362`), the **AM defect-detection demo** (inject
`make_demo_defect`, `:1287-1297`), and the **inverse-correction checkbox** (`:944`, drives
`inverse_on=`). The **B.4 serializable reference** numbers (decoupling/error-ratio) are computed
by `showcase_metrics.steep_region_ratios` via `_update_dynamic_range_readout`
(`main_window.py:1647, 1684`), the single core the GUI readout and the saved reference both call.

---

## 5. The hardware digital twin (geometry)

**Summary.** A `ProjectorProfile` system drives the projector body+lens meshes from data, so a
projector swap is a profile change, not a geometry rewrite. The camera is a fixed FLIR body + the
verified Edmund #58-259 telecentric lens. Four advisory checks (`clip_detection.py`) test the
posed bodies for collisions and coverage.

### 5.1 The `ProjectorProfile` system (`scene.py`)

`ProjectorProfile` (frozen dataclass, `scene.py:189-236`) carries `body_dims_mm`,
`lens_diameter_mm`, `lens_length_mm`, `lens_face_offset_mm`, a `lens_options` table, and
`default_lens_index`. The registry `PROJECTOR_PROFILES = (PICO_GENIE, WINTECH_PRO4500)`
(`scene.py:282`) is mirrored by the GUI dropdown. Mesh builders take a profile:
`make_projector_body/lens(profile=PICO_GENIE)` — no-arg byte-identical to the Pico defaults
(`scene.py:285, 596-619`). A `LensOption` is a `(working_distance, fov_w, fov_h,
projected_pixel_um)` row (`scene.py:160-186`).

- **Pico Genie** (`scene.py:243-249`): 55³ mm body, 20×5 mm lens stub, offset (−6.5, 17.5, 1.5),
  single throw-ratio lens (no `lens_options`).
- **Wintech PRO4500, as-built** (`scene.py:266-277`): body **84×54×145 mm**; the lens is a
  **30 mm-dia × 65 mm protruding barrel** modeled *as the lens mesh* (`lens_diameter_mm=30`,
  `lens_length_mm=65`), so 145 body + 65 barrel = 210 total optical-axis reach; lens centered
  horizontally but **7 mm below** the 54 mm-height center (`lens_face_offset_mm=(0,−7,2)`); two
  field-swappable lenses (92 mm / 184 mm WD), default 184 mm (full camera coverage). Both lenses
  share cone half-angle `(65.6/2)/92 == (131.2/2)/184 == 0.3565` (lens choice changes
  WD/footprint, not cone slope).

### 5.2 Camera + telecentric lens (`scene.py`)

- **Camera body** FLIR Blackfly S: 29×29×30 mm (`scene.py:146`).
- **Edmund #58-259 telecentric lens** — verified geometry: stepped 3-section, 200 mm total
  (76 mm rear @55 dia + 59 mm taper + 65 mm front @110 dia), `make_camera_lens`
  (`scene.py:563-593`), confirmed against the official GoldTL spec table (§ PROJECT_CONTEXT §2).

### 5.3 Clip-detection advisories (`clip_detection.py`)

`detect_clips` (`clip_detection.py:525`) runs three collision checks (gray the offending bodies)
plus three banner-only coverage/obstruction advisories. What each consumes:
- **Lens-front disc vs surface (checks 1 & 2)** — `_lens_front_disc_lowest_z`
  (`clip_detection.py:296`): the tilted lens-front disc's lowest world-z vs the z=0 plane. For
  the projector this is now **profile-aware** — front-z and radius derive from the **same**
  `local_corners[KEY_PROJECTOR_LENS]` the SAT box uses (front-z = max local-Z = lens_length/2 =
  32.5; radius = max local-X = lens_diameter/2 = 15 for the PRO4500 barrel), with the camera and
  no-profile Pico path on the module-dict literals (§6.3).
- **Body-overlap (check 3)** — `_obb_overlap` SAT over the four camera/projector body+lens pairs,
  corners derived from `make_projector_body/lens(profile)` so the barrel is tracked
  (`clip_detection.py:320, 588-595, 637-646`).
- **Coverage (checks 4 & 5)** — surface samples vs the viewing-prism / projection-cone *volumes*
  (`_points_in_prism`/`_points_in_cone`, `clip_detection.py:397, 434`); 2 mm advisory tolerance
  on the cone (real edge falloff), exact on the telecentric prism.
- **Cross-arm obstruction (check 6)** — each assembly's body+lens box edges sampled (7 pts ×
  12 edges) against the *other* arm's optical volume, axially bounded to the lens→surface segment
  (`clip_detection.py:251, 676-712`).

### 5.4 Pose composition & the lens-front invariant (`hardware_scene.py`, `scene_compose.py`)

`compute_arm_transforms` (`hardware_scene.py:163`) places each body+lens along its arm:
`body_distance = throw + lens_length + body_depth/2` (`:248-252`); the lens-front/cone-apex sits
at `body_depth/2 + lens_length − recess` along local +Z (`scene_compose.py:254`). Body-depth and
lens-length **cancel** between these two consumers, so the projector lens-front lands at
`throw + recess` regardless of how the total reach is split into body vs barrel — the cancellation
invariant (§6.2).

---

## 6. Invariants & locked decisions — the cross-session danger zone

**Do not reopen these.** Each is a settled decision with a load-bearing reason; re-litigating them
silently breaks the seal or a hard-won correctness property.

### 6.1 The sealed-core seal — `std_err` byte-identical 1.764505e-05
The synthetic showcase prints `[pipeline] model=taylor std_err=1.764505e-05 (baseline=...)` and
the same for `model=exact` (`tests/test_pipeline_synthetic.py`, `tests/test_inverse_fpp.py`). It
measures the recovered-vs-truth error of the sealed pixel-space pipeline. **Every viz/geometry/
mesh/profile change must preserve it byte-for-byte** — guaranteed structurally by the one-way
dependency (§1.3), checked by running the seal after any change. *Why:* it is the single objective
proof that a visualization change did not perturb the math.

### 6.2 The cancellation invariant — lens-front = throw + recess
Projector body-depth and lens-length cancel in both the body-distance and the cone-apex consumers
(`hardware_scene.py:248-252`; `scene_compose.py:196, 254`), so the lens-front holds at
`throw + recess` no matter how the 210 mm reach is partitioned into body + barrel. *Why:* it is
what made the PRO4500 reshape (body 210→145 + a 65 mm barrel) provably throw-neutral; **re-verify
it whenever projector profile geometry changes** (the `[0,0,186]` canary tests).

### 6.3 Single source of truth for disc geometry
The projector disc-clearance front-z/radius derive from the **same** `local_corners` the SAT box
uses (`clip_detection.py`), never hardcoded per-profile. *Why:* the disc tip/radius can then never
disagree with the SAT box; the no-profile path keeps the Pico module-dict literals
(byte-identical).

### 6.4 Canonical profile, not `replace()`
`self._projector_profile` stays the literal `PICO_GENIE`/`WINTECH_PRO4500` object
(`main_window.py:374`); the active lens is carried separately by `self._active_lens_index`
(`:379`), threaded as an int (None→`default_lens_index`, byte-identical). *Why:* preserves
mesh-rebuild identity guards and test identity; `dataclasses.replace()` would break them.

### 6.5 FOV custom entry — height-first, persist-not-reset, browser-only
`_fov_shape = (H_px, W_px)` height-first throughout; 0.1 mm/px grid; `_fov_shape` does **not**
reset on surface switch; FOV widgets enabled only in Browser mode; the camera prism stays
hardcoded 68×55 mm (custom FOV is a measurement-planning ROI, not the prism)
(`main_window.py:368, 2225, 2284`). *Why:* consistency with the preset path and with the
height-first label convention.

### 6.6 STL-browser gate on `currentText() == STL_LABEL`
The browser-mode blocks in `_refresh_surface_preview` gate on the combo text, **never** on the
`_stl_is_browser_mode` flag alone (`main_window.py`). *Why:* a stale flag after an STL→procedural
switch applied a shrunken FOV mask to a full-size array → swallowed IndexError → frozen view (the
bug fixed in `25d93b5`).

### 6.7 PRO4500 dual-lens shared cone half-angle
Both PRO4500 lenses have equal `(fov/2)/WD = 0.3565` (`scene.py:272-276`). *Why:* lens choice
changes WD/footprint/apex-height, **not** the cone slope; coverage math keys off the half-angle.

### 6.8 The −7 mm vertical lens offset — confirmed sign
`lens_face_offset_mm[1] = −7` for the PRO4500 (lens 20 mm up from the 54 mm-height bottom = 7 mm
below center; body-local +Y is "up the face"), confirmed by in-GUI render (lens visibly below
body center). *Why:* it is the PRO4500's measured sign, no longer the Pico's inherited-UNVERIFIED
guess (the Pico's own face-vertical sign stays separately unverified).

### 6.9 `Z_EXAGGERATION = 1.0` — permanent honest scale
`surface_preview.py:78`. Bodies, cones, and the recovered surface render in one un-exaggerated mm
frame. *Why:* the lab view is a metrology digital twin; any z-stretch would make the
clip/coverage advisories lie.

### 6.10 `numpy-stl` via pip, not conda-forge
STL loading depends on `numpy-stl` installed through **pip**, not conda-forge. *Why:* the
conda-forge build introduced an ABI mismatch that crashed STL import (the Stage-4c environmental
hazard, recorded in the frozen archive); kept here so a fresh environment setup does not reopen it.

---

*End of GUI Simulation Analysis. State reference only — for what to do next (hardware integration,
the abstract-proposal model), see the `handoff` doc.*
