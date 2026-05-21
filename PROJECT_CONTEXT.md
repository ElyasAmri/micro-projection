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
│   ├── stl_loader.py              # Stage 4c — STL → heightmap loader (pure NumPy, peer of test_surfaces.py)
│   └── gui/                       # Stage 4a/4b — PyQt6 GUI package
│       ├── __init__.py
│       ├── __main__.py            # `python -m src.gui` entry
│       ├── app.py
│       ├── main_window.py
│       ├── surface_preview.py     # SurfacePreview + HardwareScene host + ErrorColorbar
│       ├── hardware_scene.py      # Stage 4b — HardwareScene class + compute_arm_transforms
│       ├── clip_detection.py      # Stage 4b — pure NumPy clip-detection (5 checks)
│       ├── stages_view.py         # 2×3 grid of pipeline-stage images
│       └── stl_browser.py         # Stage 4d — Browser tab (whole-STL + minimap + windowed slice + FOV overlay)
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
│   ├── test_stl_loader.py         # Stage 4c — 14 cases (synthetic in-memory meshes via tmp_path)
│   ├── test_stl_loader_full_scale.py # Stage 4d — full-scale loader (oversized STL → (heightmap, origin))
│   ├── test_main_window.py        # Stage 4d sub-task 1.5 — module-level invariants (no GUI construction)
│   ├── test_main_window_stl.py    # Stage 4c+4d — GUI-level tests (small-path + Browser flow + commit)
│   ├── regression_data.npz
│   └── conftest.py
├── scripts/                       # standalone runnable scripts
│   └── stage4c_smoke.py           # Stage 4c — GUI smoke harness (verify | Flat | Gaussian | STL). Verify mode updated in Stage 4d sub-task 2.5 to assert Gaussian amp cap == 120.0.
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
| **4c** | **STL import for arbitrary specimens: surface dropdown reduced to (Flat, Gaussian, STL file...); pure-NumPy STL→heightmap loader; QFileDialog flow; hard-reject for STLs exceeding the (68, 55, 55) mm working volume** | No | ✅ Done |
| **4d** | **STL Browser for full-scale specimens: windowed FOV selection on oversized parts via minimap + draggable cyan FOV rectangle; live windowed-slice preview; surface-following highlight overlay on whole-STL view; Commit FOV button promotes dragged slice to lab view + math pipeline; QTabWidget refactor for view modes (3D Scene / Pipeline Stages / STL Browser)** | No | ✅ Done |
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

- **The "View Mode" radio toggle lives on the left pane**, not as an overlay on the right. Keeps the right pane pure visualization, no UI chrome. ~~Locked design decision.~~ **Superseded by Stage 4d sub-task 1:** when the third tab (STL Browser) was added, the radio toggle's two-state ergonomics didn't scale to three states cleanly. Refactored to a `QTabWidget` at the top of the right pane. The original principle ("right pane stays pure visualization") still holds — the tab bar is a navigation chrome at the top of the pane, not an overlay on the GL viewport.

- **STL-import flow (delivered in Stage 4c, see "Stage 4c — Done" section below)** plugs into the existing `make_*` surface contract `(shape, pixel_size_mm) → (H, W) float64 heightmap in mm`. The Stage 4c loader `src/stl_loader.py` produces this contract; the GUI surface dropdown gained an "STL file..." entry; no math-layer changes required.

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
| `Z_EXAGGERATION = 1.0` honest scale | Hardware bodies provide visual scale reference; exaggeration would desync visual from clip math. Sub-mm specimens vanish — by design; error overlay handles fine variation. **Confirmed permanent doctrine in Stage 4d:** the lab view IS the real-scale view; exaggerating Z would lie about geometry the system is designed to measure honestly. Configurable Z exaggeration is NOT on the roadmap. |
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

- **Stage 4b sub-task 4 went through a reset.** Surface-vs-lens contact checks (commit c53dd36) were added then reverted (commit 20d6771) when interactive testing showed they're unreachable from slider ranges. The reset is preserved in history rather than rebased away, because the lesson — "validate that the bug can actually be triggered before adding the check" — is worth remembering. Stage 4c reused this discipline (see "Stage 4c sub-task 4 pivot — design record" below) when the originally-drafted Rescale/Truncate dialog for sub-task 4 got pivoted to a hard-reject + Stage 4d Browser plan.

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

### Stage 4c — Done (STL import for arbitrary specimens)

**Goal achieved.** The surface dropdown collapses to three honest options: Flat (calibration reference + zero-height smoke test), Gaussian (known-answer validator), and STL file... (real CAD specimens). Tilt, Step, and Sphere are deleted end-to-end. STL files load through a `QFileDialog`, get rasterized to the existing `(shape, pixel_size_mm) → (H, W) float64 mm` contract via projected-barycentric rasterization, and feed the unchanged math layer with zero pipeline changes.

**Stage 4c sub-task table:**

