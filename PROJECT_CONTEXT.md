# Fringe Projection Project — Context for Claude Code

> **Read this file first at the start of every session.** It captures the full project context, hardware setup, theoretical framework, design decisions, and roadmap. Treat it as the source of truth until told otherwise.

---

## 1. What This Project Is

A **fringe projection 3D measurement system** being built in a research lab. The goal is to recover the height profile of test objects by projecting sinusoidal fringe patterns onto a surface, capturing phase-shifted images with a camera, and processing the captured fringes to extract a height map.

The project is based on **Chapter 2 (theory)** and **Chapter 4 (practical implementation)** of a thesis by the thesis author. The thesis lives in the `reference/` folder.

The user's deliverables:
1. A **Python user interface (UI)** that controls the experiment end-to-end (pattern generation, projection, capture, calibration, processing, visualization).
2. The **math/processing core** behind the UI.
3. Eventually: **integration with real hardware** in the lab.

The user has an existing Jupyter notebook (`notebooks/Fringe_Projection_Python.ipynb`) that implements an end-to-end synthetic simulation. **It works** — recovers a Gaussian bump from simulated fringes with mean error ~10⁻⁵ after DC alignment. Stages 1, 2, 3 have been completed (see Section 12). The notebook is the starting point for refactoring, not a thing to start over.

---

## 2. Hardware Setup

### Currently in the lab (confirmed)

**Camera: FLIR Blackfly S BFS-U3-13Y3M-C** (SN: 26048170)
- Monochrome, USB3 Vision, global shutter
- 1280 × 1024 pixels at 4.8 µm pitch
- Up to 170 fps
- 1/2" sensor format (active area 6.14 × 4.92 mm)
- C-mount
- **SDK: Spinnaker / PySpin** (Python bindings)
- Sold by Edmund Optics as stock #36-451

