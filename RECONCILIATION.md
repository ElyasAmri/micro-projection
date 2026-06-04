# Reconciliation: `micro-projection` → `fringe-projection-3d`

Gap analysis and merge plan for folding our work (`micro-projection`, the "app/sim"
repo) into Husam's `fringe-projection-3d`, which is now the **canonical base**.

- **Base (canonical):** `fringe-projection-3d` (HusamArdah) — thesis-grounded
  simulation, rigorous geometry, large pytest suite, PyQt6 3D digital-twin GUI.
- **Source of ports:** `micro-projection` (ours) — PRO4500 USB projector control,
  physical-units specs, PySide6 instrument GUI, Blender Cycles simulation.
- **Status:** examination complete; no code merged yet. This doc decides *what*
  moves, *how*, and *in what order*.

---

## 1. Executive summary

The two repos barely overlap in scope, which makes reconciliation mostly
*additive* rather than a conflicting-merge:

- His repo is strong exactly where ours is thin: **theory/geometry, tests, 3D
  visualization**.
- Ours is strong exactly where his is **explicitly unstarted**: **real hardware
  control** (his Stages 6/7, his `Camera`/`Projector` protocols are deferred
  stubs) and **physical-unit hardware specs**.

So the headline move is: **port our hardware layer + physical specs onto his
foundation**, conforming to the `Camera`/`Projector` protocol shapes he already
sketched in `PROJECT_CONTEXT.md §7.3`. Two things gate any merge of the **DSP
core**: a sin-vs-cos fringe-basis clash and a pixels-vs-mm unit clash (§5).

---

## 2. Repo inventory (condensed)

### His — `fringe-projection-3d`
- **DSP core** (`src/`, pure NumPy, pixel units): `geometry.py` (Geometry
  Protocol; `HybridGeometry` operational, `SymmetricGeometry` reference; λ_eq via
  two-angle Eq. 2-51 + `lambda_eq_override`), `synthetic_fringes.py`
  (Taylor/exact projector-bias forward model), `phase_shifting.py`,
  `unwrapping.py` (row-then-col + skimage Goldstein), `reconstruction.py`,
  `pipeline.py`, `calibration.py` (inverse-grating tilt-flip).
- **GUI** (`src/gui/`, PyQt6 + pyqtgraph + PyOpenGL): STL loader, hardware-bodies
  3D scene with live pose sliders, clip/collision/coverage detection,
  recovered-vs-ground-truth comparison + error colormaps, coordinate grids,
  ~71 KB `main_window.py`.
- **Tests:** ~25 pytest files + 5.5 MB regression fixture (`tests/regression_data.npz`).
- **Stubs / not started:** `pattern_generator.py`, `io_utils.py` (empty stubs);
  `Camera`/`Projector` hardware protocols deferred to Stage 6/7 (§7.3); upgraded
  projector "status unknown" (§2).
- **Stack:** Python 3.10, numpy 2.2.6, scipy, scikit-image, numpy-stl, PySpin
  (vendored wheel). No Blender.

### Ours — `micro-projection`
- **App** (`app/src/microprojection/`, PySide6): `acquisition/camera.py`
  (PySpin + OpenCV threads), **`acquisition/projector.py` (DLPC350/PRO4500 USB
  control via pycrafter4500 — NEW)**, `processing/steps.py` + `pipeline.py`
  (sin-based PSA, unwrap, height, filtering, roughness), `core/paper_specs.py` +
  `calibration/priors.py` (**physical mm units; PRO4500 = 305 µm/px, 460 nm,
  FOV 400×250 mm**), `export/report.py`, calibration tab.
- **Simulation** (`simulation/`): Blender Cycles physically-based fringe-projection
  render pipeline (geometry, recording, reconstruction).
- **Tests:** none in the app.
- **Stack:** PySide6, opencv, numpy; optional `[hardware]` extra
  (pycrafter4500 + pyusb); Blender for sim.

---

## 3. Side-by-side comparison

| Dimension | His (base) | Ours (source) | Reconciliation |
|---|---|---|---|
| GUI toolkit | PyQt6 + pyqtgraph + PyOpenGL | PySide6 (2D views) | Keep his; port logic, not widgets (§4f) |
| Simulation | Analytic forward model (Taylor/exact bias) | Blender Cycles raytrace | Complementary — add ours as alt forward model (§4e) |
| Ground truth | STL meshes + comparison | — | Adopt his |
| Geometry/theory | Thesis `Geometry` + inverse-grating cal | `paper_specs` + simple priors | Adopt his; feed our numbers in (§4d) |
| Tests | Large pytest + fixture | None | Adopt his; add tests for ported hardware |
| Units | Pixels internally (pitch exposed) | Physical mm | **Clash — resolve first (§5)** |
| Fringe basis / PSA | cos, `atan2(−ΣIsin, ΣIcos)` | sin, `atan2(ΣIsin, ΣIcos)` | **Clash — resolve first (§5)** |
| Projector control | None (Stage 6/7 stub) | **DLPC350 USB (built)** | **Port — headline (§4a)** |
| Camera | PySpin (vendored wheel) | PySpin + OpenCV | Merge; OpenCV path is a bonus (§4b) |
| Projector specs | Pico Genie (placeholder) | **PRO4500 (the upgrade)** | Port; resolves his "pending" gap (§4d) |