| # | Commit | What landed |
|---|---|---|
| 1 | `eecaeac` | Dropdown reduction (Flat, Gaussian) + Gaussian amplitude cap 100→55 mm. `make_tilt`, `make_step`, `make_sphere` generators, their tests, their slider widgets, page builders, and dispatch branches all deleted. Net −223 lines. Surviving slider inventory: Flat (none); Gaussian (amplitude 0–55 mm, sigma 1–30 mm). `tests/test_clip_detection.py:256` left at amplitude=100 (Gaussian-based coverage case; `make_gaussian` has no internal cap, math layer free). New `scripts/stage4c_smoke.py` smoke harness (verify \| Flat \| Gaussian). 122 tests. |
| 2 | `db0cd21` | `src/stl_loader.py` (pure NumPy peer of `test_surfaces.py`): `load_stl_heightmap(path, shape, pixel_size_mm)` and `get_stl_bbox_mm(path)`. Projected-barycentric rasterization, per-pixel max-z upper envelope (camera-visible top surface; closed-solid bottom discarded). Lift by **global** mesh-Z minimum (the part's true base, including discarded bottom shell — not envelope minimum), so a closed solid's diameter lands at the right peak height. Coordinate convention replicated from `test_surfaces._centered_grid_mm` (no cross-module private import). Empty mesh raises `ValueError`; non-empty-but-all-XY-degenerate (vertical-walls-only) returns all-zero heightmap legitimately. 14 new tests covering cube, pyramid, tilted triangle, closed UV sphere, vertical-walls-only, empty mesh, offset cube, bbox extents — all synthetic in-memory via `tmp_path`. `numpy-stl==3.2.0` added to `environment.yml` pip block (NOT conda-forge — see "Stage 4c environmental lessons" below). 136 tests. |
| 3 | `2c73955` | STL wired into the surface dropdown as `"STL file..."`. `_build_stl_page` with inner `QStackedWidget` (placeholder ↔ `STL: <basename> [Change...]` row, full path as tooltip). `_on_surface_combo_changed` slot inserted between page-swap and refresh in `currentIndexChanged` connection order. `_load_stl_from_path(path) → bool` is the no-dialog hook used by the `QFileDialog` flow, the Change button, the smoke script, and the tests. Cache lives for the window's lifetime; switching to Flat/Gaussian and back to STL re-renders the cache without re-importing. `_revert_stl_dropdown` carries a maintainer comment explaining why both the combo AND the surface_pages stacked widget need manual `setCurrentIndex` under `blockSignals`. Temporary `QMessageBox.warning` bbox guard (replaced in sub-task 4). 6 new GUI tests in `tests/test_main_window_stl.py` (monkeypatched `QFileDialog`/`QMessageBox`). Smoke harness extended with STL mode (synthetic 30 mm cube). 142 tests. |
| 4 | `286ebb3` | Finalize the bbox guard: hard-reject only. `QMessageBox.warning` text rewritten to explain why oversized STLs are rejected and point at Stage 4d's STL Browser. The earlier draft of sub-task 4 (custom `QDialog`, `rescale_mesh_uniform`, `truncate_heightmap_z`) was **dropped during planning** — rescale and truncate both distort the geometry being measured. Five stale "sub-task 4" forward-references in `src/stl_loader.py` comments cleaned up to point at where the bbox check actually landed (`main_window.py`'s `_load_stl_from_path`). Text-only commit; 142 tests unchanged. |
| 5 (close) | this commit | Docs update + tag `stage-4c-complete`. |

**Key design decisions locked during Stage 4c:**

