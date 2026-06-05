# Fringe Projection Project — Conversation Summary

> **Companion to PROJECT_CONTEXT.md.** Captures the full history of decisions, hardware identification, theoretical reasoning, and open items from the planning conversation. Read this if you need *why* something was decided, not just *what*.

---

## 1. The User's Goal

A student/researcher building a **fringe projection 3D measurement system** in a lab. Project supervised by a professor (whose own thesis chapter is the reference material). Deliverables:

1. Python UI for experiment control end-to-end
2. Math/processing pipeline behind the UI
3. Eventually: hardware integration

The user wants to deeply understand the theory and how it maps to hardware **before** writing production code. The conversation has been heavily theoretical for that reason.

---

## 2. Reference Material

| File | Purpose |
|---|---|
| `reference/CHAPTER2_Moire_and_Fringe_Projection.pdf` | Theory: moiré effect, fringe projection geometry, perspective bias, telecentric correction, inverse grating method (§2.3.4.3) |
| `reference/Chapter4_Experimental_procedures.pdf` | Practical: how the original thesis built and calibrated their hardware |
| `reference/` (other thesis chapters as added) | Other chapters from Ayman Samara's thesis (Chapters 1, 3, 5, 6); kept for completeness, not active references |
| `notebooks/Fringe_Projection_Python.ipynb` | User's working synthetic pipeline (Stage 1 complete) |
| `docs/Projector_Geometry_Summary.docx` | Document handed off to a Three.js collaborator who is building a 3D simulation of the lab setup |
| `docs/Fringe_Projection_Roadmap.pdf` | Implementation roadmap (Stages 0–6) |
| `PROJECT_CONTEXT.md` | Concise project context |
| `CONVERSATION_SUMMARY.md` | This file |

The thesis chapter author is **Ayman Samara**. Equations: "Eq. 2-X" → Chapter 2; "Eq. 4-X" → Chapter 4.

The chapters in the reference folder are **the math basis for the inverse fringe projection method, not a template for a thesis the user is writing.** The user's own paper comes later, if at all.

---

## 3. Hardware Identification (Confirmed via Photos)