---

## 4. Gap analysis by subsystem

### 4a. Projector hardware control — **headline contribution**
- **His state:** none. `Projector` protocol deferred (§7.3, lists only
  `MockProjector` / `RealProjector` as future); upgraded projector "status
  unknown"; `pattern_generator.py` is an empty stub.
- **Ours:** `acquisition/projector.py` — `ProjectorController` wrapping
  `pycrafter4500` (DLPC350 over USB-HID + libusb): power, video/pattern mode,
  triggered high-speed sequencing, `enumerate_projectors()`, `HAS_PYCRAFTER`
  guard. Optional `[hardware]` extra.
- **Port plan:** introduce his `Projector` protocol concretely, with our
  controller as `RealProjector` (USB pattern mode) and his planned
  `MockProjector` (synthetic / extended-display) alongside. Move the PRO4500
  pattern-mode trigger contract into his Stage 6/7 capture loop. Note: our
  controller goes *beyond* his "extended display" sketch — it drives hardware
  pattern sequencing with per-pattern camera triggers, which his pipeline can
  exploit for fast synced capture.
- **Risk:** low. Net-new code, no conflict. Needs libusb/Zadig on the lab PC.

### 4b. Camera acquisition
- **His state:** PySpin wheel vendored; no live acquisition layer found in `src/`
  (capture is Stage 6).
- **Ours:** `acquisition/camera.py` — `PySpinCameraThread` + `OpenCVCameraThread`
  + `enumerate_cameras()`, QThread-based frame streaming.
- **Port plan:** adapt to his `Camera` protocol (`capture(exposure_ms)->ndarray`).
  Our QThread streaming is PySide6-signal-based; re-home onto PyQt6 signals or
  refactor the SDK calls behind a toolkit-neutral core (preferred — matches his
  §7.2 "pure core, thin Qt layer" discipline). OpenCV path is a useful
  no-FLIR-hardware fallback he lacks.
- **Risk:** medium (Qt-signal re-homing).

### 4c. DSP core (phase → height) — **mostly his, do not double-port**
- His `phase_shifting`/`unwrapping`/`reconstruction`/`pipeline`/`calibration`
  are more complete and **tested**. Ours (`processing/steps.py`) is a simpler
  single-file version.
- **Port plan:** **keep his.** Do *not* port our PSA/unwrap. The one piece worth
  lifting from ours is the **roughness/filtering stage** (Sa/Sq/Sz, Gaussian vs
  morphological S-filter). **Confirmed gap:** his `src/` contains no
  roughness/surface-finish computation at all (grep for `roughness|Sa|Sq|Sz|
  Gaussian filter|morpholog` → nothing). So this is a real second contribution,
  not a maybe — his pipeline stops at a height map; ours turns a height map into
  surface-metrology parameters.
- **Blocker:** before our roughness stage consumes his height maps, the
  conventions in §5 must agree.

### 4d. Physical specs / units
- **His:** camera pitch 4.8 µm, M=0.09 → ~53 µm/px on surface; pixel units
  internal; Pico Genie projector placeholder.
- **Ours:** `paper_specs.py` now carries real PRO4500 numbers (912×1140 DMD,
  460 nm, FOV 400×250 mm @ 700 mm, **305 µm/px on plane**) and physical-mm
  priors.
- **Port plan:** move PRO4500 constants into his config (his `Geometry` already
  exposes `pixel_pitch_um` and `lambda_eq_override` — clean insertion points).
  Set `theta_projector`/`a` from PRO4500 optics; confirm whether the PRO4500 is
  telecentric (his geometry collapses the bias term gracefully if so — §2).
- **DATA DISCREPANCY (must settle):** our `paper_specs.py` labels the camera
  `BFS-U3-13Y3M-C` but with a **Sony IMX304, 4112×3008, 3.45 µm** sensor. His
  doc has the same model as **1280×1024, 4.8 µm** (correct for the 13Y3M).
  One is wrong — almost certainly ours pasted a different camera's sensor block.
  **His numbers look right; fix ours / confirm the actual lab camera.**

### 4e. Simulation — complementary, keep both
- His analytic forward model (fast, Taylor/exact bias, STL ground truth) and our
  Blender Cycles raytrace (photorealistic, models real illumination/shadow) are
  not redundant.
- **Port plan (optional, later):** expose Blender as an alternate "forward model"
  that emits PSI stacks his `pipeline.run_pipeline` can ingest, and/or feed his
  STL + geometry into our Blender scene builder. Bridge at the **PSI-stack array
  boundary** (H×W×N intensity), the natural seam. Lowest priority; do after
  hardware + specs land.

