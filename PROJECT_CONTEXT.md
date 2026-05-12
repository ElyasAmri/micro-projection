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

The user has an existing Jupyter notebook (`notebooks/Fringe_Projection_Python.ipynb`) that implements an end-to-end synthetic simulation. **It works** — recovers a Gaussian bump from simulated fringes with mean error ~10⁻⁵ after DC alignment. Stage 1 has been completed (see Section 12). The notebook is the starting point for refactoring, not a thing to start over.

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
- **Confirmed telecentric — viewing-arm perspective bias is hardware-eliminated**

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

---

## 3. System Configuration: HYBRID

The system is **hybrid**:
- **Viewing arm: telecentric** (locked by Edmund Optics lens — cannot be turned off)
- **Projection arm: non-telecentric** (Pico Genie; future projector status unknown)

The camera arm therefore contributes essentially zero perspective bias. **All measurable bias comes from the projection arm.**

### Method choice

The thesis describes three correction strategies (Chapter 2):

| Section | Method | Used here? |
|---|---|---|
| §2.3.4.1 | Recognize perspective effect (no correction) | No — the problem to fix |
| §2.3.4.2 | Telecentric lenses on **both** arms | Partial — only viewing arm is telecentric |
| §2.3.4.3 | **Project a custom pre-distorted (inverse) grating** | **YES — chapter explicitly says this is what the project does** |

Combined with the telecentric viewing lens already canceling camera-side bias, the inverse grating cancels the remaining projection-side bias. End result: clean uniform fringes on the surface, clean phase measurement.

If the upgraded projector turns out to be telecentric, the inverse grating reduces gracefully to a uniform pattern (no harm done).

### Critical insight — system parameters not needed

Chapter 4 §4.3.1 states explicitly:

> *"It is difficult to measure the system parameters accurately. Instead, the system is calibrated using a standard VLSI step height."*

> *"...the new projected phase map, φ₂, can be determined from the measured phase map φ₁ by subtracting the tilt from φ₁, multiplying the result by -1, and then adding the tilt back. This allows us to correct for the system biases in real time without the need for measuring the system parameters precisely."*

This means **θ, projection-arm M, and the internal projector parameter `a` are NOT required.** Calibration on a flat reference absorbs all of them automatically.

### Key chapter equations

| Equation | What it is | Used in module |
|---|---|---|
| 2-44 | Full intensity equation `I(x₁, h)` (general non-telecentric) | `synthetic_fringes` (forward model) |
| 2-46 / 2-47 | Phase → height + λ_eq (general) | `reconstruction` |
| 2-51 | λ_eq (general, two angles `tan θ₁ + tan θ₂`) | `reconstruction` — hybrid case reduces θ_camera → 0 |
| 2-52 | Simplified λ_eq (symmetric telecentric, sanity check) | `reconstruction` |
| 2-54 | Inverse grating period p₂(x₁) — theoretical reference | `pattern_generator` |
| 2-57 | Phase → height with inverse grating | `reconstruction` |
| **4-2 → 4-7** | **Tilt-flip trick — operational core** | **`calibration`** |
| 4-9 / 4-10 | Clean phase on object after bias correction | reference |
| 4-11 / 4-12 | λ_eq (symmetric form with `sin θ`) — used in current notebook | `reconstruction` (will be replaced in Stage 2) |

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
Cell 14 uses the symmetric `λ_eq = (p1·M) / (4π sin θ)` formula (Eq. 4-11). For the hybrid hardware, the strict formula is `λ_eq = (p1·M) / tan(θ_projector)` (from Eq. 2-51 with θ_camera = 0). The simulation still converges correctly because one consistent θ is used everywhere; the formula is replaced in Stage 2 / measured empirically in Stage 6.

**Stage 2 update:** the notebook itself is unchanged — Stage 2 refactored the formula into `geometry.py` (both `HybridGeometry` and `SymmetricGeometry` implementations), not into the notebook. The notebook remains as a historical reference and as the source of the regression fixture (`tests/regression_data.npz`).

**Stage 3 update:** notebook cell 25 (Stage 1-S.1) is the spec for the exact-form forward model. The `+u` denominator convention adopted by `project(model='exact')` is documented there and in the function's docstring. Cell 25 stays as the authoritative reference for the sign convention.

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
│   └── io_utils.py
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
| 4 | Build PyQt6 GUI with mock hardware | No | ⏳ Next |
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

---

## 8. Open Questions for Supervisor (not blocking)