### Camera: FLIR Blackfly S BFS-U3-13Y3M-C
- Identified from sticker on the camera body (SN: 26048170)
- Monochrome USB3 machine vision camera
- 1280 × 1024 pixels, 4.8 µm pitch, up to 170 fps, global shutter
- 1/2" sensor (active area 6.14 × 4.92 mm)
- Body: 29 × 29 × 30 mm (relevant for Stage 4b's hardware-bodies-in-scene rendering)
- C-mount
- Sold by Edmund Optics as stock #36-451
- Python bindings: PySpin (part of Spinnaker SDK from Teledyne FLIR)

### Lens: Edmund Optics #58-259 (TECHSPEC GoldTL Telecentric)
- Identified from "0.09×" and "58259" markings on the lens body
- 0.09× magnification (modern convention)
- 132–182 mm working distance (focusable)
- < 0.2° telecentricity
- 1/2" sensor format
- **Physical lens profile (measured during Stage 4b):** stepped 3-section, 200mm total. 76mm rear at 55mm dia + 59mm taper + 65mm front at 110mm dia.
- **Confirmed telecentric**. NOTE (Stage 4 clarification): telecentric only locks the lens magnification; the camera body's physical tilt angle is independent. "Telecentric ≠ mounted vertical." Camera arm tilt is a separate parameter (θ_camera in Eq. 2-51).

### Projector: Pico Genie Impact 2.0 Plus Elite (placeholder)
- Identified from "Pico Genie Impact 2 Plus Elite" label on bottom of unit
- DLP projector
- 854 × 480 native, 1.2:1 throw, 16:9 aspect
- 55 × 55 × 55 mm cube
- HDMI input
- Confirmed **NOT** telecentric (consumer DLP)
- Will be replaced with a more advanced projector (telecentric status unknown)
- **Lens dimensions (estimated, refine later):** ~20mm dia × 5mm protrusion.

### Geometry measurements taken
- Throw 30 cm → image 25 × 14 cm (matches spec)
- Lens center in body frame: (21, ~1, 45) mm (equivalent to (X=−6.5, Z=17.5) in body-centered frame used in Stage 4b)
- Vertical optical offset: 0° (well-confirmed)
- Horizontal optical offset: ~12° (tentative — possibly setup misalignment)
- Auto-keystone: confirmed OFF

### Pending hardware
- Upgraded projector
- Mounting hardware (kinematic stages, rigid mounts)
- Optical breadboard
- Calibration artifacts (flat reference, step gauge, lateral grid scale)

---

## 4. Software Inventory (User's Setup)

### Already installed
- Python 3.10 + 3.14 (use 3.10 for this project; 3.14 for other things)
- NumPy, OpenCV
- Fiji/ImageJ (quick fringe inspection)
- VS Code with extensions
- Gemini Code Assist (recommend disabling for this project to avoid conflict)
- Claude Code (in VS Code) — Claude Opus 4.7, 1M context as of Stage 4 start
- MATLAB + Image Processing Toolbox + Simulink (for cross-validation)
- Chocolatey, Node.js, Git
- MeshLab + CloudCompare (for 3D mesh viewing later)
- GitHub CLI (authenticated)
- Miniconda
- **PyQt6 + PyQtGraph + PyOpenGL** (installed during Stage 4a task 2; pip channel in environment.yml because PyPI's PyQt6 conflicts ABI-wise with conda-forge's pyqt6)

### Pending (add to IT list when needed)
- **Spinnaker SDK + PySpin** — needed for FLIR camera; needs admin install

---

## 5. The System Configuration Decision

### How we got there
Initially user asked whether the system was telecentric or not. Through several rounds of clarification:

1. Camera arm lens telecentric: ✅ confirmed (Edmund Optics lens, hardware-locked)
2. Projector arm lens: ❌ Pico Genie is not telecentric
3. Future projector: ❓ unknown until hardware arrives
4. Therefore: **HYBRID in lens type** is the only honest description
5. Build code for hybrid; it gracefully degrades to symmetric-telecentric if upgraded projector turns out to be telecentric

**Stage 4 clarification (important):** "Hybrid" refers to *lens type only* (telecentric vs non-telecentric on each arm). The arm *angles* (θ_projector, θ_camera) are independent of lens type — both can be tilted at any angle, both arm tilts contribute to triangulation per Eq. 2-51. Stage 2's framing implicitly conflated these.

### Why this matters
- Chapter 2 §2.3.4 derives all math under the **symmetric** non-telecentric assumption (both arms identical: same M, same θ, same a, same b)
- Eq. 2-54 (inverse grating period) was derived under that assumption
- For your hybrid system, Eq. 2-54's exact form isn't quite right — but the **method** still works
- The chapter's Eq. 2-54 isn't used directly anyway. **In practice, the inverse pattern is computed from empirical flat-reference calibration**, not from theoretical formulas. This is what Chapter 4 does.
- **The two-angle form (Eq. 2-51) handles arbitrary arm angles for λ_eq**, which is what the GUI needs.

---

## 6. The Calibration-Based Approach (Chapter 4)

The single most important insight from Chapter 4:

> *"It is difficult to measure the system parameters accurately. Instead, the system is calibrated using a standard VLSI step height."* — Chapter 4 §4.3.1

This means **for the inverse-grating bias correction**, you don't need θ, projection-arm M, or the internal projector parameter `a`. The "tilt-flip trick" of §4.3.1 computes the inverse pattern from calibration data alone:

```
1. Project uniform fringes onto flat reference
2. Capture phase-shifted frames, extract unwrapped phase φ₁
3. Fit a tilted plane:        P(x, y) = m_x·x + m_y·y + c
4. Subtract tilt:             curvature = φ₁ − P
5. Flip sign:                 inverse_curvature = −curvature
6. Add tilt back:             φ₂ = P + inverse_curvature = 2·P − φ₁
```

φ₂ is then used to generate the pre-distorted projection pattern (Eq. 4-5). When projected through the same biased system, the pre-distortion and the system bias cancel. Result: clean uniform fringes (Eq. 4-9), regardless of what the underlying system parameters actually are.

**However**, this only handles the bias-correction step. The phase-to-height conversion (λ_eq, Eq. 2-51) still depends on both arm angles. In real hardware, λ_eq is calibrated empirically against a step gauge, sidestepping the need to measure both angles precisely. In simulation, λ_eq is computed from Eq. 2-51 directly because both angles are known by definition (they're sliders).

Chapter 4 also covers:
- Repeating the bias measurement 50× with phase offsets and surface position changes for averaging
- Vertical (height) calibration: measure a known step, compute λ_eq empirically
- Lateral (xy) calibration: image a known grid scale, compute µm/pixel

---

## 7. State of the Project Through Stage 3

### Notebook (Stage 1 work, frozen as historical reference)

The user's `Fringe_Projection_Python.ipynb` implements the math and includes the Stage 1 simulation-loop and strengthened validations:
- Phase shifting, unwrapping, tilt fitting, tilt-flip correction, height reconstruction
- Recovers a synthetic Gaussian to ~10⁻⁵ precision
- `project()` function added (Stage 1.1) — Taylor-approximation forward model
- Roadmap validations 1.2 / 1.3 done (consistency check + curvature cancellation on flat reference)
- Strengthened validations 1-S.1 / 1-S.2 / 1-S.3 done (Taylor error bounded, parameter scaling verified, limit cases pass)

The notebook is frozen as the source of truth for the regression fixture `tests/regression_data.npz`, which Stage 2 modules are tested against. **Notebook cell 25 (Stage 1-S.1) is also the spec for the Stage 3 exact-form forward model** — the `+u` denominator convention adopted in `project(model='exact')` is documented there.

### Validation philosophy arrived at during Stage 1

The user pushed back hard on tests that compare two quantities both derived from the same analytical formula — correctly identifying that such tests can't fail in simulation regardless of whether the underlying physics is right. Key insight:

> *Simulation validation can only catch bugs where the test path uses different logic than the thing being tested. Tests that share the same formula on both sides are tautological.*

This led to:
- Recognition that Stage 1.2 (`project(uniform) == phi1`) is operationally a typo-guard, not a physics test.
- Recognition that an originally drafted Stage 1-S.4 cell (end-to-end recovery via explicit `project()` chain) was redundant with what cells 14–20 already validate. **It was deliberately omitted.**

Real validation comes from (a) cross-implementation comparison (MATLAB, Three.js), (b) real hardware, or (c) analytical limit checks. Stage 1 covers (c). Stage 2's regression test will start (a). Stage 6 brings (b).

### Stage 2 — Refactor into Python modules (Complete)

Six task-prompts handled one at a time; one module per commit (plus chores). Final state: 12 tests, all passing, closing commit `b5b7342` tagged `stage-2-complete`.

| Task | Module(s) | What landed |
|---|---|---|
| 2.1 | `geometry.py` + scaffolding | `Geometry` Protocol, `HybridGeometry` (default), `SymmetricGeometry` (cross-check). All-arg constructors. Regression fixture script + `tests/regression_data.npz`. |
| 2.2 | `synthetic_fringes.py` | `project(input_phase, geometry, model='taylor')` + `synthesize_psi_stack`. Architectural lock: `project()` does not read `λ_eq`. |
| 2.3 | `phase_shifting.py` + `unwrapping.py` | Generalized N-step PSI via `arctan2(-Σ I sin δ, Σ I cos δ)`. |
| 2.4 | `calibration.py` | `fit_tilt_plane` (2D lstsq), `compute_inverse_phase` (tilt-flip, Eq. 4-7). |
| 2.5 | `reconstruction.py` | `phase_to_height` (dispatcher to geometry), `recover_object_height` (full pipeline composition). |
| 2.5b | `calibration.py` (hotfix) | Added `fit_tilt_line_1d` to lift inline polyfit out of test code. |
| 2.6 | `tests/test_pipeline_synthetic.py` | End-to-end integration test through public APIs only. |

### Stage 2 architectural decisions (with Stage 4 corrections noted)

These were made during refactor and bind future stages (also mirrored in PROJECT_CONTEXT.md Section 12):

- **Module order swapped from PROJECT_CONTEXT Section 11**: calibration before reconstruction, so tests follow data flow.
- **`project()` is `λ_eq`-independent**, locked by `test_project_is_lambda_eq_independent` (`atol=1e-15`). Both Geometry types produce bit-identical bias output. Stage 3's exact-form forward model preserves this. Stage 3.5 preserved it too.
- **Two non-interchangeable tilt fits in `calibration.py`**: `fit_tilt_plane` (2D, flat refs) vs `fit_tilt_line_1d` (1D, object self-cal).
- **`recover_object_height` is operand-agnostic on `phi_calibration`**.
- **Integration test does NOT close the inverse-grating loop.** Same tautology limit as Stage 1's omitted 1-S.4.
- **Stage 2 Decision 3 (one-angle hybrid λ_eq) is SUPERSEDED by Stage 3.5** — see Section 7c below for the full rationale. The Stage 2 form `λ_eq = Mp / tan(θ_projector)` implicitly assumed `θ_camera = 0°` by conflating "telecentric lens" with "vertically mounted camera." Stage 4 surfaced this and upgrades to the full Eq. 2-51 two-angle form.

### Tooling / housekeeping in Stage 2

- Two-tier regression tolerance: `ATOL_ANALYTICAL = 1e-12`, `ATOL_PIPELINE = 1e-8`.
- `.npz` for regression fixtures.
- `.gitattributes` with `* text=auto eol=lf`.
- `environment.yml` pins Python 3.10, NumPy 2.2.6, pytest, etc.
- Git-history rewrites at Stage 2 close: purged `FPP Thesis/` PDFs from history; updated commit authorship.

### Stage 3 — Exact forward model (Complete)

Two task-prompts across two commits. Final state: 17 tests, all passing, closing commit `e5201fb` tagged `stage-3-complete`.

| Task | File(s) | What landed |
|---|---|---|
| 3.1 | `src/synthetic_fringes.py`, `tests/test_synthetic_fringes.py` | `project(model='exact')` per cell 25's `+u` denominator: `phi_exact(x) = (2π/p)·x / (1 + 2x·tan(θ)/a)`. 4 new unit tests. ValueError guard on denom ≤ 0. Commit `b752f47`. |
| 3 close | `tests/test_pipeline_synthetic.py` | Integration test parametrized over `model in {'taylor', 'exact'}`. Exact branch: only `isfinite` checks; std_err printed informationally. Commit `e5201fb`. Tag: `stage-3-complete`. |

Roadmap sub-tasks 3.2 and 3.3 deliberately reframed (skipped / folded in).

### Stage 3 architectural decisions

- **`+u` denominator is the project's operational convention.** Textbook Ch.4 Eq. 4-6 has `−u`; notebook cell 25 documents the typo.
- **Default stays `model='taylor'`.**
- **Validation reframed as informational, not gatekept.**
- **Object leg still synthesizes `phi3` analytically.** Documented honestly in the test docstring.

### Tooling / housekeeping in Stage 3

- Stage 3 close commits: `b752f47`, `e5201fb`, `3716687` (docs). Tag `stage-3-complete` on `e5201fb`. All pushed.

---

## 7a. Stage 4 Planning (strategy chat — Stage 4 pre-implementation)

### What the GUI is, in plain words

A simulator that operates as a **digital twin** of the user's lab setup. The user adjusts hardware-realistic controls and sees both a scientific result (true vs. recovered height with error map) and a spatial result (the apparatus in 3D). The point is to validate the math under different parameter regimes **before** the real hardware is fully built and mounted.

### Stage 4 sequence (originally planned)

- **Stage 3.5 (pre-task):** math layer upgrade to two-angle λ_eq (Eq. 2-51). One commit. See Section 7c.
- **Stage 4a:** surface library + GUI + recovered-height view (the scientific tool)
- **Stage 4b:** lab setup view (the spatial visualization) — originally planned as a separate view; refactored during Stage 4a to a unified scene (see Section 7e).

Each stage 4 sub-stage ships as its own tag (`stage-4a-complete`, `stage-4b-complete`). Build the useful one first; the pretty one second. Math modules from Stages 2–3 are called by the GUI, not modified (except for the Stage 3.5 pre-task).

### Final slider/control list (locked after long planning discussion)

Mirrored in PROJECT_CONTEXT.md Sec 12. Five controls plus a surface dropdown:

- Surface type (flat / tilt / Gaussian / step / sphere) + per-surface params
- **θ_projector** slider (projector arm tilt from surface normal)
- **θ_camera** slider (camera arm tilt from surface normal — independent of projector)
- Projector distance from surface slider — **lab-design tool only**, does not affect chapter's bias math
- PSI step count dropdown (4 or 8)

Everything else (M, `a`, `p`, camera distance, FOV, throw ratio, λ_eq, model='taylor', resolution) is locked at hardware values and shown in a read-only info panel.

**Stage 4b additions to the slider set:** camera_distance slider (132–182 mm Edmund WD range) became live so the camera body can be repositioned in the scene. Theta sliders extended to ±75° (from ±60°) because clip-detection cases need ~67° to fire at minimum WD.

**Degenerate case handling:** when `tan(θ_proj) + tan(θ_cam) → 0`, λ_eq → ∞ → "no height sensitivity." GUI shows clear warning, freezes the 3D view on its last good frame (implemented in Stage 4a task 4c).

### The reasoning trail (preserve this — easy to forget; it took many turns to get clean)

The slider list emerged from peeling back five false starts. Recording them so a fresh chat doesn't re-walk the same ground:

**False start 1: "M as a slider to explore distance changes."** Wrong because the camera lens is telecentric — M and distance are independent within the working distance range (132–182 mm). Moving the camera changes focus, not magnification or FOV. M is locked at 0.09× regardless of camera position.

**False start 2: "Projector M and projector distance are coupled."** Wrong framing. Projectors don't have an "M" in the chapter's framework. They have `a` (internal grating-to-lens distance) and a throw ratio (lab-side). The chapter's M refers to the camera arm only (Eq. 2-41: `M = l/b` where l is camera-to-surface distance and b is camera-to-sensor distance).

**False start 3: "Projector throw distance can drive `a` via the thin-lens equation."** Mathematically derivable (`a = f·D/(D−f)`), but this is image-side optics — the wrong `a`. The chapter's `a` is the **internal** distance from the DMD chip to the projector lens, which is **fixed by the projector hardware**. Moving the projector in the lab does NOT change `a`.

**False start 4: "Symmetric assumption means projector distance must equal camera distance."** The symmetric form in Figure 4-4 (`l_p = l_k`, `a = b`, `θ_1 = θ_2`) is an expository convenience in the chapter, not a physical requirement. The tilt-flip method (§4.3.1) absorbs whatever bias the actual setup produces. Asymmetric distances are fine; the math handles them.

**False start 5 (the biggest one, surfaced late in planning): "Telecentric camera lens means θ_camera = 0° (camera vertical)."** This was baked into Stage 2 Decision 3 (`λ_eq = Mp / tan(θ_projector)`). It was wrong. Telecentric only locks the lens's magnification (M is constant regardless of object distance, which is the property that eliminates lens-side perspective bias). The camera *body* can be mounted at any tilt angle relative to the surface — that's an independent mechanical parameter. The chapter's Eq. 2-51 takes both θ_projector and θ_camera as separate inputs, and the user's setup actually has the camera tilted at some non-zero angle (the lens being telecentric doesn't dictate the mount angle).

**What survived all five false starts:**

- **Camera lens M is locked by telecentric lens spec.** No slider for M.
- **`a` is fixed inside the projector.** No slider.
- **Projector distance moves projector body in 3D space but doesn't change bias math.** Slider kept for lab-design intuition (became live in the unified-scene Stage 4b).
- **Both arm angles (θ_projector and θ_camera) are independent sliders.** Both contribute to triangulation via Eq. 2-51. Either or both can be zero (resulting in degenerate λ_eq → ∞).
- **PSI step count** is a measurement-protocol toggle, not a hardware property.

### Two 3D views (original Stage 4 plan — superseded during Stage 4a)

The user wanted both a recovered-height 3D view and a separate lab setup view (camera body, projector body, cones, etc.) toggled by a button. **This was refactored mid-Stage-4a to a single unified scene** — see Section 7e.

The user considered embedding their Three.js collaborator's existing lab visualization via Qt-WebEngine to avoid rebuilding it in Python, but **explicitly rejected this** in favor of building the lab view native in PyQt6 for full ownership and tighter integration with the controls.

### Why MockCamera / MockProjector got deferred

PROJECT_CONTEXT Sec 7.3 designs the hardware boundary as `Camera`/`Projector` Protocols with `MockCamera`/`MockProjector` synthetic implementations. The roadmap puts these in Stage 4. **The user opted to defer them entirely to Stage 5/6.**

Rationale (user's own framing, paraphrased): *it's better to have a working theoretical simulation that matches hardware specs first, and then design the hardware abstraction when the real hardware is in hand and its actual SDK calls / frame formats / timing are known. Designing protocols against unknown hardware is premature.*

### Hardware values for the GUI's info panel (locked at planning, real where known)

| Quantity | Value | Status |
|---|---|---|
| Camera M | 0.09× | Real (Edmund Optics #58-259 spec) |
| Camera-to-surface distance | 157 mm | Real (middle of 132–182 mm WD range) |
| Camera FOV | 68 × 55 mm | Derived from real specs |
| Pixel pitch on surface | ~53 µm | Derived from real specs |
| Sensor | 1280 × 1024 at 4.8 µm | Real (FLIR Blackfly spec) |
| Projector throw ratio | 1.2:1 | Real (Pico Genie spec) |
| Projector distance (default) | 82 mm | Computed: 68 mm × 1.2 (matches projector FOV to camera FOV) |
| `a` (projector internal) | 2000 px | Placeholder until measured |
| `p` (fringe period) | placeholder | Placeholder until measured |
| θ_projector (default tilt) | 15° | Placeholder until mount geometry settled |
| θ_camera (default tilt) | 15° | Placeholder until mount geometry settled (default = symmetric for fixture compatibility) |

**Both `HybridGeometry` and `SymmetricGeometry` defaults must update in lockstep** when real hardware arrives, or `test_project_is_lambda_eq_independent` silently breaks.

### 3D viewer backend decision

**PyQtGraph (OpenGL)** is the strong default for both views. Reasons: fast live updates needed for slider response, decent orbital camera built in, single dependency for both views. Matplotlib 3D considered and rejected (too slow). VTK/Mayavi considered and rejected (overkill).

### Resolution decision

Locked at 480×640 for live updates. Full-res toggle deferred.

---

## 7b. Stage 4 critical discoveries (what changed in our understanding during planning)

These are the substantive mid-conversation discoveries that the planning history is worth preserving for. Each one corrected a previous-stage assumption or clarified a chapter equation.

### The "telecentric = vertical camera" conflation (biggest discovery)

For the entire planning session leading up to the slider list, I (the strategy assistant) was working under an implicit assumption that turned out to be wrong: that the camera being telecentric meant it was mounted vertical (looking straight down at the surface). This wasn't anywhere in the chapter — it was a residual assumption from Stage 2 Decision 3.

The user surfaced this by repeatedly asking "what about the projector angle?" and "can I have both vertical?" Their physical intuition (different from textbook chapter framing) was that **both arms are independently mountable** — telecentric only means M is constant. The chapter's Fig. 2-10 shows θ₁ and θ₂ as separate parameters, and Eq. 2-51 takes both. Stage 2 had collapsed θ_camera to zero based on telecentric reasoning that was just wrong.

This is the kind of discovery that's invisible until someone asks the right question. The user did. Strategy chat should have caught it earlier, but didn't until the user pushed multiple times.

**Concrete fix:** Stage 3.5 pre-task before Stage 4. Math layer got θ_camera as an explicit constructor arg. λ_eq formula uses Eq. 2-51 directly. Stage 2 Decision 3 explicitly superseded.

### Eq. 2-51 is the right formula, not Eq. 4-11

The user asked "what does the paper have? It has one right since it's symmetric." The honest answer: the paper has **Eq. 2-51 as the general two-angle form** and **Eq. 2-52 as the symmetric special case**. Eq. 4-11 (`λ_eq = Mp / (4π sin θ)`) is a Chapter 4 restatement of the symmetric form using a slightly different parameterization. The notebook (cell 14) uses Eq. 4-11. Stages 2/3 inherited that.

Stage 3.5 updated the math layer to use Eq. 2-51 directly. Doing so:
- Is more faithful to the paper's general framework.
- Reduces cleanly to Eq. 2-52 / Eq. 4-11 in the symmetric case (sanity check).
- Doesn't break the regression fixture, because the default θ_camera = θ_projector (symmetric default) was chosen — which matches the fixture's setup.

### θ = 0 is mathematically valid but physically degenerate

When the user asked about projector-vertical configurations: with θ_projector = 0 AND θ_camera = 0 (or any pair where they sum to zero — equal-and-opposite angles), `tan(θ_p) + tan(θ_c) = 0`, so λ_eq → ∞. This means "no height sensitivity" — physically, both arms looking from mirror-symmetric directions can't triangulate. This is not a bug, it's the correct physical answer. The GUI implements this as a warning banner that freezes the 3D view at its last good frame (Stage 4a task 4c).

---

## 7c. Stage 3.5 — Math layer upgrade (executed before Stage 4a)

**Status: Done.** Commit `658f331`, pushed, not tagged (pre-task to Stage 4a).

**Why this existed.** Stage 4 planning surfaced that the Stage 2 `HybridGeometry.equivalent_wavelength()` was using the simplified form `λ_eq = Mp / tan(θ_projector)`, which implicitly assumed `θ_camera = 0°`. To support a GUI with separate θ_projector and θ_camera sliders, the math layer needed Eq. 2-51's full two-angle form.

**What landed:**

- `src/geometry.py`: `HybridGeometry.__init__` gained `theta_camera` arg (radians, default `= theta_projector` — preserves fixture compatibility). `equivalent_wavelength()` updated to `M·p / (2π·(tan θ_proj + tan θ_cam))`. Same change to `SymmetricGeometry`. Note: the code's `lambda_eq` is numerically `λ_textbook / (2π)` — the `× ψ/(2π)` from Eq. 2-51 is pre-folded into the wavelength constant. This naming was confirmed correct (not a physics bug) during Stage 4a task 4c.
- `tests/test_geometry.py`: 13 new tests (existing 17 still pass = 30 total).
- `tests/test_reconstruction.py`: small update to derive `phi3_unwrapped` from PSI extract + unwrap internally rather than reading from regression fixture (the cross-coupled λ_eq leaked ~1e-6 residual from the old Eq. 4-11 sin formula). Fixture itself untouched.
- Architectural invariants preserved: `project()` stays λ_eq-independent at atol=1e-15. HybridGeometry and SymmetricGeometry remain bit-identical in `project()` output.

**Spec deviation worth noting:** the test fixture update wasn't in the original Stage 3.5 spec; the residual surfaced during execution and was fixed in the same commit, documented in the commit message.

---

## 7d. Stage 4a — Execution history (PyQt6 GUI digital twin, complete)

Tag: `stage-4a-complete`. 70 tests passing.

### Sub-task summary (commit by commit)

| Task | Commit | One-line summary |
|---|---|---|
| 1 (surface library) | `f4bd4fb` | 5 pure-NumPy heightmap generators (`make_flat/tilt/gaussian/step/sphere`) + 30 unit tests. |
| 2 (GUI skeleton) | `e45bff5` | PyQt6 package skeleton, all widgets visible, no behavior wired except dropdown → page swap. PyQt6 install confirmed via pip (conda-forge mismatch with already-installed PyPI build). |
| 3 (live preview) | `cfa0772` | Surface controls wired to live 3D ground-truth rendering. First math import in GUI. pyqtgraph 0.14.0 `GLSurfacePlotItem.setData(colors=...)` docstring inaccuracy documented as known quirk. |
| 4 (pipeline integration) | `fa12e30` | `src/pipeline.py` with `run_pipeline()`. Geometry + PSI sliders wired. 3D view shows recovered height. **Unit-system mismatch caught before commit** — Claude Code's pre-commit sanity check found recovery ~3000× inflated when info-panel mm-values were plugged directly into math layer; user redirected to notebook pixel-units (M=1, p=40 px, a=2000 px). |
| 4b (error overlay) | `f224a4f` | Display Mode toggle + Error Statistics groupbox (mean/std/max-abs/RMS). Diverging colormap (CET-D1) on signed error. Amplitude slider maxes bumped to 100 mm. `Z_EXAGGERATION = 20.0`. |
| 4c (warning banner) | `03ed339` | Degenerate-case red warning banner with textbook-form Eq. 2-51. `ErrorColorbar` widget below view_3d with `-max / 0 / +max` labels. `Z_EXAGGERATION` dropped to 2.0 (prep for Stage 4b). Stats auto-format to scientific notation for sub-precision values. |
| 4d (stages viewer) | `13a4372` | 2×3 grid of 5 camera-view heatmaps (ground truth, projected fringes, wrapped phase, unwrapped phase, recovered height) with title + ImageView + equation per panel. `run_pipeline(return_stages=True)` kwarg. View Mode radio toggle on left pane. Right pane wrapped in QStackedWidget. CET-C1 cyclic colormap on wrapped phase. |
| 4e (close) | `7ecd788` | Docs update + tag `stage-4a-complete`. |

### Stage 4a planning conversation (strategy chat — pre-task-4)

Five design questions were settled before drafting task 4's prompt:

**Q1 — What the 3D view shows.** Three options considered: recovered only, true + recovered side-by-side, recovered with error map overlay. Settled on: **recovered as main view + toggle-able error overlay coloring** (recovered surface stays as the geometry, error magnitudes drive the color). Diverging colormap (blue under-recovered / white perfect / red over-recovered). Plus an error-stats panel (mean / std / max abs / RMS) that appears when overlay is on. The original "see how true would have looked" framing got pushed back — error is what the user actually wants to see, not redisplay of the input they set with sliders. **NOTE (Stage 4d follow-up parking lot):** the "see how true would have looked" framing was REVISITED during the follow-up review and accepted as valid for a future refactor. Lab view will default to showing the ground-truth FOV slice with the recovered surface as an opt-in toggleable overlay; a dedicated 4th tab ("Recovered Surface") will show both surfaces by default for quantitative comparison. See §7h for the design discussion.

**Q2 — Degenerate λ_eq handling.** Detect `|tan θ_proj + tan θ_cam| < 1e-3` before calling the pipeline. Show a red warning banner explaining why height info isn't available; keep the last good 3D frame visible. Don't crash, don't blank, don't clamp. The banner uses the **textbook form** of Eq. 2-51 (with no `2π` in the denominator) so the equation matches what the user sees in the chapter PDF — independent of the code's internal `λ_textbook/(2π)` convention.

**Q3 — Performance.** Ship at full 480×640, measure, only optimize if actually slow. Don't pre-emptively add "compute on release" or downsample.

**Q4 — Bad-parameter handling.** No defensive try/except in task 4. Slider ranges prevent the known failure modes (exact-model denominator non-positive requires extreme angles outside the slider range; degenerate λ_eq has its own banner). Adding catch-all error handling for unknown failures was deferred until a real failure mode surfaces.

**Q5 — Commit shape.** Task 4 split into three commits instead of one: 4a (pipeline plumbing + recovered-height view), 4b (error overlay + stats), 4c (warning banner + colorbar + Z exaggeration tuning). Each ~250–400 lines. Same pattern as Stages 2/3 — one concept per commit. After the user's professor reviewed the work, task 4d (pipeline stages viewer) was added as a fourth commit and task 4e (close commit + tag) as the fifth.

### Stage 4a discoveries during execution

**Pyqtgraph 0.14.0 `GLSurfacePlotItem.setData(colors=...)` docstring is wrong.** The docstring claims `colors` should be `(width, height, 4)`, but the data is passed straight to `MeshData.setVertexColors`, which requires the flat `(N_vertices, 4)` form. Workaround: `colors.transpose(1, 0, 2).reshape(-1, 4)`.

**Pyqtgraph 0.14.0 doesn't bundle 'gray' or 'hsv' colormaps.** Workarounds: manual 2-stop black-to-white `ColorMap` for the fringe-frame panel; `CET-C1` (perceptually-uniform cyclic) for wrapped-phase panel.

**The unit-mismatch incident (task 4).** The original task-4 prompt told Claude Code to construct `HybridGeometry` with the info-panel's mm-space values (M=11.1 chapter convention, p=2.0 mm, a=50 mm). Claude Code did so, then ran a pre-commit magnitude sanity check before launching the visual. The result: recovered Gaussian peaked at ~1535 mm against an input of 0.5 mm — a ~3000× inflation, caused by the math layer interpreting M=11.1 as the modern convention (silently inflating λ_eq by ~123×) plus the carrier `(2π/p)·X` with `p=2.0` and `X = np.arange(W)` producing a Nyquist-aliased fringe density. Claude Code stopped before commit and surfaced the issue. The fix: hardcode notebook pixel-space units in `_build_geometry()` (M=1.0, p=40.0, a=2000.0) and leave the info panel's mm-space display values decorative for now. Unit reconciliation deferred to Stage 5/6 when real hardware values arrive.

**The λ_eq naming verification (task 4c).** A verification pass on `geometry.py` and `reconstruction.py` confirmed the code is correct: `equivalent_wavelength()` returns `λ_textbook / (2π)`, and `phase_to_height()` is implemented as `ψ × equivalent_wavelength()` — the `2π` from Eq. 2-51 is pre-folded into the wavelength constant. Final pipeline output matches Eq. 2-51 exactly. **No physics bug, only a naming convention difference.** The warning banner displays the textbook form so users cross-referencing the chapter PDF see the same equation.

**Professor feedback that shaped task 4d.** After tasks 4a/4b/4c landed, the user showed the GUI to his professor. Professor's feedback: (1) STL-import flow for custom test objects (deferred — eventually Stage 4c); (2) the user should be able to see intermediate pipeline stages, not just the final recovered surface. The latter became task 4d — a pipeline stages viewer showing all 5 stages.

### Stage 4b refactor — unified scene supersedes "separate lab view"

Originally planned as a separate 3D view toggled by a button. During Stage 4a's task-4d planning conversation, the user clarified their actual mental model: they want the lab apparatus (camera body, projector body, cones) **added to the same 3D scene** that shows the recovered surface — not a separate view. Same coordinate frame, same orbital camera, just more items in the scene.

**This is cleaner.** Hardware bodies provide visual reference scale (Z exaggeration can drop further toward honest). Projector-distance slider becomes meaningful (lab-view changes). User sees the recovered surface AND the rig that produced it simultaneously. No mode switching.

---

## 7e. Stage 4b — Execution history (Unified hardware-bodies scene + clip-detection, complete)

Tag: `stage-4b-complete`. 143 tests passing.

### Sub-task summary (commit by commit)

| # | Commit | One-line summary |
|---|---|---|
| 1 | `3c4e5e5` | `src/scene.py` mesh builders. Camera/projector body cubes at real dimensions (29×29×30 mm, 55³ mm). CCW outward winding, pure `(verts, faces)` returns. 12 new tests. |
| 2 | `fbc5853` | `_cylinder` / `_stepped_cylinder` helpers. `make_camera_lens` matching Edmund's stepped 3-section profile (200mm total). `make_projector_lens` (20×5mm). `src/scene_compose.py` new: pose composition layer with `camera_arm_transform`, `projector_arm_transform`, `body_lens_offset`. 33 new tests. |
| 3 | `7bb2b41` | `src/gui/hardware_scene.py` new: `HardwareScene` class hosting GLMeshItems, GLLinePlotItems for the wireframes, and `compute_arm_transforms()`. main_window: new `camera_distance` slider (132–182mm Edmund WD range), renamed `projector_distance` slider labels to optics convention (lens-front to surface, NOT body-center). `LabeledFloatSlider.set_value()` added. View distance bumped 80→600mm. 6 new tests. |
| 4 (1/3) | `e96e1fc` | Projection + viewing cones + clip-detection v1. Three checks — camera/projector lens disc-edge vs surface plane, body assembly AABB overlap. `ClipState` dataclass. Theta sliders extended ±60° → ±75°. Gray override + warning banner. 18 new tests. |
| 4 close (Z retune) | `45c2071` | **Z_EXAGGERATION 2.0 → 1.0** (honest scale). User picked from empirical 4-screenshot comparison (Z = 1, 2, 5, 10). |
| 4 (2/3, REVERTED) | `c53dd36` → `20d6771` | Originally added surface-peak-vs-lens 3D contact checks. **Reverted** after interactive GUI testing showed these are unreachable in practice. Reset preserved in history rather than rebased away. 139 tests after revert. |
| 4 (3/3) | `5d4b4c4` | **FOV/cone coverage advisories — 3D volume tests.** Replaces the buggy 2D z=0 footprint coverage check with 3D point-in-volume tests against the camera viewing prism and projector projection cone. 11×11 heightmap sampling. Cone test uses angular criterion only. Banner-only, no gray override. 4 new tests, total 143. |
| 5 (close) | this commit | Docs update + tag `stage-4b-complete`. |

### Stage 4b critical mid-execution discoveries

**Surface-vs-lens contact checks are unreachable in practice.** At any combination of slider values within their stated ranges (WD 132–182 mm, surface amplitude 0–100 mm, θ ±75°), the lens never gets close to the peak. At WD=132 (closest), camera_body sits at z ≈ 132·cos(0) = 132 mm above the origin; surface peak max is 100 mm; clearance ≥ 32 mm. The check was dead code. Commit 20d6771 reverted c53dd36 cleanly.

**The vertical-spill FOV bug (user-caught).** With the surface tilted toward the camera and the Gaussian peak tall enough, the tip poked out the **top** of the tilted prism volume, but the 2D footprint check (z=0 only) said all was well. Fix: switch to 3D point-in-volume tests on 11×11 sampled heightmap points.

**The cone upper-bound (`s <= throw`) was wrong.** `throw` is the projector's nominal DLP focus distance, not a hard light cutoff. The beam keeps diverging past the focus plane. The angular criterion alone is the correct geometric test.

**Distance slider semantics: lens-front vs body-center.** Decision: sliders report lens-front. `compute_arm_transforms` adds the body offsets internally.

**The Z exaggeration decision.** Four smoke tests rendered at Z=1, 2, 5, 10. User reviewed all four and picked Z=1.0 with: "Z=10 is a lie. Z=2 is a lie. Z=1 is the right answer because that's what's actually there. The lens IS that far above the peak."

### Stage 4b architectural decisions worth carrying forward

- **Banner vs gray semantics.** Collision (gray + banner) = physical impossibility. Coverage (banner only) = measurement incompleteness. Math runs regardless.
- **Math-layer purity extended to clip-detection.** `clip_detection.py` is pure NumPy + scene imports.
- **All clip-detection geometry constants derived from cone builders, not duplicated.**
- **The 3D viewport is a geometric ruler with Z=1.0.**
- **Two independent banners.** Degenerate-λ_eq + clip-warning, both can show simultaneously.
- **Smoke-test capture protocol.** Programmatic GUI launch → `view_3d.grabFramebuffer()` to `%TEMP%`, gated by user greenlight. One-process-per-render.
- **Banners DON'T appear in `grabFramebuffer` captures.** Verify state programmatically.
- **Stage 4b sub-task 4 went through a reset.** Preserved in history.
- **No Co-Authored-By trailers.**

---

## 7f. Stage 4c — Execution history (STL import for arbitrary specimens, complete)

Tag: `stage-4c-complete`. 142 tests passing.

### Sub-task summary (commit by commit)

| # | Commit | One-line summary |
|---|---|---|
| 1 | `eecaeac` | Dropdown reduction (Flat, Gaussian only) + Gaussian amplitude cap 100→55 mm. `make_tilt`/`make_step`/`make_sphere` deleted. Net −223 lines. 122 tests. |
| 2 | `db0cd21` | `src/stl_loader.py`: `load_stl_heightmap(path, shape, pixel_size_mm)`, `get_stl_bbox_mm(path)`. Projected-barycentric rasterization with per-pixel max-z upper envelope. Lift convention at the time of this commit: by **global mesh-Z minimum**. **This convention was reset to visible-envelope minimum in the Stage 4d follow-up GUI review** — see §7h. 14 new tests. `numpy-stl==3.2.0` added to `environment.yml` pip block. 136 tests. |
| 3 | `2c73955` | STL wired into the surface dropdown as `"STL file..."`. `_load_stl_from_path(path) → bool` no-dialog hook. Cache lives for the window's lifetime. Temporary `QMessageBox.warning` bbox guard (replaced in sub-task 4). 6 new GUI tests. 142 tests. |
| 4 | `286ebb3` | Finalize the bbox guard: hard-reject only. The earlier draft (custom dialog with Rescale/Truncate/Cancel) was **dropped during planning** — see pivot below. Text-only commit; 142 tests unchanged. |
| 5 (close) | this commit | Docs update + tag `stage-4c-complete`. |

### Stage 4c critical mid-execution discoveries

**The lift-formula contradiction (sub-task 2 halt).** The prompt for sub-task 2 said "lift = subtract the minimum finite envelope value, sentinel→0." During summarize-back, Claude Code worked through the cube and sphere test cases and surfaced that the stated arithmetic was impossible for those tests. The tests were satisfied only by **subtracting the global minimum-Z vertex over all mesh triangles**, including the camera-invisible bottom shell. Caught before any code was written. **Important update from the Stage 4d follow-up:** the Stage 4d GUI review surfaced that the "true base across all vertices" convention was itself wrong — see §7h. The cube and sphere test assertions got updated under the visible-envelope convention.

**The numpy-stl conda-forge ABI hazard.** `conda install -c conda-forge numpy-stl` dragged in a duplicate numpy + MKL/BLAS/LAPACK stack that broke `numpy.linalg`. Recovery via revision-0 rollback + pip reinstall numpy + pip install numpy-stl. **The rule:** since this env's numpy is pip-installed, every new dependency goes in the pip block regardless of how pure-Python it looks.

**The blockSignals + manual setCurrentIndex coupling (sub-task 3 halt).** `_revert_stl_dropdown` needs to call BOTH `surface_combo.setCurrentIndex(prev)` AND `surface_pages.setCurrentIndex(prev)` under `blockSignals` because the slots that normally do the page-swap don't fire under blockSignals.

**The grid-vs-FOV mismatch (sub-task 4 halt).** Surfaced that `SURFACE_SHAPE = (480, 640)` at `SURFACE_PIXEL_SIZE_MM = 0.1` produces a 48×64 mm grid, but the working volume is 68×55 mm. The reconciliation was deferred when the dialog got dropped. **Reconciled in Stage 4d sub-task 1.5:** math grid bumped to (550, 680) = exact 68×55 mm patch at 0.1 mm/px.

### Stage 4c sub-task 4 pivot — the dropped Rescale/Truncate dialog

The most consequential strategy-chat decision of Stage 4c. The originally-drafted Rescale/Truncate/Cancel `QDialog` would have implemented cleanly. The user pivoted during planning:

> "im still trying to push it because i want to consider practicality of the simulation.... realistically we cant have a full sized object that fits in the small FOV. most artifacts will be alot bigger than the FOV."

After one more refinement:

> "we have what i suggested which is showing a FOV portion of the top STL file..... and then having its top surface shown on top bird eye view at like lets say bottom right region of lab view. then it has a square on top of it which symbolizes the FOV grid. this grid can then be dragged across the surface which then updates to what is seen on the hardware components."

**The reframing.** Rescale and truncate both distort the geometry the simulation claims to measure. Windowed FOV selection preserves the part at native scale. Sub-task 4 collapsed from ~700 lines of new code to a 24-line text edit. The Browser became Stage 4d's headline.

**The lesson.** When a sub-task feels technically right but the user pushes on practicality, the spec is what's wrong, not the user.

### Stage 4c architectural decisions worth carrying forward

- **STL loader is a peer of `test_surfaces.py` in the surface-library role.** Same `(shape, pixel_size_mm) → (H, W) float64 mm` contract.
- **The math layer doesn't know STL exists.** **Stage 4d follow-up extension:** even Browser-mode off-part padding and recovered-output masking live in the GUI layer.
- **`_load_stl_from_path(path) → bool` is the GUI-facing entry.**
- **Cache on MainWindow is the surface-state contract.**
- **Halt-and-confirm gates fired three times productively in Stage 4c.**
- **The conda-forge ABI hazard is documented in `environment.yml`.**
- **No Co-Authored-By trailers.**

---

## 7g. Stage 4d — Execution history (STL Browser for full-scale specimens, complete)

Tag: `stage-4d-complete`. 181 tests passing.

### Sub-task summary (commit by commit)

| # | Commit | One-line summary |
|---|---|---|
| 1 | `759c933` | QTabWidget refactor. Replaced View Mode radio toggle with `QTabWidget` at top of right pane. Tabs: "3D Scene", "Pipeline Stages". 142 tests. |
| 1.5 | `6e1c434` | Math grid reconciled to camera FOV. `SURFACE_SHAPE (480, 640) → (550, 680)` at 0.1 mm/px, giving an exact 68×55 mm patch matching the advertised camera FOV. New `test_surface_grid_matches_camera_fov` invariant. 143 tests. |
| 2 | `fd5cb9f` | Full-scale STL data model + bbox-reject three-way branch. `load_stl_heightmap_full_scale(path, pixel_size_mm)` added. `WORKING_VOLUME_MM = (68, 55, 55)` and `ABSURDLY_LARGE_MM = (272, 220, 55)` constants. Z-overflow → hard-reject; XY within working volume → direct path; oversized XY but within ABSURDLY_LARGE → Browser path; XY > ABSURDLY_LARGE → reject. 154 tests. |
| 3 | `4d82d98` | Browser tab skeleton. New `src/gui/stl_browser.py`. QStackedWidget pattern: placeholder vs three-panel layout (minimap + whole-STL + windowed slice). 160 tests. |
| 2.5 | `bce7a7c` | STL Z cap + Gaussian amplitude cap raised 55 → 120 mm. Empirical bench + 20 mm margin. Bug-bait classification critical: "55" appeared in three semantic buckets, only Z-cap/Gaussian-cap edited. 161 tests. |
| 4 | `366fac8` | Browser Panels 1 + 3 read-only 3D rendering. Two methods: `update_whole_stl` and `update_windowed_slice`. Camera defaults tuned per panel (Panel 1 isometric scales to part bbox; Panel 3 fixed at distance=200). Mid-execution correction: distance bumped from 600 to 200 when screenshot review showed the windowed surface as a tiny diamond. 166 tests. |
| 5 | `ce3667a` | Panel 2 minimap + draggable FOV rectangle + live Panel 3 update. `pg.RectROI` with bright cyan `(0, 220, 255)` 2 px outline. `fov_dragged` signal. Drag does NOT touch lab view (drag-vs-commit separation). Mid-execution correction: initial view padded from half-FOV to full-FOV on each side after C3 capture showed clipping. 172 tests. |
| 5.5 | `8fafa94` | Panel 1 FOV highlight overlay (surface-following, live, opaque cyan). Second `GLSurfacePlotItem` in Panel 1, positioned at Z = surface + 0.05 mm. **Pyqtgraph 0.14.0 alpha-rendering bug discovered** — see diagnostic chain below. Workaround: alpha=1.0. 176 tests. |
| 6 | `27385b9` | Commit FOV button + lab view promotion. `QPushButton("Commit FOV")` below the minimap. `commit_fov_requested` signal. Lab view auto-shows the centered initial FOV at load via implicit refresh chain through `_open_stl_dialog` — third prompt-assumption catch of Stage 4d (no explicit auto-commit needed). 181 tests. |
| close | docs + tag `stage-4d-complete` |  |

### Stage 4d critical mid-execution discoveries

**Sub-task 1.5 — math grid was never honestly the camera FOV.** Stage 4a chose (480, 640) at 0.1 mm/px = 48×64 mm, but the camera FOV had always been advertised as 68×55 mm. Hairline-narrow planning miss that would have been confusing to debug later. Bumped to (550, 680).

**Sub-task 2.5 — the bug-bait around "55".** Halt-gate summarize-back produced a classification table of every "55" in the codebase. 30+ occurrences across three semantic buckets: Z-cap/Gaussian-cap (change to 120), camera FOV Y extent (stays at 55, hardware-locked), and hardware-body dimensions (stay at 55, unrelated). A blanket find-replace of "55" → "120" would have corrupted the camera FOV invariant. Two prompt-assumption catches landed in the same summarize-back: "55 doesn't appear in stl_loader.py" (false — two docstrings) and the smoke script omitted from in-scope-to-edit list (has hard-coded `amp_max == 55.0`).

**Sub-task 4 — Panel 3 camera distance vs SurfacePreview's distance.** Original prompt locked Panel 3 at 600 to match SurfacePreview. C2 capture showed the windowed surface as a tiny diamond. Mid-sub-task correction: distance=200 in the same sub-task. "Visual continuity" arguments can lose to "readability" arguments.

**Sub-task 5 — minimap padding spec mismatch.** First spec was half-FOV padding. C3 capture showed clipping at extreme off-part drag. Worst case is rectangle bottom-left at bbox edge, so outer edge sits at bbox edge + FULL FOV. Bumped to full-FOV padding in the same sub-task.

**Sub-task 5.5 — the maroon-vs-cyan investigation (longest diagnostic chain of Stage 4d).** Initial implementation used alpha=0.5 for translucency. The highlight rendered maroon instead of cyan. Strategy chat made **two wrong recommendations in a row** before the right diagnosis emerged.

First recommendation: switch to setColor() (uniform-color path). Result: still maroon.

Second recommendation: switch to shader=None. User asked strategy chat to investigate before fixing.

Six diagnostic experiments ran:
1. Single-item-in-view: still maroon — rules out GL state leakage between siblings.
2. White-on-white test: highlight systematically darker than the whole-STL — rules out color-input-specific bug.
3. glOptions inspection: identical → rules out blending state leakage.
4. Pure-RGB channel test: output was the COMPLEMENT of input. Channel inversion confirmed.
5. shader=None test: bug persisted.
6. Cyan with alpha=1.0: clean cyan rendered correctly.

**Root cause: pyqtgraph 0.14.0's `GLSurfacePlotItem` with `alpha < 1.0` produces inverted-complement colors regardless of shader, color path, or sibling-item state.** Empirical: `output_X ≈ 127 - 44 · input_X` for `alpha=0.5`. Workaround: alpha=1.0.

The lesson: **diagnostic-prompt-before-decision.** When strategy chat catches itself about to recommend a decision built on guesses about library internals, write a read-only diagnostic prompt first. Two failure modes: (1) confident-sounding recommendations built on guesses; (2) treating "make the symptom go away" workarounds as equivalent to fixing the underlying bug.

**Sub-task 6 — implicit refresh chain.** Strategy chat's prompt said the lab view "doesn't show the FOV at load time, so we need an explicit auto-commit." Halt-gate grep-traced the call chain and found that `_open_stl_dialog` (the only current caller) calls `_refresh_surface_preview` after the load returns. The proposed explicit auto-commit would have been a redundant refresh.

### Stage 4d architectural decisions worth carrying forward

- **`Z_EXAGGERATION = 1.0` is permanent doctrine, not a "for now" value.** User's words: *"i genuinely dont think i should exaggerate Z from its true height when the lab view is supposed to be a real scale. were supposed to know how object looks relevant to system. you feel me?"* Configurable Z exaggeration is NOT on the roadmap.

- **The lab view shows only the committed FOV slice, not the whole part.** **Stage 4d follow-up amendment:** the lab view will be REFACTORED to default to ground-truth FOV slice display with the recovered surface as an opt-in toggleable overlay; a dedicated 4th tab ("Recovered Surface") will be added for quantitative comparison. See §7h.

- **Drag-vs-commit separation is the core interaction discipline.** Cheap previews update live on drag. Expensive paths update only on Commit. The Commit FOV button is the latency boundary.

- **Math layer stayed pure across all 9 Stage 4d commits.** Zero lines added to `src/pipeline.py`, `src/geometry.py`, `src/synthetic_fringes.py`, `src/calibration.py`, `src/reconstruction.py`. **Stage 4d follow-up extends this** — even off-part edge-extend and recovered-output masking live in the GUI layer.

- **Module-level invariants get their own test file (`tests/test_main_window.py`).**

- **Half-step sub-task naming records planning order, not execution order.** Execution order: 1 → 1.5 → 2 → 3 → 2.5 → 4 → 5 → 5.5 → 6.

- **Browser lifecycle uses the `_*_item is not None` pattern.**

- **Pyqtgraph 0.14.0 alpha-rendering bug is a permanent codebase note.** Any future GLSurfacePlotItem color work must use alpha=1.0.

- **Three prompt-assumption catches during halt-gate summarize-back.** Pattern: when strategy chat writes "X doesn't appear in module Y" or "the system currently doesn't do Z," it's making a claim about state strategy chat doesn't have grep-level access to. Halt-gate's grep-first-claim-second discipline catches mismatches before code lands.

- **Visual review found and fixed two issues mid-execution.** When a sub-task touches visual behavior, the smoke captures are load-bearing, not extra.

---

## 7h. Stage 4d follow-up — Hands-on visual GUI review (complete; unpushed pending tag)

After Stage 4d closed with tag `stage-4d-complete`, the user opened a hands-on visual review session. The framing locked in early: **launch the GUI, exercise real STL files (the user's `fringe_demo_block_pillars.stl` and `fringe_demo_block_draft.stl`), catch any cosmetic or behavioral issue that didn't surface during programmatic smoke-testing.**

The review was originally expected to be cosmetic. It evolved into five focused commits driven by diagnostic discipline — four real bugs found (lift convention, off-part padding interaction with phase unwrap, body-overlap SAT false positives, projector-cone hairline triggers) plus one usability bump (ABSURDLY_LARGE_MM raised to support 450×450 mm specimens). Plus a design conversation that produced four parking-lot items for the next session's lab-view-and-recovered-surface refactor.

**Working model during the follow-up:** every fix was preceded by at least one read-only diagnostic probe. Three times during the session, the prediction the diagnostic was set up to confirm was overturned by the results, which is exactly why the probes were worth running.

### Follow-up commit summary

Five focused commits, all unpushed on `main`:

| # | Commit | What landed |
|---|---|---|
| 1 | `9480b94` | **STL lift convention: visible-envelope minimum, not global mesh minimum.** Reset of the Stage 4c sub-task 2 convention. `tris[:, :, 2].min() → acc[finite].min()` in both `load_stl_heightmap` and `load_stl_heightmap_full_scale`. Variable rename `z_min_mesh → z_min_visible`. Docstrings rewritten. Five existing tests' assertions updated: cube and full-scale box collapse to z=0 (flat-topped boxes have no relief under envelope-min lift); sphere peak ≈ R, not 2R (visible equator at z=0); pyramid and sphere tolerances loosened (0.15 / 0.25) to cover the discretization offset. 181 → 181 tests. |
| 2 | `fb19e0c` | **Off-part edge-extend into pipeline, mask recovered output to 0.** Three new helpers in `main_window.py`: `_browser_offpart_window`, `_browser_offpart_mask`, `_edge_extend_offpart`. `_refresh_surface_preview` gains gated padding before `run_pipeline` (Browser mode only) and masking-to-zero of recovered output after. Pipeline Stages tab's ground-truth panel still shows the ORIGINAL slice (off-part=0); phase panels reflect the padded input the math actually processed. One new GUI test using a synthetic X-ramp. 181 → 182 tests. |
| 3 | `e3c14bb` | **SAT body-overlap (OBB intersection) replaces assembly-AABB.** New `_obb_overlap` helper in `clip_detection.py`: pure NumPy SAT, 15 candidate axes, strict no-epsilon separation, cross-axis degeneracy threshold 1e-9. Removed `_world_aabb` and `_aabb_overlap`. One new regression test locking both documented false-positive poses (θ_cam=-13°, θ_proj=-45°, throw=200, WD=180 with 31.6 mm OBB clearance; θ_cam=30°, θ_proj=30°, throw=50, WD=132 with 22.3 mm OBB clearance). All four existing body-overlap tests kept their assertions, verified by SAT-classification probe before the edit. 182 → 183 tests. Closes the §13.8 deferred-OBB note. |
| 4 | `079cde4` | **2 mm advisory tolerance on projector-cone coverage check.** New `_CONE_COVERAGE_TOLERANCE_MM = 2.0` constant. `_surface_exceeds_cone` widens per-depth lateral half-extents by the tolerance; axial `s >= 0` check is NOT relaxed. Camera prism check stays exact. One new regression test locking the documented 0.40 mm hairline false positive at θ_cam=0°, θ_proj=-41°, throw=149, WD=157 with a flat 15 mm slab. 183 → 184 tests. |
| 5 | `48efdc4` | **ABSURDLY_LARGE_MM raised to (500, 500, 120) for 450×450 mm specimens.** XY raised from (272, 220) to (500, 500); Z kept at 120 (Stage 4d sub-task 2.5's empirical raise + lockstep invariant `WORKING_VOLUME_MM[2] == ABSURDLY_LARGE_MM[2]`). Memory footprint at 0.1 mm/px: 200 MB per heightmap. `stl_browser.py`'s `_PLACEHOLDER_TEXT` updated "272 × 220 mm" → "500 × 500 mm". Memory comment updated. Reject test updated: box 300×250 → 550×550, message assertions "300.0"→"550.0" and "272"→"500". **Headline catch in halt-gate:** the original prompt requested target (500, 500, 55), but Z was already 120 — setting Z=55 would have silently regressed sub-task 2.5 and broken `test_z_cap_matches_absurd_z`. The grep-check before the edit caught it. 184 → 184 tests. |

**Test suite progression:** 181 → 181 → 182 → 183 → 184 → 184.

### Stage 4d follow-up critical mid-execution discoveries

**Commit 1 — the three-symptom-one-root-cause discovery.** The visual review opened with three apparently-different symptoms in the GUI:

1. STL parts appearing to float above the stage grid in the lab view (a fraction of a mm gap visible).
2. A ~15 mm step at the FOV-bbox boundary when straddling FOVs were committed.
3. Recovered shape changing noticeably as θ_projector or θ_camera changed even at "valid" angles.

Strategy chat's first instinct was to treat them as three independent bugs. The user pushed back: "I think these are all the same problem, can you double-check?" Diagnostic probe confirmed the user's intuition. All three traced to the Stage 4c global-mesh-Z-minimum lift convention:

- **Floating part:** the global-min reference includes the closed solid's bottom shell. For a part 5 mm thick with the camera-visible top surface at z=5 (relative to the visible envelope), the global-min lift placed the visible base at z=5 instead of z=0. The "float" was the displaced visible base.
- **15 mm step at FOV-bbox boundary:** when the FOV straddled the part edge, the on-part region used the lifted heightmap (visible base at z=5 from the global lift), while the off-part region was filled with 0.0 by `_extract_fov_slice`. The 5 mm discrepancy at the boundary fed the phase unwrap a discontinuity, which the 2D unwrap couldn't follow — producing branch errors that propagated the 5 mm step plus accumulated phase ambiguity into the recovered surface as a 15 mm step.
- **Angle-sensitive recovered shape:** the 15 mm step's phase-unwrap branch errors changed differently as angles changed (because λ_eq changes with angles, so the same phase discontinuity wraps to different fractions of λ_eq at different angles). Symptom 3 was a downstream consequence of symptom 2, which was a downstream consequence of symptom 1.

The reset to visible-envelope minimum closed all three symptoms in one commit. Cube tests' assertions updated: flat-topped boxes legitimately collapse to z=0; sphere peak adjusted to R not 2R.

**Commit 2 — the byte-identical θ=15° vs θ=30° prediction that overturned.** During the off-part padding investigation, strategy chat predicted that the off-part-related recovery error would be **byte-identical** at θ=15° and θ=30° because λ_eq cancels through the pipeline. Claude Code ran a comparative recovery probe: identical input across both angles, byte-compare the recovered surfaces.

**Result: the recoveries were byte-identical from θ_proj=5° to θ_proj=50°, but diverged structurally at θ_proj > 55°.** The prediction held inside the working envelope and broke outside it. Strategy chat had been right about the cancellation principle and wrong about its bounds. The divergence at >50° traced to phase-unwrap branch failures when the part's relief exceeded ~h/λ_eq > 2π (working envelope: 30 mm pillars at θ=64° gives h/λ_eq ≈ 9.3 rad, multiple wraps per step). This is honest physics — real FPP would fail the same way at the same angles — but it surfaces in the GUI as "angle-sensitive recovered shape" that looks like a simulation bug.

**The follow-up commits don't try to fix the >50° unwrap divergence.** It's correct physics. The parking-lot item is the warning banner that explains the regime.

**Commit 3 — body-overlap false positive triage.** The user reported the "assemblies overlapping" banner firing at a pose that visually appeared clear (θ_cam=-13°, θ_proj=-45°, throw=200, WD=180). Diagnostic probe confirmed the false positive and quantified it: 31.6 mm OBB clearance vs assembly-AABB-overlap True.

A comparative three-option probe tested:
- Option 1 (full SAT — exact OBB intersection)
- Option 2 (lens-as-cylinder approximation)
- Option 3 (per-component AABB instead of assembly AABB)

Strategy chat's lean before the probe was Option 3 ("smallest commit"). The probe overturned this: Option 3 didn't fix the false positive — the 200 mm camera lens's own per-component world-AABB still inflated into the projector body's box. Options 1 and 2 both resolved the tested poses. Strategy chat's first preference shifted to Option 2 (medium-sized commit). User push-back: "do whatever you think is best." Strategy chat reconsidered: Option 2 retains an axis-aligned body-body test that would itself become a false-positive vector at high-tilt close-distance body-body pairs. Option 1 (full SAT) closes that weak spot too.

**Final decision: Option 1 (SAT).** The lesson: "smallest commit" is the wrong default when the bigger commit closes a future false-positive surface the smaller commit leaves open.

Second discovery during Option 1 implementation: the SAT-classification verification probe checked that all four existing body-overlap tests' assertions would hold under SAT. The at-risk one was `test_body_overlap_at_same_side_pose` at (θ=30°, throw=150, WD=157) which asserts True. SAT verdict: True (genuine same-side stack collision under SAT). The 30°/30°/150/157 same-side stack is **a different physical configuration** from the 30°/30°/50/132 false positive — same angles, different distances, different geometric reality. Without the verification probe, the new SAT code might have flipped a test assertion that should have stayed.

**Commit 4 — the structural-vs-inflation cone-coverage question.** The user reported the "Test surface extends outside projector cone" banner firing at θ_cam=0°, θ_proj=-41°, throw=149, WD=157. Visual inspection suggested the cone covered the part with room to spare. Two possibilities:

(a) The check is correctly identifying a feature point outside the cone that's hard to see visually.
(b) An over-sensitive check analogous to the AABB body-overlap bug.

Strategy chat's prediction (from grep-first analysis): (a). Unlike the AABB body-overlap (an over-approximation by construction), the cone-coverage check is a pure angular test — no inflation structure.

The diagnostic probe confirmed the prediction. Two of 121 sample points failed, each by exactly 0.40 mm — sub-millimeter hairline triggers at the FOV-patch corners under the tilted cone's 9:16 vertical wall at z=15 mm elevation. PROJECT_CONTEXT §13.7 already documented hairline triggers as feature, not defect.

**But the user asked: "in real life would we actually have even a very small region of the object not highlighted by projector?"** The answer: technically yes by 0.4 mm, but a real projector's gradual edge falloff covers that range. So the banner was technically correct and practically misleading.

Decision: 2 mm advisory tolerance on the projector-cone check. Camera prism stays exact (parallel-sided telecentric prism, no soft boundary).

**Commit 5 — Z-value catch in the ABSURDLY_LARGE_MM bump.** Strategy chat drafted the prompt to raise to (500, 500, 55) — the "55" from strategy chat's stale recollection of pre-sub-task-2.5 days. Halt-gate's bug-bait grep caught it: ABSURDLY_LARGE_MM's Z was already 120, locked in lockstep with WORKING_VOLUME_MM[2] by `test_z_cap_matches_absurd_z`. Setting Z=55 would have silently regressed sub-task 2.5 AND broken the invariant test.

The correct target was (500, 500, 120) — XY-only bump. Halt-gate proposed the correction, user confirmed, commit landed clean.

### Stage 4d follow-up diagnostic-pattern lessons

**Diagnostic-before-decision matured into the default workflow.** Every commit was preceded by a probe. The pattern got tighter than in Stage 4d's reactive sub-task-5.5 chain — strategy chat structured prompts around expected-evidence-needed, with "prediction on record" sections that explicitly stated what the probe would confirm and what it might overturn.

**Three predictions overturned, two confirmed:**

1. **Three-symptom unification (commit 1) — confirmed.** User push-back surfaced the single-root-cause hypothesis; probe confirmed.

2. **θ=15° vs θ=30° byte-identical recovery (commit 2 area) — overturned.** Strategy chat predicted byte-identical across angles inside the working envelope; the asymmetric sweep showed byte-identical for θ_proj 5-50° and structural divergence at 55°+. The bound discovery was the substantive finding.

3. **Body-overlap fix sufficiency (commit 3) — initial lean Option 3, overturned to Option 1.** Strategy chat first leaned smallest commit; probe ruled it out. Reflection on Option 2's body-body weak spot redirected to Option 1.

4. **Cone-coverage spill nature (commit 4) — confirmed.** Honest hairline trigger, not structural inflation.

5. **ABSURDLY_LARGE_MM Z value (commit 5) — overturned by grep, not by probe.** Strategy chat's prompt referenced Z=55 from stale memory. Halt-gate caught it before the edit.

**The summarize-back ritual matured.** Every halt-gate during the follow-up started with "grep-check the prompt's core assumption" — explicitly. Multiple prompt-assumption catches landed: the Z value (commit 5); the bug-bait 272/220 classification (commit 5); the at-risk same-side-stack test (commit 3).

### Stage 4d follow-up design conversation — parking-lot items for the next session

During the cone-tolerance work, the user surfaced a higher-order design observation. Seed: the "shape changes with angle" observation from commit 1, traced to phase-unwrap branch failures at >50° angles. User's framing: *"the object doesn't change shape when I move the camera in real life — it's supposed to represent real life — so why does the object change shape in the lab view when I change angle?"*

The honest answer: **what changes in the lab view isn't the object, it's the recovered measurement of the object.** The recovered surface is a math output that legitimately changes when angles change. The lab view conflates "what the camera sees" with "what the math produces from what it sees."

User's proposed resolution (refined across multiple turns):

1. **Lab view should default to showing the ground-truth FOV slice** alongside the hardware bodies. The recovered surface becomes an **opt-in toggleable overlay** drawn from the same origin in a contrasting color (translucent or wireframe, depending on pyqtgraph alpha-bug resolution). Both can be off, either can be on, or both visible simultaneously. Live updates as angle/distance sliders change. No xyz coordinate grid in lab view — that's the 4th tab's job.

2. **A new 4th tab "Recovered Surface"** next to STL Browser. Dedicated quantitative-comparison view containing:
   - Rotatable 3D view of the recovered heightmap
   - **Translucent (or wireframe) ground-truth overlay drawn from the same origin in a contrasting color**, both visible by default. Overlay constrained to the FOV-slice region, NOT the whole STL.
   - **x/y/z coordinate grid with labeled scales in mm** — unique to this tab.
   - Existing error stats panel migrates here.
   - Existing error-colormap overlay toggle migrates here.
   - Contract: input is a `(H, W) float64 mm` heightmap from any source — synthetic pipeline OR real hardware capture.
   - Known landmine: pyqtgraph 0.14.0 alpha-rendering bug may force wireframe overlay.

3. **Pipeline Stages 6th slot stays empty** as a future placeholder.

4. **Hardware coordinate readout.** Display camera and projector physical positions in world coordinates. Camera position = center of lens front face; projector position = center of projector lens exit pupil / front face (accounts for `PROJECTOR_LENS_X_OFFSET_MM = -6.5`).

5. **STL Browser panel swap.** Swap Panels 1 and 3 — windowed slice gets the big right real estate; whole-STL context becomes the smaller bottom-left view. Minimap stays.

6. **Web port as final design surface.** PyQt6 = reference implementation; web port = final design surface for larger screens and shareability.

7. **Smaller items:** extreme-angle warning banner (h/λ_eq > 2π threshold), load-time progress indicator, STEP file support, body-overlap design history preservation, console mojibake dash in `MSG_SURFACE_OUTSIDE_CONE`.

**The lab-view-vs-4th-tab design discussion was the most consequential parking-lot decision of the session.** Initial proposal was "lab view shows ONLY ground truth." User refined: "lab view shows ground truth by default with recovered surface as opt-in toggle; 4th tab shows both by default." The refinement preserves the live-comparison-while-adjusting-sliders use case AND gives the dedicated quantitative-comparison view its own home.

### Stage 4d follow-up architectural decisions worth carrying forward

- **Lift convention = visible-envelope minimum (PROJECT_CONTEXT §7.6 doctrine).** The Stage 4c global-mesh-minimum convention is gone.

- **Off-part contract in Browser mode = padded internally, masked externally (PROJECT_CONTEXT §7.7 doctrine).** Math layer remains agnostic.

- **Clip-detection tolerance philosophy (PROJECT_CONTEXT §7.8 doctrine).** Asymmetric by physical-boundary-softness: cone gets advisory tolerance, prism and body-overlap stay exact.

- **Diagnostic-before-decision as default, not exception.** Every commit was preceded by a probe.

- **Halt-gate grep-check-the-prompt is a hard ritual.** Stale strategy-chat memory propagates wrong values into prompts.

- **Test-suite progression prediction as a sanity check.** Each commit's halt-gate predicted the expected pass count.

- **PyQt6 = reference implementation; web port = final design surface.**

- **One commit per concept; no drive-by changes.**

- **The user's instinct to ask "are these three symptoms the same problem?" caught commit 1.** Pattern matches the Stage 4 "telecentric = vertical?" surfacing: when the user pushes on a framing strategy chat hasn't questioned, the framing is what's wrong.

---

## 7i. Stage 5 — Execution history (Lab-view + Recovered-Surface refactor, hardware-coordinate readout, cross-arm obstruction)

Tag: `stage-5-complete`. 271 tests passing. 11 commits (4d.2–4d.12) on `main`, plus the docs/tag close.

Stage 5 grew directly out of the Stage 4d follow-up parking lot (§7h). The commits are prefixed `Stage 5 (4d.X)` — the `4d.` numbering is a historical continuation of the Stage 4d sub-task sequence, but the stage itself is **Stage 5**. Hardware familiarization/integration shifted to Stages 6/7. The two-role workflow held throughout: this strategy chat drafted prompts and reviewed diffs; Claude Code implemented/tested/committed; the user was the gatekeeper and the visual verifier (every GUI-affecting commit had a live-launch eyeball before commit).

### Sub-task summary (commit by commit)

| # | Commit | One-line summary |
|---|---|---|
| 4d.2 | `68173e5` | **Lab-view ground-truth/recovered XOR toggle.** Two-radio exclusive selector; STL-mode scoped (disabled in Flat/Gaussian); defaults to ground truth in STL ("honest by default"). Error overlay render-suppressed (not state-mutated) when GT shown. 250 tests. |
| 4d.3 | `9fa6266` | **Labeled XYZ mm coordinate grid** (`coordinate_grid.py`). Pure `compute_axis_ticks` (nice-step 1/2/5) + thin `CoordinateGrid` GL class. Opaque dark-bg-legible labels; adaptive Z tick density + lateral offset for the short honest-scale Z axis. +27 tests. `scripts/stage5_grid_smoke.py`. |
| 4d.4 | `cff19e3` | **`RecoveredComparisonView`** (`comparison_view.py`) + **shared render core** (`surface_render.py`: `centered_coords`, `apply_heightmap`, `error_colors`, `ERROR_COLORMAP`). Solid recovered + translucent ground-truth. The pyqtgraph alpha bug did NOT reproduce on 0.14.0 / Qt 6.11.0 — §14 amended. SurfacePreview now calls the shared helper. +14 tests. |
| 4d.5 | `b385eb1` | **Wired comparison view into the 4th "Recovered Surface" tab** (`RECOVERED_TAB_INDEX=3`) + tab-local recovered/GT visibility checkboxes. Rides the existing `currentChanged` refresh. +6 tests. |
| 4d.6 | `eda7ec6` | **Error stats + colormap + colorbar migrated** off the left panel / 3D Scene tab onto the Recovered Surface tab. "Color by error" mode (recolors recovered, render-suppresses GT). `show_error_overlay` deleted from the 3D Scene tab. Error UI reparented for cross-tab isolation. +7 tests. |
| 4d.7 | `b6c6e2b` | **STL Browser panel swap.** Whole-STL+cyan-highlight → big right; windowed slice → small bottom-left. **REVERSE of parking-lot #5's wording** — the user's actual preference was whole-STL-context in the big panel. Layout-only; highlight stays bound to `_whole_stl_view`. +1 layout-lock test. |
| 4d.8 | `d42c29e` | **"Color by error" gated on "Recovered surface".** Untick recovered → color-by-error force-OFF + disabled (one cascade refresh); re-tick → re-enabled but stays OFF. +4 tests. |
| 4d.9 | `b6e2bbd` | **Numeric entry on all sliders.** Extended `LabeledFloatSlider`: read-only label → editable `QDoubleSpinBox`, bidirectional blockSignals-guarded sync. No step changes; off-grid snaps to nearest, out-of-range clamps, commit on Enter/focus-out. `value()/set_value()/valueChanged` contract preserved. +7 tests. |
| 4d.10 | `26b2a7c` | **Projector lens center anchored at origin-when-vertical.** Added the missing face-vertical offset + recess; body shifts by negative of the in-face offset so the LENS anchors on-axis (body hangs at +6.5,+17.5). `PROJECTOR_LENS_X_OFFSET_MM` → signed `ProjectorLensOffset(face_x=-6.5, face_vertical=17.5, recess=1.5)` NamedTuple (face-vertical SIGN UNVERIFIED; scalar alias kept). Cone helper gained `y_offset_mm`+`recess_mm`. Visualization-only. +4 tests, 3 updated. |
| 4d.11 | `abfbb3e` | **Hardware coordinate readout.** Pure `arm_lens_front_world(...)` → `{camera, projector}` lens-center world (x,y,z); extracted `_camera_cone_world`/`_projector_cone_world` (shared by `update_pose` + helper). "Hardware Coordinates" GUI group after Geometry (live in `_on_pose_changed`). CLI `scripts/hardware_coords.py`. Projector reads (0,0,~throw), camera (0,0,WD) vertical. +4 tests. |
| 4d.12 | `a266c8c` | **Cross-arm optical-obstruction advisory.** Banner-only 6th check: camera-in-projector-cone / projector-in-camera-prism. Extracted bounded predicates `_points_in_prism`/`_points_in_cone` (axial_max); coverage funcs call with axial_max=inf (behavior-preserving). Edge-sampling (7 pts × 12 edges) catches the 200 mm camera lens spearing the cone. Axial bound (0..throw / 0..WD) excludes behind-lens/beyond-surface. Cross-only pairing. +5 tests. |
| close | docs + tag `stage-5-complete` |  |

**Test suite progression:** 242 → 250 → 277 → … → 266 → 271 (the grid component added the largest single jump at +27; the count reflects new tests minus none removed).

### Stage 5 critical mid-execution discoveries

**The lab-view / recovered-surface split (4d.2 + 4d.5) — "honest by default."** The seed was the Stage 4d-follow-up parking-lot insight: the lab view conflated "what the camera sees" with "what the math produced." The resolution split it cleanly — the lab view defaults to ground truth (recovered as opt-in in STL mode only), and a dedicated 4th tab owns quantitative comparison. The XOR toggle is scoped to STL mode because Flat/Gaussian have no separate "ground truth vs recovered" story worth toggling. The error overlay is render-suppressed (not state-mutated) when ground truth is shown, so toggling back doesn't lose the user's error-view state.

**The translucent-primitive probe (4d.4) — settling the alpha bug before architecting around it.** The Stage 4d follow-up had flagged the pyqtgraph 0.14.0 alpha-rendering bug as a known landmine that might force a wireframe ground-truth overlay. Rather than design around the worst case, sub-task 1 ran a throwaway probe: a translucent `GLSurfacePlotItem` via `setGLOptions("translucent")` on the current stack (pyqtgraph 0.14.0 / Qt 6.11.0). **The bug did NOT reproduce** — `setGLOptions("translucent")` is the load-bearing call, distinct from the `alpha=0.5` color path that triggered the Stage 4d inversion. §14 was amended to record the non-reproduction. The comparison view was built so the render style is swappable to wireframe if the inversion ever returns on other hardware — but solid-translucent is the validated default.

**The solid-recovered / translucent-ground-truth decision (4d.4 + 4d.6).** Translucent-over-solid reads divergence well for *smooth* parts. The user observed it interpenetrates confusingly for *blocky/tall* parts where the two surfaces cross. Rather than replace it, the migrated error colormap (4d.6, "Color by error") is the complementary quantitative tool for exactly those cases — recolors the recovered surface by signed error (CET-D1 blue=under / red=over) and render-suppresses the GT overlay so the color field is unobstructed. The two views are deliberately complementary, both on the tab.

**The projector lens-offset correction (4d.10) — the missing face-vertical offset.** The headline geometry find of Stage 5. A read-only recon (run before any edit) established that the sim applied only the −6.5 mm face-X offset and was **missing the +17.5 mm face-vertical offset entirely** (the earlier recon found the projector lens-front landing at (−6.5, 0, throw) — note Y=0). The user's measured lens center on the Pico Genie's front face is 21 mm along face-X and 45 mm up face-vertical (recessed ~1.5 mm) — relative to the 55 mm face center, that's (−6.5, +17.5, 1.5). The correction anchored the LENS CENTER (not the body) over world (0,0) when vertical by shifting the body by the negative of the in-face offset.

The recon settled three things before the build:
- **Axis mapping.** At θ=0 the arm transform `T(0,0,d) @ R_x(π)` maps face-X → world +X, face-vertical → world **−Y**, optical → world −Z. The arm swings about world-Y (`R_y(θ)`), so the face-vertical offset stays purely in Y at every angle — anchoring at θ=0 anchors at all θ. (The user confirmed this live: the y-coordinate readout stays 0 as the arm swings.)
- **The "is the frame physically anchored?" discussion.** The user clarified the world frame is a deliberate *logical* convention (lens-straight-down → (0,0), stage → z=0) that will *become* the physical anchor when the new projector arrives and the rig is finalized. So the readout reports in this convention now and is the instrument to match the physical setup to it later. The face-vertical SIGN is left UNVERIFIED (the +17.5 → world −Y mapping reflects the sim's current orientation; confirm against the real projector at mount time). The projector is being replaced, so the offset becomes a one-line constant edit — hence the parameterized `ProjectorLensOffset` triple.
- **Blast radius — the user's worry that this would touch the recovered-object math.** The recon confirmed (and the user verified live) that the body/lens placement is **visualization-only**: the math pipeline reads slider angles, not mesh placement (`_build_geometry` builds `HybridGeometry` from `theta_*.value()`, never from the arm transforms). Moving the projector body 17.5 mm cannot change the recovered surface or pipeline stages. The only downstream effect is the projection cone re-centering (which makes the coverage banner fire *less*, an improvement).

**The obstruction-check insight (4d.12) — the user's observation while positioning hardware.** The user noticed that the existing checks caught bodies *touching* and surface-outside-cone *coverage*, but NOT one arm's hardware sitting inside the *other* arm's optical volume — e.g. the camera body falling within the projection cone, blocking the beam before it reaches the surface (seen live, photographed). A distinct failure mode from collision. The recon settled three design points:
- **Edge-sampling, not corner-only (correctness, not preference).** The 200 mm camera lens can spear the cone with all 8 corners outside but the middle inside — corner-only would silently miss the exact case the user observed. Edge-sampling (7 pts along each of the 12 box edges) catches it; both volumes are convex so interior edge samples are reliable. Cost ≈ the existing 121-pt coverage sample.
- **The along-axis bound (the subtle false-positive the recon caught).** The coverage volumes are unbounded along-axis (prism infinite, cone diverges past throw). Reused as-is, the check would false-fire on hardware *behind the camera* or *below the surface* — laterally inside the volume but not actually between lens and surface. The fix bounds the test to 0 ≤ s ≤ WD (prism) / 0 ≤ s ≤ throw (cone). Implemented by extracting the per-point INSIDE mask into bounded predicates; the coverage checks call them with `axial_max=inf` (behavior-preserving, locked by the existing coverage tests staying green).
- **Cross-only pairing.** Camera-vs-projector-volume and projector-vs-camera-volume, never an arm against its own volume (its own lens sits at the apex/origin and would always self-trigger).

### Stage 5 design conversation — the web port and what carries forward

The web port (parking-lot #6) is the next phase after stage close. The framing locked: **the PyQt6 GUI is the reference implementation.** Every UX target validated in PyQt6 across Stage 5 — the 4-tab layout (3D Scene / Pipeline Stages / STL Browser / Recovered Surface), the lab-view XOR toggle, the comparison view (solid recovered + translucent GT over a labeled grid + color-by-error mode), the hardware-coordinate readout, and the clip/coverage/obstruction advisories — becomes a requirement for the web port. The pure-NumPy math layer is reused or reimplemented to match; the visualization layer is rebuilt for the browser (Three.js or similar). Note the earlier "no Three.js embed inside PyQt6" rejection does NOT apply to the web port — the browser is the appropriate venue for browser-based 3D. Hardware integration (Stages 6/7) follows the web port.

### Stage 5 architectural decisions worth carrying forward

- **The 4-tab right pane is the reference UX** (3D Scene / Pipeline Stages / STL Browser / Recovered Surface). The lab-view-vs-Recovered-Surface split — live exploration vs quantitative comparison — is deliberate (PROJECT_CONTEXT §7.10). The lab view is honest-by-default (ground truth); the 4th tab is the home for "what the math produced vs what it should have."

- **`surface_render.py` is the shared render core.** The pyqtgraph axis/colors transpose quirk and the error-color normalization live in ONE place; `SurfacePreview` and `RecoveredComparisonView` both call it. Any new surface rendering (web port included) follows the same convention from this source.

- **The comparison-view pattern** (solid recovered + translucent GT over a labeled grid + color-by-error) is the validated quantitative-comparison UX. Translucent overlay for smooth parts; error colormap for blocky/tall parts where the surfaces interpenetrate — complementary, not either/or.

- **Visualization is decoupled from the math** (PROJECT_CONTEXT §7.11), confirmed and relied on in 4d.10. The web port's 3D can be rebuilt freely without touching the recovered-surface math.

- **The hardware-coordinate readout shares one pure helper for GUI + CLI** (`arm_lens_front_world`). It is the cross-check instrument for the hardware-anchoring phase. The CLI is tested to print the same numbers as the GUI panel — single source of truth.

- **Diagnostic-before-decision held throughout** (matured from Stage 4d). The translucent-primitive probe, the projector-geometry recon, and the obstruction-check recon each ran read-only *before* the build and each caught something that would have been a wrong commit — the missing face-vertical offset, the corner-vs-edge sensitivity, the axial-bound false positive.

- **The user's hands-on observation drove two of the four substantive Stage 5 features.** The hardware-coordinate readout and the obstruction check both came from the user actually positioning the hardware and noticing what the existing tooling didn't capture — the same pattern as the Stage 4d-follow-up parking lot. When the user is exercising the digital twin physically, the gaps they find are real.

- **One commit per concept; visual verification before commit.** Every GUI-affecting Stage 5 commit had a live-launch eyeball by the user before it was committed.

### Carry-forward flags for the hardware phase (Stages 6/7)

- **FACE-VERTICAL SIGN UNVERIFIED** (4d.10): confirm the projector lens's world-Y side against the real projector at mount time; flip `ProjectorLensOffset.face_vertical` if needed. Magnitude (17.5) and the anchoring behavior are correct regardless.
- **World frame = logical convention, physically anchored later.** Intended anchor: lens-straight-down → world (0,0), stage → z=0. Becomes physical when the new projector arrives and the rig is built. The hardware-coordinate readout reports in this frame and is the tool to match the physical setup to it.
- **Deferred mm-vs-pixel unit reconciliation** (unchanged): math layer = notebook pixel units; info panel = mm. Reconcile when real hardware arrives.
- **Camera/Projector protocols + mocks** still deferred to Stage 6/7.
- **Extreme-angle warning banner** deliberately parked (user's call): the >50° unwrap divergence is correct physics; a future advisory would just flag the regime.

---

## 8. Open Questions for Supervisor

Non-blocking — proceed on best assumptions and ask in parallel.

1. Is the upgraded projector telecentric?
2. ~~Simplified λ_eq formula for the hybrid case?~~ **Resolved at Stage 4 planning:** use Eq. 2-51's two-angle general form. Real hardware will also calibrate empirically against a step gauge per Chapter 4 §4.3.1.
3. Software post-correction or hardware pre-correction?
4. Number of phase-shift steps (4 vs. 8)?
5. Calibration artifacts available in lab?
6. ~~GUI framework preference?~~ **Resolved: PyQt6** (Stage 4 plan).
7. **Mount geometry decision:** what are the intended mounting angles for both camera and projector? The chapter's Fig. 4-4 shows symmetric arms (~15° each). Chapter 5 shows an asymmetric setup (camera vertical at 0°, projector at 60°). The user's preference suggested vertical projector, but that requires non-vertical camera for triangulation to work. Worth clarifying with the professor before committing physical mount geometry.
8. ~~**Stage 4b prep — physical dimensions to measure**~~ **Resolved during Stage 4b:** camera lens profile measured (stepped 200mm). Projector lens estimated (20mm dia × 5mm protrusion); refine when lab-accessible.

---

## 9. Theoretical Insights From the Walkthrough

### Additional insights added during Stage 1 walkthrough

- **The notebook's `phi1` vs `phi1_unwrapped` parallel structure** — `phi1` (analytical) is the ground truth; `phi1_unwrapped` (intensity → PSI → wrap → unwrap) is the simulated measurement.
- **Best-fit tilt absorbs both real tilt and a bit of curvature.**
- **Cell 14's K constant implicitly assumes a telecentric receiver.** No `capture()` function exists; the camera arm is treated as a perfect pass-through.
- **OpenCV is not needed for the fringe analysis math** — PSI, unwrap, tilt fitting, height conversion all live in NumPy.

### Additional insights added during Stage 3 walkthrough

- **The textbook's Eq. 4-6 has a sign typo.** Printed as `1/(1 − 2x·tan(θ)/a)`, but the `+u` form is correct.
- **Validation criteria for user-facing toggles should be informational, not gating.**
- **A test parametrization can technically pass without meaningfully exercising the parametrized variable.**

### Additional insights added during Stage 4 planning

- **The chapter's M is camera-side only.** Eq. 2-41 defines M as `l/b`. Projectors don't have an "M" in the chapter's framework.
- **`a` is fixed inside the projector** (DMD-to-lens distance, mechanical).
- **For telecentric cameras, M and distance are independent within the working-distance range.**
- **The symmetric assumption (Fig. 4-4) is expository, not required.**
- **A slider that doesn't affect the science view is still valuable** if it serves a real lab-design purpose.
- **Telecentric ≠ vertical mount.** Most important Stage 4 discovery.
- **Both arms vertical = no triangulation = no height info.**

### Additional insights added during Stage 4a execution

- **The math layer and the info panel use different unit systems.** Math layer is in notebook pixel-space; info panel is in mm-space hardware values. Reconciliation deferred to Stage 5/6.
- **The code's `equivalent_wavelength()` returns `λ_textbook / (2π)`, not the textbook's λ_eq directly.** No physics bug, only naming.
- **Self-cal recovery is structurally λ-cancellation-immune.** The pipeline tests cannot catch a factor-of-2π scaling bug in λ_eq.
- **Pyqtgraph documentation drift is a real maintenance risk.**

### Additional insights added during Stage 4b execution

- **Telecentric optics means rectangular prism, not cone, for the viewing volume.**
- **DLP throw distance is the focus plane, not a light cutoff.**
- **AABB overlap on rotated bodies is over-sensitive but acceptable for advisories.** **Stage 4d follow-up update:** "acceptable for advisories" turned out to be wrong at ordinary slider ranges — measured false positives of 22.3 mm and 31.6 mm. The §13.8 deferred-OBB note was closed by commit `e3c14bb` with full SAT replacement. See §7h.
- **Disc-edge math for lens-vs-plane collision.** At tilt θ, lowest world-z is `WD·cos(θ) − r·sin(θ)`.
- **11×11 sampling is enough.** ~250µs/tick.
- **Strict-correctness checks beat tolerance-based checks for advisory triggers.** **Stage 4d follow-up refinement:** the strict-correctness rule is refined into a physical-boundary-softness asymmetry. Cone (diverging beam with real edge falloff) gets a 2 mm advisory tolerance. Camera prism (parallel-sided telecentric prism) stays exact. Body-overlap (geometric intersection) stays exact. See PROJECT_CONTEXT §7.8.

### Additional insights added during Stage 4c execution

- **The "lift to z=0" semantic for heightmaps depends on what z=0 means physically.** Flat/Gaussian sit naturally at z=0; STL files arrive with arbitrary world-origins. The lift reference at Stage 4c sub-task 2 was the global mesh-Z minimum across all vertices. **Stage 4d follow-up update:** reset to the visible-envelope minimum (the lowest camera-VISIBLE point). The Stage 4c convention put a closed solid's full diameter above the stage; the visible-envelope convention puts the visible base flush with z=0, matching what a real FPP camera would measure. See PROJECT_CONTEXT §7.6 and §7h.
- **Projected-barycentric rasterization scales better than z-buffer search on dense CAD STLs.**
- **Rescale and truncate distort the geometry being measured.** A digital twin that lies about what it's measuring is worse than one that refuses to measure.
- **The math-layer pixel-space grid (48×64 mm) and the hardware FOV (68×55 mm) are not yet reconciled.** **Reconciled in Stage 4d sub-task 1.5:** math grid bumped to (550, 680) = exact 68×55 mm patch.
- **Conda solver behavior matters more than package source-code purity.**
- **GUI tests don't have to launch real dialogs.** Monkeypatching works.
- **Halt-and-confirm gates catch design-frame contradictions, not just technical ones.**

### Additional insights added during Stage 4d follow-up execution

- **Three symptoms with the same root cause look like three independent bugs until you ask the question.** The floating-part appearance, the 15 mm FOV-bbox-boundary step, and the angle-sensitive recovered shape were all consequences of the global-mesh-Z-minimum lift convention. Lesson: when multiple symptoms appear simultaneously after the same code change, the null hypothesis is "they share a cause," not "they're independent."

- **Working envelope is bounded; outside the bound, recovery diverges by design.** Byte-identical recovery from θ_proj 5° to 50°; structural divergence at 55°+. h/λ_eq > 2π is the unwrap-failure threshold; real FPP hardware fails at the same threshold. The fix is not "make recovery work at >50°" (impossible without 3D unwrap or temporal phase unwrapping); the fix is "warn the user when they enter the failure regime."

- **"Smallest commit" is the wrong default when the bigger commit closes a future false-positive surface.** Option 3 was the smallest body-overlap fix and didn't work. Option 2 worked at tested poses but left a body-body weak spot. Option 1 (full SAT) was the biggest commit and closed both weak spots. Choose the fix that doesn't require revisiting.

- **Physical-boundary-softness justifies asymmetric tolerance.** The projector cone's boundary is sharp in the math but soft in reality (gradual edge falloff). The camera prism's boundary is sharp in the math AND in reality. The body-overlap test's boundary is sharp in both. Tolerance only makes sense for the first case.

- **Diagnostic probes are not extra work; they replace wrong-fix cycles.** Five probes during the follow-up, three of which overturned strategy chat's prediction. Each overturned prediction would have been a wrong commit if the probe hadn't run.

- **The user's framing question can be more diagnostic than any test.** "Are these three symptoms the same problem?" (commit 1). "In real life would we actually have a small region not highlighted?" (commit 4). "But it's supposed to represent real life, so why does the object change shape when I change angle?" (parking lot). Each question reframed strategy chat's understanding of the problem.

---

### Additional insights added during Stage 5 execution

- **The lab view conflated "what the camera sees" with "what the math produced."** The fix wasn't a bug fix — it was a UX split: lab view defaults to ground truth (honest-by-default), a dedicated 4th tab owns quantitative comparison. The recovered surface legitimately changes with angle because it's a measurement, not the object.

- **A "known landmine" is worth a 10-minute probe before you architect around its worst case.** The pyqtgraph alpha bug was carried forward from Stage 4d as "may force wireframe." A throwaway translucent-primitive probe showed it does NOT reproduce via `setGLOptions("translucent")` on the current stack — so the solid-translucent comparison view was built directly, no wireframe fallback needed (kept swappable just in case).

- **Visualization placement and the recovered-object math are fully decoupled.** Moving the projector body 17.5 mm to anchor its lens at the origin cannot touch the recovered surface — the math reads slider angles, not mesh placement. This decoupling is what made the projector-geometry correction safe, and it's the reason the web port can rebuild the 3D layer freely.

- **A measured offset can be physically honest AND a frame mismatch at the same time — the user decides which.** The projector lens sits −6.5 mm off its body centerline; "projector straight down" landing at (−6.5, …) is physically correct for the Pico Genie. Whether the *frame* should redefine that to (0,0) is a mounting decision, not a code decision — and it's moot because the projector is being replaced. The readout reports the honest position; the constant changes when the hardware does.

- **Bodies not touching ≠ optical paths clear.** The user caught (by positioning hardware and looking) that one arm can sit inside the other's optical cone/prism without any body collision — blocking the beam or line of sight. A distinct failure mode the collision and coverage checks both missed.

- **Edge-sampling vs corner-only is a correctness question for long thin boxes.** A 200 mm lens can spear a convex volume with every corner outside but the middle inside. For an obstruction check this isn't a nicety — corner-only silently misses the exact case that motivated the feature.

- **Reusing an unbounded volume test for a bounded question introduces false positives.** The coverage volumes extend infinitely along-axis; an obstruction check must bound to the lens→surface segment or it fires on hardware behind the camera / below the surface. Extracting a bounded predicate (and routing coverage through it with `axial_max=inf`) keeps one source of truth without changing coverage behavior.

### Additional insights added during Stage 6 B.3b execution

- **A believable STL part at honest mm scale is sub-Nyquist by design.** Mm heights at 0.1 mm/px scale per-pixel gradients down 10× vs the math-pixel dome — a real steep part would need *multi-metre Z within a 68×55 mm FOV* to cross the wall. So the STL is the **defect-detection** story (§7.14), not the beyond-Nyquist dynamic-range headline. (Part B's sharp machined edges *do* nick f>0.5 over ~0.72% of frame, but that's an edge artifact — which is why the dynamic-range readout is gated off for STL.)
- **A telecentric camera at an angle has no perspective bias.** Camera tilt is a triangulation angle (θ_camera in the two-angle λ_eq, Eq. 2-51), NOT a new bias term. So a projector-at-0°/camera-at-angle placement does not "shift the bias source" — the non-telecentric projector remains the sole bias the inverse grating corrects. This **corrected an earlier PROJECT_CONTEXT §2 note** that had flagged a bias-arm-inversion concern on a wrong premise.
- **FOV margin for camera tilt.** With the camera tilted, the draggable object-FOV grid should be shrunk INSIDE the camera's true 68×55 mm capture footprint to leave room for the tilt (margin ~ `object_height × tan θ_camera`). A coupled future task with the projector swap.

## 10. Project Conversations Note

- User had a friend building a separate **Three.js 3D simulation** of the lab geometry. The Three.js work is **complementary**, not duplicative. The user **explicitly rejected** embedding the Three.js work into the Stage 4 GUI.
- User added a virtual representation of the test object with live sliders during Stage 4a. The intermediate-stages viewer (task 4d) was added based on the user's professor's feedback.
- User added a **test-surface library** (`src/test_surfaces.py`) as part of Stage 4a task 1. Initially 5 surfaces; reduced to 2 (flat, Gaussian) in Stage 4c sub-task 1. STL files joined via `src/stl_loader.py` as a peer module.
- **STL import for arbitrary specimens delivered in Stage 4c.** Math layer untouched. Stage 4c supports specimens that fit the working volume; larger parts supported by Stage 4d's STL Browser via windowed FOV selection.
- User clarified during Stage 3 and reaffirmed in Stage 4 planning that **the chapters in the reference folder are the math basis for the inverse fringe projection method, not a template for a thesis the user is writing.**
- User wants **the GUI to be updatable with real hardware specs once they arrive.** Most important Stage 4 acceptance criterion.
- **User raised wanting to mount projector vertical (per professor preference).** Both-angles-as-sliders design supports this exploration.
- **User caught a near-miss at Stage 4b docs close.** Strategy chat initially drafted updated PROJECT_CONTEXT.md and CONVERSATION_SUMMARY.md from chat memory alone, without reading the existing 600-line files. User caught it with "did you check the existing files first?" — saving the project's Stage 0-4a history from being silently erased. **The Stage 4d follow-up docs-close phase re-applied this discipline:** strategy chat read the full PROJECT_CONTEXT.md (1031 lines) and CONVERSATION_SUMMARY.md (987 lines) end-to-end before writing the replacements. No reconstruct-from-memory; full read-pass first.

---

## 11. Resolved During the Conversation

- Identified all hardware (camera, lens, projector models)
- Confirmed system is **hybrid in lens type** (telecentric viewing lens, non-telecentric projector lens); arm angles are independent of lens type
- Confirmed inverse grating method (§2.3.4.3 / Chapter 4) is the project's chosen approach
- Measured projector lens position; ~0° vertical optical offset confirmed
- Measured camera lens physical profile (Stage 4b): stepped 3-section, 200mm total length
- Computed practical FOV, pixel pitch, magnification numbers
- Identified the gap in the existing notebook (missing `project()` function) — **closed in Stage 1**
- Established that hardware-free development is the right starting approach
- Built a roadmap (Stages 0–6)
- **Stage 0, Stage 1, Stage 2, Stage 3, Stage 3.5, Stage 4a, Stage 4b, Stage 4c, Stage 4d, and Stage 4d follow-up completed.**
- Validation philosophy formalized: simulation-only validation has fundamental limits.
- **Stage 4 plan locked at the strategy-chat level.** Five sliders + surface dropdown, locked values, build sequence (3.5 → 4a → 4b), 3D viewer backend (PyQtGraph), resolution (~~480×640~~ → (550, 680) post-Stage-4d-sub-task-1.5), MockCamera/Projector deferred.
- **Stage 3.5 pre-task executed:** math layer upgrade to two-angle λ_eq. Commit `658f331`.
- **Stage 4a executed:** 7 task commits + close. Tag `stage-4a-complete`. 70 tests passing.
- **Stage 4b executed:** 8 task commits including 1 reset + close. Tag `stage-4b-complete`. 143 tests passing.
- **Stage 4c executed:** 4 sub-task commits + close. Tag `stage-4c-complete`. 142 tests passing.
- **Stage 4d executed:** 9 sub-task commits + close. Tag `stage-4d-complete`. 181 tests passing.
- **Stage 4d follow-up executed:** 5 focused commits, all unpushed pending docs+tag+push at session close. (1) `9480b94` STL lift convention reset to visible-envelope minimum. (2) `fb19e0c` off-part edge-extend + masked recovered output. (3) `e3c14bb` SAT body-overlap; closes §13.8 deferred-OBB note. (4) `079cde4` 2 mm advisory tolerance on projector-cone coverage (camera prism stays exact). (5) `48efdc4` ABSURDLY_LARGE_MM raised to (500, 500, 120). 184 tests passing.
- **λ_eq naming convention clarified** during Stage 4a task 4c. Code's `lambda_eq` = `λ_textbook / (2π)`; no physics bug.
- **Stage 4b redesigned** from a "separate lab view" to a "unified 3D scene."
- **Distance slider semantics locked:** sliders report lens-front to surface (optics convention).
- **Z_EXAGGERATION locked at 1.0** (honest scale). **Made explicit doctrine in Stage 4d.**
- **Surface-vs-lens contact checks dropped** as unreachable in practice.
- **FOV/cone coverage tests upgraded** from 2D z=0 footprint to 3D point-in-volume. **Stage 4d follow-up refinement:** projector cone gets 2 mm advisory tolerance; camera prism stays exact; body-overlap upgraded from AABB to SAT.
- **Tilt/step/sphere surfaces deleted in Stage 4c sub-task 1.**
- **Gaussian amplitude slider cap tightened 100→55 mm in Stage 4c**, then raised 55 → 120 mm in Stage 4d sub-task 2.5.
- **STL loader written as pure-NumPy peer of `test_surfaces.py`.** Projected-barycentric rasterization, per-pixel max-z upper envelope. Lift convention: **visible-envelope minimum** (the lowest camera-VISIBLE point) — placed in Stage 4d follow-up commit `9480b94`, replacing the Stage 4c global-mesh-Z-minimum convention. Math layer doesn't know STL exists. Stage 4d added `load_stl_heightmap_full_scale` as a sibling for Browser mode.
- **`numpy-stl` installed via pip block, NOT conda-forge.** Rule documented in `environment.yml`.
- **Stage 4c sub-task 4 design pivot.** Sub-task 4 collapsed from ~700 lines of code to a 24-line text edit; the Browser became Stage 4d's headline.
- **Math grid reconciled to camera FOV in Stage 4d sub-task 1.5.** `SURFACE_SHAPE (480, 640) → (550, 680)`.
- **Pyqtgraph 0.14.0 alpha-rendering bug discovered and documented (Stage 4d sub-task 5.5).** Workaround: alpha=1.0.
- **Lab view shows only the committed FOV slice (3D mesh with depth).** **Stage 4d follow-up amendment (parking lot for next session):** lab view will be refactored to default to ground-truth FOV slice display with the recovered surface as an opt-in toggleable overlay; a dedicated 4th tab will host the quantitative comparison view with translucent ground-truth overlay over recovered surface + xyz coordinate grid + migrated error stats.
- **§13.8 deferred-OBB note closed in Stage 4d follow-up commit `e3c14bb`.** SAT (Separating Axis Theorem) replaces assembly-AABB. Strict no-epsilon separation.
- **Stage 4d follow-up parking lot for next session (lab view + recovered surface refactor):** (1) lab view defaults to ground-truth FOV slice + opt-in recovered overlay toggle; (2) new 4th tab "Recovered Surface" with translucent (or wireframe) ground-truth overlay + xyz coordinate grid in mm + migrated error stats and overlay; (3) Pipeline Stages 6th slot stays empty as future placeholder; (4) hardware coordinate readout (camera and projector lens-front-face-center positions in world coords); (5) STL Browser panel swap (windowed slice → big right; whole-STL context → small bottom-left); (6) web port as final design surface (PyQt6 = reference implementation); (7) smaller items: extreme-angle warning banner (h/λ_eq > 2π threshold), load-time progress indicator, STEP file support, body-overlap design history preservation, console mojibake dash.

---

## 12. Tone & Style Notes

The user prefers:
- **Short concrete answers** over long expositions
- Step-by-step physical reasoning, not equation walls
- Honest disagreement when something's hand-wavy
- One thing at a time
- Practical code suggestions kept minimal

The user pushes back when something feels redundant or tautological. This is a strength — Stage 1 ended up with a smaller, cleaner validation suite than originally proposed because of it, Stage 3 collapsed from three sub-tasks to one for the same reason, and Stage 4's slider list went through five false starts before settling on the right shape. Strategy chat should default to less, not more.

The user also says when they don't understand something. When that happens, strategy chat should **simplify, not double down on technical accuracy.** Long technical explanations are the wrong response to "I don't get this" — shorter answers, more analogy, fewer equations.

**The user is also good at asking questions whose answers force the strategy chat to catch its own mistakes.** The "telecentric = vertical?" question that surfaced Stage 2 Decision 3's hidden assumption was an example. So was the lab-view redesign question during Stage 4a planning. The Stage 4b vertical-spill FOV bug was another. **The Stage 4d follow-up extended this:** the user's three-symptom-one-cause hypothesis (commit 1) and the lab-view-vs-recovered-surface design question (parking lot) both reframed strategy chat's understanding of the problem. Strategy chat should treat user pushback as a diagnostic, not as resistance.

**The Stage 4b docs near-miss.** At Stage 4b close, strategy chat drafted updated docs from working memory rather than reading the existing 600-line files. User caught it. **The Stage 4d follow-up docs-close phase re-applied this discipline:** strategy chat re-read the full PROJECT_CONTEXT.md (1031 lines) and CONVERSATION_SUMMARY.md (987 lines) end-to-end before writing the replacements. The user explicitly confirmed the read-pass before the artifact drafts started.

---

## 13. Working Model with Claude Code (Refined Through Stages 2, 3, 3.5, 4a, 4b, 4c, 4d, 4d follow-up, and 5)

The handoff pattern that worked across all stages (Stage 2's six tasks, Stage 3's two tasks, Stage 3.5, Stage 4a's seven tasks, Stage 4b's eight tasks including the reset, Stage 4c's four sub-tasks, Stage 4d's nine sub-tasks, the five follow-up commits, and Stage 5's eleven commits):

1. **Strategy chat (this assistant) drafts the prompt.** Includes the architectural constraints, the exact tests to write, and the binding decisions Claude Code shouldn't relitigate. Prompts go in fenced ``` code blocks for the user's copy button.
2. **User reviews and pastes into Claude Code (terminal).**
3. **Claude Code summarizes back what it understands before writing code.**
4. **Claude Code implements, runs tests, commits.** One module per commit. Surfaces deviations from spec inline. Magnitude/numeric sanity checks before commit when the math output is user-visible.
5. **User pastes Claude Code's diff + test output back to strategy chat for review.**
6. **User decides on adjustments.**

Belt-and-suspenders verifications the user does in their own terminal before any destructive operation:
- Independent verification of git rewrites with own queries.
- Confirmation that working-tree files match expectations after history operations.

### Stage 3 refinement: prompts shrink when the deliverable is reframed

During Stage 3, the user's reframe ("validation is informational, not gating") collapsed two of three roadmap sub-tasks. Strategy chat should challenge the framing of upcoming tasks before drafting prompts.

### Stage 4 planning refinement: false starts get surfaced and corrected before code

Stage 4 planning produced five named false starts before settling on the final slider list. Each was caught in strategy chat, **before** any prompt went to Claude Code. The savings vs catching these post-implementation are real: each false start would have been a partial GUI rewrite if it had landed in src/.

The most important catch was the "telecentric = vertical camera" assumption that had been baked into Stage 2 Decision 3 for the entire project's history. It wasn't caught until Stage 4 planning, when the user kept pushing on "what about projector angle / both vertical / camera tilt?" The pattern: when the user repeatedly asks the same question framed differently, strategy chat should look harder rather than repeat the same answer.

### Stage 4a refinement: summarize-back catches real failures before commits

Two times during Stage 4a, Claude Code's "summarize back before coding" + pre-commit sanity checks caught issues that would have shipped wrong:

- **Task 4 unit mismatch.** Pre-commit magnitude check found recovery ~3000× inflated. Claude Code stopped, surfaced the issue with three resolution options, and user chose option 1 (notebook pixel-units).
- **Task 4b/4d colormap availability.** Both tasks initially specified pyqtgraph colormaps that turned out to not be bundled with version 0.14.0. Claude Code probed the installed colormaps first and substituted available alternatives.

The pattern: **specs from strategy chat are first drafts, not contracts.** Claude Code's job includes catching the gaps. When it does, surfacing them mid-execution is the right move.

### Stage 4a refinement: scope-creep is OK when it's the user's professor

Task 4d (pipeline stages viewer) was not in the original Stage 4a plan. It was added after the user's professor asked to see intermediate stages. Strategy chat's instinct was to defer; the user's correction was to fold it into Stage 4a. The right call. Lesson: external feedback can justify mid-stage scope additions if the architecture makes the addition cheap.

### Stage 4b refinement: interactive GUI verification finds bugs unit tests miss

Stage 4b's clip-detection went through two iterations of user-caught geometry bugs that all unit tests passed: the unreachable surface-vs-lens contact check (reverted) and the vertical-spill FOV bug (rewritten as 3D point-in-volume). In both cases the unit tests were correct in what they tested — but they tested the wrong things.

The pattern: **for geometry code, interactive GUI testing is a load-bearing verification step, not an extra.** Unit tests verify the math is correct in the parameter regimes it's tested in; the GUI explores the parameter regimes a real user can reach. **The Stage 4d follow-up was the most aggressive application yet:** the entire 5-commit pass came from interactive GUI review finding bugs that the 181-test suite had passed silently (the lift convention, the off-part padding interaction with phase unwrap, the body-overlap false positives, the cone hairline triggers).

### Stage 4b refinement: revert preserved in history, not rebased

When commit c53dd36 (surface-vs-lens contact check) was reverted by 20d6771, strategy chat suggested keeping both commits visible in history rather than `git reset --hard`. Rationale: the lesson "validate the bug is triggerable before adding the check" is more useful preserved as a visible reset than hidden by a rebase. Buried-in-rebase lessons are forgotten lessons.

### Stage 4b refinement: smoke-test capture protocol matters

The Stage 4b smoke-test protocol (programmatic GUI launch + framebuffer capture, gated by user greenlight, one-process-per-render) became load-bearing during sub-task 4. One-process-per-render: a single-process loop trying to render multiple poses leaves all-but-first framebuffer blank. Banner state is verified programmatically because banners don't appear in `grabFramebuffer` captures.

### Stage 4 fresh-session bootstrap

When a new strategy chat or Claude Code session starts after a stage closes:

- Strategy chat: re-upload latest PROJECT_CONTEXT.md and CONVERSATION_SUMMARY.md.
- Claude Code: open a fresh terminal. First prompt: "Read PROJECT_CONTEXT.md and CONVERSATION_SUMMARY.md. Summarize back what we're building, where we are, and what's binding for [Stage X]. Don't write code yet."

The two .md files carry all the context.

### Stage 4c refinement: design-frame contradictions caught by halt-gates

Stage 4b's halt-gate doctrine framed halts as catching **technical** contradictions. Stage 4c sub-task 4 added a new category: **design-frame** contradictions. The Rescale/Truncate/Cancel dialog was technically correct — it would have implemented cleanly. The frame was wrong: rescale and truncate distort the geometry being measured. The halt-gate caught this because the user pushed back on practicality. Listening is part of the protocol.

### Stage 4c refinement: environmental dependencies fight back

Stage 4c hit one full env-corruption incident in sub-task 2: a single `conda install -c conda-forge numpy-stl` dragged in a duplicate numpy + MKL/BLAS/LAPACK stack. Recovery took ~45 minutes (revision rollback + pip reinstall numpy + VS Code kernel coordination + typing_extensions collateral + final pip install).

Two protocol notes carried forward:
1. **Mixed conda + pip envs have a strict rule:** whichever package manager owns numpy owns every new dependency.
2. **Claude Code's "won't kill processes I didn't start" discipline is correct.** Claude Code surfaced the PIDs with their command lines, recommended Option A (close the notebook), and waited for the user.

### Stage 4c refinement: smoke script is the evidence trail

Stage 4b established the smoke-test capture protocol; Stage 4c extended it into a versioned artifact. `scripts/stage4c_smoke.py` was committed in sub-task 1 with 3 modes and grew to 4 modes (added STL) in sub-task 3. Pattern that will continue: every GUI-touching sub-task adds or extends a smoke mode. The script lives in version control.

### Stage 4c refinement: halt-gate output formatting

Three Stage 4c halts followed the same output format: numbered ambiguities, each with the choices laid out, Claude Code's lean stated, rationale brief. This format made strategy-chat review fast. Pattern to lock in: halt-gate output should be **numbered, with options stated explicitly, with Claude Code's pick named**. Open-ended halts ("I'm not sure how to proceed") are worse than picky halts ("Here are three options, I lean B, please confirm").

### Stage 4b close: docs-update protocol clarified

User updates PROJECT_CONTEXT.md and CONVERSATION_SUMMARY.md manually at stage close. Strategy chat drafts the updates — but **must read the existing files first** to preserve prior-stage content. Strategy chat memory of "what this chat discussed" is not a substitute for "what the files actually contain."

### Stage 4c close: docs delivered as files, not pasted inline

User preference clarified at Stage 4c close: docs updates are delivered as **complete, openable files**, not as inline code blocks the user has to copy-paste-stitch. Strategy chat generates the updated files in `/mnt/user-data/outputs/`, presents them, and the user opens them in VS Code and replaces the originals. Pattern for all future stage closes.

Push and tag happen together at end of stage:

```
git tag stage-Xx-complete
git push origin main
git push origin stage-Xx-complete
```

(No co-authored-by trailers.)

### Stage 4d refinement: diagnostic-prompt-before-decision

The biggest working-model lesson of Stage 4d landed in sub-task 5.5's maroon-vs-cyan investigation. Strategy chat made two wrong recommendations in a row before the right diagnosis emerged. Each wrong recommendation cost a code cycle. The pattern that emerged:

**When strategy chat catches itself about to recommend a decision built on guesses about library internals, write a read-only diagnostic prompt for Claude Code to investigate before recommending anything.** Evidence drives the next recommendation, not strategy-chat speculation.

Two specific failure modes the lesson is designed to catch:

1. **Confident-sounding recommendations built on guesses about library behavior or unread code.** When strategy chat notices "I'm not sure what pyqtgraph 0.14.0 actually does here, but I think..." — that's the signal to write a diagnostic prompt instead of finishing the sentence.

2. **Treating "make the symptom go away" workarounds as equivalent to fixing the underlying bug without diagnosing it.** The first two recommendations in sub-task 5.5 were both symptom-mitigation attempts. The user's intervention forced the investigate-first discipline.

The pattern was internalized by sub-task 6: when strategy chat wrote "the lab view currently doesn't show the FOV at load time," halt-gate summarize-back grep-traced the actual call chain and found that strategy-chat's claim was false. The grep-first-claim-second discipline that sub-task 5.5 hammered home applied cleanly to sub-task 6's planning.

**The Stage 4d follow-up made this the explicit default.** Every fix was preceded by a read-only diagnostic probe. Three out of five probes overturned strategy chat's prediction. The probes' aggregate cost was lower than the cost of the avoided wrong commits would have been.

### Stage 4d refinement: visual review during sub-tasks beats deferring to stage close

Two sub-tasks (4 and 5) had screenshot reviews that caught issues mid-execution and fixed them in the same sub-task rather than punting to a later cleanup. The reasoning: a visual issue with a quantifiable diagnosis is cheaper to fix in the active sub-task than to remember and re-context later. The smoke captures are load-bearing verification, not extra.

**The Stage 4d follow-up extended this principle to the limit:** the entire 5-commit pass was hands-on visual review finding bugs that programmatic smoke tests had silently passed. Five fixes from a single review session. Pattern that should continue for every stage close: launch the GUI, exercise real-world inputs, catch what the test suite couldn't.

### Stage 4d refinement: half-step sub-task naming

Stages 4a and 4b used sequential sub-task numbering. Stage 4c introduced sub-task 4's mid-stage pivot. Stage 4d formalized **half-step sub-task naming** for mid-stream additions:

- Sub-task **1.5** (math grid reconciliation) landed between 1 and 2. Planned and executed in that order.
- Sub-task **2.5** (Z cap raise) was planned to land between 2 and 3 but landed AFTER 3 because the user raised it during sub-task 3 planning.
- Sub-task **5.5** (Panel 1 FOV highlight overlay) was an in-stage addition surfaced during sub-task 5 review.

The numbering records the **logical neighborhood** of the addition, not necessarily execution order. When the two diverge, the commit body notes the mismatch.

### Stage 4d refinement: prompt-assumption grep-discipline

Three prompt-assumption catches during Stage 4d halt-gate summarize-back:

1. Sub-task 2.5: prompt said "55 doesn't appear in src/stl_loader.py" — appears at lines 23 and 185.
2. Sub-task 2.5: prompt omitted `scripts/stage4c_smoke.py` from in-scope-to-edit — has hard-coded `amp_max == 55.0`.
3. Sub-task 6: prompt said "lab view doesn't show the FOV at load time" — does via `_open_stl_dialog`'s implicit refresh chain.

**The Stage 4d follow-up tripled down on this discipline:** halt-gate summarize-backs explicitly start with "grep-check the prompt's core assumption." Three more catches landed during the follow-up: the Z value in commit 5 (prompt said 55, code already had 120); the bug-bait 272/220 classification in commit 5; the at-risk same-side-stack test in commit 3 (strategy chat assumed SAT would flip the assertion; SAT-verification probe showed it stayed True for the genuine collision).

The discipline: **when strategy chat writes "X doesn't appear in module Y" or "the system currently doesn't do Z," that's a claim about state strategy chat can't verify.** The halt-gate's job is the verification. The lesson is to flag those claims explicitly in the prompt as "halt-gate item: verify whether X" rather than asserting them and hoping.

### Stage 4d refinement: pyqtgraph 0.14.0 quirks pile up — document them, don't re-derive

Stage 4d added two new pyqtgraph 0.14.0 quirks to PROJECT_CONTEXT §14:

1. **Alpha-rendering bug.** `GLSurfacePlotItem` with `alpha < 1.0` produces inverted-complement colors. Workaround: alpha=1.0.
2. **Sibling-GLSurfacePlotItem GL state hazard.** Two `GLSurfacePlotItem`s in one view with different `a_color` GL paths are unsafe. Workaround: both use the constant-attribute path via `setColor()`.

These add to the earlier Stage-4-collected quirks. The pattern: pyqtgraph 0.14.0 has enough sharp edges that the project will keep finding new ones; document each one with the diagnostic chain and the workaround so future sub-tasks don't re-derive the discovery.

### Stage 4d follow-up refinement: the prompt-and-context budget for end-of-session docs

The Stage 4d follow-up docs-close phase confirmed the protocol locked in at Stage 4c close: full files in `/mnt/user-data/outputs/`, the user opens them in VS Code, replaces the originals. **The follow-up added one explicit step before drafting:** strategy chat MUST read the existing files end-to-end before generating the replacement. No exceptions. The user explicitly confirmed the read-pass intent before the artifact drafts started.

The read-pass surfaced things strategy chat would have gotten wrong from memory: the existing file's section structures, the specific table column formats, the cross-reference patterns between sections, the project's preserved-history conventions (Stage 4b reset commits, Stage 4c sub-task 4 pivot rationale). All of these flow through to the new file's structure. Working from memory would have produced a clean-but-divergent file; reading-then-writing produced a file that maintains the project's documentation idiom across the transition.

The read-pass takes time and tool calls. Strategy chat should budget for this explicitly at every stage close: re-read both files end-to-end, then write replacements. The cost is reasonable; the alternative (re-deriving project state from memory) is the failure mode Stage 4b nearly hit.

### Stage 4d follow-up refinement: the user's pivot signals are diagnostic

Multiple times during the follow-up, the user pivoted strategy chat's direction with short reframing questions:

- *"I think these are all the same problem, can you double-check?"* (commit 1) → three-symptom unification probe.
- *"In real life would we actually have even a very small region of the object not highlighted by projector?"* (commit 4) → 2 mm tolerance decision instead of leaving the hairline trigger as documented-feature.
- *"The object doesn't change shape when I move the camera in real life — so why does the object change shape in the lab view when I change angle?"* (parking-lot conversation) → the lab-view-vs-recovered-surface refactor framing.
- *"Do whatever you think is best."* (commit 3, Option 1 vs Option 2) → strategy chat reconsidered the body-body weak spot and escalated from medium to full fix.

Each pivot reframed the problem strategy chat had been solving. The lesson: when the user pushes back with a framing question (not a clarification question), strategy chat should treat it as a diagnostic that something about the current framing is wrong. The right response is to investigate, not to defend the current framing.

This is the same pattern as Stage 4's "telecentric = vertical?" surfacing and Stage 4c sub-task 4's dialog pivot. It's now firmly established as a working-model invariant: **user framing questions are diagnostic; treat them accordingly.**

### Stage 4d follow-up refinement: tag and push only at stage close, even for follow-ups

The five follow-up commits all land unpushed on `main` between `stage-4d-complete` (existing tag at base) and the eventual `stage-4d-followup-complete` tag at session close. The pattern matches the rest of the project: push only at stage close, never per-commit. The follow-up is its own stage close even though the original Stage 4d already had one.

The docs commit (this one, sixth) lands first; then strategy chat presents the new PROJECT_CONTEXT.md and CONVERSATION_SUMMARY.md; user replaces the project files; user commits the docs update; user tags `stage-4d-followup-complete` (or similar); user pushes the full six-commit stack + the tag together.

---

*End of summary. For the structured project context, see PROJECT_CONTEXT.md.*

### Stage 5 refinement: read-only recon before geometry-critical edits

Stage 5 leaned on the diagnostic-before-decision discipline most heavily for the geometry-critical work. Two of the four substantive features (the projector lens-offset correction and the obstruction check) were each preceded by a dedicated read-only recon prompt — no code, answer specific questions, halt. The recons earned their keep: the projector recon caught the missing face-vertical offset (the sim had only the −6.5 face-X) and confirmed the math-untouched blast radius before any edit; the obstruction recon caught both the corner-vs-edge sampling sensitivity and the axial-bound false-positive before the build. The pattern: when an edit is geometry-critical or the user voices a worry about blast radius, spend a turn on a recon that answers the worry against the actual code, rather than reasoning from memory of how the code works.

### Stage 5 refinement: the docs pass is strategy-chat's, the commit is Claude Code's

The stage-close docs (PROJECT_CONTEXT.md, CONVERSATION_SUMMARY.md) are regenerated by THIS strategy chat as complete downloadable files (reading the current versions from the project, weaving in the stage, fixing stale claims), which the user pastes over the real files in VS Code. Claude Code's role at close is the small mechanical one: commit the pasted docs, tag, push. A drafted "Stage 5 CLOSE" prompt that told Claude Code to write the docs itself was discarded — writing the docs is strategy-chat's job, not Claude Code's.

### Stage 6 B.3b refinement: byte-exact fixture before optimizing a numeric core

Before optimizing the STL rasterizer, a frozen byte-exact baseline of its current output was committed (perf.0) and every optimization proved `np.array_equal` against it — including the cube's ~1.7764e-15 sub-ULP residual. The existing atol-0.1–0.25 tests would have passed a byte-drifting rewrite; the frozen fixture is what made "byte-identical" provable rather than asserted. A "cleaner" output (exact 0.0 on the cube) would have been a FAILURE, not an improvement. This generalizes the sealed-core `[pipeline] std_err` discipline to any numeric output a refactor touches, and is now the standing rule for optimizing a numeric core (PROJECT_CONTEXT §7.17).

### Stage 6 B.3b refinement: recon-before-build held across a 5-commit perf arc

Every commit of the B.3b performance arc was preceded by a targeted read-only recon that caught a real issue before any code: perf.0 exists *because* a recon found the existing tests couldn't catch a byte drift; perf.1's recon enumerated the ULP-sensitive details of the rasterizer inner block (the two separate coordinate paths, `l3 = 1−l1−l2`, the −inf sentinel) the vectorization had to preserve exactly; perf.1b's recon discovered the residual ~433 MB peak was the *caller's* lift, not the rasterizer it had just optimized; perf.2's recon established the camera-distance/mm-extent constraint that lets the display downsample skip the pinned tests. The discipline that started as "geometry-critical" (Stage 5) and broadened to "physics-or-architecture-critical" (Stage 6 A→B.3a) is now simply the default for any non-trivial change — the recon's aggregate cost was far below the wrong commits it prevented.

---

## Stage 6 (Phase A → B.3a) — the inverse-FPP pipeline + the physical beyond-Nyquist wall

This phase is where the project first built things the paper's abstract actually claims. The arc, the *why*, and the working-model lessons:

### What this phase was for (the framing that drove it)

The pre-Stage-6 sim recovered everything perfectly — bias-free live path (`carrier + height_to_phase`, no `project()`, no sampling limit, no noise). That made it impressive-looking but useless for a paper: with no limit in it, straight-fringe and inverse-FPP looked identical because nothing ever failed. The phase's job was to put the **physical resolution limit a real system has** into the sim, then demonstrate inverse-FPP beating it. The user grasped this from the user side at close: "before this phase my recovered would virtually be almost the same as ground truth" — exactly right, and the new steep-feature failure (without correction) is the sim becoming *more honest*, not breaking.

### Three findings from the supervisor's thesis (Samara Ch.2/3/4) that shaped the plan

1. **Ch.3 already simulates this nulling technique** (object-adapted fringes, no prior CAD, waviness-filtering). So the nulling *concept* is not the novelty — the novelty is the real-time DLP hardware closed loop + the AM/in-situ framing. The sim reproduction is a **validation gate**; the novel headline lives in the hardware phase. (To be confirmed with the professor.)
2. **The thesis used 8 phase-shifted frames, not 4.** N defaulted-parameterizable; A.4 made N physically matter (1/√N noise averaging).
3. **The thesis built its form-filtering inverse grating by reusing the bias-correction OPD scaled by 0.1** — NOT a clean golden-part loop. So a measured-golden-part reference (B.2) is a genuine extension/rewrite, not a copy.

### The two hidden prerequisites the recons surfaced (the phase's biggest lessons)

Both were found by read-only recons *before* building, and both reshaped the plan:

1. **The sim had no real sampling ceiling (Item D of Recon 1).** It point-sampled `cos()` on an integer grid — it aliased *implicitly and silently* via `arange`, with no pixel-pitch model, no fill-factor, no frequency guard. "Aliases as an accidental side-effect of arange" is not a defensible Nyquist limit for a paper. → A.0.2 built an explicit pixel-area sampling fade. **The sim must contain the limit it claims to beat.**
2. **The fade alone is transparent to recovery (A.2b halt-gate).** Noiselessly, the contrast envelope `B·env` divides straight out of `extract_phase`'s arctan2 (it's common to all N frames). A faded fringe recovers *perfectly* until contrast hits zero. So the fade by itself produces no gradual wall — the "beyond-Nyquist" claim **also requires noise**. → A.4 added per-frame read noise, the second prerequisite. This was nearly invisible; the halt-gate caught it before a test could pass for the wrong reason.

### The unit-reconciliation fork (bridge vs rewrite), settled on evidence

The math layer runs in notebook pixel-space; the one physical-length constant (`pixel_pitch_um=53`) was dead. A sampling wall needs a real object-space pixel size. Recon 3 established the core is **unit-polymorphic** (the height boundary scales with whatever unit `p` carries) BUT the `(2π/p)·X` carrier couples `p` to the integer pixel grid — so native-metric would reopen the 271-passing core + regenerate fixtures, while a thin scale-bridge constant touches **zero** tests. Decision: **bridge** (§7.12). The user's instinct to keep the core sealed was right; reopening a validated core to avoid one documented px↔µm scale is a bad trade. (My initial lean was the bridge, and I'd flagged I'd reconsider if the core turned out almost-metric — the recon showed the carrier coupling was the real obstacle, so the bridge held.)

### The golden-part recon that overturned my prediction

I predicted the tilt-flip would NOT null a 2D-curved golden (that `fit_tilt_plane` keeping only the linear part would mishandle genuine curvature). **The algebra proved me wrong** — flipping curvature about the fitted plane is *precisely* what produces `−C[h_golden]`; the plane-fit is *supposed* to keep only the linear carrier and flip all curvature. So B.2 was a clean reference-swap, not a new derivation. The recon-discipline earned its keep by overturning the strategy-chat prediction with evidence rather than building on the flattering guess. (It then surfaced a *different* 2D concern one layer down — the 1D self-cal leaking a y-ramp — which a follow-up recon bounded as benign-but-non-negligible and fixed with the `selfcal_fit` parameterization, §7.15.)

### The B.3 showcase-physics recon (what the headline actually is)

The crux tension: the inverse grating un-crushes the fringe only where the projected pre-distortion *matches* the part (part ≈ golden); a defect is by definition where they don't match. The recon (numerical probes) settled: **both wins are honest** — inverse-FPP recovers a steep golden *shape* straight-fringe loses to Nyquist (decoupling 42×, ~21,000× error improvement on the probe dome), AND detects a *gentle* defect on a steep flank straight-fringe buries — with the bound that a defect whose *own* gradient exceeds Nyquist degrades (61% at own-f 0.81). This produced the two pinned honest bounds (§7.14) and the two-showcase split (dome=validation, STL=realism, §7.16).

### The hands-on GUI review at close (a real finding)

The user exercised the steep-dome showcase and reported "a really really long vertical object that goes almost infinitely up and down." Correct observation: the steep dome renders at Z≈6000 (the §7.12 unit-seam, cosmetic). The **3D render is unusable for the showcase**; the result reads only via the Error Statistics (897mm→1.3mm on the Inverse-FPP toggle) and the dynamic-range readout. Toggling correction on a steep **Gaussian** (amp~22mm) was the more legible demonstration — it mangles visibly with correction off, snaps clean with it on. → B.3 polish item logged (normalize the Z render or auto-enable Color-by-error; consider the Gaussian as the default showcase surface). The user reasoned independently that the absurd height is a validation artifact ("realistically something that high obviously can't be measured... youre validating the inverse fpp with this test absurdly long object") and correctly relocated the unmeasurable thing from *height* to *steepness/slope past Nyquist* — exactly the wall.

### Working-model refinements confirmed this phase

- **Recon-before-build paid off repeatedly.** Item D (no sampling ceiling), the A.2b transparency catch (fade needs noise), the bridge-vs-rewrite decision, the golden-part prediction overturned, the self-cal y-ramp leak, the B.3 showcase physics — every one was a recon that changed the build or caught a wrong assumption before code. The discipline is now the default for any physics-or-architecture-critical step, not just geometry-critical ones.
- **The halt-gate "grep-check the prompt's core assumption" caught real errors** (e.g. the `arctan2(0,0)→0` idealization was wrong — a real zero-contrast stack yields a ~1e-16-residual-driven constant, not 0; caught by its own test mid-build and corrected in assertion + docstring).
- **Honest labeling enforced throughout.** A.2's closure labeled CONSISTENCY-not-physics; the curvature-only and defect-own-Nyquist bounds pinned in code + tests; the dynamic-range numbers labeled as convention-agnostic ratios. The showcase demonstrates the real claim and states its limits — it does not over-claim.
- **Sealed-core discipline held for all 9 commits** — `[pipeline] std_err` byte-identical at 1.764505e-05 from A.0.1 through B.3a; every new capability is additive and off-by-default on the path the existing tests exercise.

*End of Stage 6 (Phase A → B.3a) summary. B.3b is covered in the next section (done — replanned to defect-detection). B.4 (serializable reference), A.3 (consistency hygiene), and Stage 7 (hardware + the real-time novelty) remain.*

---

## Stage 6 B.3b — STL performance arc + part-agnostic defect-detection demo

B.3b was **replanned mid-stage on a physics correction**, then executed as a 5-commit performance arc + a 1-commit demo-wiring gate. The *what*, the *why*, and the lessons:

### The replan (the physics correction that reframed the whole stage)

B.3a's carry-forward called B.3b "the steep STL part — the dome's headline on a believable part." A recon at the top of B.3b killed that framing: **a believable STL at honest mm scale is sub-Nyquist by design.** Mm heights at 0.1 mm/px scale per-pixel gradients down 10× vs the math-pixel dome; a real part would need *multi-metre Z within the 68×55 mm FOV* to push the observed fringe frequency past 0.5 cyc/px. So the STL cannot carry the beyond-Nyquist dynamic-range headline. What it CAN carry is the §7.14 golden-referenced **defect-detection** story — and that became B.3b's demo. The dome stays the validation gate; the STL is the believable in-situ AM demonstration. Two stories, deliberately not conflated (PROJECT_CONTEXT §7.16).

### The performance arc (the real parts were unusable before it)

Both real parts are Browser-mode; the 12-inch baseplate rasterizes to 4500×4501 (~20 M vertices, 162 MB). Pre-arc that meant a 27 s load, a 610 MB peak, and a laggy FOV drag. Five commits, each recon-gated, each byte-identical on the metric that mattered:

- **perf.0 (`9785210`) — guardrail first.** The existing rasterizer tests were atol 0.1–0.25 + two trivial exact checks; they would NOT catch a byte drift from optimizing `_rasterize_triangles`. So perf.0 froze the current output as a committed `.npz` baseline (incl. the cube's ~1.7764e-15 sub-ULP residual) and asserted `np.array_equal`. The guardrail comes BEFORE the optimization, not after (§7.17).
- **perf.1 (`0f0043c`) — vectorize.** Vectorized setup + separable barycentric inner block + row-band tiling. The separable broadcast-add was *suspected* bit-identical (a single IEEE add of the same two operands, no regrouping) but **proven** via the perf.0 gate, not asserted — the explicit instruction was "if it fails byte-equality on any mesh, fall back to fused-in-band; do not normalize the residual." It passed. 27.2s→18.1s, rasterizer peak 610→229 MB.
- **perf.1b (`7169e24`) — in-place lift, and the gap it closed.** Recon found the ~433 MB end-to-end peak was now the *caller's* lift (`acc[finite]` boolean-index copies, done twice, + a separate output alloc), not the rasterizer. A shared in-place `_lift_to_zero` helper (both loaders) dropped it to 244 MB. Bonus: `load_stl_heightmap_full_scale` had no byte-exact test of its own; the shared helper gives it the perf.0 gate transitively (perf.0 exercises `load_stl_heightmap`, which now calls the same helper).
- **perf.2 (`0a4ebe5`) — display-only downsample.** The lag source was the 20 M-vertex GL surface. `_display_stride` thins ONLY the arrays handed to setData/setImage (vertex budget 1.5 M, pixel budget 4 M); the full-res `_stl_full_heightmap` stays the slice source of truth, camera distance comes from the full-res extent (the ==75/==375 test is untouched), and the minimap `setRect` stays at full mm extent so the FOV ROI doesn't shift. Verified smooth in-GUI.

### The demo gate (one wiring problem, found by recon)

The defect path was *already* part-agnostic (mm defect on the STL golden, clean null, deviation error-map — confirmed by recon). The ONE wiring problem: `_update_dynamic_range_readout` prints a "decoupling Nx" line whenever `f_straight.any()>0.5` — and part B's **sharp machined edges cross Nyquist over ~0.72% of frame**, so it would print a bogus beyond-Nyquist headline on what is the defect-detection story. Fix (`a8b1ab0`): thread `is_stl` in and early-return BEFORE any compute, setting the label to "Surface deviation — see Error Statistics (dynamic-range decoupling: steep-dome showcase only)". The gate sits ahead of all `is_steep` logic so dome/Flat/Gaussian are byte-identical; the test asserts absence of the *numeric* headline, not the disclaimer word.

### In-GUI verification (both real parts)

Defect OFF: golden-vs-golden nulls to ~1e-13 (Max abs error 4.99e-13 mm) — matching geometry recovers cleanly. Defect ON: a clean isolated 2.95 mm hot-spot in the error map; the pillars do NOT light up; the STL readout shows the "Surface deviation" text, not a decoupling number. Both parts (`fringe_demo_block_pillars.stl` 160×80mm; `12INCH_Baseplate_HBKU_STL.stl` 450×450mm, ~28MB, centered origin) load + render + drag smoothly post-arc.

### Working-model lessons confirmed

- **Recon-before-build held across the whole 5-commit arc.** Each perf commit was preceded by a targeted read-only recon that caught a real issue before code: the guardrail gap (perf.0 exists because recon found the atol tests can't catch byte drift); the ULP-sensitive details of the rasterizer inner block (the two coordinate paths, l3=1−l1−l2, the −inf sentinel); the camera-distance/mm-extent constraint that keeps perf.2's downsample from breaking a pinned test; the discovery that the 433 MB peak was the caller's lift, not the rasterizer.
- **Byte-exact fixture before optimizing a numeric core** is now a standing discipline (§7.17) — the generalization of the sealed-core std_err rule to any numeric output a refactor touches. A normalized-away residual is a regression in disguise.
- **The bump's validation-tautology limit was named, not papered over.** Injecting a defect and recovering it in a sim only re-confirms the §7.14 nulling property the math already guarantees; doing it with *more/placeable* bumps adds polish, not truth. Defect interactivity is PARKED, not deferred.
- **A staleness discovery surfaced the next task.** The 3D Scene lab view still renders a recovered surface that predates the inverse-FPP work — it diverges from the Recovered Surface tab. Feeding it the same inverse-FPP recovered surface (live, over ground truth) is the next task, coordinated around Ilyas's pending projector swap (keep the two concerns in separate methods, never blind-merge).

*End of Stage 6 B.3b summary (tagged `stage-6-b3b-complete`, pushed at close). The three arcs that followed — lab-view consistency, FOV presets, and B.4 — are covered in the next section.*

---

## Stage 6 B.3b-labview + FOV presets + B.4 — lab-view consistency, FOV planning tool, serializable reference

Three arcs landed after the `stage-6-b3b-complete` tag, all **unpushed** on `main`: (1) the lab-view recovered-surface consistency that was B.3b's carry-forward NEXT TASK, (2) a selectable FOV-grid preset tool, (3) the B.4 deterministic serializable reference. **8 commits, 357 tests passing** (341 at B.3b close → +16), `[pipeline] std_err` byte-identical at **1.764505e-05** throughout, every commit byte-neutral or additive and confirmed **DISJOINT** from the Ilyas projector-build boundary (`HardwareScene`/`scene.py`). Each was recon-gated; the GUI-touching ones were verified in-GUI before commit.

### The arc (8 commits)

| # | Commit | What landed |
|---|---|---|
| labview.1 | `961709a` | **Extract shared `_recover_part_surface` (byte-neutral).** The inverse-FPP recovery dispatch (inverse-on → `run_inverse_fpp` + reconstruct; off → `run_straight_fringe`) was inlined in the Recovered Surface tab branch; lifted to one method so the lab view can call the same producer next. |
| labview.2 | `8d6871f` | **Wire the 3D-Scene lab view to the same inverse-FPP recovery.** It was rendering the pre-inverse-FPP **forward `run_pipeline`** surface → diverged from tab 3. Now both call `_recover_part_surface`; the lab view passes `part=golden` (clean, NO defect) and `inverse_on=True` hardcoded (always the honest corrected showcase, decoupled from tab 3's checkbox). **Key result, verified in-GUI: the recovered surface is now ANGLE-INVARIANT** — projector tilt used to distort it (projection-arm perspective bias flowing into the forward recovery); inverse-FPP nulls the bias, so the surface no longer changes shape with angle (the §7.14 property made visible). One conscious test update (a test that pinned the lab view to the `run_pipeline` surface). |
| fov-preset.1 | `363e6b8` | **Thread `_fov_shape` as single source of truth** for the Browser FOV-slice size (default `SURFACE_SHAPE`, byte-neutral). The slice extraction, the off-part mask, and the drawn minimap ROI all read it — so the captured window and the rectangle that draws it can't desync. |
| fov-preset.2 | `356d651` | **Preset dropdown + runtime ROI resize.** Selectable sizes (px @ 0.1 mm): `(550,680)` full / `(440,544)` / `(330,408)` / `(220,272)`. Re-centers on the current FOV center (shrink = zoom in, no jump), resizes the ROI at runtime (`setSize` under `blockSignals`), browser-only (greyed in synthetic/direct). +7 tests. |
| B.4.1 | `96592e0` | **`ShowcaseConfig` JSON serializer** (fills the `io_utils` stub). Captures the full B.3a reproducing param set; geometry stored as INPUT fields with `lambda_eq` recomputed on load (never serialized — can't desync); `lambda_eq_override` rejected at capture; vestigial H/W/pixel_pitch_um excluded; `schema_version`. **GUI-agnostic** — `io_utils` imports only `geometry`; the B.3a VALUES bind in the test/generator. |
| B.4.2a | `204754c` | **Lift `steep_region_ratios` → new `src/showcase_metrics.py` core** (byte-neutral). The headline ratio math was GUI-buried in `_update_dynamic_range_readout`; lifting it means the GUI readout AND the B.4 reference compute the same numbers from one source. The `:.0f` display rounding + label strings stayed in the GUI. |
| B.4.2a2 | `f1f5f2a` | **Lift `make_demo_defect` → `src/test_surfaces.py` core** (renamed from the GUI-private `_demo_defect`; byte-neutral). Needed so the GUI-free generator injects the IDENTICAL defect (the center `0.40·H/0.62·W` is hardcoded in the fn, not a config param — replicating would hardcode it twice and risk drift). |
| B.4.2b | `bb3ee56` | **The committed B.3a reference + reload-verify test, fully GUI-free.** `scripts/build_b4_reference.py` builds the config, runs the headline+recovery from it, freezes `tests/fixtures/b4_reference/{b3a_reference_config.json, b3a_reference.npz}` (+ `.gitignore` whitelist). **Frozen:** decoupling **219×**, error-ratio **37691×** (integers, EXACT via the `int(format(x,'.0f'))` `:.0f` mirror), `std_err 1.298556963203`, `max_abs 29.92299835680`, recovered `(550,680)` — floats/array at **atol 1e-8**. `tests/test_b4_reference.py` reloads + re-derives via the same core (it imports the shared `derive_b3a_headline` the generator uses). The Stage 7 hardware-phase validation target. +3 tests. |

### Key decisions

- **Light-reading XOR swap.** Only the *recovered leg* of the existing Stage-5 ground-truth/recovered toggle changed; no dual-surface overlay was added to the lab view (recovered-over-GT comparison stays tab 3's job). The lab view renders one surface, as before.
- **Clean / no-defect lab view.** `part=golden` so the lab view is orientation/recovery intuition as the rig moves; the defect-detection story is tab 3's. `inverse_on=True` is hardcoded — the inverse-correction checkbox is tab-3 UI, not in the lab view's scope; coupling them would be scope-widening.
- **Footprint-sourced prism (the FOV-preset payoff).** The coverage advisory's viewing-prism half-extents (34.0/27.5 mm) come from `make_viewing_cone_wireframe` (the camera footprint), **NOT** from `SURFACE_SHAPE`/the grid — byte-verified in recon before building. So a smaller grid leaves the real 68×55 capture intact underneath and buys tilt headroom; the existing height-aware advisory shows the payoff for free.
- **Two core lifts, because a reference must not drift.** A reference that re-derives the headline via a parallel copy of the GUI formula can silently diverge from what the GUI shows — exactly the inconsistency a validation reference exists to prevent. So the ratio math (`steep_region_ratios`) and the defect (`make_demo_defect`) were lifted to core, each as its own byte-neutral commit, so the GUI and the reference call **one** function each.
- **Integer-exact vs float-tolerance.** A determinism audit found the run byte-reproducible **same-machine** (all RNG is fresh-seeded `default_rng(seed)` per call — call order is irrelevant) but `np.polyfit`/`np.linalg.lstsq` route through BLAS, whose accumulation order differs **across** builds → ~ULP drift in recovered float arrays. So the integer headline ratios are pinned EXACTLY (the `:.0f` mirror absorbs ULP), while `std_err`/`max_abs`/recovered use `atol 1e-8` (the `regression_data.npz` tier, NOT the byte-exact rasterizer tier). The 219×/37691× values are the precise seeded-config point — they legitimately sit outside PROJECT_CONTEXT §7.16's recon-era "~42–135×" *general* range, which is left unchanged.

### In-GUI verifications

- **Lab view (labview.2):** the recovered surface no longer changes shape under projector tilt (angle-invariant — the headline result); defect ON in tab 3 → NO bump in the lab view (proves `part=golden` clean); inverse-correction OFF in tab 3 → lab view unchanged (proves the `inverse_on=True` decoupling).
- **FOV presets (fov-preset.2), 5 steps:** stepping the dropdown shrinks the rectangle centered on the same spot; the lab-view capture follows; drag still works and stays in-bounds at the 22×27 minimum; tilting θ_camera with a small preset shows more edge-height headroom via the coverage advisory; the dropdown greys out on synthetic/direct surfaces.

### Working-model lessons confirmed

- **Recon-before-build held across all three arcs.** The lab-view recon produced the **DISJOINT** boundary verdict (recovered-surface path vs projector `_build_*` path — zero method/data intersection) that lets Ilyas's swap and this work coexist; the FOV recon **byte-verified** the prism is footprint-sourced before any preset code; the B.4 recon's determinism audit forced the integer-exact/float-tolerance split *before* the build rather than discovering it mid-artifact.
- **Lift-before-reference is a single-source discipline.** A serializable reference is only as honest as the code it re-derives from. The two byte-neutral lifts (each its own commit, suite-proven identical) are what make "what the reference froze" provably equal to "what the GUI shows" — the same single-source-of-truth reasoning as the `_fov_shape` and `_recover_part_surface` threads.
- **Physical sanity anchors make a big headline trustworthy.** The 219×/37691× ratios are extreme by construction (straight-fringe fails catastrophically beyond Nyquist, inverse recovers near-perfectly), so the pre-commit check leaned on two physical anchors instead: `max_abs 29.92 ≈ the 30 px defect amplitude` (the recovered defect) and `recovered max 5999.5 ≈ the 6000 dome amplitude`. Both held — which is what licenses trusting the headline integers.

*End of Stage 6 B.3b-labview + FOV presets + B.4 summary. **Current state: three arcs complete and UNPUSHED — 8 commits on `main` past `stage-6-b3b-complete` (`961709a` → `bb3ee56`), 357 tests passing, `[pipeline] std_err` byte-identical 1.764505e-05. Docs updated mid-stage (no push/tag yet). Open: FOV-margin-for-tilt, the ~2× lab-view pipeline-cost gating, A.3 consistency hygiene, and Stage 7 (hardware + the real-time novelty).***