**Camera lens: Edmund Optics #58-259** (TECHSPEC GoldTL Telecentric)
- 0.09× magnification
- 132–182 mm working distance (focusable)
- < 0.2° telecentricity
- 1/2" sensor format
- **Confirmed telecentric.** Note: telecentric means **M is constant regardless of object distance** (the lens's defining property). It does NOT mean the camera body must be mounted vertical or at any specific tilt — the camera body's physical tilt angle (θ_camera) is independent of the lens's optical properties.

**Projector (placeholder unit, will be upgraded): Pico Genie Impact 2.0 Plus Elite**
- DLP projector
- 854 × 480 (FWVGA) native resolution
- 1.2:1 throw ratio, 16:9 aspect ratio
- 55 × 55 × 55 mm cube
- **Non-telecentric** consumer optics
- HDMI input (acts as a second display)
- **Auto-keystone confirmed OFF**
- Confirmed projector is **NOT telecentric** — projection-arm perspective bias must be corrected via inverse grating method

### Pending hardware

- **Upgraded projector** (more capable than Pico Genie). Telecentric or not — **status unknown**, user will confirm with supervisor.
- **Mounting hardware** (kinematic stages / rigid mounts). Until this arrives, real measurements aren't viable; calibration depends on stable repeatable geometry.
- **Optical breadboard** for stable component layout.
- **Calibration artifacts**: flat reference (gauge block / optical flat), step-height standard, calibrated grid scale (lateral).

### Derived parameters (camera arm)

- **Field of view on test surface:** ~68 × 55 mm
- **Pixel pitch on test surface:** ~53 µm/pixel
- **Imaging-arm magnification (M, modern convention):** 0.09×
- **Imaging-arm magnification (M, chapter convention = 1/0.09):** ~11.1×
  - ⚠️ The chapter uses the inverse convention; be careful when plugging into chapter equations.

### Pico Genie geometry (measured, in projector body frame)

Body frame: origin at front-bottom-left corner of cube; +X right, +Y into body, +Z up.

- Lens center: (X = 21 mm, Y ≈ 1–2 mm recess, Z = 45 mm)
- **Vertical optical offset: 0°** (confirmed — image center collinear with lens optical axis)
- **Horizontal optical offset: ~12° tentative** (likely setup misalignment; to be re-measured with proper mounting)
- Image at 30 cm throw: ~25 cm wide × ~14 cm tall (matches throw ratio + aspect ratio prediction)

### Derived projector parameter (computed for GUI digital-twin defaults)

- **Optimal projector throw distance:** ~82 mm (computed: `68 mm camera FOV width × 1.2 throw ratio`). At this distance the projected pattern matches the camera FOV exactly.
- This is a GUI default, not a hard hardware constraint — Stage 4's GUI exposes throw distance as a slider so the user can model coverage trade-offs.

---

## 3. System Configuration: HYBRID (lens telecentricity), arbitrary arm angles

The system is **hybrid in lens type**:
- **Viewing arm lens: telecentric** (locked by Edmund Optics lens — cannot be turned off)
- **Projection arm lens: non-telecentric** (Pico Genie; future projector status unknown)

The camera arm therefore contributes essentially zero **perspective bias from the lens**. **All measurable bias from lens-distortion comes from the projection arm.**

**But arm angles are independent of lens telecentricity.** Both arms can be mounted at any physical tilt angle relative to the test surface normal. The chapter's general framework (Eq. 2-51) takes **two angles** as input: θ_projector and θ_camera. Telecentric viewing handles the lens-side perspective bias; the arm angle handles the triangulation geometry. These are two different things.

### Method choice

The thesis describes three correction strategies (Chapter 2):

| Section | Method | Used here? |
|---|---|---|
| §2.3.4.1 | Recognize perspective effect (no correction) | No — the problem to fix |
| §2.3.4.2 | Telecentric lenses on **both** arms | Partial — only viewing arm is telecentric |
| §2.3.4.3 | **Project a custom pre-distorted (inverse) grating** | **YES — chapter explicitly says this is what the project does** |

Combined with the telecentric viewing lens already canceling camera-side lens-bias, the inverse grating cancels the remaining projection-side lens-bias. End result: clean uniform fringes on the surface, clean phase measurement. Arm angles still drive triangulation (Eq. 2-51), independent of the bias-correction story.

If the upgraded projector turns out to be telecentric, the inverse grating reduces gracefully to a uniform pattern (no harm done).

### Critical insight — system parameters not needed for the inverse-grating correction

Chapter 4 §4.3.1 states explicitly:

> *"It is difficult to measure the system parameters accurately. Instead, the system is calibrated using a standard VLSI step height."*

> *"...the new projected phase map, φ₂, can be determined from the measured phase map φ₁ by subtracting the tilt from φ₁, multiplying the result by -1, and then adding the tilt back. This allows us to correct for the system biases in real time without the need for measuring the system parameters precisely."*

This means **for the bias-correction step**, θ, projection-arm M, and the internal projector parameter `a` are NOT required — calibration on a flat reference absorbs all of them automatically.

**However** — and this is a distinction we previously missed — the **height conversion** (Eq. 2-51, λ_eq) does depend on the arm angles. The tilt-flip trick gives you a clean phase map; converting that phase map to *millimeters of height* requires λ_eq, which requires both θ_projector and θ_camera.

In real hardware, λ_eq is calibrated empirically against a step-height gauge, sidestepping the need to measure both angles precisely (per §4.3.1). In simulation (Stage 4), λ_eq is computed from Eq. 2-51 because both angles are known by definition (they're sliders).

### Key chapter equations

| Equation | What it is | Used in module |
|---|---|---|
| 2-44 | Full intensity equation `I(x₁, h)` (general non-telecentric) | `synthetic_fringes` (forward model) |
| 2-46 / 2-47 | Phase → height + λ_eq (general) | `reconstruction` |
| **2-51** | **λ_eq general two-angle form: `Mp / [2π·(tan θ₁ + tan θ₂)]`** — **operational formula for the project's math layer** | `reconstruction` / `geometry` |
| 2-52 | Simplified λ_eq (symmetric case, θ₁ = θ₂) | `reconstruction` (sanity check) |
| 2-54 | Inverse grating period p₂(x₁) — theoretical reference | `pattern_generator` |
| 2-57 | Phase → height with inverse grating | `reconstruction` |
| **4-2 → 4-7** | **Tilt-flip trick — operational core** | **`calibration`** |
| 4-9 / 4-10 | Clean phase on object after bias correction | reference |
| 4-11 / 4-12 | λ_eq (symmetric form with `sin θ`) — used in current notebook | `reconstruction` (legacy, superseded) |

---

## 4. State of the Existing Notebook

`notebooks/Fringe_Projection_Python.ipynb` already implements the end-to-end synthetic pipeline with Stage 1 additions. **It works.**

### Implemented (Cells 0–20, original pipeline)
- Grid/parameter setup (toy values — to be replaced with real hardware values in Stage 2)
- Forward-model simulation of biased phase φ₁ (Taylor approximation of Eq. 2-44)
- 4-step phase shifting, phase extraction via `arctan2`, phase unwrapping with `np.unwrap`
- Tilt fitting and bias extraction (calibration)
- Tilt-flip computation of correction phase φ₂
- Synthetic Gaussian object simulation
- End-to-end height reconstruction with mean error ~10⁻⁵

### Implemented (Cells 21–23, Stage 1 simulation-loop additions)
- `project()` function (cell 2) — Taylor-approximation forward model with docstring
- Stage 1.2: roadmap-mandated consistency check (`project(uniform) == phi1`)
- Stage 1.3: curvature-cancellation validation on flat reference (suppression factor ~10¹⁴)

### Implemented (Cells 24–29, Stage 1 strengthened validation)
- **1-S.1 Exact-vs-Taylor**: bounds the Taylor truncation error and confirms it scales as predicted (ratio O(1))
- **1-S.2 Parameter scaling**: confirms bias scales linearly in `tan(θ)` and inversely in `a` (relative variation < 1e-10)
- **1-S.3 Limit cases**: bias → 0 when `θ = 0` or `a → ∞`
- Markdown summary of all three checks

### Cell 14 caveat
Cell 14 uses the symmetric `λ_eq = (p1·M) / (4π sin θ)` formula (Eq. 4-11). The simulation still converges correctly because one consistent θ is used everywhere; the formula is superseded by Stage 4's two-angle form from Eq. 2-51.

**Stage 2 update:** the notebook itself is unchanged — Stage 2 refactored the formula into `geometry.py` (both `HybridGeometry` and `SymmetricGeometry` implementations), not into the notebook. The notebook remains as a historical reference and as the source of the regression fixture (`tests/regression_data.npz`).

**Stage 3 update:** notebook cell 25 (Stage 1-S.1) is the spec for the exact-form forward model. The `+u` denominator convention adopted by `project(model='exact')` is documented there and in the function's docstring. Cell 25 stays as the authoritative reference for the sign convention.

**Stage 4 pre-task update:** the one-angle hybrid form `λ_eq = Mp / tan(θ_projector)` (Stage 2 Decision 3) is being replaced with the two-angle form `λ_eq = Mp / [2π·(tan θ_projector + tan θ_camera)]` (Eq. 2-51). The Stage 2 form assumed θ_camera = 0° — a hidden assumption from conflating "telecentric lens" with "camera mounted vertical." Telecentric only locks the lens magnification; the camera body's tilt angle is independent.

---

## 5. Project Directory Layout

```
Fringe_Projection_Project_Phase1/
├── PROJECT_CONTEXT.md             # this file — start here every session
├── CONVERSATION_SUMMARY.md        # detailed history of decisions
├── README.md                      # short orientation for newcomers
├── reference/
│   ├── CHAPTER2_Moire_and_Fringe_Projection.pdf
│   ├── Chapter4_Experimental_procedures.pdf
│   └── (other thesis chapters as added)
├── notebooks/
│   └── Fringe_Projection_Python.ipynb
├── src/                           # importable Python modules (Stage 2+)
│   ├── geometry.py
│   ├── pattern_generator.py
│   ├── synthetic_fringes.py
│   ├── phase_shifting.py
│   ├── unwrapping.py
│   ├── calibration.py
│   ├── reconstruction.py
│   ├── io_utils.py
│   ├── test_surfaces.py           # Stage 4a — heightmap generators
│   ├── scene.py                   # Stage 4b — 3D scene primitives
│   └── gui/                       # Stage 4 — PyQt6 GUI modules
├── tests/
│   └── test_pipeline_synthetic.py
├── scripts/                       # standalone runnable scripts
├── data/                          # synthetic frames, calibration files
├── docs/
│   ├── Projector_Geometry_Summary.docx
│   └── Fringe_Projection_Roadmap.pdf
└── .gitignore
```

---

## 6. Roadmap

The detailed roadmap is in `docs/Fringe_Projection_Roadmap.pdf`. Stages summary:

| Stage | What | Hardware needed? | Status |
|---|---|---|---|
| 0 | Project setup, Git, Python env | No | ✅ Done |
| 1 | Close simulation loop in notebook (add `project()` function) | No | ✅ Done |
| 2 | Refactor notebook into Python modules | No | ✅ Done |
| 3 | Upgrade forward model to exact Eq. 2-44 | No | ✅ Done |
| **3.5** | **Math layer upgrade: two-angle λ_eq (Eq. 2-51)** | No | ⏳ Next (Stage 4 pre-task) |
| 4 | Build PyQt6 GUI (digital twin) with two 3D views | No | After 3.5 |
| 5 | Hardware familiarization (capture frame, project pattern) | Optional | — |
| 6 | Real hardware integration with mounting + new projector | Yes | — |

---

## 7. Design Principles

### 7.1 — Geometry abstraction
All system-specific math lives behind a `Geometry` interface so the rest of the pipeline doesn't care which configuration is in use:

```python
class Geometry(Protocol):
    def equivalent_wavelength(self) -> float: ...
    def height_to_phase(self, h: np.ndarray) -> np.ndarray: ...
    def phase_to_height(self, psi: np.ndarray) -> np.ndarray: ...
    def projected_pattern(self, p: float, phase_shift: float, shape: tuple) -> np.ndarray: ...
    def forward_intensity(self, h: np.ndarray, p: float, phase_shift: float) -> np.ndarray: ...
```

Concrete implementations: `HybridGeometry` (default for this project), `SymmetricTelecentricGeometry`, `NonTelecentricGeometry`.

### 7.2 — No hardware coupling in math modules
`pattern_generator`, `synthetic_fringes`, `phase_shifting`, `unwrapping`, `calibration`, `reconstruction`, `geometry` should be **pure Python with no hardware dependencies**. They take/return NumPy arrays. This means:
- They can be tested entirely with synthetic data.
- They are reusable (the user's friend is building a separate Three.js geometric simulation — these same math functions support that work).

### 7.3 — Hardware behind a thin interface
When hardware is added, define abstractions like:

```python
class Camera(Protocol):
    def capture(self, exposure_ms: float) -> np.ndarray: ...

class Projector(Protocol):
    def display(self, pattern: np.ndarray) -> None: ...
```

Initial implementations: `MockCamera` (returns synthetic frames), `MockProjector` (saves PNGs / writes to extended display). Real implementations: `FLIRCamera` (PySpin wrapper), `RealProjector` (extended display).

**Note (Stage 4 deferral):** the `Camera` / `Projector` protocols and their mock implementations are deliberately deferred to Stage 5/6, not Stage 4. The Stage 4 GUI calls math modules directly. Rationale: the hardware shape isn't finalized (upgraded projector pending), so designing protocols against unknown specs is premature. When real hardware arrives, the protocols get designed against actual SDK calls and frame formats.

---

## 8. Open Questions for Supervisor (not blocking)

1. Is the upgraded projector telecentric? If yes, the hybrid case collapses to symmetric-telecentric (still two angles though).
2. ~~Simplified `λ_eq` formula for the hybrid case?~~ **Resolved at Stage 4 planning:** use Eq. 2-51's two-angle general form `Mp / [2π·(tan θ_proj + tan θ_cam)]`. In real hardware, also calibrate empirically against a step gauge per Chapter 4 §4.3.1.
3. Software post-correction (subtract bias from measurement) or hardware pre-correction (project inverse pattern)? Both are mathematically equivalent. Chapter uses pre-correction.
4. How many phase-shift steps (4 or 8)? Notebook uses 4; chapter uses 8. (Stage 4 GUI exposes this as a toggle.)
5. What calibration artifacts are available in the lab vs. need to be ordered?
6. ~~GUI framework preference?~~ **Resolved:** PyQt6 (per roadmap + Stage 4 plan).

---

## 9. Coordinate / Sign Conventions

- **Projector body frame**: origin at front-bottom-left corner of cube; +X right, +Y into body, +Z up.
- **Wall plane** at projection: Y = −D where D is throw distance.
- **Image arrays**: NumPy convention `(H, W)` = (rows, cols). When mapping to physical X (horizontal) and Y (vertical), array axis 0 = vertical (Y), axis 1 = horizontal (X).
- **Phase units**: radians.
- **Length units**: SI in equations; pixels in synthetic notebook. Document units explicitly in every function docstring.
- **Forward-model bias sign (`project()`):** Taylor branch subtracts a positive bias `(4π/p)·x²·tan(θ)/a`. Exact branch uses `+u` denominator `1 + 2x·tan(θ)/a` to match (notebook cell 25). Textbook Ch.4 Eq. 4-6 prints `−u` — treated as a sign typo, see Section 12 Stage 3 notes.
- **Arm angles**: θ_projector and θ_camera are measured from the test surface normal to the optical axis of the respective arm. θ = 0° means the arm is pointing straight down at the surface (normal-incident). Positive vs negative sign indicates which side of the normal the arm sits.
- **Lab setup reference frame**: test surface center is the world origin. Surface normal (vertical line through center) is the z-axis. Both arms (projector and camera) are positioned by (angle, distance) where angle is measured from the surface normal and distance is along the arm's optical axis. Both arms remain aimed at the surface center regardless of their angle and distance — these are the only degrees of freedom for arm positioning in the simulator.

---

## 10. User Notes for Working with Claude Code

- Prefers **short concrete answers** over long expositions.
- Learns by analogy and step-by-step physical reasoning.
- Pushes back on hand-wavy assumptions (correctly).
- Comfortable with Python, decent experience.
- Has Claude Code, Git, Conda, MATLAB, VS Code, Node.js installed.
- Wants to validate algorithm thoroughly in simulation before touching real hardware.
- When the user says "I don't get this," simplify rather than doubling down on technical accuracy. Shorter answers, more analogy, fewer equations.

When refactoring, work **one module at a time**, write a small test that confirms the module reproduces the notebook's behavior, and commit before moving on.

---

## 11. Suggested Starting Tasks for Claude Code (Stage 2 — Historical)

In rough priority order. Do them with the user, one at a time:

1. Read this file, the conversation summary, and the notebook. Summarize back to confirm understanding.
2. Set up the package structure (`src/` with empty stub modules per the layout above).
3. Refactor Cells 1–2 of the notebook into `geometry.py` (system parameters + `HybridGeometry` class). **See Section 12 for required Stage 2 decisions.**
4. Refactor the forward model (`project()` function and `phi1` construction) into `synthetic_fringes.py`.
5. Refactor PSI cells (4–7) into `phase_shifting.py` and `unwrapping.py`.
6. Refactor object recovery (cell 18) into `reconstruction.py`.
7. Refactor calibration cells (8–11) into `calibration.py` (tilt-flip trick).
8. Write `tests/test_pipeline_synthetic.py` reproducing the notebook's end-to-end Gaussian recovery (~1e-5 std error).
9. Once the test passes, the math core is done — start the GUI (Stage 4).

For each module, write **clear docstrings** with units, dimensions, and references to the relevant chapter equation (e.g., `# Implements Eq. 4-7 from Samara Chapter 4`).

**Note:** the actual Stage 2 module order differed from the list above — see Section 12 "Stage 2 architectural decisions worth carrying forward" for details. Section 12 supersedes this section.

---

## 12. Stage 1 Completion Notes & Stage 2 / Stage 3 / Stage 4 Decisions

### Stage 1 — Done

- 1.1 `project()` function added (Taylor-approximation forward model)
- 1.2 Roadmap-mandated consistency check (cell 22)
- 1.3 Curvature-cancellation validation on flat reference (cell 23, suppression ~10¹⁴)
- 1.4 Markdown documentation + Git commit
- **Strengthened validation** added beyond roadmap: 1-S.1 (Taylor error bounded), 1-S.2 (parameter scaling verified), 1-S.3 (limit cases pass)
- A fourth strengthened check (1-S.4 end-to-end object recovery via explicit `project()` chain) was considered and **deliberately omitted**: in simulation, the same analytical bias formula is used both to construct `phi2` and inside `project()`, so cancellation is satisfied by construction and provides no independent verification.

### Validation philosophy arrived at

Simulation validation can only catch bugs where the test path uses *different* logic than the thing being tested. Tests that share the same formula on both sides are tautological. Real validation comes from (a) cross-implementation comparison (MATLAB, Three.js sim), (b) real hardware measurements, or (c) analytical limit checks. The Stage 1 validations cover (c) and small portions of (a). Stages 2+ open the door to (a) more broadly via the regression test script; Stage 6 brings (b).

### Stage 2 decisions (with Stage 4 corrections noted inline)

1. **Default geometry: `HybridGeometry`** (telecentric camera lens, non-telecentric projector lens), matching the actual hardware.
2. **Replace toy parameter values** with real hardware values from Section 2 of this file (M = 0.09 modern / 11.1 chapter, sensor 1280×1024 at 4.8 µm pitch, pixel pitch on test surface ~53 µm, projector parameters from real geometry once measured).
3. ~~**`λ_eq` formula:** use `M·p / tan(θ_projector)` (reduction of Eq. 2-51 with θ_camera → 0).~~ **SUPERSEDED by Stage 3.5 pre-task:** use Eq. 2-51's full two-angle form `λ_eq = Mp / [2π·(tan θ_projector + tan θ_camera)]`. The original Stage 2 simplification conflated "telecentric camera lens" with "camera mounted vertical (θ_camera = 0°)" — these are different things. Telecentric only locks the lens magnification; the arm tilt is independent and must be a separate input.
4. **Keep `SymmetricGeometry`** as an alternative implementation for textbook reference / cross-validation, but it's not the operational default.
5. **Document the geometry choice** explicitly in `geometry.py` docstrings, including the camera/projector telecentricity status and which equations apply.
6. **Forward model stays Taylor for Stage 2;** exact Eq. 2-44 form is Stage 3 work. The `project()` interface should be designed to accept a `model={'taylor', 'exact'}` parameter even if only `'taylor'` is implemented now.
7. **`pattern_generator.py` is intentionally left as an empty stub for Stage 2.** The synthetic pipeline closes without it. Becomes load-bearing in Stage 5.

### Stage 2 — Done

- Notebook refactored into 6 src/ modules: `geometry.py`, `synthetic_fringes.py`, `phase_shifting.py`, `unwrapping.py`, `calibration.py`, `reconstruction.py`. `pattern_generator.py` and `io_utils.py` remain stubs (deferred to Stage 5 per Decision 7).
- 12 regression tests passing across 6 test files plus a final integration test (`tests/test_pipeline_synthetic.py`).
- Closing commit: `b5b7342` (Stage 2.6 end-to-end integration test). Tag: `stage-2-complete`.
- Repository pushed to private GitHub remote (`HusamArdah/fringe-projection-3d`).

### Stage 2 architectural decisions worth carrying forward

- **Module order swapped from Section 11.** Calibration was refactored before reconstruction (not the order suggested in Section 11) so each module's tests naturally consume the previous module's output. Section 11's order was an early draft; Section 12 supersedes it.

- **`project()` is `λ_eq`-independent.** The Taylor forward model reads only `p`, `theta_projector`, and `a` from the Geometry — never `lambda_eq`. This means `HybridGeometry` and `SymmetricGeometry` produce bit-identical `project()` output (test `test_project_is_lambda_eq_independent` locks this invariant). `λ_eq` enters only at the height↔phase boundary in `reconstruction.py`. **Stage 3's exact-Eq.-2-44 forward model preserves this invariant** (test `test_project_exact_lambda_eq_independent`, atol=1e-15). **Stage 3.5 will preserve it too** — adding `theta_camera` to `HybridGeometry` doesn't affect `project()`, only `equivalent_wavelength()`.

- **Two tilt fits live in `calibration.py`, not one. They are NOT interchangeable on non-trivial inputs.**
  - `fit_tilt_plane` (2D lstsq, `[x, y, 1]` design matrix): for flat references or any measurement where genuine y-tilt may be present.
  - `fit_tilt_line_1d` (1D polyfit on row-mean, tiled): for object-phase self-calibration per Ch.4 §4.3.1 / notebook cell 18. The recovered tilt has `m_y == 0` by construction.
  - The two diverge by ~4e-5 in recovered height on object-phase fixtures. `recover_object_height` uses `fit_tilt_line_1d`; `compute_inverse_phase` uses `fit_tilt_plane`.

- **`recover_object_height` subtracts a self-cal tilt, not a cross-cal flat-reference phase.** This matches notebook cell 18's `tilt3_2d`. The function signature is operand-agnostic — the caller passes `phi_calibration`. When real cross-calibration enters in Stage 6, the same function still works.

- **The integration test does NOT exercise the closed inverse-grating loop.** Synthesizes object stack from `phi3` directly. Same tautology limit as Stage 1's omitted 1-S.4. Real validation needs cross-impl or hardware.

- **Real hardware values (Section 2) replace toy defaults when measured.** Both `HybridGeometry` and `SymmetricGeometry` currently default to identical bias parameters. When real values arrive in Stage 6, both geometries' defaults must update in lockstep, or the bit-identical `project()` invariant silently breaks.

### Stage 3 — Done

- 3.1 `project(model='exact')` implemented per notebook cell 25's `+u` denominator form: `phi_exact(x) = (2π/p) · x / (1 + 2x·tan(θ)/a)`. Commit: `b752f47`.
- 3.2 (comparison script) deliberately skipped. The model toggle is the deliverable; cell 25 + `test_project_exact_taylor_consistency` already capture the diff numbers.
- 3.3 (inverse-grating cancellation under exact) folded into the parametrized integration test.
- Integration test parametrized over `model in {'taylor', 'exact'}`. Both branches run end-to-end. Commit: `e5201fb`. Tag: `stage-3-complete`.
- 17 tests passing.

### Stage 3 architectural decisions worth carrying forward

- **Default remains `model='taylor'`.** Flip is deferred; no driver to flip it yet.
- **The `+u` denominator convention is the project's operational convention.** Textbook Ch.4 Eq. 4-6 as printed has `−u`; the notebook (cell 25) treats this as a sign typo. The exact branch's docstring documents this; cell 25 remains the authoritative reference.
- **Validation is informational, not gatekept.** No numerical bound on the exact branch's `std_err` in the integration test.
- **The exact branch is `λ_eq`-independent, same invariant as Taylor.** Locked at `atol=1e-15`.
- **Denominator-positivity guard.** Raises `ValueError` if `1 + 2x·tan(θ)/a ≤ 0` anywhere on the grid.
- **Object leg of the integration test still skips `project()`.** Per the documented Stage 2.6 deviation. The test confirms "the pipeline runs under both models without crashing"; it does NOT independently verify that exact's calibration cancels exact's bias.

### Stage 3.5 — Math layer upgrade: two-angle λ_eq (pre-task before Stage 4)

**Why this exists.** Stage 4 planning surfaced that `HybridGeometry.equivalent_wavelength()` currently uses `λ_eq = Mp / tan(θ_projector)` — the Eq. 2-51 form with `θ_camera = 0°` assumed. The Stage 2 reasoning for this simplification ("telecentric camera → drop θ_camera") was wrong: telecentric only locks the lens magnification; the camera body's tilt angle is independent. To support a GUI with separate θ_projector and θ_camera sliders, the math layer needs Eq. 2-51's full form.

**Task scope (one Claude Code task, one commit):**

1. **`src/geometry.py`:**
   - `HybridGeometry.__init__` gains a new arg `theta_camera` (radians). Default value: same as current `theta_projector` (symmetric default — matches existing fixture's effective behavior at θ_camera = θ_projector, which is what Eq. 2-52 collapses to).
   - `HybridGeometry.equivalent_wavelength()` updated to: `λ_eq = M·p / (2π·(tan θ_proj + tan θ_cam))`.
   - Same change to `SymmetricGeometry` (gains `theta_camera` arg; sets θ_camera = θ_projector by default to preserve symmetric behavior).
   - Docstrings updated with Eq. 2-51 reference and the typo note about Stage 2 Decision 3.

2. **`tests/test_geometry.py` (or wherever λ_eq tests live):**
   - Existing test for hybrid λ_eq updated to use `theta_camera=0` explicitly (keeps the test's intent: "what hybrid degenerates to when camera is vertical").
   - New test: at `theta_camera = theta_projector`, the two-angle form matches Eq. 2-52's symmetric form (`λ_eq = Mp / (2π·2·tan θ)`).
   - New test: λ_eq → ∞ when `tan θ_proj + tan θ_cam = 0` (both zero, or equal-opposite). GUI uses this as the "no height sensitivity" warning trigger.

3. **`tests/test_pipeline_synthetic.py`:**
   - Verify integration test still passes. The fixture was generated with the old one-angle formula; we expect it to still pass because the default `theta_camera = theta_projector` makes the new formula symmetric, which matches the fixture's setup. **If the fixture breaks**, regenerate it deliberately, documenting in the commit message what changed and why.

4. **All other tests:** must continue to pass without modification.

**Architectural invariants preserved:**
- `project()` stays `λ_eq`-independent. `test_project_is_lambda_eq_independent` and `test_project_exact_lambda_eq_independent` both stay at atol=1e-15.
- HybridGeometry and SymmetricGeometry remain bit-identical in their `project()` output.

**Commit message format:**
```
Stage 3.5: two-angle λ_eq (Eq. 2-51), supersede Stage 2 Decision 3

- HybridGeometry / SymmetricGeometry gain theta_camera arg
- equivalent_wavelength() now Mp / (2π·(tan θ_proj + tan θ_cam))
- Default theta_camera = theta_projector (preserves fixture)
- 17 tests still passing (or N+M if new tests added)
- Math layer now matches paper's Eq. 2-51 exactly
```

Tag: not needed — this is a pre-task to Stage 4, not a stage close.

### Stage 4 plan (pre-implementation — drafted in strategy chat, awaiting Stage 3.5 + Claude Code execution)

**Goal:** A PyQt6 GUI that operates as a **digital twin** of the lab's fringe projection setup. The user adjusts hardware-realistic controls and sees both:
1. A **recovered-height view** showing true vs. recovered surface with an error map.
2. A **lab setup view** showing the full physical setup as a 3D scene the user can orbit around.

Stage 4 is split into 4a (the scientific tool) and 4b (the lab visualization). Each ships and tags separately. Math modules are called by the GUI, not modified (except for the Stage 3.5 pre-task).

#### Stage 4 controls (locked)

**Sliders / dropdowns in the GUI:**

| Control | Type | Range / Options | Notes |
|---|---|---|---|
| Surface type | dropdown | flat, tilt, Gaussian, step, sphere | Drives `src/test_surfaces.py`. |
| Per-surface params | sliders | depends on surface | Hidden/shown by dropdown. ~2–3 sliders per surface (e.g. Gaussian: amplitude, width; step: height, edge position). Always centered on grid. |
| **θ_projector** | slider | ~−60° to +60° | Projector arm tilt from surface normal. Triangulation angle. Updates λ_eq live. |
| **θ_camera** | slider | ~−60° to +60° | Camera arm tilt from surface normal. Independent of projector. Triangulation angle. Updates λ_eq live. |
| Projector distance from surface | slider | ~50–200 mm | Does NOT affect chapter's bias math. Drives only the lab view + a coverage indicator. **Lab-design tool**. |
| PSI step count | dropdown | 4 or 8 | Trade-off between speed and noise immunity. |

**Locked in code, shown in read-only info panel:**

| Quantity | Value | Source |
|---|---|---|
| Camera M | 0.09× | Edmund Optics #58-259 lens spec |
| Camera distance to surface | 157 mm | Middle of telecentric WD range (132–182 mm) |
| Camera FOV | 68 × 55 mm | Derived: sensor 6.14×4.92 mm / M |
| Pixel pitch on surface | ~53 µm | Derived: 4.8 µm / M |
| Sensor | 1280×1024 at 4.8 µm | FLIR Blackfly spec |
| Projector throw ratio | 1.2:1 | Pico Genie spec |
| Projector FOV | live | Derived: throw_distance / throw_ratio |
| Coverage indicator | live | Compares projector FOV vs camera FOV |
| `a` (projector internal) | placeholder (2000 px) | Fixed inside projector hardware, NOT a slider |
| `p` (fringe period) | placeholder | Fixed |
| `λ_eq` | live | Derived: `Mp / [2π·(tan θ_proj + tan θ_cam)]` |
| Forward model | `'taylor'` | Stage 3 default |
| Resolution | 480×640 | Live updates |

**Degenerate case handling:**
- When `tan(θ_proj) + tan(θ_cam) → 0` (both zero, or equal-and-opposite — both arms looking from the same direction), λ_eq → ∞ → "no height sensitivity, cannot measure"
- Info panel shows clear warning; recovered-height view is grayed out or shows "undefined."

#### Critical reasoning that drove the slider list (preserve this — easy to forget)

- **The chapter's `M = l/b` (Eq. 2-41) is a camera-arm ratio.** Projectors don't have an "M" in the chapter's framework. They have `a` (internal grating-to-lens distance) and a throw ratio (lab-side). Conflating camera-M with projector behavior was a planning false start.
- **`a` is fixed by projector hardware.** It's the physical distance from DMD chip to projector lens. Moving the projector in the lab does NOT change `a`. Therefore "projector distance" cannot drive `a` and cannot affect the chapter's bias math.
- **Telecentric camera: M and distance are independent.** Within 132–182 mm WD, M stays at 0.09× regardless of camera position. Moving the camera only affects focus, not FOV. FOV is locked at 68×55 mm. **But the camera's tilt angle is independent of M** — telecentric doesn't mean "mounted vertical." This was a separate false start (Stage 2 Decision 3's hidden assumption) that Stage 3.5 corrects.
- **Projector distance affects coverage, not math.** The slider exists for lab-design intuition.
- **Symmetric assumption (Fig. 4-4) is expository, not required.** The chapter writes derivations under symmetric arms for clarity, but Eq. 2-51 is the general two-angle form. Asymmetric arms (different angles, different distances) are fine; the math handles them.
- **Both arm angles are independent.** Stage 4's GUI exposes both θ_projector and θ_camera as sliders. The user can explore symmetric, asymmetric, vertical-projector, vertical-camera, and degenerate configurations.

#### Stage 4a — Surface library + GUI + recovered-height view

1. `src/test_surfaces.py` — 5 pure-function generators: `make_flat`, `make_tilt`, `make_gaussian`, `make_step`, `make_sphere`. Unit tested. Each takes shape + params, returns `(H, W)` heightmap. Centered on grid by construction.
2. `src/gui/` package — PyQt6 main window: control panel (sliders + dropdowns + info panel) + recovered-height 3D view. GUI calls math modules directly. No Camera/Projector protocols.
3. Live updates on slider drag (480×640 resolution). Pipeline re-runs end-to-end each update.
4. Default surface on launch: Gaussian (matches existing regression fixture).
5. Ship and tag `stage-4a-complete`.

#### Stage 4b — Lab setup view

6. `src/scene.py` — translates geometry params (θ_proj, θ_cam, projector distance, camera distance, projector throw ratio, test surface dimensions) into 3D scene primitives (camera body, projector body, test surface plane, projection cone, viewing cone).
7. Add lab setup 3D view to GUI as a second view. User orbits the entire scene with mouse. Updates live as sliders move.
8. Ship and tag `stage-4-complete`.

#### Deferred from Stage 4

- **MockCamera, MockProjector, Camera/Projector protocols** → Stage 5/6.
- **File-loaded and multi-bump surfaces** → if/when needed.
- **Taylor/exact model toggle in GUI** → adds two lines later; not v1.
- **Resolution toggle (480×640 vs 1280×1024)** → adds a "Compute at full res" button later.
- **Three.js embed for lab view** → explicitly rejected; lab view is native PyQt6.
- **Object position offset** → locked at center.

#### Architectural notes for Stage 4

- The math layer's existing invariants (especially `test_project_is_lambda_eq_independent`) must continue to pass after Stage 3.5.
- 3D viewer backend: **PyQtGraph (OpenGL)** is the strong default — fast live updates, good orbital camera, single dependency for both views.
- All slider updates re-run the pipeline. At 480×640 this is millisecond-scale.

#### When real hardware arrives (Stage 6 prep)

- Update `HybridGeometry` defaults to real measured values (`a`, `p`, θ_projector_actual, θ_camera_actual, distances).
- Update info-panel constants in GUI to match.
- Empirically calibrate `λ_eq` against a step gauge; override formula-derived value if needed.
- `test_project_is_lambda_eq_independent` must still pass after the update — `HybridGeometry` and `SymmetricGeometry` defaults must change in lockstep.
- Scene primitives in `src/scene.py` update to reflect real lab layout.

### Future-stage hooks deferred during Stage 2 / Stage 3 / Stage 4

- **`pattern_generator.py`** (Decision 7): empty stub. Stage 5+.
- **`io_utils.py`**: empty stub. Adds frame I/O when capture loop lands.
- **`scripts/compare_forward_models.py`**: deliberately not created.
- **`MockCamera` / `MockProjector` / Camera-Projector protocols**: deferred to Stage 5/6.

---

*End of context. Ask the user for clarification before starting work.*