### 4f. GUI — keep his, port behaviors not widgets
- His PyQt6 3D digital twin is far ahead of our 2D PySide6 views. Do **not** port
  our GUI wholesale.
- **Port plan:** cherry-pick *behaviors* his GUI lacks: live projector USB
  controls (menu → `ProjectorController`), camera/projector device pickers,
  report export. Re-implement against PyQt6. Our PySide6 `ProjectorWindow`
  (fullscreen HDMI pattern display) maps to his `MockProjector`/extended-display
  path.
- **Risk:** PySide6→PyQt6 API differences are small but real (enum scoping,
  signal syntax). Port logic, rewrite widget glue.

### 4g. Testing
- His suite is an asset; ours has none. Every ported module (projector, camera,
  specs) must arrive **with tests** to match his bar. Hardware tests should use
  mock backends (his planned `MockCamera`/`MockProjector`) so CI runs without
  the rig.

---

## 5. Conflicts & risks (resolve before DSP merge)

1. **Fringe basis + PSA sign (BLOCKER for any shared DSP).**
   - His: cos fringe `A + B·cos(φ+δ)`, `extract_phase = atan2(−ΣI·sinδ, ΣI·cosδ)` → +φ.
   - Ours: sin fringe, `atan2(ΣI·sinδ, ΣI·cosδ)` → +φ.
   - Both return +φ **within their own basis**; mixing sin frames into his PSA
     (or vice-versa) flips the sign. **Decision needed:** standardize on his
     cos basis (recommended — it's the canonical base and is what the projector
     patterns/tests assume). Anything we port that generates or consumes phase
     must use the cos convention.
2. **Units: pixels (his) vs mm (ours).** His core is pixel-native with
   `pixel_pitch_um` for conversion. Keep his internal pixel convention; apply our
   physical numbers only at the `Geometry`/calibration boundary. Don't push mm
   into his array math.
3. **Camera sensor data discrepancy** (§4d) — factual conflict to settle against
   the real lab camera.
4. **Toolkit split** PyQt6 vs PySide6 — affects only GUI ports (§4f).
5. **Env/packaging:** his is conda (`environment.yml`) + vendored Spinnaker wheel;
   ours is pip/pyproject with a `[hardware]` extra. Fold our `pycrafter4500` +
   `pyusb` deps into his `environment.yml` pip block (matches his "everything in
   pip" rule). Note Spinnaker wheel versions differ (his 4.3.0.190 vs our
   .189/.190) — align on one.

---

## 6. Recommended merge sequence

Phased, each phase independently landable + testable on his base:

1. **Specs & units (low risk, unblocks everything).** Port PRO4500 constants into
   his config/geometry; resolve the camera-sensor discrepancy; confirm projector
   telecentricity. No behavior change to his pipeline.
2. **Decide & document conventions (§5.1, §5.2).** Write the sin→cos / px↔mm
   decision into his `PROJECT_CONTEXT.md` before touching DSP.
3. **Projector control (headline).** Land `ProjectorController` as his concrete
   `RealProjector` + define the `Projector` protocol + `MockProjector`. With
   tests (mock backend). Fold deps into `environment.yml`.
4. **Camera acquisition.** Port our PySpin/OpenCV threads behind his `Camera`
   protocol (toolkit-neutral core + thin Qt layer). With tests.
5. **Roughness/finishing stage** (confirmed gap — his pipeline ends at a height
   map) — port our filter + Sa/Sq/Sz roughness step onto his height-map output,
   in his convention.
6. **GUI behaviors** — projector/camera controls + export, re-homed to PyQt6.
7. **(Optional, last) Blender bridge** — alt forward model at the PSI-stack seam.

---

## 7. Open questions (for Husam / supervisor)

1. **Is the PRO4500 the confirmed upgraded projector?** His doc lists the upgrade
   as "status unknown." Our work assumes PRO4500 (Wintech / TI DLP LightCrafter
   4500 / DLPC350).
2. **Is the PRO4500 telecentric?** Drives whether his projector bias term stays
   active or collapses (his §3 / `HybridGeometry`).
3. **Which camera is actually in the lab** — 13Y3M (1280×1024, 4.8 µm, his) or the
   IMX304 12 MP body our `paper_specs` lists? Settles §4d / §5.3.
4. **Keep both GUIs during transition, or his only?** Affects whether we maintain
   our PySide6 app at all post-merge.
5. **Conda or pip as the project's canonical env?** His is conda; our hardware
   extra is pip. Need one story for the lab PC (libusb/Zadig also required).
6. **Are Sa/Sq/Sz the wanted surface-finish outputs?** Confirmed his pipeline
   has none, so we're porting ours — just confirm the parameter set + filtering
   defaults match what the supervisor/thesis expects.
```
