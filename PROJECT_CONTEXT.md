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

The user has an existing Jupyter notebook (`notebooks/Fringe_Projection_Python.ipynb`) that implements an end-to-end synthetic simulation. **It works** — recovers a Gaussian bump from simulated fringes with mean error ~10⁻⁵ after DC alignment. Stages 1 through 4b have been completed (see Section 12). The notebook is the starting point for refactoring, not a thing to start over.

---

## 2. Hardware Setup

### Currently in the lab (confirmed)

**Camera: FLIR Blackfly S BFS-U3-13Y3M-C** (SN: 26048170)
- Monochrome, USB3 Vision, global shutter
- 1280 × 1024 pixels at 4.8 µm pitch
- Up to 170 fps
- 1/2" sensor format (active area 6.14 × 4.92 mm)
- Body: 29 × 29 × 30 mm (used in Stage 4b's hardware-bodies-in-scene rendering)
- C-mount
- **SDK: Spinnaker / PySpin** (Python bindings)
- Sold by Edmund Optics as stock #36-451

**Camera lens: Edmund Optics #58-259** (TECHSPEC GoldTL Telecentric)
- 0.09× magnification
- 132–182 mm working distance (focusable)
- < 0.2° telecentricity
- 1/2" sensor format
- **Physical lens profile (Stage 4b):** stepped 3-section, 200 mm total length. 76 mm rear (55 mm diameter) + 59 mm taper + 65 mm front (110 mm diameter front element).
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
- **Lens (estimated for Stage 4b digital twin):** ~20 mm diameter × 5 mm protrusion. To be refined when lab-accessible.

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

- Lens center: (X = 21 mm, Y ≈ 1–2 mm recess, Z = 45 mm) — equivalent to (X = −6.5, Z = 17.5) mm in body-centered frame, used in Stage 4b.
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
| **2-51** | **λ_eq general two-angle form: `Mp / (tan θ₁ + tan θ₂)` (textbook form). The code's internal `equivalent_wavelength()` returns `λ_textbook / (2π)`** — the `× ψ/(2π)` from Eq. 2-51 is pre-folded into the wavelength constant. See Section 9 for the naming convention note. | `reconstruction` / `geometry` |
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
Cell 14 uses the symmetric `λ_eq = (p1·M) / (4π sin θ)` formula (Eq. 4-11). The simulation still converges correctly because one consistent θ is used everywhere; the formula is superseded by Stage 3.5's two-angle form from Eq. 2-51.

**Stage 2 update:** the notebook itself is unchanged — Stage 2 refactored the formula into `geometry.py` (both `HybridGeometry` and `SymmetricGeometry` implementations), not into the notebook. The notebook remains as a historical reference and as the source of the regression fixture (`tests/regression_data.npz`).

**Stage 3 update:** notebook cell 25 (Stage 1-S.1) is the spec for the exact-form forward model. The `+u` denominator convention adopted by `project(model='exact')` is documented there and in the function's docstring. Cell 25 stays as the authoritative reference for the sign convention.

**Stage 3.5 update (now complete):** the one-angle hybrid form `λ_eq = Mp / tan(θ_projector)` (Stage 2 Decision 3) was replaced with the two-angle form (Eq. 2-51). The Stage 2 form assumed θ_camera = 0° — a hidden assumption from conflating "telecentric lens" with "camera mounted vertical." Telecentric only locks the lens magnification; the camera body's tilt angle is independent.

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
│   ├── pipeline.py                # Stage 4a — end-to-end pipeline composition
│   ├── io_utils.py
│   ├── test_surfaces.py           # Stage 4a — heightmap generators
│   ├── scene.py                   # Stage 4b — mesh + wireframe builders (pure NumPy)
│   ├── scene_compose.py           # Stage 4b — pose composition layer (arm transforms)
│   └── gui/                       # Stage 4a/4b — PyQt6 GUI package
│       ├── __init__.py
│       ├── __main__.py            # `python -m src.gui` entry
│       ├── app.py
│       ├── main_window.py
│       ├── surface_preview.py     # SurfacePreview + HardwareScene host + ErrorColorbar
│       ├── hardware_scene.py      # Stage 4b — HardwareScene class + compute_arm_transforms
│       ├── clip_detection.py      # Stage 4b — pure NumPy clip-detection (5 checks)
│       └── stages_view.py         # 2×3 grid of pipeline-stage images
├── tests/
│   ├── test_geometry.py
│   ├── test_synthetic_fringes.py
│   ├── test_phase_shifting.py
│   ├── test_unwrapping.py
│   ├── test_calibration.py
│   ├── test_reconstruction.py
│   ├── test_test_surfaces.py
│   ├── test_pipeline.py
│   ├── test_pipeline_synthetic.py
│   ├── test_scene.py              # Stage 4b — mesh/wireframe builders
│   ├── test_scene_compose.py      # Stage 4b — pose composition
│   ├── test_hardware_scene.py     # Stage 4b — arm transforms integration
│   ├── test_clip_detection.py     # Stage 4b — 10 cases (3 collision + 4 coverage advisories)
│   ├── regression_data.npz
│   └── conftest.py
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
| 3.5 | Math layer upgrade: two-angle λ_eq (Eq. 2-51) | No | ✅ Done |
| **4a** | **PyQt6 GUI digital twin: surface library + pipeline + recovered-height view + error overlay + warning banner + stages viewer** | No | ✅ Done |
| **4b** | **Unified hardware-bodies scene: camera + projector bodies + cones added to the same 3D view; live pose sliders; clip-detection (collisions + coverage advisories)** | No | ✅ Done |
| 4c | STL import for arbitrary test objects, sphere super-hemispherical fix, click-and-drag scene manipulation | No | ⏳ Next |
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
`pattern_generator`, `synthetic_fringes`, `phase_shifting`, `unwrapping`, `calibration`, `reconstruction`, `geometry`, `pipeline` should be **pure Python with no hardware dependencies**. They take/return NumPy arrays. This means:
- They can be tested entirely with synthetic data.
- They are reusable (the user's friend is building a separate Three.js geometric simulation — these same math functions support that work).

**Stage 4b extension of this principle:** `src/gui/clip_detection.py` is also pure NumPy despite living under `gui/`. It imports only `scene` (NumPy mesh builders) and numpy. This lets clip-detection be unit-tested without Qt, matching the math-layer discipline.

### 7.3 — Hardware behind a thin interface
When hardware is added, define abstractions like:

```python
class Camera(Protocol):
    def capture(self, exposure_ms: float) -> np.ndarray: ...

class Projector(Protocol):
    def display(self, pattern: np.ndarray) -> None: ...
```

Initial implementations: `MockCamera` (returns synthetic frames), `MockProjector` (saves PNGs / writes to extended display). Real implementations: `FLIRCamera` (PySpin wrapper), `RealProjector` (extended display).

**Note (Stage 4 deferral):** the `Camera` / `Projector` protocols and their mock implementations are deliberately deferred to Stage 5/6, not Stage 4. The Stage 4a/4b GUI calls math modules directly. Rationale: the hardware shape isn't finalized (upgraded projector pending), so designing protocols against unknown specs is premature. When real hardware arrives, the protocols get designed against actual SDK calls and frame formats.

### 7.4 — Honest scale in the 3D scene (Stage 4b)

`Z_EXAGGERATION = 1.0` in `surface_preview.py`. The 3D scene renders the recovered surface at real geometric scale alongside the hardware bodies (also at real scale). This makes the visual scene a **geometric ruler** — when the user sees the surface touch the (graying) lens, that literally means the surface height equals the clip-detection threshold. Any exaggeration would desync the visual from the clip math.

Trade-off accepted: sub-mm specimens visually vanish in the 3D dome at 1×. The error overlay (diverging colormap, already implemented in Stage 4a) is the tool for fine surface variation; the 3D dome conveys macro shape only.

### 7.5 — Banner vs gray semantics (Stage 4b)

The Stage 4b clip-detection system distinguishes two failure modes:

- **Gray hardware override** = physical collision (camera/projector lens intersects surface plane, or assemblies overlap). Pose is not physically buildable.
- **Banner only, no gray** = measurement incompleteness (surface extends outside camera FOV or projector cone). Pose is buildable, but reconstruction values in the uncovered region are simulation artifacts, not real measurements.

The math pipeline keeps running in both cases. The user sees the warning but the simulation produces a heightmap regardless. This is by design — the digital twin should let users explore "silly" rigs and see what the math does in those poses.

---

## 8. Open Questions for Supervisor (not blocking)

1. Is the upgraded projector telecentric? If yes, the hybrid case collapses to symmetric-telecentric (still two angles though).
2. ~~Simplified `λ_eq` formula for the hybrid case?~~ **Resolved at Stage 4 planning:** use Eq. 2-51's two-angle general form. Real hardware will also calibrate empirically against a step gauge per Chapter 4 §4.3.1.
3. Software post-correction (subtract bias from measurement) or hardware pre-correction (project inverse pattern)? Both are mathematically equivalent. Chapter uses pre-correction.
4. How many phase-shift steps (4 or 8)? Notebook uses 4; chapter uses 8. (Stage 4a GUI exposes this as a toggle, 3–8 range.)
5. What calibration artifacts are available in the lab vs. need to be ordered?
6. ~~GUI framework preference?~~ **Resolved:** PyQt6 (per roadmap + Stage 4 plan).
7. **Mount geometry decision:** what are the intended mounting angles for both camera and projector? Chapter 4 Fig. 4-4 shows symmetric (~15° each); Chapter 5 shows asymmetric (camera vertical at 0°, projector at 60°). User mentioned professor's preference for vertical projector — but that requires non-vertical camera to triangulate. Worth deciding before committing physical mount hardware.
8. ~~**Stage 4b prep — physical dimensions to measure**~~ **Resolved during Stage 4b:** camera lens profile measured (stepped 200 mm). Projector lens estimated at ~20mm dia × 5mm protrusion; refine when lab-accessible.

---

## 9. Coordinate / Sign Conventions

- **Projector body frame**: origin at front-bottom-left corner of cube; +X right, +Y into body, +Z up.
- **Wall plane** at projection: Y = −D where D is throw distance.
- **Image arrays**: NumPy convention `(H, W)` = (rows, cols). When mapping to physical X (horizontal) and Y (vertical), array axis 0 = vertical (Y), axis 1 = horizontal (X).
- **Phase units**: radians.
- **Length units**: SI in equations; pixels in synthetic notebook. Document units explicitly in every function docstring.
- **Forward-model bias sign (`project()`):** Taylor branch subtracts a positive bias `(4π/p)·x²·tan(θ)/a`. Exact branch uses `+u` denominator `1 + 2x·tan(θ)/a` to match (notebook cell 25). Textbook Ch.4 Eq. 4-6 prints `−u` — treated as a sign typo, see Section 12 Stage 3 notes.
- **Arm angles**: θ_projector and θ_camera are measured from the test surface normal to the optical axis of the respective arm. θ = 0° means the arm is pointing straight down at the surface (normal-incident). Positive sign = arm tilted to the +X side of the surface; negative sign = arm tilted to the −X side. |θ| = magnitude of tilt from vertical, sign = which side.
- **Lab setup reference frame**: test surface center is the world origin. Surface normal (vertical line through center) is the z-axis. Both arms (projector and camera) are positioned by (angle, distance) where angle is measured from the surface normal and distance is along the arm's optical axis. Both arms remain aimed at the surface center regardless of their angle and distance — these are the only degrees of freedom for arm positioning in the simulator.
- **Stage 4b distance slider semantics:** sliders report **optics convention** (lens-FRONT to surface, NOT body-center to surface). Edmund #58-259 WD range 132–182 mm; Pico Genie throw range 50–200 mm. `compute_arm_transforms` in `hardware_scene.py` adds the body-to-lens offsets internally (camera_body_distance = WD + 215mm; projector_body_distance = throw + 32.5mm). This matches the Edmund spec sheet and the chapter math.

### λ_eq naming convention (Stage 4a clarification)

The code's `Geometry.equivalent_wavelength()` returns a value numerically equal to **`λ_textbook / (2π)`**, not the textbook's λ_eq directly. The `× ψ/(2π)` factor from Eq. 2-51's `h = λ_eq × (ψ / 2π)` has been algebraically pre-folded into the wavelength constant, so `phase_to_height(ψ)` is implemented as `ψ × equivalent_wavelength()` — no separate `/ (2π)` needed downstream. Mathematically the pipeline output matches Eq. 2-51 exactly; only the *variable named* `lambda_eq` is conceptually `height-per-radian-of-phase`, not the textbook's wavelength.

This is documented in `geometry.py` and was confirmed correct by trace verification during Stage 4a task 4c (no physics bug; only the variable naming is potentially confusing to a reader cross-referencing the chapter PDF). The Stage 4a GUI's degenerate-case warning banner displays the **textbook form** of Eq. 2-51 (`λ_eq = Mp / (tan θ_proj + tan θ_cam)`) so users reading the warning while consulting the chapter see the same equation.

A rename of `equivalent_wavelength()` → `height_per_radian()` is a deferred cosmetic improvement; not blocking, not scheduled.

### Unit conventions: math layer vs. info-panel display (Stage 4a unresolved)

The math layer was written in **notebook pixel-space units** (M = 1, p in pixels, a in pixels, X = np.arange(W) for the carrier). The Stage 4a GUI's info panel displays **mm-space hardware values** (M = 11.1 chapter convention, p = 2.0 mm, a = 50 mm). These two unit systems are currently **not reconciled** — they coexist as parallel descriptions:

- `_build_geometry()` in `main_window.py` constructs `HybridGeometry` with hardcoded notebook-unit values (M=1.0, p=40.0, a=2000.0). These produce sensible recovery output.
- The info panel labels display the mm-space hardware values. They're decorative — they don't drive the math.

Reconciliation is a Stage 5/6 concern. When real hardware arrives, the math-layer constants will be derived from the info panel's mm values + the camera's object-space pixel pitch (~53 µm/pixel). At that point both views become consistent. For now, both are honest descriptions of what's true at their respective layer.

The mismatch was surfaced during Stage 4a task 4 when literal info-panel values were initially plugged into the math layer, producing recovery output ~3000× the input magnitude (Nyquist-aliased carrier × ~123× λ_eq inflation). Magnitude sanity check caught it before commit.

---

## 10. User Notes for Working with Claude Code

- Prefers **short concrete answers** over long expositions.
- Learns by analogy and step-by-step physical reasoning.
- Pushes back on hand-wavy assumptions (correctly).
- Comfortable with Python, decent experience.
- Has Claude Code, Git, Conda, MATLAB, VS Code, Node.js installed.
- Wants to validate algorithm thoroughly in simulation before touching real hardware.
- When the user says "I don't get this," simplify rather than doubling down on technical accuracy. Shorter answers, more analogy, fewer equations.
- **No Co-Authored-By trailers in commit messages.** Project convention from Stage 4b onward. User drives design decisions; Claude Code writes implementation.
- **Push only at end of stage**, not per sub-task. Stage tag + push happen together.
- **PROJECT_CONTEXT.md and CONVERSATION_SUMMARY.md are updated by the user** at stage close (not by Claude Code). Strategy chat drafts the updates; user replaces the files manually and commits them.

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

## 12. Stage Completion Notes & Architectural Decisions

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
3. ~~**`λ_eq` formula:** use `M·p / tan(θ_projector)` (reduction of Eq. 2-51 with θ_camera → 0).~~ **SUPERSEDED by Stage 3.5:** use Eq. 2-51's full two-angle form. The original Stage 2 simplification conflated "telecentric camera lens" with "camera mounted vertical (θ_camera = 0°)" — these are different things.
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

- **`project()` is `λ_eq`-independent.** The Taylor forward model reads only `p`, `theta_projector`, and `a` from the Geometry — never `lambda_eq`. This means `HybridGeometry` and `SymmetricGeometry` produce bit-identical `project()` output (test `test_project_is_lambda_eq_independent` locks this invariant). `λ_eq` enters only at the height↔phase boundary in `reconstruction.py`. **Stage 3's exact-Eq.-2-44 forward model preserves this invariant** (test `test_project_exact_lambda_eq_independent`, atol=1e-15). **Stage 3.5 preserved it too** — adding `theta_camera` to `HybridGeometry` doesn't affect `project()`, only `equivalent_wavelength()`.

- **Two tilt fits live in `calibration.py`, not one. They are NOT interchangeable on non-trivial inputs.**
  - `fit_tilt_plane` (2D lstsq, `[x, y, 1]` design matrix): for flat references or any measurement where genuine y-tilt may be present.
  - `fit_tilt_line_1d` (1D polyfit on row-mean, tiled): for object-phase self-calibration per Ch.4 §4.3.1 / notebook cell 18. The recovered tilt has `m_y == 0` by construction.
  - The two diverge by ~4e-5 in recovered height on object-phase fixtures. `recover_object_height` uses `fit_tilt_line_1d`; `compute_inverse_phase` uses `fit_tilt_plane`.

- **`recover_object_height` subtracts a self-cal tilt, not a cross-cal flat-reference phase.** This matches notebook cell 18's `tilt3_2d`. The function signature is operand-agnostic — the caller passes `phi_calibration`. When real cross-calibration enters in Stage 6, the same function still works.

- **The integration test does NOT exercise the closed inverse-grating loop.** Synthesizes object stack from `phi3` directly. Same tautology limit as Stage 1's omitted 1-S.4. Real validation needs cross-impl or hardware.

- **Real hardware values (Section 2) replace toy defaults when measured.** Both `HybridGeometry` and `SymmetricGeometry` currently default to identical bias parameters. When real values arrive in Stage 6, both geometries' defaults must update in lockstep, or the bit-identical `project()` invariant silently breaks.

### Stage 3 — Done

- 3.1 added `model='exact'` branch to `project()` per cell 25's `+u` denominator. 4 new unit tests including a `test_project_exact_lambda_eq_independent` invariant at atol=1e-15. Commit: `b752f47`.
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

### Stage 3.5 — Done (Math layer upgrade: two-angle λ_eq)

**Why this existed.** Stage 4 planning surfaced that `HybridGeometry.equivalent_wavelength()` was using `λ_eq = Mp / tan(θ_projector)` — the Eq. 2-51 form with `θ_camera = 0°` assumed. The Stage 2 reasoning for this simplification ("telecentric camera → drop θ_camera") was wrong: telecentric only locks the lens magnification; the camera body's tilt angle is independent.

**What landed (commit `658f331`, pushed, not tagged — pre-task to 4a):**

- `HybridGeometry` and `SymmetricGeometry` both gained `theta_camera` as a constructor arg with default `= theta_projector` (preserves fixture compatibility — the symmetric default matches Eq. 2-52, which is what the old single-angle form effectively computed).
- `equivalent_wavelength()` now returns `M·p / (2π·(tan θ_proj + tan θ_cam))`. Note: this is `λ_textbook / (2π)`, not λ_textbook itself — see Section 9 "λ_eq naming convention."
- Degenerate case (`tan θ_proj + tan θ_cam = 0`) returns `float('inf')`, no exception.
- 30 tests passing (17 baseline + 13 new in `tests/test_geometry.py`).

**Spec deviation worth noting:** `tests/test_reconstruction.py` needed a small update because it was reading `phi3_unwrapped` directly from the regression fixture (generated on the old Eq. 4-11 sin formula). After the Stage 3.5 math change, the cross-coupled `λ_eq` leaked ~1e-6 residual. Fix: derive `phi3_unwrapped` internally via PSI extract + unwrap, matching the integration test's pattern. The fixture itself was untouched.

**Architectural invariants preserved:**
- `project()` stays `λ_eq`-independent at atol=1e-15.
- HybridGeometry and SymmetricGeometry remain bit-identical in their `project()` output.

### Stage 4a — Done (PyQt6 GUI digital twin)

**Goal achieved.** A PyQt6 GUI that operates as a digital twin of the lab's fringe projection setup, with the following deliverables landed:

1. Heightmap generator library (5 surfaces: flat, tilt, Gaussian, step, sphere)
2. PyQt6 + PyQtGraph GUI with live slider-driven updates
3. Full pipeline integration (forward model → PSI extract → unwrap → calibrate → reconstruct)
4. Error overlay toggle with diverging colormap, colorbar legend, and stats panel (mean / std / max abs / RMS)
5. Degenerate-case warning banner (when tan θ_proj + tan θ_cam ≈ 0)
6. Pipeline stages viewer — 2×3 grid showing all intermediate stages as live camera-view images with equations: ground truth → projected fringes → wrapped phase → unwrapped phase → recovered height
7. View mode toggle (3D Scene ↔ Pipeline Stages)

**Stage 4a sub-task table:**

| Task | Commit | What landed |
|---|---|---|
| 1 (surface library) | `f4bd4fb` | `src/test_surfaces.py` — 5 pure-NumPy heightmap generators with `_centered_grid_mm` helper. 30 unit tests in `tests/test_test_surfaces.py`. Centered (H, W) float64 outputs in mm. |
| 2 (GUI skeleton) | `e45bff5` | `src/gui/` package with `__init__.py`, `__main__.py`, `app.py`, `main_window.py`. PyQt6 + PyQtGraph + PyOpenGL added to `environment.yml` pip section. QMainWindow with QSplitter, all widget tree built layout-only with one wired behavior (dropdown → QStackedWidget page). |
| 3 (live preview wiring) | `cfa0772` | `src/gui/surface_preview.py` — `SurfacePreview(GLViewWidget)` with reference grid + `GLSurfacePlotItem` + viridis colormap + 'shaded' shader. Surface controls wired to live 3D rendering of ground-truth heightmap. First math import in GUI (`src.test_surfaces`). Pyqtgraph `GLSurfacePlotItem` colors quirk documented (upstream `colors=` docstring is wrong; flat `(N_vertices, 4)` is required). |
| 4 (pipeline integration) | `fa12e30` | `src/pipeline.py` — `run_pipeline()` end-to-end. `_build_geometry()` constructs `HybridGeometry` from slider values. `theta_projector`, `theta_camera`, `psi_steps` wired. `projector_distance_mm` intentionally inert (lab view concern). `SurfacePreview` now renders recovered height. 8 new pipeline tests. Geometry constants use **notebook pixel-space units** (M=1, p=40 px, a=2000 px); info panel's mm-space values are decorative — reconciliation deferred to Stage 5/6. |
| 4b (error overlay) | `f224a4f` | "Display Mode" groupbox with overlay checkbox. "Error Statistics" groupbox (hidden when overlay off) with mean/std/max-abs/RMS labels. Diverging CET-D1 colormap on signed error. `SurfacePreview.update_heightmap(error_mm=...)` overlay path. `Z_EXAGGERATION = 20.0`. Amplitude slider maxes bumped to 100 mm (Gaussian amplitude, Step height, Sphere cap height). |
| 4c (warning banner) | `03ed339` | Degenerate-case warning banner (red rich-text QLabel) at the top of the right pane when `\|tan θ_proj + tan θ_cam\| < 1e-3`. Pipeline short-circuits in degenerate state; 3D view keeps last good frame. `ErrorColorbar` widget below `view_3d` showing colormap range with `-max / 0 / +max` labels. `Z_EXAGGERATION` dropped to 2.0 (prep for Stage 4b's real-scale hardware bodies). Error stats auto-format to scientific notation when sub-precision (< 1e-4 mm). |
| 4d (stages viewer) | `13a4372` | `src/gui/stages_view.py` — `StagesView(QWidget)` with 2×3 grid of 5 panels (ground truth, projected fringes, wrapped phase, unwrapped phase, recovered height) each with title + `pyqtgraph.ImageView` + equation label. Last cell empty per spec. `src/pipeline.py` refactored: `run_pipeline(..., return_stages=True)` returns `(recovered, stages_dict)` with refs to intermediates (no extra computation). "View Mode" groupbox with `3D Scene` / `Pipeline Stages` radio buttons. Right pane wrapped in `QStackedWidget`. CET-C1 cyclic colormap on wrapped phase; manual black-to-white gray ramp on fringe frame (pyqtgraph 0.14.0 doesn't bundle 'gray' or 'hsv'). 2 new pipeline tests for `return_stages` (70 total). |
| 4e (close) | `7ecd788` | Docs update + tag `stage-4a-complete`. |

**Architectural decisions worth carrying forward from Stage 4a:**

- **Working model held up.** Strategy chat drafts prompt → user pastes to Claude Code → Claude Code summarizes back → implements + tests + commits → user pastes diff back to strategy chat for review. Pattern worked across all 7 sub-tasks. "Summarize back" caught real issues (the unit-mismatch in task 4, the colormap-name unavailability in task 4b/4d) before commits landed.

- **`run_pipeline` is the entry point for any caller that needs end-to-end fringe projection.** GUI calls it. Future scripts call it. `return_stages` kwarg exposes intermediates without imposing the cost on default callers.

- **The 8 pipeline tests in `tests/test_pipeline.py` lock the contract** but are λ-cancellation-immune (self-cal recovery is structurally independent of λ_eq). A 2π-magnitude bug would not be caught by these tests. Real magnitude validation needs cross-implementation comparison or hardware. This is acknowledged in `tests/test_pipeline_synthetic.py` and `tests/test_reconstruction.py` docstrings.

- **The fringe-frame equation displayed in the stages viewer matches what the code actually computes**, not the textbook Taylor form. The pipeline's object leg skips `project()` (matches integration test's deliberate omission); the rendered fringe frame is `I = A + B·cos[2π·x/p + h/λ_eq + δ_k]`. This is honest.

- **The "View Mode" radio toggle lives on the left pane**, not as an overlay on the right. Keeps the right pane pure visualization, no UI chrome. Locked design decision.

- **STL-import flow (deferred to Stage 4c)** will plug into the existing `make_*` surface contract `(shape, pixel_size_mm) → (H, W) float64 heightmap in mm`. Any STL importer that produces this contract slots into the existing GUI with zero changes elsewhere.

### Stage 4b — Done (Unified hardware-bodies scene + clip-detection)

**Goal achieved.** The lab's physical apparatus (camera body, camera lens, projector body, projector lens, viewing cone, projection cone) now lives in the same 3D scene as the recovered surface. Live pose sliders rotate/translate hardware in real time. Five clip-detection checks (3 collision + 2 coverage) drive gray-override and warning banners.

**Stage 4b sub-task table:**

| # | Commit | What landed |
|---|---|---|
| 1 | `3c4e5e5` | `src/scene.py` mesh builders: camera/projector body cubes (29×29×30, 55³ mm), CCW outward winding, pure `(verts, faces)` tuples. 12 tests, total 82. |
| 2 | `fbc5853` | `_cylinder`, `_stepped_cylinder` helpers. `make_camera_lens` (Edmund stepped 3-section, 200mm), `make_projector_lens` (20×5mm). `src/scene_compose.py` new: `camera_arm_transform`, `projector_arm_transform` (4×4 row-major float32), `body_lens_offset`. 33 new tests, total 115. |
| 3 | `7bb2b41` | `src/gui/hardware_scene.py` new: `HardwareScene` class + `compute_arm_transforms`. `SurfacePreview.update_hardware_pose` pass-through. main_window: new `camera_distance` slider (132–182mm Edmund WD), renamed sliders to optics convention. **Slider value = lens-FRONT to surface (not body-center).** View distance bumped 80→600mm. `LabeledFloatSlider.set_value()` added. 6 new tests, total 121. |
| 4 (1/3) | `e96e1fc` | Cones + clip-detection v1. `make_projection_cone_wireframe` (5v/8e diverging pyramid), `make_viewing_cone_wireframe` (8v/12e telecentric prism — parallel sides). `cone_local_to_world_transform` helper. `src/gui/clip_detection.py` new: `detect_clips` with 3 checks: camera/projector lens vs surface plane (disc-edge: `WD·cos(θ) − r·sin(θ) < 0`), body assembly AABB overlap. `ClipState` dataclass. Theta sliders extended ±60° → ±75°. Gray override `(0.4, 0.4, 0.4, 1.0)` + warning banner. 18 new tests, total 139. |
| 4 close (Z retune) | `45c2071` | **Z_EXAGGERATION 2.0 → 1.0** (honest scale). Single-constant change. User picked from empirical 4-screenshot comparison (Z = 1, 2, 5, 10) at the close of sub-task 4. |
| 4 (2/3, REVERTED) | `c53dd36` → `20d6771` | Originally added surface-peak-vs-lens 3D contact checks. **Reverted** because checks are unreachable in practice: at slider ranges (WD 132–182, surface amp 0–100, θ ±75°), no pose produces lens-on-peak contact. Lens always clears the peak by ≥30mm at min WD; tilting only increases clearance. Same for projector. Revert restores `ClipState` to 3 reachable collisions. 139 tests. |
| 4 (3/3) | `5d4b4c4` | **FOV/cone coverage advisories — 3D volume tests.** Replaces the buggy 2D z=0 footprint coverage check with 3D point-in-volume tests against the camera viewing prism and projector projection cone. 11×11 heightmap sampling. Catches both lateral spill (wide surface) and vertical spill (tall Gaussian peak penetrating tilted prism's "ceiling" — the bug found in live GUI testing). Cone test uses angular criterion only (no `s ≤ throw` bound — throw is DLP focus distance, not light cutoff). Banner-only, no gray override. 4 new tests, total 143. |
| 5 (close) | this commit | Docs update + tag `stage-4b-complete`. |

**Key design decisions locked during Stage 4b:**

| Decision | Rationale |
|---|---|
| Distance sliders = lens-front (optics convention), NOT body-center | Matches Edmund spec + chapter math. `compute_arm_transforms` adds body offsets internally. |
| `Z_EXAGGERATION = 1.0` honest scale | Hardware bodies provide visual scale reference; exaggeration would desync visual from clip math. Sub-mm specimens vanish — by design; error overlay handles fine variation. |
| Theta sliders ±75° (was ±60°) | Surface-clip cases need ~67° to fire at minimum WD. Defaults stay ±30°. |
| No surface-vs-lens contact checks | Unreachable in practice with slider ranges. Removing dead code keeps the module clean. |
| FOV/cone coverage as banner-only, not gray | Coverage failure = measurement incompleteness, not physical collision. Gray would imply unbuildable rig. |
| 3D point-in-volume coverage tests, not 2D footprint | The 2D footprint check missed tall peaks penetrating the prism's "ceiling" at tilt. 3D is geometrically correct. |
| Strict-correctness FOV check (no tolerance) | Hairline triggers happen only at extreme synthetic surfaces (amp=100mm) that won't exist in real fringe projection use. Tolerance would hide real coverage failures and require a magic threshold. |
| Cone test: `s ≥ 0` only, no upper bound | `throw` is DLP focus distance, not a hard light cutoff — the beam keeps diverging past it. Bounding at throw plane false-flagged flat surfaces. |
| 11×11 grid sampling | Catches both lateral and vertical spill at constant ~250µs/tick cost. |
| No Co-Authored-By trailers | User drives design decisions; Claude Code writes implementation. Established as project convention. |

**Architectural decisions worth carrying forward from Stage 4b:**

- **Math-layer purity extended to clip-detection.** `src/gui/clip_detection.py` is pure NumPy (imports only `scene` + numpy). Despite living under `gui/`, it's headlessly unit-testable. Same discipline as the math layer.

- **Two banners stack independently above the GL viewport.** The degenerate-λ_eq banner (Stage 4a) short-circuits the pipeline. The clip-warning banner (Stage 4b) is advisory — math keeps running. Both can be visible simultaneously.

- **Banners live above the GL framebuffer in the Qt widget stack.** They DO appear in the live GUI but NOT in `grabFramebuffer()` captures. Smoke tests verify banner state programmatically (read `.isVisible()` and `.text()` in Python).

- **Two-phase smoke-test pattern** for sub-tasks involving visual change: programmatic GUI launch + `view_3d.grabFramebuffer()` captures to `%TEMP%`, gated by user greenlight before commit. One-process-per-render rule: a reconstruction loop in a single process leaves all-but-first-window's framebuffer blank, so each pose config gets its own `python script.py <arg>` invocation.

- **The 3D viewport is a geometric ruler** (with Z=1.0). When the user sees the surface touching the (graying) lens, that literally means the surface height equals the clip-detection threshold. This is the most important pedagogical property of Stage 4b — and the reason `Z_EXAGGERATION` is locked at honest scale.

- **Stage 4b sub-task 4 went through a reset.** Surface-vs-lens contact checks (commit c53dd36) were added then reverted (commit 20d6771) when interactive testing showed they're unreachable from slider ranges. The reset is preserved in history rather than rebased away, because the lesson — "validate that the bug can actually be triggered before adding the check" — is worth remembering for Stage 4c.

### Stage 4b hardware specs encoded in code

Constants in `src/gui/hardware_scene.py`:

```python
_CAMERA_BODY_DEPTH_MM = 30.0
_CAMERA_LENS_LENGTH_MM = 200.0  # Edmund stepped profile total
_PROJECTOR_BODY_DEPTH_MM = 55.0
_PROJECTOR_LENS_LENGTH_MM = 5.0  # protrusion only
PROJECTOR_LENS_X_OFFSET_MM = -6.5  # Pico Genie body-frame measurement
```

Constants in `src/gui/clip_detection.py`:
- Lens front radii: `_LENS_FRONT_RADIUS = {camera: 55.0, projector: 10.0}` mm
- Prism half-extents: `_PRISM_HALF_U_MM = 34.0`, `_PRISM_HALF_V_MM = 27.5` mm (= 68/2, 55/2 — derived from `make_viewing_cone_wireframe`)
- Cone divergence: `_CONE_HALF_U_PER_L = 1.0/2.4`, `_CONE_HALF_V_PER_L = (1.0/2.4) * 9/16` (1.2:1 throw, 16:9 aspect — derived from `make_projection_cone_wireframe`)

All clip-detection geometry constants are derived from the cone builders themselves at module load, so the math tracks `scene.py` rather than duplicating spec numbers.

### Stage 4 controls (locked as of Stage 4b close)

**Sliders / dropdowns in the GUI:**

| Control | Type | Range / Options | Status |
|---|---|---|---|
| Surface type | dropdown | flat, tilt, Gaussian, step, sphere | ✅ Wired |
| Per-surface params | sliders | depends on surface | ✅ Wired. Amplitude/height maxes 100 mm. |
| **θ_projector** | slider | **−75° to +75°** (extended in 4b) | ✅ Wired (Eq. 2-51 triangulation). |
| **θ_camera** | slider | **−75° to +75°** (extended in 4b) | ✅ Wired (Eq. 2-51 triangulation). |
| Projector throw distance (lens-front to surface) | slider | 50–200 mm | ✅ Wired (4b). Drives projector body translation + cone size. |
| Camera working distance (lens-front to surface) | slider | 132–182 mm | ✅ Wired (4b). Drives camera body translation. |
| PSI step count | spinbox | 3–8 | ✅ Wired. |
| View Mode | radio | 3D Scene / Pipeline Stages | ✅ Wired. |
| Show error overlay | checkbox | on/off | ✅ Wired. |

**Locked in code, shown in read-only info panel:**

| Quantity | Value | Source |
|---|---|---|
| Camera M (modern) | 0.09× | Edmund Optics #58-259 lens spec |
| Camera M (chapter) | 11.1× | 1/0.09 — info panel display |
| Camera FOV | 68 × 55 mm | Derived: sensor 6.14×4.92 mm / M |
| Pixel pitch on surface | ~53 µm | Derived: 4.8 µm / M |
| Sensor | 1280×1024 at 4.8 µm | FLIR Blackfly spec |
| Projector throw ratio | 1.2:1 | Pico Genie spec |
| `a` (projector internal, math layer) | 2000 px | Notebook fixture units |
| `p` (fringe period, math layer) | 40 px | Notebook fixture units |
| `a` (projector internal, info panel display) | 50 mm | Hardware estimate (Stage 5/6 reconcile) |
| `p` (fringe period, info panel display) | 2.0 mm | Hardware estimate (Stage 5/6 reconcile) |
| `λ_eq` | live (internal) | Derived: `Mp / [2π·(tan θ_proj + tan θ_cam)]` (code form, = λ_textbook/(2π); see Section 9) |
| Forward model | `'taylor'` | Stage 3 default; toggle in GUI deferred |
| GUI resolution | 480×640 | Live updates |

**Degenerate case handling (implemented):**
- When `|tan(θ_proj) + tan(θ_cam)| < 1e-3`, the pipeline short-circuits; warning banner shows with textbook-form Eq. 2-51 and the explanation that triangulation requires angular separation.
- The 3D view (or stages view) keeps the last good frame so the user can drag back without seeing a crash or NaN garbage.

**Clip-detection warning banner (new in 4b):**
- 5 advisory checks (3 collision + 2 coverage). Collisions gray the offending hardware bodies + cones; coverage advisories show banner only.
- Banner is independent of the degenerate-λ_eq banner; both can show simultaneously.
- Math pipeline keeps running regardless of clip state.

### Critical reasoning that drove the slider list (preserve this — easy to forget)

- **The chapter's `M = l/b` (Eq. 2-41) is a camera-arm ratio.** Projectors don't have an "M" in the chapter's framework. They have `a` (internal grating-to-lens distance) and a throw ratio (lab-side). Conflating camera-M with projector behavior was a planning false start.
- **`a` is fixed by projector hardware.** It's the physical distance from DMD chip to projector lens. Moving the projector in the lab does NOT change `a`. Therefore "projector distance" cannot drive `a` and cannot affect the chapter's bias math.
- **Telecentric camera: M and distance are independent.** Within 132–182 mm WD, M stays at 0.09× regardless of camera position. Moving the camera only affects focus, not FOV. FOV is locked at 68×55 mm. **But the camera's tilt angle is independent of M** — telecentric doesn't mean "mounted vertical." This was a separate false start (Stage 2 Decision 3's hidden assumption) that Stage 3.5 corrected.
- **Projector distance affects coverage, not math.** The slider exists for lab-design intuition. **Now meaningful in Stage 4b's unified scene** (drives projector body translation + cone size).
- **Symmetric assumption (Fig. 4-4) is expository, not required.** The chapter writes derivations under symmetric arms for clarity, but Eq. 2-51 is the general two-angle form. Asymmetric arms (different angles, different distances) are fine; the math handles them.
- **Both arm angles are independent.** Stage 4a's GUI exposes both θ_projector and θ_camera as sliders. The user can explore symmetric, asymmetric, vertical-projector, vertical-camera, and degenerate configurations.

### Stage 4c — Deferred features

**STL import for arbitrary test objects** (the headline feature for Stage 4c). Architecturally enabled by Stage 4a's `(shape, pixel_size_mm) → (H, W) float64 mm` heightmap contract. Implementation needs:
- `QFileDialog` for STL picker
- One-shot config dialog (viewing axis + Z-offset + scaling)
- Mesh rasterization onto the heightmap grid (numpy-stl or trimesh library; need to evaluate)
- Plug into existing surface dropdown as "STL file..." option

Plugs into existing pipeline with zero math-layer changes.

**Sphere super-hemispherical cliff bug.** `make_sphere` in `src/test_surfaces.py` is only C0-continuous when `cap_height ≤ footprint_radius`. For `h > a`, the sagitta formula gives `R < h` and `z(footprint_radius) ≠ 0`, producing a discontinuous cliff (~33.7 mm → 0 at h=43, a=20) that renders as a vertical-walled mesa. Fix in the surface model (validate/clamp `cap_height ≤ footprint_radius`, or rewrite to handle tall caps), not the renderer. `GLViewWidget` clip planes ruled out empirically during Stage 4b close (near/far changes had no effect; tightening them degraded the hardware bodies). Won't affect STL files (STL brings its own mesh).

**Click-and-drag scene manipulation.** Let user reposition cameras / surface via mouse drag in the 3D view. Needs raycasting + Qt mouse-event capture.

### Deferred from Stage 4 (still deferred)

- **MockCamera, MockProjector, Camera/Projector protocols** → Stage 5/6.
- **Taylor/exact model toggle in GUI** → adds two lines later; not v1.
- **Resolution toggle (480×640 vs 1280×1024)** → adds a "Compute at full res" button later.
- **Three.js embed for lab view** → explicitly rejected; lab view is native PyQt6 (now part of unified scene).
- **Object position offset** → locked at center.
- **`equivalent_wavelength()` → `height_per_radian()` rename** → cosmetic; documented in code instead.
- **Unit reconciliation between info panel mm-values and math-layer pixel-values** → Stage 5/6 when real hardware arrives.

### When real hardware arrives (Stage 6 prep)

- Update `HybridGeometry` defaults to real measured values (`a`, `p`, θ_projector_actual, θ_camera_actual, distances) — in physically-consistent units after deciding the unit story.
- Reconcile the math-layer pixel-space constants with the info-panel mm-space display.
- Empirically calibrate `λ_eq` against a step gauge; override formula-derived value if needed.
- `test_project_is_lambda_eq_independent` must still pass after the update — `HybridGeometry` and `SymmetricGeometry` defaults must change in lockstep.
- Scene primitives in `src/scene.py` (Stage 4b) update to reflect real lab layout. Projector lens dimensions (~20mm dia × 5mm protrusion) refined from lab measurement.

### Future-stage hooks deferred during Stages 2–4

- **`pattern_generator.py`** (Stage 2 Decision 7): empty stub. Stage 5+.
- **`io_utils.py`**: empty stub. Adds frame I/O when capture loop lands.
- **`scripts/compare_forward_models.py`**: deliberately not created.
- **`MockCamera` / `MockProjector` / Camera-Projector protocols**: deferred to Stage 5/6.

---

## 13. Clip-detection geometry reference (NEW in Stage 4b)

This section documents the precise 3D math used in `src/gui/clip_detection.py`. Self-contained: a fresh chat / future maintainer can reconstruct the geometric reasoning from here alone.

### 13.1 Five checks at a glance

`detect_clips(transforms, *, heightmap_mm, surface_pixel_size_mm, camera_distance_mm, projector_distance_mm, viewing_cone_world, projection_cone_world)` returns a `ClipState` with five booleans:

**Collision checks** (gray-override on offending hardware + warning banner):
1. `camera_clipping_surface` — camera lens-front disc dips below z=0 plane
2. `projector_clipping_surface` — projector lens-front disc dips below z=0 plane
3. `bodies_overlapping` — camera assembly AABB overlaps projector assembly AABB (in world frame)

**Coverage advisories** (banner only, no gray):
4. `surface_outside_camera_fov` — any 3D surface sample is outside the camera viewing prism volume
5. `surface_outside_projector_cone` — any 3D surface sample is outside the projector cone volume

### 13.2 World-frame axis extraction

The viewing prism and projection cone each have a `(4, 4)` world transform computed by `cone_local_to_world_transform` in `scene_compose.py`. To extract a world-frame direction vector from a local-frame direction:

```python
def _world_unit(M, local_dir):
    """Local direction (w=0) -> world, normalized.
    Row-major convention: (M @ [x, y, z, 0])[:3]."""
    d = (M @ np.asarray(local_dir, float))[:3]
    n = np.linalg.norm(d)
    return d / n if n > 0 else d
```

Local axes commonly used:
- `[1, 0, 0, 0]` → u-axis (cross-section "horizontal")
- `[0, 1, 0, 0]` → v-axis (cross-section "vertical")
- `[0, 0, 1, 0]` → optical axis (along arm direction toward surface)

The `w = 0` term ensures the result is a *direction*, not a position (translation is ignored).

To extract a world-frame *position* from a local point (e.g., lens center, cone apex), use:

```python
center = (M @ [0, 0, 0, 1])[:3]
```

### 13.3 Telecentric viewing prism (camera) — 3D point-in-volume

The Edmund #58-259 is **telecentric**: chief rays through the rear aperture stop are constrained parallel. The viewing volume is therefore a rectangular **prism** (parallel sides), not a true cone. Cross-section is fixed at 68 × 55 mm regardless of axial position.

Test: is a world-frame 3D point `P` inside the prism?

```python
C = (viewing_cone_world @ [0, 0, 0, 1])[:3]       # lens-front center
u = _world_unit(viewing_cone_world, [1, 0, 0, 0]) # 68mm-side axis
v = _world_unit(viewing_cone_world, [0, 1, 0, 0]) # 55mm-side axis

d = P - C
u_proj = d @ u                  # along-u offset from axis
v_proj = d @ v                  # along-v offset from axis

inside = (abs(u_proj) <= 34.0) and (abs(v_proj) <= 27.5)
```

The along-axis coordinate is **deliberately ignored** — that's the defining property of telecentric. Any depth is fine; only the perpendicular offset from the optical axis matters.

This works for ALL camera tilts. The prism axes rotate with the camera arm; the |u|, |v| checks remain against the same fixed half-extents.

### 13.4 Projection cone (projector) — 3D point-in-volume

The Pico Genie is **non-telecentric**: the cone diverges linearly from the lens. At axial distance `s` from the apex, the cone's cross-section half-extents are:

```
hw(s) = (s / 1.2) / 2 = s / 2.4
hh(s) = hw(s) * 9 / 16
```

These derive from the 1.2:1 throw ratio (width = throw / 1.2) and 16:9 aspect.

Test: is a world-frame 3D point `P` inside the cone?

```python
apex = (projection_cone_world @ [0, 0, 0, 1])[:3]
axis = _world_unit(projection_cone_world, [0, 0, 1, 0])
u    = _world_unit(projection_cone_world, [1, 0, 0, 0])
v    = _world_unit(projection_cone_world, [0, 1, 0, 0])

rel = P - apex
s   = rel @ axis            # along-axis distance from apex
lat = rel - s * axis        # lateral component (perpendicular to axis)
lu  = lat @ u
lv  = lat @ v

inside = (s >= 0) and (abs(lu) <= s/2.4) and (abs(lv) <= (s/2.4) * 9/16)
```

**Why `s >= 0` only, no upper bound:** `throw` is the projector's nominal DLP **focus distance**, not a hard light cutoff. The beam keeps diverging past it. The outer regions of a flat surface sit a few mm beyond the tilted nominal-focus plane (`s` slightly > throw) yet are physically still illuminated. Bounding at `s ≤ throw` would false-flag those regions. The angular criterion alone is the correct coverage test. This was a real geometry correction discovered during Stage 4b sub-task 4 (3/3); the original plan had `s ≤ throw` and the clean-baseline test failed until the bound was dropped.

### 13.5 Disc-edge math for surface-plane collision (checks 1, 2)

A lens-front "disc" (camera 110mm dia = 55mm radius; projector 20mm dia = 10mm radius) tilts with the arm. At arm tilt `θ` and lens-front center world-z `z_center`, the disc's **lowest world-z** is:

```
disc_lowest_z = z_center - r * sin(θ)
              = WD * cos(θ) - r * sin(θ)
```

(WD = working distance; `z_center = WD * cos(θ)` at θ measured from vertical.)

Collision fires when `disc_lowest_z < 0` (disc has dipped below the surface plane). This catches the *edge* of the lens hitting the surface even when the *center* is still above — critical at high tilt.

### 13.6 11×11 grid sampling rationale

The heightmap is sampled on 11×11 = 121 points spanning the modelled surface region. For each sample `(x_s, y_s)`, the height is read from the heightmap and the 3D point `(x_s, y_s, h_s)` is tested against the prism / cone volumes (Sec 13.3, 13.4).

**Why 11×11:** dense enough to catch both failure modes —
- **Lateral spill:** a wide surface footprint with corners outside the cone (11×11 grid puts samples at the corners and edges of the surface, catching this)
- **Vertical spill:** a tall narrow peak whose tip pokes out of the tilted prism volume (the central samples catch this — the peak is usually at or near the origin)

Cost: 121 samples × 2 vectorized tests per pose update ≈ 250µs total. Negligible at every slider tick.

### 13.7 Hairline-trigger behavior (documented as feature)

At extreme synthetic surface heights (e.g., Gaussian amp=100 mm with camera tilted -20° at WD=157, where the 100mm peak's tip sits 0.25 mm outside the FOV `u_proj = +34.248 mm > 34.0 mm`), the advisory will fire on a single sample at the boundary.

This is honest geometric reporting, not a bug or tunable parameter. Real fringe projection measures sub-mm features (solder bumps ~40µm); the 100mm amplitude slider was set in Stage 4a for math-layer exploration before hardware bodies were in the scene. The hairline triggers happen only at slider extremes that don't exist in real operation.

Alternatives considered and rejected:
- **Tolerance margin** (e.g., flag only if exceeding by > 1mm): hides real coverage failures; magic threshold.
- **Sample-count threshold** (e.g., flag only if > K of 121 samples outside): depends on grid resolution; magic threshold.

### 13.8 Body-overlap AABB approximation

Check 3 (`bodies_overlapping`) uses world-frame AABB (axis-aligned bounding box) intersection between the camera assembly (body + lens AABB union) and projector assembly. Rotated bodies have inflated AABBs vs. their true oriented bounding boxes — this makes the check **slightly over-sensitive on rotation** (it may flag near-collisions as collisions). Acceptable for advisory feedback. Documented in the function docstring.

A future OBB (oriented bounding box) implementation would be more accurate but more complex; deferred unless real false positives surface.

---

## 14. Known cosmetic issues

**Sphere super-hemispherical cliff** — see Stage 4c deferred features in Sec 12. Sphere surface renders as a "carved mesa" when `cap_height > footprint_radius`; bug is in `make_sphere`, not in the renderer.

**pyqtgraph 0.14.0 destructor noise** — harmless `RuntimeError` on shutdown from pyqtgraph's GraphicsView teardown. Upstream issue; safe to ignore.

**Banners and grabFramebuffer** — QLabel banners sit above the GL viewport in the Qt widget stack. They DO appear in the live GUI, but `grabFramebuffer()` captures only the GL surface and misses them. Smoke tests verify banner state programmatically (read `.isVisible()` and `.text()` in Python) rather than visually.

**pyqtgraph 0.14.0 colormap availability** — doesn't bundle 'gray' or 'hsv'. Workarounds: manual 2-stop black-to-white `ColorMap` for the fringe-frame panel; `CET-C1` (perceptually-uniform cyclic) for wrapped-phase panel. Documented in `stages_view.py`.

**pyqtgraph 0.14.0 `GLSurfacePlotItem.setData(colors=...)` docstring is wrong** — claims `(width, height, 4)`, actually needs flat `(N_vertices, 4)`. Workaround documented in `surface_preview.py`.

---

*End of context. Ask the user for clarification before starting work.*