1. Is the upgraded projector telecentric? If yes, the hybrid case collapses to symmetric-telecentric.
2. **Still open:** What's the simplified `λ_eq` formula for the hybrid case (telecentric viewing + non-telecentric projection)? Eq. 2-51 with θ_camera = 0 gives `Mp / tan(θ_projector)`, but in practice we'd skip the formula and use empirical step-height calibration per Chapter 4 §4.3.1.
3. Software post-correction (subtract bias from measurement) or hardware pre-correction (project inverse pattern)? Both are mathematically equivalent. Chapter uses pre-correction.
4. How many phase-shift steps (4 or 8)? Notebook uses 4; chapter uses 8.
5. What calibration artifacts are available in the lab vs. need to be ordered?
6. GUI framework preference?

---

## 9. Coordinate / Sign Conventions

- **Projector body frame**: origin at front-bottom-left corner of cube; +X right, +Y into body, +Z up.
- **Wall plane** at projection: Y = −D where D is throw distance.
- **Image arrays**: NumPy convention `(H, W)` = (rows, cols). When mapping to physical X (horizontal) and Y (vertical), array axis 0 = vertical (Y), axis 1 = horizontal (X).
- **Phase units**: radians.
- **Length units**: SI in equations; pixels in synthetic notebook. Document units explicitly in every function docstring.
- **Forward-model bias sign (`project()`):** Taylor branch subtracts a positive bias `(4π/p)·x²·tan(θ)/a`. Exact branch uses `+u` denominator `1 + 2x·tan(θ)/a` to match (notebook cell 25). Textbook Ch.4 Eq. 4-6 prints `−u` — treated as a sign typo, see Section 12 Stage 3 notes.

---

## 10. User Notes for Working with Claude Code

- Prefers **short concrete answers** over long expositions.
- Learns by analogy and step-by-step physical reasoning.
- Pushes back on hand-wavy assumptions (correctly).
- Comfortable with Python, decent experience.
- Has Claude Code, Git, Conda, MATLAB, VS Code, Node.js installed.
- Wants to validate algorithm thoroughly in simulation before touching real hardware.

When refactoring, work **one module at a time**, write a small test that confirms the module reproduces the notebook's behavior, and commit before moving on.

---

## 11. Suggested Starting Tasks for Claude Code (Stage 2)

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

## 12. Stage 1 Completion Notes & Stage 2 / Stage 3 Decisions

### Stage 1 — Done

- 1.1 `project()` function added (Taylor-approximation forward model)
- 1.2 Roadmap-mandated consistency check (cell 22)
- 1.3 Curvature-cancellation validation on flat reference (cell 23, suppression ~10¹⁴)
- 1.4 Markdown documentation + Git commit
- **Strengthened validation** added beyond roadmap: 1-S.1 (Taylor error bounded), 1-S.2 (parameter scaling verified), 1-S.3 (limit cases pass)
- A fourth strengthened check (1-S.4 end-to-end object recovery via explicit `project()` chain) was considered and **deliberately omitted**: in simulation, the same analytical bias formula is used both to construct `phi2` and inside `project()`, so cancellation is satisfied by construction and provides no independent verification. Object recovery is already exercised by cells 14–20 of the original pipeline. A meaningful version of this test belongs in Stage 6 with real hardware.

### Validation philosophy arrived at

Simulation validation can only catch bugs where the test path uses *different* logic than the thing being tested. Tests that share the same formula on both sides are tautological. Real validation comes from (a) cross-implementation comparison (MATLAB, Three.js sim), (b) real hardware measurements, or (c) analytical limit checks. The Stage 1 validations cover (c) and small portions of (a). Stages 2+ open the door to (a) more broadly via the regression test script; Stage 6 brings (b).

### Stage 2 decisions (instruct Claude Code accordingly)