| Decision | Rationale |
|---|---|
| Surface dropdown collapses to (Flat, Gaussian, STL file...) | Tilt/step/sphere were synthetic surfaces with no calibration role; Flat (zero-height ref) and Gaussian (known-answer) cover all the smoke-test use cases. STL covers real specimens. Three is the right number. |
| Gaussian amplitude cap 100 → 55 mm | Matches the 55 mm Z component of the working volume so the GUI can't drive the surface beyond what the camera FOV honestly supports. `make_gaussian` itself has no internal cap; the bound is GUI-only. |
| `numpy-stl` in the pip block, NOT conda-forge | Installing `numpy-stl` via conda-forge dragged in MKL/BLAS/LAPACK and a duplicate numpy build that broke `numpy.linalg` at the ABI level. Pip is clean because this env's numpy is pip-installed; matching the install mechanism avoids ABI conflicts. Documented in `environment.yml` comment. |
| Projected-barycentric rasterization (not z-buffer search) | Scales O(N_triangles × pixels-per-triangle), not O(N_pixels × N_triangles). CAD STLs have 10k+ triangles; the projected-barycentric path is the only one fast enough to feel interactive. |
| Per-pixel max-z upper envelope | Matches what a single-viewpoint FPP camera actually sees: the top surface, not the closed solid's interior or bottom. Documented in the loader docstring. |
| Lift by global mesh-Z min, not envelope-min | Caught during sub-task 2 summarize-back. Envelope-min would put a cube's top face at 0 (envelope-min = envelope-max = z_top inside footprint) and a sphere at peak = R, not 2R. Global mesh-min puts the part's base at z = 0, matching the physical setup (the part rests on a flat stage). |
| STL coordinates are assumed to be mm (no unit parameter) | mm is the de-facto CAD convention. Wrong-unit files trip the bbox guard immediately on normally-sized parts — failure mode is loud and self-diagnosing. |
| Empty mesh raises `ValueError`; XY-degenerate returns zeros | Empty = malformed input; degenerate vertical walls = legitimately invisible to a top-down camera. Two different cases, two different behaviors. |
| Coordinate convention replicated, not imported | `stl_loader.py` and `test_surfaces.py` are peers in the surface-library role. Cross-module private imports would couple them. The 4-line `_centered_grid_mm` formula is small enough to replicate with a "source of truth" comment. |
| Cache lifecycle: STL persists for window lifetime | Switching to Flat/Gaussian doesn't clear cache. Switching back re-renders without re-import. Change→Cancel keeps the cached STL active (typical UI convention). |
| `_load_stl_from_path` factored as the no-dialog hook | Single entry point used by the dialog flow, the Change button, the smoke script, and the tests. Tests inject a path; smoke script injects a path; dialog flow calls it after `QFileDialog` returns. |
| Hard-reject oversized STLs (no rescale, no truncate) | Rescale shrinks the part (lies about size); truncate clips data (lies about what's measurable). Both distort the geometry being measured. Stage 4d's STL Browser supports full-scale STLs via windowed FOV selection instead. |
| ASCII three-dot ellipsis in `"STL file..."` label | Cross-platform safer than Unicode `…`; no encoding surprises in test assertions / grep. |

**Architectural decisions worth carrying forward from Stage 4c:**

- **The STL loader is a peer of `test_surfaces.py` in the surface-library role.** Same `(shape, pixel_size_mm) → (H, W) float64 mm` contract; different generation method (file rasterization vs. analytic). The math layer doesn't know the difference. Future surface sources (e.g., a `make_random_terrain` for stress-testing) can join the surface library the same way.

- **`_load_stl_from_path(path) → bool` is the GUI-facing entry, not the QFileDialog flow.** This factoring made the smoke script trivial (just inject a path) and the GUI tests trivial (monkeypatch the dialog, call the method directly). When Stage 4d adds the Browser, it will call into the same `_load_stl_from_path`-style hooks rather than re-implementing the import path.

- **The cache in `main_window` (`_stl_heightmap`, `_stl_path`, `_stl_filename`) is the surface-state contract.** Stage 4d's Browser will extend this with FOV-window state (`_stl_full_heightmap`, `_stl_fov_origin`, etc.); the dispatch in `_compute_current_heightmap` reads from one shared place.

- **Halt-and-confirm gates earned their cost three times in Stage 4c.** Sub-task 2's halt caught the lift-formula contradiction (envelope-min vs global-min). Sub-task 3's halt confirmed connection-ordering risk with `blockSignals`. Sub-task 4's halt-and-pivot replaced a substantial dialog implementation with a 24-line message edit. None of these would have been caught by the test suite — they're all "prompt vs. actual code intent" mismatches that only surface in summarize-back.

- **The Stage 4c sub-task 4 pivot is the most substantial design decision in the stage.** The originally-drafted Rescale/Truncate/Cancel dialog was a real, defensible design path — it would have worked, with tests. The user pushed back during summarize-back: "we cant have a full sized object that fits in the small FOV, most artifacts will be a lot bigger." That observation reframed the problem from "salvage oversized parts" to "explore oversized parts FOV-by-FOV," which made rescale/truncate the wrong answer regardless of how cleanly implemented. Stage 4d's STL Browser is the right answer; sub-task 4 became a 2-file text edit. The lesson: when a sub-task feels right technically but the user pushes on practicality, the spec is what's wrong, not the user.

### Stage 4c environmental lessons (the conda-forge ABI hazard)

Installing **any** package via conda-forge in an env whose `numpy` is pip-installed risks pulling in a conflicting numpy / BLAS / LAPACK stack. Conda's solver doesn't read package source code — it reads the dependency graph, and any conda dep that pins numpy will install a second numpy alongside (or over) the pip one.

The Stage 4c incident: `conda install -n fringe -c conda-forge numpy-stl` (a pure-Python + numpy package, which "should be safe") dragged in MKL, libblas, liblapack, tbb, llvm-openmp, AND a duplicate numpy build. Result: `numpy.linalg.lstsq` raised a native `0xc06d007f` (proc-not-found) DLL error on every code path that touched it (calibration, tilt-plane fit, etc.). Recovery required:

1. `conda install -n fringe --revision 0` — exact-inverse rollback of the single bad transaction.
2. `pip install --ignore-installed --no-deps numpy==2.2.6` — restore the pip-managed numpy that the rollback gutted (the rollback removed conda-tracked files that the pip install shared, leaving an empty `numpy` directory with no `RECORD` or `__version__`).
3. Coordinated VS Code Jupyter kernel shutdown (the broken DLL was held loaded by a long-running kernel, blocking the pip reinstall with `Access denied`).
4. `pip install typing_extensions==4.15.0` — rollback collateral (pytest's `exceptiongroup` depends on it).
5. `pip install numpy-stl` — the actually-correct install path. Pure Python + numpy; no native footprint; doesn't touch LAPACK.

**The rule that came out of this** (documented inline in `environment.yml`): since this env's `numpy` is pip-installed, **every new dependency goes in the pip block regardless of how pure-Python it looks**. Conda-forge entries are only safe for packages with no numpy dependency at all, and even then the conda-forge convention from earlier stages should be revisited rather than trusted by default.

### Stage 4c sub-task 4 pivot — design record

The originally-drafted sub-task 4 was a custom `QDialog` offering three buttons: Rescale uniformly, Center+Truncate to FOV, Cancel. Pure-NumPy helpers `rescale_mesh_uniform` and `truncate_heightmap_z` would handle the geometry transforms. The dialog would compute and display previewed post-transform bounding boxes so the user could see what each option would produce.

This was a real, working design. It got through one round of strategy-chat halt-and-confirm (six numbered ambiguities resolved). It was ~10 minutes from being implemented.

The user pivoted during that confirm step:

> "im still trying to push it because i want to consider practicality of the simulation.... realistically we cant have a full sized object that fits in the small FOV. most artifacts will be alot bigger than the FOV."

The proposal that replaced it (after one round of refinement):

> "we have what i suggested which is showing a FOV portion of the top STL file..... and then having its top surface shown on top bird eye view at like lets say bottom right region of lab view. then it has a square on top of it which symbolizes the FOV grid. this grid can then be dragged across the surface which then updates to what is seen on the hardware components."

The shift: **rescale/truncate distort the geometry the simulation claims to measure; windowed FOV exploration preserves the part at native scale and matches real-world large-part metrology.** Stage 4c sub-task 4 became a 24-line text edit (hard-reject message + comment cleanup). The Browser becomes Stage 4d's headline (see "Stage 4d planning anchor" above).

**This record exists** because the dialog work was preserved-in-history-as-a-reset would have wasted a sub-task's worth of code. Catching it before implementation was a halt-gate win, and the design rationale is worth preserving so future stages don't re-derive "why didn't we just rescale" from scratch.

### Stage 4 controls (locked as of Stage 4b close)

**Sliders / dropdowns in the GUI:**

| Control | Type | Range / Options | Status |
|---|---|---|---|
| Surface type | dropdown | Flat, Gaussian, STL file... | ✅ Wired (3-entry as of Stage 4c). |
| Per-surface params | sliders | Flat (none); Gaussian (amplitude 0–120 mm, sigma 1–30 mm) | ✅ Wired. Amplitude cap was 100 → 55 in Stage 4c, then 55 → 120 in Stage 4d sub-task 2.5 (empirical: user's 100 mm specimen + 20 mm safety margin). |
| **θ_projector** | slider | **−75° to +75°** (extended in 4b) | ✅ Wired (Eq. 2-51 triangulation). |
| **θ_camera** | slider | **−75° to +75°** (extended in 4b) | ✅ Wired (Eq. 2-51 triangulation). |
| Projector throw distance (lens-front to surface) | slider | 50–200 mm | ✅ Wired (4b). Drives projector body translation + cone size. |
| Camera working distance (lens-front to surface) | slider | 132–182 mm | ✅ Wired (4b). Drives camera body translation. |
| PSI step count | spinbox | 3–8 | ✅ Wired. |
| View Mode | tabs | 3D Scene / Pipeline Stages / STL Browser | ✅ Wired. QTabWidget at top of right pane (refactored from radio toggle in Stage 4d sub-task 1). |
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
| GUI resolution | (550, 680) | Live updates. Math grid sized to camera FOV exactly: 68×55 mm at 0.1 mm/px (Stage 4d sub-task 1.5 — was (480, 640) in Stages 4a–4c). |

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

### Stage 4c — Completion notes & residuals

**STL import for arbitrary test objects.** ✅ Delivered. See Sec. 7f for the execution history (sub-tasks, commits, design decisions). The originally-listed planning items have been resolved as follows:

- `QFileDialog` for STL picker → delivered (sub-task 3).
- One-shot config dialog (viewing axis + Z-offset + scaling) → not implemented; superseded by the design decision in sub-task 4 to hard-reject oversized STLs rather than rescale/truncate them. Full-scale STL support moves to Stage 4d's STL Browser (see "Stage 4d planning anchor" below).
- Mesh rasterization → `src/stl_loader.py` with projected-barycentric rasterization + per-pixel max-z upper envelope (numpy-stl as the parser, our own rasterizer).
- Plugs into existing pipeline with zero math-layer changes. ✅ Confirmed: math layer untouched across all four sub-tasks.

**Sphere super-hemispherical cliff bug.** ✅ Obsolete. `make_sphere` was deleted in Stage 4c sub-task 1 along with `make_tilt` and `make_step`. The cliff bug can no longer trigger.

**Click-and-drag scene manipulation.** Still deferred. Originally queued as a lower-priority Stage 4c item; not touched. Remains a design problem (drag what — lens, body, cone, surface? drag does what — rotate, translate, free 6DOF? sync back to sliders how?), not a sub-task. Needs its own planning conversation before any implementation. Deferred to a future stage; same status as before Stage 4c.

### Stage 4d — Done (STL Browser for full-scale specimens)

**Goal achieved.** A user can import an STL that exceeds the (68, 55, ~~55~~) mm working volume (Z cap raised to 120 mm during Stage 4d, see sub-task 2.5 below) and explore it FOV-by-FOV. The math layer continues to measure one 68×55 mm patch at a time; the Browser is a UI for choosing which patch via a draggable cyan rectangle on a top-down minimap, with live windowed-slice preview and a surface-following highlight overlay on the whole-STL view. A Commit FOV button promotes the dragged slice to the lab view + Pipeline Stages + math pipeline.

**Why this design (and not rescale/truncate, the earlier draft of Stage 4c sub-task 4):** rescale shrinks the part to fit, lying about its true size; truncate clips data, lying about what was measurable. Both distort the geometry the simulation claims to measure. Windowed FOV selection preserves the part at native scale and is also how real-world large-part metrology works (commercial FPP systems do exactly this with translation stages).

**Stage 4d sub-task table:**

| # | Commit | What landed |
|---|---|---|
| 1 | `759c933` | **QTabWidget refactor.** Replaced View Mode radio + QStackedWidget with `QTabWidget` at top of right pane. Tabs: "3D Scene", "Pipeline Stages". `right_pane_stack → right_pane_tabs`. `currentChanged` wired to `_refresh_surface_preview` to preserve slider-drag-while-tab-hidden refresh. 142 tests. |
| 1.5 | `6e1c434` | **Math grid reconciled to camera FOV.** `SURFACE_SHAPE (480, 640) → (550, 680)` at `SURFACE_PIXEL_SIZE_MM = 0.1`, giving an exact 68×55 mm patch matching the advertised camera FOV. New `test_surface_grid_matches_camera_fov` invariant test (in `tests/test_main_window.py`, the new module-level invariants file). Recovered Gaussian min shifted 0.578 → 0.289 mm per Gaussian-floor prediction (boundary-zero-fixed grid is larger). 143 tests. |
| 2 | `fd5cb9f` | **Full-scale STL data model + bbox-reject three-way branch.** Added `load_stl_heightmap_full_scale(path, pixel_size_mm) → (heightmap, (x_min, y_min))` in `src/stl_loader.py`. MainWindow gains `_stl_full_heightmap`, `_stl_full_origin_mm`, `_stl_fov_origin_mm`, `_stl_is_browser_mode` cache state. `WORKING_VOLUME_MM = (68, 55, 55)` and `ABSURDLY_LARGE_MM = (272, 220, 55)` constants. Three-way branch in `_load_stl_from_path`: Z-overflow → hard-reject; XY within working volume → existing direct path; oversized XY but within ABSURDLY_LARGE → Browser path with centered FOV slice; XY > ABSURDLY_LARGE → reject. New `_extract_fov_slice` helper handles off-part windows with 0.0 fill. 154 tests. |
| 3 | `4d82d98` | **Browser tab skeleton.** New `src/gui/stl_browser.py` with `STLBrowser(QWidget)`. QStackedWidget pattern: placeholder page (no Browser-mode STL) vs three-panel layout (horizontal QSplitter `[400, 600]` of `(vertical QSplitter [440, 360] minimap-on-top / whole-STL-on-bottom) / windowed-on-right`). Always-enabled-with-placeholder visibility model. `_refresh_browser_panel` trigger sites locked to the 3 mutation points of `_stl_is_browser_mode`. 160 tests. |
| 2.5 | `bce7a7c` | **STL Z cap + Gaussian amplitude cap raised 55 → 120 mm.** `WORKING_VOLUME_MM[2]` and `ABSURDLY_LARGE_MM[2]` both rise to 120; Gaussian amplitude slider cap likewise. Empirical: user's hardware did not contact the 100 mm specimen during bench testing; +20 mm safety margin gives 120. New `test_z_cap_matches_absurd_z` invariant locks `WORKING_VOLUME_MM[2] == ABSURDLY_LARGE_MM[2]` (Browser doesn't help with Z). Lands AFTER sub-task 3 (half-step name records planning order, not execution order). Bug-bait classification critical: "55" appeared in three semantic buckets — Z-cap/Gaussian cap (a, change to 120), camera FOV Y extent (b, stays at 55), and hardware-body dimensions like Pico Genie cube + camera lens radius (c, stays). Diagnostic chain documented in commit body. Smoke script + stl_loader docstrings updated in same commit. 161 tests. |
| 4 | `366fac8` | **Browser Panels 1 + 3 read-only 3D rendering.** Replaced QFrame placeholders with `GLViewWidget` + lazy-constructed `GLSurfacePlotItem`. Two methods: `update_whole_stl(heightmap, ps)` (Panel 1) and `update_windowed_slice(heightmap, ps)` (Panel 3) — separated so sub-task 5's drag handler can re-render Panel 3 without re-meshing Panel 1. Camera defaults: Panel 1 isometric `(distance=1.5×max_bbox, elevation=30°, azimuth=45°)`; Panel 3 `(distance=200, elevation=20°, azimuth=45°)` — distance decoupled from `SurfacePreview`'s 600 (mid-sub-task correction after screenshot review showed 600 left the windowed surface as a tiny diamond; surface-only scene needs closer pose). `z=heightmap.T` transpose required by pyqtgraph. `shader="shaded"`, `smooth=False`, `drawEdges=False`. 166 tests. |
| 5 | `ce3667a` | **Panel 2 minimap + draggable FOV rectangle + live Panel 3 update.** `pg.GraphicsLayoutWidget` + `PlotItem` + `ImageItem` (grayscale, row-major, Y-up, aspect-locked) + `pg.RectROI` with bright cyan `(0, 220, 255)` 2 px outline, fixed FOV size 68×55 mm, `movable=True, resizable=False, rotatable=False`, all handles scrubbed in a loop for pg version safety. `fov_dragged = pyqtSignal(tuple)` emits on `sigRegionChanged`. MainWindow's `_on_fov_dragged` slot updates the cache, calls `_extract_fov_slice`, calls `update_windowed_slice`. Lab view and Pipeline Stages NOT touched on drag (drag-vs-commit separation). Mid-execution correction: initial view padding bumped from half-FOV to full-FOV when C3 capture showed rectangle clipped at extreme off-part drag (`+40, -27.5`). 172 tests. |
| 5.5 | `8fafa94` | **Panel 1 FOV highlight overlay (surface-following, live, alpha=1.0 cyan).** Second `GLSurfacePlotItem` at the FOV-windowed region in Panel 1's GLView, positioned at Z = part-surface + 0.05 mm epsilon, rendered in opaque cyan matching the minimap rectangle. Updates live on `_on_fov_dragged`. **Pyqtgraph 0.14.0 alpha-rendering bug discovered:** `alpha < 1.0` on `GLSurfacePlotItem` produces inverted-complement colors (empirical: `output_X ≈ 127 - 44·input_X`) regardless of shader, color-input path, sibling-item presence, or `glOptions`. Six diagnostic experiments ran (single-item, white-on-white, pure-RGB inputs, shader=None, alpha=1.0) before isolating alpha as the trigger. Workaround locked at alpha=1.0; root cause undiagnosed (would require Qt/driver source dive). Diagnostic chain captured as a 17-line comment above `_FOV_HIGHLIGHT_COLOR_RGBA`. 176 tests. |
| 6 | `27385b9` | **Commit FOV button + lab view promotion path.** `QPushButton("Commit FOV")` lives below the minimap in Panel 2 (wrapped with the minimap in a `QVBoxLayout(panel2_wrapper)` so the inner splitter stays two-region). `commit_fov_requested = pyqtSignal()` (no payload — cache already current from drag handler). MainWindow's `_on_commit_fov_requested` slot calls `_refresh_surface_preview` to propagate `_stl_heightmap` to the lab view + Pipeline Stages + math pipeline. Button enabled on `show_panels`, disabled on `show_placeholder`, belt-and-suspenders `setEnabled(False)` in `__init__`. Lab view auto-shows the centered initial FOV at load via the implicit refresh chain through `_open_stl_dialog` (line 958 calls `_refresh_surface_preview` after `_load_stl_browser` returns) — no explicit auto-commit needed; the implicit chain is the load-bearing contract, documented in `_load_stl_browser`'s docstring. Z-overflow at commit is impossible by construction (load-time bbox classification already rejects Z > 120, and `_extract_fov_slice` is monotonic in Z). Degenerate-geometry short-circuit is handled by `_refresh_surface_preview` itself. 181 tests. |
| close (this commit) | docs update + tag `stage-4d-complete`. |

**Key design decisions locked during Stage 4d:**

| Decision | Rationale |
|---|---|
| Math grid reconciled to exact 68×55 mm patch ((550, 680) at 0.1 mm/px) | Sub-task 1.5. Stage 4a chose (480, 640) at 0.1 mm/px = 48×64 mm grid, which never honestly matched the advertised 68×55 mm camera FOV. Stage 4d's Browser couldn't proceed with that mismatch — the FOV rectangle on the minimap is the user's mental model of what the camera sees, and it has to match the math grid bit-for-bit. |
| Three-way bbox classification: direct / Browser / hard-reject | Sub-task 2. Two thresholds (`WORKING_VOLUME_MM`, `ABSURDLY_LARGE_MM`) give three buckets. The direct path stays for parts that fit; the Browser path activates for oversized-but-bounded XY; absurd-sized XY (>272×220 mm) hard-rejects with the same memory-bound + usability ceiling reasoning as Stage 4c's hard-reject. |
| Z cap raised 55 → 120 mm (placeholder backed by empirical observation) | Sub-task 2.5. Stage 4c chose 55 mm to match the camera FOV Y extent — a coincidence-equal value, not a derived hardware constraint. User's bench testing showed 100 mm parts cleared the hardware without contact. 120 mm = 100 mm specimen + 20 mm safety margin. Real Z constraint (projector focus depth, phase unambiguity range, triangulation lateral-spill) is a Stage 5/6 derivation. |
| `Z_EXAGGERATION` permanently locked at 1.0 (honest scale) — **DOCTRINE** | Stage 4b locked Z=1.0 at honest scale; Stage 4d makes this permanent. The lab view's job is to show the part as the system sees it — at true scale, in proper proportion to camera/projector/stage. Exaggerating Z would lie about the geometry the rest of the simulation is designed to measure honestly. A 50 µm bump shouldn't look like a 5 mm bump because the visualization would then communicate different information than the math is computing. **Configurable Z exaggeration is NOT on the roadmap; do not add it.** |
| Lab view shows only the committed FOV slice (3D mesh with depth) | Sub-task 6. The slice is itself a heightmap, so the lab view renders it as a 3D mesh with full Z relief — user can orbit around to read the depth profile. Whole-part-with-FOV-cone visualization is deferred to Stage 5/6 (depends on real hardware-mounting geometry to set the relative scale of part vs apparatus). |
| Drag updates Panel 3 + Panel 1 highlight only; lab view + Pipeline Stages wait for commit | Sub-tasks 5 + 5.5 + 6. Re-running the math pipeline at 60 Hz drag rate would be unacceptably laggy. Two NumPy slices + two GPU uploads per drag tick is the cheap path; pipeline + tab-render is the expensive path. The Commit FOV button is the latency boundary. |
| Browser tab placeholder always visible; panels shown only when Browser-mode STL active | Sub-task 3. The QTabWidget always shows "STL Browser" as a tab — clicking it shows either the placeholder ("Load an oversized STL to use the Browser") or the three-panel layout. Tab-disable was rejected as worse UX (the user can't see what the tab does until they try). |
| FOV highlight color matches minimap rectangle cyan exactly | Sub-task 5.5. Visual continuity — "the same region" across two panels reinforces the FOV selection metaphor. Bright cyan `(0, 220, 255)` is high-contrast against grayscale minimap content and unused elsewhere in the GUI color vocabulary. |
| FOV highlight opaque (alpha=1.0), not translucent | Sub-task 5.5. Pyqtgraph 0.14.0 alpha-rendering bug forces alpha=1.0 — translucency was a nice-to-have, not load-bearing. Panel 3 (windowed preview) shows the FOV contents directly anyway; the highlight's job is "show WHICH region" not "show through to underlying contour." |
| Implicit refresh chain via `_open_stl_dialog`, not explicit auto-commit in `_load_stl_browser` | Sub-task 6. `_open_stl_dialog` already calls `_refresh_surface_preview` after `_load_stl_browser` returns. Adding an explicit auto-commit would be a redundant 2nd/3rd refresh per load — a real perf cost (272×220 mm parts can be 10s of MB heightmaps × pipeline run) for hypothetical future-caller decoupling we don't have a concrete use case for. The implicit chain is the load-bearing contract, documented in `_load_stl_browser`'s docstring. Future direct callers would invoke `_refresh_surface_preview` themselves. |
| Two-method update API for Browser content (`update_whole_stl` + `update_windowed_slice` separate, not unified) | Sub-task 4. Sub-task 5's drag handler calls `update_windowed_slice` on every mouse-move tick; redoing Panel 1's whole-STL mesh on every drag would be wasted GPU work. Separation is the perf path. |
| Panel 1 distance scales to part bbox; Panel 3 distance fixed at 200 mm | Sub-task 4. Panel 1's content size varies with the part (100×80 → 272×220 mm); a fixed distance would over-zoom small parts or under-zoom large ones. `1.5 × max(W, H)` keeps the part filling ~30% of frame width across the range. Panel 3 always shows a fixed 68×55 mm slice, so fixed distance is fine. |
| Minimap initial view padded by full-FOV on each side | Sub-task 5. Half-FOV padding (the original spec) clipped the rectangle at extreme off-part drag positions, surfaced by the C3 capture. Full-FOV padding keeps the rectangle visible across all drag positions including worst-case dragged-fully-off-part. Cosmetic cost: part appears ~30% of minimap width instead of ~60%. The silent-failure mode of "I dragged my rectangle and now I can't see it" loses to the cosmetic-failure mode of "part looks smaller." |
| FOV rectangle: 2 px cyan outline, no fill | Sub-task 5. Outline-only keeps the part's grayscale content visible inside the rectangle, which is the region the user is about to measure. Adding fill would compete with the part content the user wants to see. |

**Architectural decisions worth carrying forward from Stage 4d:**

- **`Z_EXAGGERATION = 1.0` is a permanent design tenet, not a "for now" value.** The lab view IS the real-scale view of the measurement geometry. Exaggerating Z would desync the visual from the math. If a part's features look subtle at honest scale, that's information about the part, not a deficiency in the visualization.

- **The lab view shows only the committed FOV slice, not the whole part.** Whole-part context lives in the Browser's Panel 1 (whole-STL 3D preview, rotatable from any angle). The "whole part on stage with FOV cone highlighting the measured region" visualization is deferred to Stage 5/6 when real hardware-mounting geometry determines the relative scale of part vs apparatus.

- **Drag-vs-commit separation is the core interaction discipline.** Drag updates the cheap previews (Panel 3 windowed slice, Panel 1 surface-following highlight). Commit promotes to the expensive paths (lab view, Pipeline Stages, math pipeline). The Commit FOV button is the latency boundary between exploration and measurement.

- **The math layer never knew Browser mode existed.** Sub-tasks 1.5 through 6 added zero lines to `src/pipeline.py`, `src/geometry.py`, `src/synthetic_fringes.py`, `src/calibration.py`, `src/reconstruction.py`. The math layer continues to receive one 68×55 mm heightmap and produces one 68×55 mm recovered surface. The Browser is a UI for choosing which 68×55 mm patch the math sees, nothing more.

- **MainWindow's cache is the surface-state contract.** `_stl_heightmap` (the currently active slice — what the math reads), `_stl_full_heightmap` (the entire rasterized part, Browser mode only), `_stl_fov_origin_mm` (current FOV position in part-local coordinates), `_stl_is_browser_mode` flag. `_extract_fov_slice(origin_xy_mm)` is the shared arithmetic used by both `_on_fov_dragged` (drag refresh) and the highlight-overlay path.

- **Module-level invariants live in their own test file (`tests/test_main_window.py`).** Established by sub-task 1.5 for `test_surface_grid_matches_camera_fov` (parses `HARDWARE_INFO_ROWS` to verify the grid matches the advertised FOV at byte-level). Sub-task 2.5 added `test_z_cap_matches_absurd_z`. The pattern: lightweight invariants that don't need a MainWindow QApplication go in this file; full GUI-level integration tests go in `test_main_window_stl.py`.

- **Half-step sub-task naming records planning order, not execution order.** Sub-task 1.5 landed between 1 and 2 (in execution order); sub-task 2.5 was planned between 2 and 3 but landed after 3 (execution order: 1 → 1.5 → 2 → 3 → 2.5 → 4 → 5 → 5.5 → 6). The half-step name preserves the rationale ("this is the small one-constant addition to that sub-task's logical neighborhood") even when execution order shifts. The chronological vs logical mismatch is documented in the commit body when it happens.

- **Browser internal state attributes use the `_*_item is not None` pattern for lifecycle.** `_whole_stl_item`, `_windowed_item`, `_minimap_image_item`, `_minimap_roi`, `_whole_stl_highlight_item` all start at `None` and get lazy-constructed on first `update_*` call. The `has_*` properties read `is not None`. `clear_panel1_highlight()` is the only path that resets one back to `None` (real `removeItem` + reassignment, not just `setVisible(False)`). Sub-tasks 4, 5, 5.5 use this pattern consistently.

- **Pyqtgraph 0.14.0 has a destructor-noise quirk on shutdown** (harmless `RuntimeError` from `ViewBox.forgetView` lambda when `sid`/`name` go out of scope). Smoke harness output greps `^Traceback|^  File|^RuntimeError|^    ` to filter these out. Documented in PROJECT_CONTEXT §14.

- **Pyqtgraph 0.14.0 GL state hazard: sibling `GLSurfacePlotItem`s with different `a_color` paths in the same view are unsafe.** SurfacePreview (one item per view) works fine. Browser Panel 1 (two items: whole-STL using constant-attribute path + highlight using buffer-backed path) initially produced GL state leakage. Workaround: both items now use the constant-attribute path via `setColor()` at construction. Documented in `stl_browser.py`'s `update_panel1_highlight` docstring. (This was an intermediate diagnostic finding; the actual rendering bug turned out to be alpha-rendering, but the GL-path hazard is still real and worth recording.)

### Stage 4d FOV semantics + coordinate reconciliation reference

This subsection documents the coordinate-frame math the Browser uses. Self-contained so a fresh chat can reconstruct it.

**Three coordinate frames are in play:**

1. **Part-local frame (CAD coordinates).** The STL file's own coordinate system. `_stl_full_origin_mm = (x_min, y_min)` is the part's bbox bottom-left corner in this frame. `_stl_fov_origin_mm = (x_origin, y_origin)` is the FOV slice's bottom-left corner in this frame — what the user effectively "dragged to."

2. **Minimap plot frame.** Same as part-local. The minimap's `ImageItem.setRect(x_min, y_min, W_full*ps, H_full*ps)` positions the image so axes display real mm in part-local coords. The `pg.RectROI.pos()` returns its bottom-left in this same frame, with Y growing up (`axisOrder="row-major"`, plot Y not inverted). Row 0 of the heightmap array ⇒ Y = `y_min` ⇒ bottom of minimap.

3. **Panel 1 GLView frame (part-bbox-centered).** Panel 1's whole-STL `GLSurfacePlotItem` is constructed with x/y arrays centered at origin: `x = (arange(W) - (W-1)/2) * ps`. The mesh's center is at GLView's (0, 0). The highlight overlay must use the same centering convention so it aligns with the whole-STL surface. **The reconciliation formula** (in `update_panel1_highlight`):

```python
part_center_x = x_full_min + W_full * pixel_size_mm / 2
part_center_y = y_full_min + H_full * pixel_size_mm / 2

x_highlight = (fov_origin_x - part_center_x) + arange(W_fov) * pixel_size_mm
y_highlight = (fov_origin_y - part_center_y) + arange(H_fov) * pixel_size_mm
```

The `(fov_origin - part_center)` subtraction undoes the part's arbitrary CAD-offset so Panel 1's whole-STL and the highlight share the same GLView origin regardless of where the STL sat in its source coordinates.

**`_extract_fov_slice(origin_xy_mm)` arithmetic (in MainWindow):**

```python
col = int(round((fov_origin_x - x_full_min) / pixel_size_mm))
row = int(round((fov_origin_y - y_full_min) / pixel_size_mm))
# Slice _stl_full_heightmap[row:row+H_fov, col:col+W_fov] with off-part 0.0 fill.
```

Row 0 corresponds to Y = `y_full_min` (bottom of part in plot frame), consistent with the minimap's Y-up convention.

**FOV size in pixels:** `SURFACE_SHAPE = (H_fov, W_fov) = (550, 680)` at `SURFACE_PIXEL_SIZE_MM = 0.1` ⇒ 55×68 mm patch matching the camera FOV exactly (sub-task 1.5 invariant).

### Stage 4d diagnostic-pattern lessons (for stage close)

Recording these because they came up repeatedly and the pattern matters more than the specific bugs.

**Diagnostic-prompt-before-decision.** When strategy chat catches itself about to recommend a decision built on guesses about library internals, code-not-yet-read, or environment-specific quirks, the right move is to pause and write a **read-only diagnostic prompt** for Claude Code to investigate first. Evidence drives the next recommendation. The pattern surfaced repeatedly in sub-task 5.5's cyan-vs-maroon investigation — the original recommendation (try per-vertex layout) was strategy-chat guessing at pyqtgraph 0.14.0's color-binding API. Replacing it with "investigate first, then decide" caught two wrong recommendation cycles before they landed in code.

**Two failure modes to watch for:**

1. Confident-sounding recommendations built on guesses about library behavior or unread code. These sound identical to recommendations built on evidence. When strategy chat notices "I'm not sure what pyqtgraph 0.14.0 actually does here, but I think..." — that's the signal to write a diagnostic prompt instead of finishing the sentence.

2. Treating "make the symptom go away" workarounds as equivalent to fixing the underlying bug without diagnosing it. In sub-task 5.5, the first two "fixes" (per-vertex layout swap, then setColor switch) both failed because the actual bug was alpha-rendering, not what strategy chat hypothesized. Each fix attempt without diagnosis cost a cycle. The pattern is **"fix attempt → diagnose if it doesn't work" not "fix attempt → different fix attempt."**

**Prompt-assumption catches.** Three times during Stage 4d, halt-gate summarize-back caught strategy-chat prompt assumptions that were factually wrong about the codebase:

1. Sub-task 2.5: prompt said "55 doesn't appear in `src/stl_loader.py`" — it actually appears at lines 23 and 185 in docstrings. Honoring the prompt's "Do NOT touch stl_loader.py" rule would have left stale documentation.
2. Sub-task 2.5: prompt omitted `scripts/stage4c_smoke.py` from the in-scope-to-edit list — but the script has a hard-coded `amp_max == 55.0` assertion that the bump would break.
3. Sub-task 6: prompt said "the lab view doesn't show the FOV at load time" — it actually does, via the implicit refresh chain through `_open_stl_dialog`. Strategy chat's proposed explicit auto-commit would have been a redundant 2nd/3rd refresh.

The pattern: when strategy chat writes "X doesn't appear in module Y" or "Currently the system doesn't do Z," that's a claim about state the strategy chat doesn't have direct access to. Halt-gate summarize-back's grep-level read catches the discrepancy before code lands. The fix is to grep first, claim second.

### Deferred from Stage 4 (still deferred)

- **MockCamera, MockProjector, Camera/Projector protocols** → Stage 5/6.
- **Taylor/exact model toggle in GUI** → adds two lines later; not v1.
- **Resolution toggle (480×640 vs 1280×1024)** → adds a "Compute at full res" button later. Note: math grid is now (550, 680) post-Stage-4d-sub-task-1.5.
- **Three.js embed for lab view** → explicitly rejected; lab view is native PyQt6 (now part of unified scene).
- **Object position offset** → locked at center.
- **`equivalent_wavelength()` → `height_per_radian()` rename** → cosmetic; documented in code instead.
- **Unit reconciliation between info panel mm-values and math-layer pixel-values** → Stage 5/6 when real hardware arrives.
- **Click-and-drag scene manipulation (rotate/translate hardware bodies + surface via mouse, sync back to sliders)** → still deferred. The FOV-rectangle drag in Stage 4d's Browser was a concrete instance of mouse-event handling, but it's specialized to a 2D ImageItem + RectROI in a `pg.PlotItem`, not the 3D scene manipulation problem. No shared abstraction was extracted; YAGNI until a second concrete use case appears.
- **Multi-FOV stitching / batch capture** → not in any planned stage yet. Would let the user queue several FOV positions and process them in sequence, producing a stitched result. Out of scope for the simulation; possibly relevant when real hardware lands with motorized stages.
- **Persistence (save/load FOV positions, save committed slices, export results)** → not in any planned stage yet. The simulation is currently stateless across runs.
- **Performance work for absurd-limit (272×220 mm) parts** → flagged as a known issue; rasterization on load can be 5–15 seconds for ~50k-triangle parts. A loading indicator is the obvious palliative; full perf work depends on real use patterns.
- **Robust STL ingestion (degenerate triangles, non-manifold meshes, very large files)** → handled to a basic standard (empty mesh raises `ValueError`, XY-degenerate returns zeros). Hardening against pathological inputs is deferred.

### When real hardware arrives (Stage 6 prep)

- Update `HybridGeometry` defaults to real measured values (`a`, `p`, θ_projector_actual, θ_camera_actual, distances) — in physically-consistent units after deciding the unit story.
- Reconcile the math-layer pixel-space constants with the info-panel mm-space display.
- Empirically calibrate `λ_eq` against a step gauge; override formula-derived value if needed.
- `test_project_is_lambda_eq_independent` must still pass after the update — `HybridGeometry` and `SymmetricGeometry` defaults must change in lockstep.
- Scene primitives in `src/scene.py` (Stage 4b) update to reflect real lab layout. Projector lens dimensions (~20mm dia × 5mm protrusion) refined from lab measurement.
- **Re-derive the STL Z cap from hardware** — the 120 mm value is a placeholder backed by bench observation + safety margin. Real value depends on projector focus depth, phase unambiguity range, and triangulation lateral-spill, none of which map to a clean single number until measured against real hardware. `WORKING_VOLUME_MM[2]` and `ABSURDLY_LARGE_MM[2]` must update in lockstep (locked by `test_z_cap_matches_absurd_z`).
- **Whole-part-with-FOV-cone visualization in the lab view** becomes viable. Currently the lab view shows only the committed FOV slice because hardware-mounting geometry isn't finalized — the relative scale of part vs apparatus depends on real mounting. Once real mounting is in, the lab view can show the whole part on the stage with the camera/projector cones highlighting the active FOV region, and the Browser's role narrows to FOV-selection-on-minimap (Panel 1's whole-STL view may then be redundant). Significant lab view refactor; planned as a Stage 5/6 sub-task.

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

**pyqtgraph 0.14.0 destructor noise** — harmless `RuntimeError` on shutdown from pyqtgraph's GraphicsView teardown. Upstream issue; safe to ignore.

**Banners and grabFramebuffer** — QLabel banners sit above the GL viewport in the Qt widget stack. They DO appear in the live GUI, but `grabFramebuffer()` captures only the GL surface and misses them. Smoke tests verify banner state programmatically (read `.isVisible()` and `.text()` in Python) rather than visually.

**pyqtgraph 0.14.0 colormap availability** — doesn't bundle 'gray' or 'hsv'. Workarounds: manual 2-stop black-to-white `ColorMap` for the fringe-frame panel; `CET-C1` (perceptually-uniform cyclic) for wrapped-phase panel. Documented in `stages_view.py`.

**pyqtgraph 0.14.0 `GLSurfacePlotItem.setData(colors=...)` docstring is wrong** — claims `(width, height, 4)`, actually needs flat `(N_vertices, 4)`. Workaround documented in `surface_preview.py`.

**pyqtgraph 0.14.0 `GLSurfacePlotItem` alpha-rendering bug (Stage 4d sub-task 5.5)** — `alpha < 1.0` on a `GLSurfacePlotItem` produces inverted-complement colors in the rendered output, regardless of shader (`shaded`, `None`, or any other), regardless of color-input path (per-vertex `colors=` or uniform `setColor()`), regardless of sibling-item presence, regardless of `glOptions`. Empirical formula: `output_X ≈ 127 - 44 · input_X` for `alpha=0.5`. Six diagnostic experiments ran during sub-task 5.5 (single-item, white-on-white, pure-RGB inputs, shader=None, alpha=1.0) before isolating alpha as the trigger. Root cause undiagnosed analytically — would require Qt OpenGL driver source-level inspection. **Workaround: use `alpha=1.0` (opaque)** anywhere `GLSurfacePlotItem` color matters. Full diagnostic chain captured in the comment above `_FOV_HIGHLIGHT_COLOR_RGBA` in `stl_browser.py`.

**pyqtgraph 0.14.0 sibling `GLSurfacePlotItem` GL state hazard (Stage 4d sub-task 5.5)** — two `GLSurfacePlotItem`s in the same `GLViewWidget` using different `a_color` GL paths (one with constant-attribute `glVertexAttrib4f`, the other with buffer-backed `glVertexAttribPointer`) introduces unreliable GL state transitions. Discovered as a candidate hypothesis during the maroon-vs-cyan investigation (eventually superseded by the alpha-rendering finding above — but the hazard is real even after the alpha workaround). `SurfacePreview` works because it has one `GLSurfacePlotItem` per view. Browser Panel 1 has two, and both must now use the constant-attribute path via `setColor()` at construction. Documented in `stl_browser.py`'s `update_panel1_highlight` docstring.

---

*End of context. Ask the user for clarification before starting work.*