1. **Default geometry: `HybridGeometry`** (telecentric camera, non-telecentric projector), matching the actual hardware.
2. **Replace toy parameter values** with real hardware values from Section 2 of this file (M = 0.09 modern / 11.1 chapter, sensor 1280×1024 at 4.8 µm pitch, pixel pitch on test surface ~53 µm, projector parameters from real geometry once measured).
3. **`λ_eq` formula:** use `M·p / tan(θ_projector)` (reduction of Eq. 2-51 with θ_camera → 0), not the symmetric `4π sin θ` form from Eq. 4-11. Even better: design `reconstruction.py` so `λ_eq` can be computed *or* loaded from a calibration file (Chapter 4 §4.3.1 approach).
4. **Keep `SymmetricGeometry`** as an alternative implementation for textbook reference / cross-validation, but it's not the operational default.
5. **Document the geometry choice** explicitly in `geometry.py` docstrings, including the camera/projector telecentricity status and which equations apply.
6. **Forward model stays Taylor for Stage 2;** exact Eq. 2-44 form is Stage 3 work. The `project()` interface should be designed to accept a `model={'taylor', 'exact'}` parameter even if only `'taylor'` is implemented now.
7. **`pattern_generator.py` is intentionally left as an empty stub for Stage 2.** The synthetic pipeline closes without it (`phi2` is the projector pattern in phase form; intensity synthesis is handled by `synthetic_fringes.synthesize_psi_stack`). `pattern_generator` becomes load-bearing in Stage 5 when real hardware needs an actual image written to the projector's framebuffer. Defer until then.

### Stage 2 — Done

- Notebook refactored into 6 src/ modules: `geometry.py`, `synthetic_fringes.py`, `phase_shifting.py`, `unwrapping.py`, `calibration.py`, `reconstruction.py`. `pattern_generator.py` and `io_utils.py` remain stubs (deferred to Stage 5 per Decision 7).
- 12 regression tests passing across 6 test files plus a final integration test (`tests/test_pipeline_synthetic.py`).
- Closing commit: `b5b7342` (Stage 2.6 end-to-end integration test). Tag: `stage-2-complete`.
- Repository pushed to private GitHub remote (`HusamArdah/fringe-projection-3d`).

### Stage 2 architectural decisions worth carrying forward

These were made during Stage 2 and bind future stages:

- **Module order swapped from Section 11.** Calibration was refactored before reconstruction (not the order suggested in Section 11) so each module's tests naturally consume the previous module's output. Section 11's order was an early draft; Section 12 supersedes it.

- **`project()` is `λ_eq`-independent.** The Taylor forward model reads only `p`, `theta_projector`, and `a` from the Geometry — never `lambda_eq`. This means `HybridGeometry` and `SymmetricGeometry` produce bit-identical `project()` output (test `test_project_is_lambda_eq_independent` locks this invariant). `λ_eq` enters only at the height↔phase boundary in `reconstruction.py`. **Stage 3's exact-Eq.-2-44 forward model preserves this invariant** (test `test_project_exact_lambda_eq_independent`, atol=1e-15).

- **Two tilt fits live in `calibration.py`, not one. They are NOT interchangeable on non-trivial inputs.**
  - `fit_tilt_plane` (2D lstsq, `[x, y, 1]` design matrix): for flat references or any measurement where genuine y-tilt may be present (small optical-axis rotation, future hardware calibration). Strict superset of the 1D form on y-invariant data.
  - `fit_tilt_line_1d` (1D polyfit on row-mean, tiled): for object-phase self-calibration per Ch.4 §4.3.1 / notebook cell 18. The recovered tilt has `m_y == 0` by construction — intentional, because absorbing the bump into `m_y` is precisely what we don't want for self-cal.
  - The two diverge by ~4e-5 in recovered height on object-phase fixtures (Gaussian bump whose center sits ~0.5 px off the grid centroid). `recover_object_height` uses `fit_tilt_line_1d`; `compute_inverse_phase` uses `fit_tilt_plane`.

- **`recover_object_height` subtracts a self-cal tilt, not a cross-cal flat-reference phase.** This matches notebook cell 18's `tilt3_2d`. The function signature is operand-agnostic — the caller passes `phi_calibration`. When real cross-calibration enters in Stage 6 (flat-reference measurement separate from object), the same function still works; only the operand changes.

- **The integration test does NOT exercise the closed inverse-grating loop.** `tests/test_pipeline_synthetic.py` synthesizes the object stack from `phi3` directly, not from `project(phi3, geom)`. This matches the notebook's assumption (inverse-grating correction already applied → projector emits clean fringes), and avoids a ~36-unit height contamination from adding the projector bias on top of the object phase. A true closed-loop test (display `phi2`, let bias cancel through, recover height) requires either cross-implementation comparison (MATLAB, Three.js) or real hardware — Stage 6 work. Same tautology limit identified in Stage 1.

- **Real hardware values (Section 2) replace toy defaults when measured.** Both `HybridGeometry` and `SymmetricGeometry` currently default to identical bias parameters (`a = 2000` pixels, `θ = 15°`) — both marked as `# PLACEHOLDER`. When real values arrive in Stage 6, both geometries' defaults must update in lockstep, or the bit-identical `project()` invariant silently breaks.

### Stage 3 — Done

- 3.1 `project(model='exact')` implemented per notebook cell 25's `+u` denominator form:
  `phi_exact(x) = (2π/p) · x / (1 + 2x·tan(θ)/a)`. Closing commit: `b752f47`.
- 3.2 (comparison script) deliberately skipped. The model toggle is the deliverable; cell 25 and the unit test `test_project_exact_taylor_consistency` already capture the diff numbers (ratio = 3.40, matches cell 25's published value). A standalone script adds nothing the toggle doesn't.
- 3.3 (inverse-grating cancellation under exact) folded into the parametrized integration test rather than written as a standalone test.
- Integration test `tests/test_pipeline_synthetic.py` parametrized over `model in {'taylor', 'exact'}`. Both branches run end-to-end. Closing commit: `e5201fb`. Tag: `stage-3-complete`.
- 17 tests passing (12 prior + 4 new unit tests for the exact branch + 1 new parametrization ID on the integration test).

### Stage 3 architectural decisions worth carrying forward

- **Default remains `model='taylor'`.** Flip is deferred; no driver to flip it yet, and keeping Taylor as default preserves bit-identical behavior for any existing caller.
- **The `+u` denominator convention is the project's operational convention.** Textbook Ch.4 Eq. 4-6 as printed has `−u`; the notebook (cell 25) treats this as a sign typo akin to the missing `2π` in Eq. 4-2. With `−u` the Taylor expansion would carry a `+` bias and disagree with the existing Taylor branch's `−` bias at the leading order. The exact branch's docstring documents this; cell 25 remains the authoritative reference.
- **Validation is informational, not gatekept.** The Taylor-vs-exact comparison is not a strict criterion. Both models are user-togglable. The exact branch in the integration test asserts only `isfinite` and prints `std_err`; no numerical bound is enforced because any bound would be arbitrary and would shift when hardware params change. Rationale: under the reframe, both models are user-facing toggles, not competing implementations to be ranked.
- **The exact branch is `λ_eq`-independent, same invariant as Taylor.** Locked by `test_project_exact_lambda_eq_independent` at `atol=1e-15`. The invariant from Stage 2 holds across both forward models.
- **Denominator-positivity guard.** The exact branch raises `ValueError` if `1 + 2x·tan(θ)/a ≤ 0` anywhere on the grid, with all relevant parameters named in the error message. Protects against future hardware params that violate the small-angle assumption. Does not fire under current defaults (`denom ∈ [1.0, 1.17]`).
- **Object leg of the integration test still skips `project()`.** Per the documented Stage 2.6 deviation, the object stack is synthesized from `phi3 = carrier + K·H_obj` directly. As a result, the parametrized test's `std_err` is identical across both models — the model toggle only affects the calibration leg. The test confirms "the pipeline runs under both models without crashing"; it does NOT independently verify that exact's calibration cancels exact's bias. Cell 23 in the notebook covers that for Taylor; an analogous demonstration for exact is deferred to Stage 4 (where the GUI will exercise it visually) or Stage 6 (hardware).

### Future-stage hooks deferred during Stage 2 / Stage 3

- **`pattern_generator.py`** (Decision 7): empty stub. Stage 5+ when hardware needs framebuffer writes.
- **`io_utils.py`**: empty stub. Adds frame I/O when capture loop lands.
- **`src/test_surfaces.py`**: not yet created. Stage 4+ work. Pure heightmap generators (flat, tilt, Gaussian, step, sphere cap, multi-bump, file-loaded, solder-bump-array). The solder-bump-array generator is the Chapter 5 application — should exist before Stage 6. Symmetric in role to `pattern_generator.py` but for the measurement side, not the projection side.
- **Slider-driven GUI** (Stage 4+): the current architecture supports it cleanly. Both `Geometry` classes take all parameters as constructor args; the pipeline is pure functions over arrays. Changing a slider → new geometry instance → re-run pipeline. No hidden state. Live re-runs of the synthetic pipeline at 480×640 are millisecond-scale; full-res 1280×1024 unwrap is not. With Stage 3 done, the GUI can also expose a Taylor/exact toggle for the forward model without any further math work.
- **`scripts/compare_forward_models.py`**: deliberately not created (Stage 3.2 was skipped). If a future need arises (e.g., a sanity check at real-hardware parameters), cell 25's logic ports cleanly to a standalone script — but the model toggle in the GUI is the operational deliverable.

---

*End of context. Ask the user for clarification before starting work.*
