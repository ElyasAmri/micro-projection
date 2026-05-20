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
| `reference/` (other thesis chapters as added) | Other chapters from the thesis author's thesis (Chapters 1, 3, 5, 6); kept for completeness, not active references |
| `notebooks/Fringe_Projection_Python.ipynb` | User's working synthetic pipeline (Stage 1 complete) |
| `docs/Projector_Geometry_Summary.docx` | Document handed off to a Three.js collaborator who is building a 3D simulation of the lab setup |
| `docs/Fringe_Projection_Roadmap.pdf` | Implementation roadmap (Stages 0–6) |
| `PROJECT_CONTEXT.md` | Concise project context |
| `CONVERSATION_SUMMARY.md` | This file |

The thesis chapter author is **the thesis author**. Equations: "Eq. 2-X" → Chapter 2; "Eq. 4-X" → Chapter 4.

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

Five design questions were settled before drafting task 4's prompt. Recording them for the same reason the Stage 4 false starts were recorded — easy to forget which framings won and which lost:

**Q1 — What the 3D view shows.** Three options considered: recovered only, true + recovered side-by-side, recovered with error map overlay. Settled on: **recovered as main view + toggle-able error overlay coloring** (recovered surface stays as the geometry, error magnitudes drive the color). Diverging colormap (blue under-recovered / white perfect / red over-recovered). Plus an error-stats panel (mean / std / max abs / RMS) that appears when overlay is on. The original "see how true would have looked" framing got pushed back — error is what the user actually wants to see, not redisplay of the input they set with sliders.

**Q2 — Degenerate λ_eq handling.** Detect `|tan θ_proj + tan θ_cam| < 1e-3` before calling the pipeline. Show a red warning banner explaining why height info isn't available; keep the last good 3D frame visible. Don't crash, don't blank, don't clamp. The banner uses the **textbook form** of Eq. 2-51 (with no `2π` in the denominator) so the equation matches what the user sees in the chapter PDF — independent of the code's internal `λ_textbook/(2π)` convention.

**Q3 — Performance.** Ship at full 480×640, measure, only optimize if actually slow. Don't pre-emptively add "compute on release" or downsample. 5 ImageViews in stages mode at 307k pixels each was a concern but ended up fine.

**Q4 — Bad-parameter handling.** No defensive try/except in task 4. Slider ranges prevent the known failure modes (exact-model denominator non-positive requires extreme angles outside the slider range; degenerate λ_eq has its own banner). Adding catch-all error handling for unknown failures was deferred until a real failure mode surfaces.

**Q5 — Commit shape.** Task 4 split into three commits instead of one: 4a (pipeline plumbing + recovered-height view), 4b (error overlay + stats), 4c (warning banner + colorbar + Z exaggeration tuning). Each ~250–400 lines. Same pattern as Stages 2/3 — one concept per commit. After the user's professor reviewed the work, task 4d (pipeline stages viewer) was added as a fourth commit and task 4e (close commit + tag) as the fifth.

### Stage 4a discoveries during execution

**Pyqtgraph 0.14.0 `GLSurfacePlotItem.setData(colors=...)` docstring is wrong.** The docstring claims `colors` should be `(width, height, 4)`, but the data is passed straight to `MeshData.setVertexColors`, which requires the flat `(N_vertices, 4)` form. Workaround: `colors.transpose(1, 0, 2).reshape(-1, 4)`. Documented in `src/gui/surface_preview.py` as "pyqtgraph axis + colors quirk." Worth knowing if pyqtgraph ever fixes their docs upstream (the workaround would need to revert).

**Pyqtgraph 0.14.0 doesn't bundle 'gray' or 'hsv' colormaps** (only `pg.colormap.get('viridis')`, `'CET-D1'`, `'CET-C1'`, and a handful of other CET-prefixed maps). Workarounds: manual 2-stop black-to-white `ColorMap` for the fringe-frame panel; `CET-C1` (perceptually-uniform cyclic) for wrapped-phase panel. Documented in `stages_view.py`.

**The unit-mismatch incident (task 4).** The original task-4 prompt told Claude Code to construct `HybridGeometry` with the info-panel's mm-space values (M=11.1 chapter convention, p=2.0 mm, a=50 mm). Claude Code did so, then ran a pre-commit magnitude sanity check before launching the visual. The result: recovered Gaussian peaked at ~1535 mm against an input of 0.5 mm — a ~3000× inflation, caused by the math layer interpreting M=11.1 as the modern convention (silently inflating λ_eq by ~123×) plus the carrier `(2π/p)·X` with `p=2.0` and `X = np.arange(W)` producing a Nyquist-aliased fringe density. Claude Code stopped before commit and surfaced the issue. The fix: hardcode notebook pixel-space units in `_build_geometry()` (M=1.0, p=40.0, a=2000.0) and leave the info panel's mm-space display values decorative for now. Unit reconciliation deferred to Stage 5/6 when real hardware values arrive.

**The λ_eq naming verification (task 4c).** While drafting the warning banner text, the strategy chat realized the project had three different conventions in circulation: notebook (`(p·M)/(4π·sin θ)`), Stage 3.5 commit message (`Mp / (2π·(tan θ_proj + tan θ_cam))`), and textbook Eq. 2-51 (`Mp / (tan θ_proj + tan θ_cam)` with `× ψ/(2π)` factor outside). A verification pass on `geometry.py` and `reconstruction.py` confirmed the code is correct: `equivalent_wavelength()` returns `λ_textbook / (2π)`, and `phase_to_height()` is implemented as `ψ × equivalent_wavelength()` — the `2π` from Eq. 2-51 is pre-folded into the wavelength constant. Final pipeline output matches Eq. 2-51 exactly. **No physics bug, only a naming convention difference.** The warning banner displays the textbook form so users cross-referencing the chapter PDF see the same equation. A rename of `equivalent_wavelength()` to `height_per_radian()` is a deferred cosmetic improvement.

**Professor feedback that shaped task 4d.** After tasks 4a/4b/4c landed, the user showed the GUI to his professor. Professor's feedback: (1) STL-import flow for custom test objects (deferred — eventually Stage 4c); (2) the user should be able to see intermediate pipeline stages, not just the final recovered surface. The latter became task 4d — a pipeline stages viewer showing all 5 stages (ground truth → projected fringes → wrapped phase → unwrapped phase → recovered height) as live camera-view heatmaps with equation labels. This was a substantial scope addition that turned out cleanly because `run_pipeline` already computed all the intermediates internally; only the dict-return refactor and the new GUI panel were needed.

### Stage 4b refactor — unified scene supersedes "separate lab view"

Originally planned as a separate 3D view toggled by a button (per PROJECT_CONTEXT Sec 12 in the pre-4b version). During Stage 4a's task-4d planning conversation, the user clarified their actual mental model: they want the lab apparatus (camera body, projector body, cones) **added to the same 3D scene** that shows the recovered surface — not a separate view. Same coordinate frame, same orbital camera, just more items in the scene.

**This is cleaner.** Hardware bodies provide visual reference scale (Z exaggeration can drop further toward honest). Projector-distance slider becomes meaningful (lab-view changes). User sees the recovered surface AND the rig that produced it simultaneously. No mode switching.

The "View Mode" radio toggle from Stage 4a task 4d (3D Scene ↔ Pipeline Stages) stays. Stage 4b just enriches what's in the "3D Scene" page.

**Implementation approach:** schematic primitives with measured proportions and physically-accurate light/viewing cones. Not photorealistic STL imports (those don't necessarily exist for the actual hardware models, and photo-realistic textures add nothing pedagogical).

---

## 7e. Stage 4b — Execution history (Unified hardware-bodies scene + clip-detection, complete)

Tag: `stage-4b-complete`. 143 tests passing.

### Sub-task summary (commit by commit)

| # | Commit | One-line summary |
|---|---|---|
| 1 | `3c4e5e5` | `src/scene.py` mesh builders. Camera/projector body cubes at real dimensions (29×29×30 mm, 55³ mm). CCW outward winding, pure `(verts, faces)` returns. 12 new tests. |
| 2 | `fbc5853` | `_cylinder` / `_stepped_cylinder` helpers. `make_camera_lens` matching Edmund's stepped 3-section profile (200mm total). `make_projector_lens` (20×5mm). `src/scene_compose.py` new: pose composition layer with `camera_arm_transform`, `projector_arm_transform`, `body_lens_offset`. 33 new tests. |
| 3 | `7bb2b41` | `src/gui/hardware_scene.py` new: `HardwareScene` class hosting GLMeshItems, GLLinePlotItems for the wireframes, and `compute_arm_transforms()`. main_window: new `camera_distance` slider (132–182mm Edmund WD range), renamed `projector_distance` slider labels to optics convention (lens-front to surface, NOT body-center). `LabeledFloatSlider.set_value()` added. View distance bumped 80→600mm. 6 new tests. |
| 4 (1/3) | `e96e1fc` | Projection + viewing cones + clip-detection v1. `make_projection_cone_wireframe` (5 verts / 8 edges diverging pyramid). `make_viewing_cone_wireframe` (8 verts / 12 edges telecentric prism — parallel sides, NOT a true cone). `cone_local_to_world_transform` helper in `scene_compose.py`. `src/gui/clip_detection.py` new (pure NumPy): `detect_clips` with 3 checks — camera/projector lens disc-edge vs surface plane, body assembly AABB overlap. `ClipState` dataclass. Theta sliders extended ±60° → ±75°. Gray override color `(0.4, 0.4, 0.4, 1.0)` applied to offending body+lens+cone on collision. Warning banner above 3D view. 18 new tests. |
| 4 close (Z retune) | `45c2071` | **Z_EXAGGERATION 2.0 → 1.0** (honest scale). Single-constant change. User picked from empirical 4-screenshot comparison (Z = 1, 2, 5, 10) at the close of sub-task 4. The 4-shot comparison was the user's call — strategy chat had been preparing a contingent argument for keeping 2.0, but the user's eye on actual frames made the decision crisp. |
| 4 (2/3, REVERTED) | `c53dd36` → `20d6771` | Originally added surface-peak-vs-lens 3D contact checks (camera and projector). **Reverted** after interactive GUI testing showed these are unreachable in practice: at slider ranges (WD 132–182, surface amp 0–100, θ ±75°), the lens always clears the peak by ≥30mm at min WD; tilting only increases clearance. Same for projector. Carrying dead code wasn't worth the maintenance cost. Reset preserved in history rather than rebased away — the lesson "validate the bug can be triggered before adding the check" is worth remembering. 139 tests after revert. |
| 4 (3/3) | `5d4b4c4` | **FOV/cone coverage advisories — 3D volume tests.** Replaces the buggy 2D z=0 footprint coverage check (which existed in the originally planned 4.2/3 but missed vertical spill) with 3D point-in-volume tests against the camera viewing prism and projector projection cone. 11×11 heightmap sampling. Catches both lateral spill (wide surface) and vertical spill (tall Gaussian peak penetrating tilted prism's "ceiling"). Cone test uses angular criterion only (`s >= 0`, no `s <= throw` upper bound — throw is DLP focus distance, not light cutoff). Banner-only, no gray override. 4 new tests, total 143. |
| 5 (close) | this commit | Docs update + tag `stage-4b-complete`. |

### Stage 4b critical mid-execution discoveries

**Surface-vs-lens contact checks are unreachable in practice.** This was the most important discovery of Stage 4b. Sub-task 4 (2/3) added 3D surface-peak-vs-lens proximity checks as a follow-on to the 2D disc-edge-on-plane collision check (which IS reachable). The intent was to gray hardware when the surface peak grew tall enough to touch the lens. The check was implemented, tested, committed (c53dd36). Then the user opened the live GUI and tried to trigger the case — and couldn't. At any combination of slider values within their stated ranges (WD 132–182 mm, surface amplitude 0–100 mm, θ ±75°), the lens never gets close to the peak. At WD=132 (closest), camera_body sits at z ≈ 132·cos(0) = 132 mm above the origin; surface peak max is 100 mm; clearance ≥ 32 mm. Tilting only increases the lens's distance from the peak. Strategy chat's analysis confirmed this with numerical sweep. The check was dead code. Commit 20d6771 reverted c53dd36 cleanly.

**The vertical-spill FOV bug (user-caught).** Sub-task 4 (3/3) was originally going to use a 2D z=0 footprint check for FOV coverage — does the surface's *outline* fit inside the cone/prism cross-section at the surface plane? The user opened the live GUI to test it and noticed: with the surface tilted toward the camera (θ_camera positive) and the Gaussian peak tall enough, the *tip* of the Gaussian poked out the **top** of the tilted prism volume — but the 2D footprint check (which looks at z=0 only) said all was well. The user reported this. Strategy chat traced it: the prism's "ceiling" (the slanted top face after tilt) was being penetrated by the peak. 2D z=0 footprint test geometrically cannot catch this. Fix: switch to 3D point-in-volume tests on 11×11 sampled heightmap points. Each sample's 3D position (x, y, h(x,y)) is tested against the actual prism/cone volume. Both lateral and vertical spill caught in one geometric test. Cost ~250µs at every slider tick, well below interactive budget.

**The cone upper-bound (`s <= throw`) was wrong.** When sub-task 4 (3/3) landed, an early version included `s <= throw` as part of the projector cone test ("point must be between lens and the throw distance"). It caused false-flags: a flat surface tilted by θ_projector has corners sitting a few mm beyond the tilted nominal-focus plane (because the surface extends past where the optical axis hits z=0). The user reported the false-flag. Strategy chat traced it: `throw` is the projector's nominal DLP **focus distance**, not a hard light cutoff. The beam keeps diverging past the focus plane. The angular criterion (`abs(lu) <= s/2.4` and `abs(lv) <= s/2.4*9/16`) alone is the correct geometric test. Removed the upper bound. Clean baseline passed.

**Distance slider semantics: lens-front vs body-center.** Sub-task 3 brought a real design question to surface: do the distance sliders report lens-front to surface (optics convention, what an Edmund spec sheet says) or body-center to surface (mechanical convention)? Strategy chat originally proposed body-center because the world transform in scene_compose.py centers on body-center. The user pushed back: every spec sheet on the user's bench is in lens-front units; chapter equations are in lens-front units; the user's intuition for "WD = 157mm" is lens-front-to-surface. Decision: sliders report lens-front. `compute_arm_transforms` adds the body offsets internally (camera_body_distance = WD + 215mm; projector_body_distance = throw + 32.5mm). This shows up in every smoke test screenshot — the lens-front of the Edmund matches the surface at the slider value, not the body-center. Right call.

**The Z exaggeration decision.** At sub-task 4 close, strategy chat asked "do we keep Z=2.0 from Stage 4a or drop further now that hardware bodies are present?" User said "let's see screenshots." Four smoke tests rendered at Z=1, 2, 5, 10 with surface_type=Gaussian, amp=10mm, θ_proj=15, θ_cam=15. User reviewed all four and picked Z=1.0 with: "Z=10 is a lie. Z=2 is a lie. Z=1 is the right answer because that's what's actually there. The lens IS that far above the peak." This locked the "geometric ruler" property of Stage 4b's scene: the visual scene is a literal-scale representation, and clip-detection thresholds match what the eye sees. Z_EXAGGERATION = 1.0 became a load-bearing decision tied to the clip-detection semantics, not just an aesthetic choice.

### Stage 4b architectural decisions worth carrying forward

- **Banner vs gray semantics.** Collision (gray + banner) = physical impossibility. Coverage (banner only) = measurement incompleteness. Math runs regardless. Documented in PROJECT_CONTEXT Sec 7.5.

- **Math-layer purity extended to clip-detection.** `clip_detection.py` is pure NumPy + scene imports. Lives under `gui/` for cohesion with `hardware_scene.py`, but architecturally is math-layer code: headlessly unit-testable, no Qt dependency.

- **All clip-detection geometry constants derived from cone builders, not duplicated.** `_PRISM_HALF_U_MM`, `_PRISM_HALF_V_MM`, `_CONE_HALF_U_PER_L`, `_CONE_HALF_V_PER_L` are computed at module load from `make_viewing_cone_wireframe()` / `make_projection_cone_wireframe()` output. If the cone builders change, clip_detection follows automatically. This is the right anti-duplication pattern for spec numbers.

- **The 3D viewport is a geometric ruler with Z=1.0.** The most important pedagogical property of Stage 4b. Surface visually touching the (graying) lens = clip-detection threshold reached. Exaggeration would desync.

- **Two independent banners.** Degenerate-λ_eq banner (Stage 4a) short-circuits the pipeline. Clip-warning banner (Stage 4b) is advisory. Both can show simultaneously.

- **Smoke-test capture protocol.** Programmatic GUI launch → `view_3d.grabFramebuffer()` to `%TEMP%`, gated by user greenlight, then commit. One-process-per-render: a single-process render loop leaves all-but-first framebuffer blank (PyQt6/OpenGL quirk). Each pose config gets its own `python -c "..."` invocation.

- **Banners DON'T appear in `grabFramebuffer` captures.** They sit above the GL viewport in the Qt widget stack. Smoke tests verify banner state programmatically (read `.isVisible()` and `.text()` in Python) — not visually.

- **Stage 4b sub-task 4 went through a reset (c53dd36 → 20d6771).** Preserved in history. The "validate the bug is triggerable before adding the check" lesson is worth keeping visible.

- **No Co-Authored-By trailers.** Established as project convention from Stage 4b onward.

---

## 7f. Stage 4c — Execution history (STL import for arbitrary specimens, complete)

Tag: `stage-4c-complete`. 142 tests passing.

### Sub-task summary (commit by commit)

| # | Commit | One-line summary |
|---|---|---|
| 1 | `eecaeac` | Dropdown reduction (Flat, Gaussian only) + Gaussian amplitude cap 100→55 mm. `make_tilt`/`make_step`/`make_sphere` generators, their tests, 6 slider widgets, 3 page builders, 3 dispatch branches deleted end-to-end. Net −223 lines. Surviving slider inventory: Flat (none); Gaussian (gaussian_amplitude 0–55 mm, gaussian_sigma 1–30 mm). `tests/test_clip_detection.py:256` left at amplitude=100 (Gaussian-based coverage case; `make_gaussian` has no internal cap, math layer is free at any amplitude — only the GUI slider is bounded). New `scripts/stage4c_smoke.py` smoke harness committed as the evidence trail (one process per render per the Stage 4b protocol). 122 tests after deletions. |
| 2 | `db0cd21` | `src/stl_loader.py` (pure NumPy, peer of `test_surfaces.py`): `load_stl_heightmap(path, shape, pixel_size_mm)`, `get_stl_bbox_mm(path)`, internal helpers. Projected-barycentric rasterization with per-pixel max-z upper envelope (camera-visible top surface; closed-solid bottom shell discarded). Lift by global mesh-Z minimum (the part's true base across ALL vertices, not the visible envelope's minimum), so a closed solid sits with its lowest point on z=0 like a part resting on a flat stage. Coordinate convention replicated from `test_surfaces._centered_grid_mm` with a "source of truth" comment (no cross-module private import). Empty mesh raises ValueError; non-empty-but-all-XY-degenerate (vertical-walls-only) returns all-zero heightmap. 14 new tests covering cube, pyramid, tilted triangle, closed UV sphere, vertical-walls-only, empty mesh, offset cube, bbox extents — all synthetic in-memory via `tmp_path`. `numpy-stl==3.2.0` added to `environment.yml` **pip block** (NOT conda-forge — see "Stage 4c environmental incident" below). 136 tests. |
| 3 | `2c73955` | STL wired into the surface dropdown as `"STL file..."` (ASCII three-dot ellipsis, not Unicode `…`, for cross-platform safety). `_build_stl_page` with inner `QStackedWidget` (placeholder ↔ `STL: <basename> [Change...]` row, full path as hover tooltip). `_on_surface_combo_changed` slot inserted between page-swap and refresh in `currentIndexChanged` connection order. `_load_stl_from_path(path) → bool` is the no-dialog hook used by the `QFileDialog` flow, the Change button, the smoke script, and the tests. Cache (`_stl_heightmap`, `_stl_path`, `_stl_filename`) lives for the window's lifetime; switching to Flat/Gaussian and back to STL re-renders without re-import. `_revert_stl_dropdown` carries a maintainer comment explaining why both the combo AND the `surface_pages` stacked widget need manual `setCurrentIndex` under `blockSignals` — future maintainer might otherwise be tempted to "simplify" by removing the second call. Temporary `QMessageBox.warning` bbox guard (replaced in sub-task 4). 6 new GUI tests in `tests/test_main_window_stl.py` (monkeypatched `QFileDialog.getOpenFileName` and `QMessageBox.warning`). Smoke harness extended with STL mode (synthetic 30 mm cube via numpy-stl `mesh.Mesh.save` to `%TEMP%`). 142 tests. |
| 4 | `286ebb3` | Finalize the bbox guard: hard-reject only. `QMessageBox.warning` text rewritten to explain *why* oversized STLs are rejected and point at Stage 4d's planned STL Browser feature. The earlier draft of sub-task 4 (custom `STLOverflowDialog` with Rescale/Center+Truncate/Cancel buttons, `rescale_mesh_uniform`, `truncate_heightmap_z`, two new `src/gui/` modules, ~7 transform tests + 5 GUI tests) was **dropped during planning** — see the "Stage 4c sub-task 4 pivot" entry below. Five stale "sub-task 4" forward-references in `src/stl_loader.py` comments cleaned up to point at `main_window.py`'s `_load_stl_from_path` (where the bbox check actually landed in sub-task 3). Text-only commit; 142 tests unchanged. |
| 5 (close) | this commit | Docs update + tag `stage-4c-complete`. |

### Stage 4c critical mid-execution discoveries

**The lift-formula contradiction (sub-task 2 halt).** The prompt for sub-task 2 said "lift = subtract the minimum finite envelope value, sentinel→0." During summarize-back, Claude Code worked through the cube and sphere test cases and surfaced that the stated arithmetic is impossible for tests 1, 4, and 12. For a 10mm cube, every covered pixel's max-z is z_top (the bottom face always loses the per-pixel max), so envelope-min = envelope-max = z_top inside the footprint; subtracting envelope-min produces an all-zero heightmap, but test 1 wants inside=10. For a closed sphere, envelope-min subtraction gives peak = R, but test 4 wants peak = 2R (the diameter, with the discarded bottom shell contributing to the lift reference). Both tests are satisfied only by **subtracting the global minimum-Z vertex over all mesh triangles**, including the camera-invisible bottom shell — which is also the physically correct "the part's base touches the stage at z=0" semantic that the docstring implied. The prompt described the wrong arithmetic. Strategy chat caught the contradiction was real, approved the corrected lift, and Claude Code proceeded. Caught before any code or tests were written. This is the highest-value halt-gate firing in Stage 4c.

**The numpy-stl conda-forge ABI hazard (sub-task 2 environmental incident).** Strategy chat approved `conda install -n fringe -c conda-forge numpy-stl` reasoning "pure Python + numpy, no ABI concern." This was wrong in practice. Conda's solver decided to install conda-forge's numpy *over the top of* the pip-installed numpy already in the env, plus MKL, libblas, liblapack, tbb, llvm-openmp. The duplicate numpy + LAPACK stack broke `numpy.linalg` at the ABI level; `numpy.linalg.lstsq` raised a native `0xc06d007f` (proc-not-found) DLL error on every code path that touched it (calibration, tilt-plane fit). Recovery required:
1. `conda install -n fringe --revision 0` (exact-inverse rollback of the single bad transaction) — needed explicit user authorization since auto-mode safety classifier blocked it as a destructive operation.
2. Discovery that the rollback also gutted the pip-managed numpy's files (no `RECORD`, no `__version__`).
3. `pip install --ignore-installed --no-deps numpy==2.2.6` to restore numpy — blocked by `Access denied` because two long-running VS Code Jupyter processes (PIDs 31656, 38844) held the OpenBLAS DLL open. User closed the notebook + reloaded VS Code window + verified the env was clear in PowerShell.
4. Discovery that `typing_extensions` was also collateral damage (rollback removed it; pytest's `exceptiongroup` depends on it). `pip install typing_extensions==4.15.0`.
5. `pip install numpy-stl` (the correct path: pure Python + numpy, no native footprint, doesn't touch LAPACK).

The rule that came out of this, documented in `environment.yml`: **since this env's numpy is pip-installed, every new dependency goes in the pip block regardless of how pure-Python it looks.** Conda's solver doesn't read package source — it reads the dependency graph. Any conda dep with a numpy pin will install a second numpy.

**The blockSignals + manual setCurrentIndex coupling (sub-task 3 halt).** Sub-task 3's `_revert_stl_dropdown` (called when the user cancels the QFileDialog) reverts the surface dropdown to its previous selection. The natural implementation is `surface_combo.blockSignals(True); surface_combo.setCurrentIndex(prev); surface_combo.blockSignals(False)`. But the `currentIndexChanged` slots that normally do the page-swap don't fire under `blockSignals`, so the visible surface page would stay on the STL page after the combo ticks back to Flat/Gaussian. Claude Code surfaced this during summarize-back. Fix: also call `surface_pages.setCurrentIndex(prev)` inside the block. The code carries a maintainer-warning comment so the next person doesn't try to "simplify" by removing the explicit page-swap call.

**The grid-vs-FOV mismatch (sub-task 4 halt, ultimately moot).** When Claude Code was about to implement the dropped Rescale/Truncate dialog, summarize-back surfaced that `SURFACE_SHAPE = (480, 640)` at `SURFACE_PIXEL_SIZE_MM = 0.1` produces a 48×64 mm grid, but the working volume is 68×55 mm. The button labeled "Center + Truncate to FOV" would actually truncate to the smaller grid (64×48 mm), not the FOV (68×55). This is a real mismatch between Stage 4a's math-layer resolution choice and Stage 4b's FOV-defined working volume. Strategy chat approved option (b): change the button label to "Center + Truncate to grid (64 × 48 mm)" and explain the distinction in the dialog body. The reconciliation between math-layer grid and hardware FOV remains a Stage 5/6 concern (when real hardware lands and unit handling is revisited per PROJECT_CONTEXT Section 7.5). The whole dialog got dropped in the next pivot anyway, but the diagnosis is preserved in case the math-grid-vs-FOV question recurs.

### Stage 4c sub-task 4 pivot — the dropped Rescale/Truncate dialog

The most consequential strategy-chat decision of Stage 4c. Worth recording in detail.

**Original sub-task 4 plan.** Custom `QDialog` subclass with three buttons:
- Rescale uniformly (factor = min(lim_i / bbox_i); scale mesh vertices, rasterize)
- Center + Truncate to FOV (center mesh, rasterize at full grid, np.minimum(hm, 55.0) for the Z cap)
- Cancel

Two button modes (XY+Z overflow vs. Z-only overflow) with different labels per mode. Pure-NumPy helpers `rescale_mesh_uniform` and `truncate_heightmap_z` in a new `src/gui/stl_transforms.py`. Public API in `src/gui/stl_overflow_dialog.py`. Refactor of `src/stl_loader.py` to extract a public `rasterize_mesh_to_heightmap(mesh, shape, pixel_size_mm)` so the rescale path could reuse it on transformed vertices. ~7 pure-NumPy tests + ~5 GUI-level tests + 2 new smoke modes (STL_rescaled, STL_truncated).

This was a defensible, well-scoped design. It would have worked. Strategy chat had already run one halt-and-confirm cycle with Claude Code (7 numbered points resolved, including the grid-vs-FOV mismatch above). Implementation was minutes away.

**The user's pivot.** During strategy-chat-side review:

> "im still trying to push it because i want to consider practicality of the simulation.... realistically we cant have a full sized object that fits in the small FOV. most artifacts will be alot bigger than the FOV."

Strategy chat initially pushed back, citing tiling as a multi-capture orchestration problem belonging in Stage 5/6. The user refined the proposal:

> "we have what i suggested which is showing a FOV portion of the top STL file..... and then having its top surface shown on top bird eye view at like lets say bottom right region of lab view. then it has a square on top of it which symbolizes the FOV grid. this grid can then be dragged across the surface which then updates to what is seen on the hardware components."

After one more refinement (the full-STL 3D preview is informational-only, not part of the data flow), the design landed as: import full-scale STL, show a top-down minimap with a draggable FOV rectangle, render only the windowed patch in the lab view, math layer keeps measuring one 68×55 patch at a time.

**The reframing.** Rescale and truncate both **distort the geometry the simulation claims to measure** — rescale lies about size, truncate lies about extent. Windowed FOV selection preserves the part at native scale. This is also how real-world large-part metrology works (commercial FPP systems with translation stages). The original sub-task 4 wasn't wrong technically; it was solving the wrong problem.

**Consequence.** Sub-task 4 collapsed from ~700 lines of new code (dialog, transforms, refactor, tests, smoke modes) to a 24-line text edit (rewrite the QMessageBox.warning body + clean up stale comments). The Browser becomes Stage 4d's headline; the dialog design becomes the cautionary tale in this section.

**The lesson.** When a sub-task feels technically right but the user pushes on practicality, the spec is what's wrong, not the user. Strategy chat's first instinct was to defend the dialog and defer tiling; the right move was to listen and replace the design. The halt-and-confirm protocol that exists for catching technical contradictions also catches design-frame contradictions — but only if strategy chat doesn't immediately argue against the user.

### Stage 4c architectural decisions worth carrying forward

- **STL loader is a peer of `test_surfaces.py` in the surface-library role.** Same `(shape, pixel_size_mm) → (H, W) float64 mm` contract; different generation method (file rasterization vs. analytic). Math layer treats them identically. Future surface sources (synthetic terrain, parametric defects) join the library the same way.

- **The math layer doesn't know STL exists.** It receives one heightmap. This is the discipline that made sub-task 3 a clean GUI-only change. Stage 4d's Browser preserves this — the windowed slice is just another heightmap to the math layer.

- **`_load_stl_from_path(path) → bool` is the GUI-facing entry, not the `QFileDialog` flow.** Single hook used by the dialog flow, the Change button, the smoke script, and the GUI tests. Each call site is one line. When Stage 4d adds the Browser, it extends this entry rather than re-implementing the import path.

- **Cache on MainWindow (`_stl_heightmap`, `_stl_path`, `_stl_filename`) is the surface-state contract.** Stage 4d's Browser extends with FOV-window state; dispatch in `_compute_current_heightmap` reads from one shared place.

- **Halt-and-confirm gates fired three times productively in Stage 4c.** Sub-task 2: lift-formula contradiction (zero broken tests). Sub-task 3: blockSignals coupling (zero invisible bugs). Sub-task 4: design pivot (zero wasted implementation). None of these are caught by the test suite — they're all "prompt vs. actual code intent" mismatches that only surface in summarize-back. The protocol earns its keep at the boundary between strategy and code.

- **The conda-forge ABI hazard is documented in `environment.yml` for Stage 4d and beyond.** When this env's numpy is pip, every subsequent dep goes in pip. Don't re-derive this rule by hitting the wall a second time.

- **No Co-Authored-By trailers.** Continued from Stage 4b convention.

- **Smoke script's role expanded.** `scripts/stage4c_smoke.py` started as a 3-mode verifier in sub-task 1 (verify | Flat | Gaussian) and grew to 4 modes by sub-task 3 (added STL with synthetic in-memory cube). Pattern that will continue: every GUI-touching sub-task adds a smoke mode that drives the new path end-to-end with grabFramebuffer capture. The script is the evidence trail; it lives in version control, not just `%TEMP%`.

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

The user worked through the chapter step by step and these were the conceptual landmarks:

### Additional insights added during Stage 1 walkthrough

- **The notebook's `phi1` vs `phi1_unwrapped` parallel structure** — `phi1` (analytical) is the ground truth; `phi1_unwrapped` (intensity → PSI → wrap → unwrap) is the simulated measurement.

- **Best-fit tilt absorbs both real tilt and a bit of curvature** — `np.polyfit(x, phi1, 1)` does not recover the analytical `2π/p₁` slope; it returns whatever slope minimizes squared error.

- **Cell 14's K constant implicitly assumes a telecentric receiver.** No `capture()` function exists to mirror `project()`. The camera arm is treated as a perfect pass-through.

- **OpenCV is not needed for the fringe analysis math** — PSI, unwrap, tilt fitting, height conversion all live in NumPy.

### Additional insights added during Stage 3 walkthrough

- **The textbook's Eq. 4-6 has a sign typo.** Printed as `1/(1 − 2x·tan(θ)/a)`, but the notebook (cell 25) shows that this convention disagrees with the existing Taylor branch's `−` bias. The `+u` form is correct.

- **Validation criteria for user-facing toggles should be informational, not gating.** Strict numerical bounds on the deviation between Taylor and exact would have been arbitrary.

- **A test parametrization can technically pass without meaningfully exercising the parametrized variable.** The Stage 3 integration test prints identical `std_err` for both models because the object leg synthesizes `phi3` analytically.

### Additional insights added during Stage 4 planning

- **The chapter's M is camera-side only.** Eq. 2-41 defines M as `l/b` — both lengths on the camera arm. The chapter uses one M everywhere because of its symmetric-arm assumption. Projectors don't have an "M" in the chapter's framework.

- **`a` is fixed inside the projector** (DMD-to-lens distance, mechanical). The "throw distance from projector to surface" is a separate physical quantity.

- **For telecentric cameras, M and distance are independent within the working-distance range.** Moving the camera only affects focus.

- **The symmetric assumption (Fig. 4-4) is expository, not required.** Eqs. 2-41 and 4-11 use one M and one θ because the chapter writes derivations under symmetric arms for clarity.

- **A slider that doesn't affect the science view is still valuable** if it serves a real lab-design purpose. The projector-distance slider is the case in point — inert in 4a, became live in 4b's unified scene driving body translation and cone size.

- **Telecentric ≠ vertical mount.** This is the most important Stage 4 discovery. Telecentric only locks the lens magnification; the arm's tilt angle relative to the surface is an independent mechanical parameter. Stage 2 Decision 3's `λ_eq = Mp / tan(θ_projector)` was wrong because it assumed θ_camera = 0°, derived from this conflation. Stage 3.5 corrected it by using Eq. 2-51's full two-angle form.

- **Both arms vertical = no triangulation = no height info.** The degenerate case `tan θ_proj + tan θ_cam = 0` makes λ_eq infinite. This is correct physics: triangulation needs angular separation between the projector beam and the camera view direction. Stage 4a task 4c implements this as a warning banner with the textbook Eq. 2-51.

### Additional insights added during Stage 4a execution

- **The math layer and the info panel use different unit systems.** Math layer is in notebook pixel-space (M=1, p in pixels, a in pixels); info panel is in mm-space hardware values. They coexist as parallel descriptions; the math layer's recovery output is correct in pixel-space units. Reconciliation deferred to Stage 5/6.

- **The code's `equivalent_wavelength()` returns `λ_textbook / (2π)`, not the textbook's λ_eq directly.** The `× ψ/(2π)` factor from Eq. 2-51 is pre-folded into the wavelength constant. Pipeline output matches Eq. 2-51 exactly. Only the *naming* is potentially confusing to a reader cross-referencing the chapter.

- **Self-cal recovery is structurally λ-cancellation-immune.** The pipeline tests pass at atol=1e-8 because the tilt-fit step removes the same `H_obj/λ` term that gets multiplied back by λ in `phase_to_height`. This means **the integration tests cannot catch a factor-of-2π scaling bug in λ_eq.** Real magnitude validation needs cross-implementation comparison or hardware.

- **Pyqtgraph documentation drift is a real maintenance risk.** Pyqtgraph 0.14.0's `GLSurfacePlotItem.setData(colors=...)` docstring claims `(W, H, 4)` but the data goes straight to `MeshData.setVertexColors` which wants flat `(N_vertices, 4)`. Discovered during task 3's first smoke test (raised IndexError). Workaround documented inline in `surface_preview.py`. Worth checking on future pyqtgraph upgrades.

### Additional insights added during Stage 4b execution

- **Telecentric optics means rectangular prism, not cone, for the viewing volume.** Edmund #58-259's parallel chief rays imply the viewing volume has fixed 68×55mm cross-section at all axial depths. The wireframe is built as 8 vertices / 12 edges (rectangular prism), not as a diverging pyramid. The point-in-volume test ignores the along-axis coordinate entirely; only perpendicular offset from the optical axis matters. This is the defining geometric difference from the projector's diverging cone.

- **DLP throw distance is the focus plane, not a light cutoff.** Bounding the projection cone at `s <= throw` false-flags flat surfaces' outer regions. The beam keeps diverging past the focus plane. The angular criterion alone is correct.

- **AABB overlap on rotated bodies is over-sensitive but acceptable for advisories.** Rotated bodies have inflated AABBs vs. their true OBBs. Bodies-overlapping check may flag near-collisions. Documented in the function docstring. OBB upgrade deferred unless real false positives surface.

- **Disc-edge math for lens-vs-plane collision.** At tilt θ, the lens-front disc's lowest world-z is `z_center − r·sin(θ) = WD·cos(θ) − r·sin(θ)`. Collision fires when this drops below zero. Catches the edge hitting the plane even when the center is still well above — critical at high tilt.

- **11×11 sampling is enough.** Dense enough to catch lateral spill (corner samples) and vertical spill (central peak samples). Cost ~250µs/tick. Negligible at every slider drag.

- **Strict-correctness checks beat tolerance-based checks for advisory triggers.** Stage 4b's FOV/cone checks use exact inequalities (no tolerance margin). Hairline triggers happen only at slider extremes outside real operating ranges (amp=100mm Gaussian) and are honest geometric reporting. Tolerance margins would hide real failures and require magic thresholds.

### Additional insights added during Stage 4c execution

- **The "lift to z=0" semantic for heightmaps depends on what z=0 means physically.** Flat/Gaussian sit naturally at z=0 because they're synthesized that way. STL files arrive with arbitrary world-origins. The right lift reference isn't the visible envelope's minimum (which would put a closed cube's top at z=0) but the **global mesh-Z minimum across all vertices, including camera-invisible faces** (which puts the cube's bottom at z=0). Physical interpretation: the part rests on a flat stage at z=0; the camera sees what's above the stage. The discarded bottom shell of a closed solid still defines where the part contacts the stage.

- **Projected-barycentric rasterization scales better than z-buffer search on dense CAD STLs.** For a 10k-triangle part at 0.1mm grid resolution (480×640), z-buffer-per-pixel is O(pixels × triangles) ≈ 3 billion comparisons; projected-barycentric is O(triangles × pixels-per-triangle's bbox) and typically completes in single-digit seconds for the worst-case parts we expect. The outer loop is over triangles; the inner pixel fill is vectorized via NumPy. This is the only rasterization strategy that's interactive-feasible for real CAD inputs.

- **Rescale and truncate distort the geometry being measured.** Two failure modes were available for oversized STLs: shrink the part to fit (rescale) or clip what doesn't fit (truncate). Both produce a heightmap that doesn't match the user's actual specimen. Stage 4c's sub-task 4 design pivot replaced these salvage modes with a hard-reject + Stage 4d Browser plan that preserves the part at native scale and lets the user explore it FOV-by-FOV. The principle: a digital twin that lies about what it's measuring is worse than one that refuses to measure.

- **The math-layer pixel-space grid (48×64 mm) and the hardware FOV (68×55 mm) are not yet reconciled.** Surfaced during sub-task 4 planning while sizing the "Center + Truncate to FOV" dialog button. The math layer uses 480×640 at 0.1mm/px (set in Stage 4a, derived from notebook-pixel-space units). The FOV is 68×55 mm (set in Stage 4b, derived from camera + lens specs). These don't match. Stage 4c didn't reconcile them — sub-task 4's pivot away from rescale/truncate sidestepped the issue. The reconciliation is a Stage 5/6 concern when real hardware lands.

- **Conda solver behavior matters more than package source-code purity.** A pure-Python + numpy package can break the env if conda's solver decides to install a second numpy alongside the existing pip one. The lesson generalizes: in mixed conda + pip envs, every new install has to be evaluated against the *solver*, not the *package*. The simple rule "this env's numpy is pip, so all new deps go in pip" replaces a more complex case-by-case analysis.

- **GUI tests don't have to launch real dialogs.** Monkeypatching `QFileDialog.getOpenFileName` and `QMessageBox.warning` at the module level lets six GUI-flow tests run without ever popping a real window. Each test asserts that the right call was made with the right args; the GUI internals get exercised; the test runner doesn't hang. Pattern reusable for any Qt modal interaction.

- **Halt-and-confirm gates catch design-frame contradictions, not just technical ones.** Stage 4b's halt-gate doctrine was framed as catching technical contradictions (the unreachable surface-vs-lens check). Stage 4c's sub-task 4 added a new category: design-frame contradictions, where the technical implementation would have been correct but the design's framing was wrong. The summarize-back protocol catches both, but only if strategy chat doesn't immediately defend the original plan. Listening is part of the protocol.

---

## 10. Project Conversations Note

- User had a friend building a separate **Three.js 3D simulation** of the lab geometry. The `Projector_Geometry_Summary.docx` was prepared for that collaborator. The Three.js work is **complementary**, not duplicative. The user **explicitly rejected** embedding the Three.js work into the Stage 4 GUI; lab view is native PyQt6 (Stage 4b's unified scene).
- User added a virtual representation of the test object with live sliders during Stage 4a. The intermediate-stages viewer (task 4d) was added based on the user's professor's feedback after seeing the digital twin in action.
- User added a **test-surface library** (`src/test_surfaces.py`) as part of Stage 4a task 1. Pure heightmap generators. Initially 5 surfaces (flat, tilt, Gaussian, step, sphere); reduced to 2 (flat, Gaussian) in Stage 4c sub-task 1 since tilt/step/sphere had no calibration role and the surface library was overdue for a tidy-up. STL files joined via `src/stl_loader.py` as a peer module.
- **STL import for arbitrary specimens delivered in Stage 4c.** Architecturally enabled by Stage 4a's `(shape, pixel_size_mm) → (H, W) float64 mm` contract; `src/stl_loader.py` produces this shape from any STL file. GUI surface dropdown reduced to (Flat, Gaussian, STL file...) — tilt/step/sphere deleted. Math layer untouched. Stage 4c supports specimens that fit the working volume (68×55×55 mm); larger parts will be supported by Stage 4d's STL Browser via windowed FOV selection.
- User clarified during Stage 3 and reaffirmed in Stage 4 planning that **the chapters in the reference folder are the math basis for the inverse fringe projection method, not a template for a thesis the user is writing.** Current deliverable is a working simulation that uses real hardware parameters. The work supports the user's thesis chapter on solder bump metrology.
- User wants **the GUI to be updatable with real hardware specs once they arrive.** The architecture supports this cleanly. This is the user's most important Stage 4 acceptance criterion.
- **User raised wanting to mount projector vertical (per professor preference).** Strategy chat surfaced that this requires non-vertical camera to preserve triangulation. Both-angles-as-sliders design supports this exploration and any other configuration the user/prof eventually decides on.
- **User caught a near-miss at Stage 4b docs close.** Strategy chat initially drafted updated PROJECT_CONTEXT.md and CONVERSATION_SUMMARY.md from chat memory alone, without reading the existing 600-line files. User caught it with "did you check the existing files first?" — saving the project's Stage 0-4a history from being silently erased. Pattern: when strategy chat hands the user a large deliverable derived from earlier project state, the user should verify strategy chat read the actual current files, not just reconstructed from working memory.

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
- Built a roadmap (Stages 0–6) with this-week to-do items
- **Stage 0, Stage 1, Stage 2, Stage 3, Stage 3.5, Stage 4a, Stage 4b, and Stage 4c completed.**
- Validation philosophy formalized: simulation-only validation has fundamental limits.
- **Stage 4 plan locked at the strategy-chat level.** Five sliders + surface dropdown, locked values, build sequence (3.5 → 4a → 4b), 3D viewer backend (PyQtGraph), resolution (480×640), MockCamera/Projector deferred.
- **Stage 3.5 pre-task executed:** math layer upgrade to two-angle λ_eq (Eq. 2-51), supersedes Stage 2 Decision 3. Commit `658f331`, pushed (not tagged).
- **Stage 4a executed:** 7 task commits + close. Tag `stage-4a-complete`. Full PyQt6 digital twin with surface library, pipeline integration, error overlay, warning banner, and intermediate-stages viewer. 70 tests passing.
- **Stage 4b executed:** 8 task commits including 1 reset (c53dd36 → 20d6771) + close. Tag `stage-4b-complete`. Unified hardware-bodies scene with live pose sliders, clip-detection (3 collision + 2 coverage advisories), honest scale (Z=1.0). 143 tests passing.
- **Stage 4c executed:** 4 sub-task commits + close. Tag `stage-4c-complete`. Surface dropdown reduced to (Flat, Gaussian, STL file...); pure-NumPy STL→heightmap loader; QFileDialog flow with cache lifecycle; hard-reject for STLs exceeding (68, 55, 55) mm working volume. 142 tests passing.
- **λ_eq naming convention clarified** during Stage 4a task 4c. Code's `lambda_eq` = `λ_textbook / (2π)`; no physics bug, only naming. Warning banner displays textbook form for user clarity.
- **Stage 4b redesigned** from a "separate lab view" to a "unified 3D scene with hardware bodies added to the existing recovered-surface scene." Cleaner architecture; hardware bodies provide reference scale.
- **Distance slider semantics locked:** sliders report lens-front to surface (optics convention); body offsets added internally in `compute_arm_transforms`.
- **Z_EXAGGERATION locked at 1.0** (honest scale). Tied to clip-detection semantics — surface visually touching the (graying) lens means literal threshold reached.
- **Surface-vs-lens contact checks dropped** as unreachable in practice. Documented as a Stage 4b lesson: validate the bug is triggerable before adding the check.
- **FOV/cone coverage tests upgraded** from 2D z=0 footprint to 3D point-in-volume on 11×11 samples (catches vertical spill, not just lateral). Cone test uses angular criterion only (no `s <= throw` upper bound).
- **Tilt/step/sphere surfaces deleted in Stage 4c sub-task 1.** Had no calibration role; cluttered the dropdown. Surviving surfaces (Flat, Gaussian) cover all smoke-test use cases. Sphere-cliff known-issue from Stage 4b became obsolete.
- **Gaussian amplitude slider cap tightened 100→55 mm in Stage 4c.** Matches working volume Z dimension. Math layer `make_gaussian` itself has no cap; bound is GUI-only.
- **STL loader written as pure-NumPy peer of `test_surfaces.py`.** Projected-barycentric rasterization, per-pixel max-z upper envelope, lift by global mesh-Z minimum (the part's true base, not the visible envelope's). Math layer doesn't know STL exists — it receives one heightmap.
- **`numpy-stl` installed via pip block, NOT conda-forge.** Conda-forge install dragged in MKL/BLAS/LAPACK and a duplicate numpy build that broke `numpy.linalg`. Recovery via revision-0 rollback + pip reinstall numpy + pip install numpy-stl. Rule documented in `environment.yml`: pip-installed numpy means every new dep goes in pip.
- **Stage 4c sub-task 4 design pivot.** Original draft was a Rescale/Truncate/Cancel `QDialog` for oversized STLs (~700 lines: dialog, transforms, refactor, tests, smoke modes). User pushed back during planning: "we cant have a full sized object that fits in the small FOV, most artifacts will be a lot bigger." Rescale and truncate distort the geometry being measured. Sub-task 4 collapsed to a 24-line text edit (hard-reject + comment cleanup). The Browser becomes Stage 4d's headline.

---

## 12. Tone & Style Notes

The user prefers:
- **Short concrete answers** over long expositions
- Step-by-step physical reasoning, not equation walls
- Honest disagreement when something's hand-wavy
- One thing at a time
- Practical code suggestions kept minimal

The user pushes back when something feels redundant or tautological. This is a strength — Stage 1 ended up with a smaller, cleaner validation suite than originally proposed because of it, Stage 3 collapsed from three sub-tasks to one for the same reason, and Stage 4's slider list went through five false starts before settling on the right shape. Strategy chat should default to less, not more.

The user also says when they don't understand something. When that happens, strategy chat should **simplify, not double down on technical accuracy.** Long technical explanations are the wrong response to "I don't get this" — shorter answers, more analogy, fewer equations. This came up several times during Stage 4 planning and during Stage 4a's λ_eq verification (where the strategy chat initially over-explained the math-layer-vs-textbook naming difference; the user redirected to "just tell me what to do" and the conversation moved on).

**The user is also good at asking questions whose answers force the strategy chat to catch its own mistakes.** The "telecentric = vertical?" question that surfaced Stage 2 Decision 3's hidden assumption was an example. So was the lab-view redesign question during Stage 4a planning ("isn't the lab view just my recovered view dressed up?") — which surfaced that the strategy chat had been describing two views as if they would be separate, when the user's mental model was always one unified scene. The Stage 4b vertical-spill FOV bug was another: the user opened the live GUI, noticed the tall peak poking out of the prism top, reported it, and the 2D-footprint test was rewritten as 3D point-in-volume. Strategy chat should treat user pushback as a diagnostic, not as resistance.

**The Stage 4b docs near-miss.** At Stage 4b close, strategy chat drafted updated docs from working memory rather than reading the existing 600-line files. User caught it. The lesson: when a large deliverable depends on existing project state (docs, code structure, prior decisions), strategy chat must read the actual current files before producing the update — not work from memory of what was discussed in this chat, because the existing files contain history strategy chat wasn't part of. Verification step now baked in: confirm the read happened before drafting the deliverable.

---

## 13. Working Model with Claude Code (Refined Through Stages 2, 3, 3.5, 4a, 4b, and 4c)

The handoff pattern that worked across Stage 2's six tasks, Stage 3's two tasks, Stage 3.5, Stage 4a's seven tasks, and Stage 4b's eight tasks (including the reset):

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

- **Task 4 unit mismatch.** Pre-commit magnitude check found recovery ~3000× inflated. Claude Code stopped, surfaced the issue with three resolution options, and user chose option 1 (notebook pixel-units). Without the sanity check, the commit would have shipped and the wrong recovery would have surfaced as a mysterious bug later.
- **Task 4b/4d colormap availability.** Both tasks initially specified pyqtgraph colormaps that turned out to not be bundled with version 0.14.0 ('coolwarm', 'hsv', 'gray'). Claude Code probed the installed colormaps first and substituted available alternatives (manual blue-white-red fallback, CET-C1 cyclic, manual gray ramp).

The pattern: **specs from strategy chat are first drafts, not contracts.** Claude Code's job includes catching the gaps. When it does, surfacing them mid-execution is the right move — not silently patching or silently failing.

### Stage 4a refinement: scope-creep is OK when it's the user's professor

Task 4d (pipeline stages viewer) was not in the original Stage 4a plan. It was added after the user's professor asked to see intermediate stages. Strategy chat's instinct was to defer ("Stage 4b should land first"); the user's correction was to fold it into Stage 4a since the professor's feedback is gold and the architecture (`run_pipeline` already had all the intermediates internally) made it cheap. The right call. Lesson: external feedback can justify mid-stage scope additions if the architecture makes the addition cheap and the feedback won't get easier to act on later.

### Stage 4b refinement: interactive GUI verification finds bugs unit tests miss

Stage 4b's clip-detection went through two iterations of user-caught geometry bugs that all unit tests passed: the unreachable surface-vs-lens contact check (sub-task 4 2/3, reverted) and the vertical-spill FOV bug (sub-task 4 3/3, rewritten as 3D point-in-volume). In both cases the unit tests were correct in what they tested — but they tested the wrong things. The unit tests for the surface-contact check verified the math gave a True boolean when the lens-and-peak-z values were close; they did not verify the slider ranges could actually produce such values. The unit tests for the 2D footprint coverage check verified the footprint was inside the prism's z=0 cross-section; they didn't verify a tall peak couldn't poke out the prism top.

The pattern: **for geometry code, interactive GUI testing is a load-bearing verification step, not an extra.** Unit tests verify the math is correct in the parameter regimes it's tested in; the GUI explores the parameter regimes a real user can reach. Both are needed; neither replaces the other. Stage 4c (STL import + sphere fix) will keep this two-step verification — code + tests, then GUI exploration before commit.

### Stage 4b refinement: revert preserved in history, not rebased

When commit c53dd36 (surface-vs-lens contact check) was reverted by 20d6771 (revert commit), strategy chat suggested keeping both commits visible in history rather than `git reset --hard` to before c53dd36. Rationale: the lesson "validate the bug is triggerable before adding the check" is more useful preserved as a visible reset than hidden by a rebase. Future maintainers (or fresh Claude Code sessions) reading the history see the two commits adjacent and can read the commit messages to learn the lesson. Buried-in-rebase lessons are forgotten lessons.

### Stage 4b refinement: smoke-test capture protocol matters

The Stage 4b smoke-test protocol (programmatic GUI launch + framebuffer capture, gated by user greenlight, one-process-per-render) became load-bearing during sub-task 4 because the clip-detection visual effects (gray override colors) needed to be verified in actual rendered output. Strategy chat learned mid-way through that a single-process loop trying to render multiple poses leaves all-but-first framebuffer blank (PyQt6/OpenGL quirk). Workaround: each pose config gets its own `python -c "..."` invocation. Banner state is verified programmatically (`.isVisible()` / `.text()`) because banners live above the GL viewport and don't appear in `grabFramebuffer` captures.

### Stage 4 fresh-session bootstrap

When a new strategy chat or Claude Code session starts after a stage closes:

- Strategy chat: re-upload latest PROJECT_CONTEXT.md and CONVERSATION_SUMMARY.md. Open chat with state-handoff message.
- Claude Code: open a fresh terminal. First prompt: "Read PROJECT_CONTEXT.md and CONVERSATION_SUMMARY.md. Summarize back what we're building, where we are, and what's binding for [Stage X]. Don't write code yet."

The two .md files carry all the context. A handoff .md is redundant when the context files are current.

### Stage 4c refinement: design-frame contradictions caught by halt-gates

Stage 4b's halt-gate doctrine framed halts as catching **technical** contradictions (the unreachable surface-vs-lens check). Stage 4c sub-task 4 added a new category: **design-frame** contradictions. The originally-drafted Rescale/Truncate/Cancel dialog was technically correct — it would have implemented cleanly, passed tests, rendered screenshots. The frame was wrong: rescale and truncate distort the geometry the simulation claims to measure. The halt-gate caught this not because Claude Code surfaced an inconsistency, but because the user pushed back on practicality during planning. Strategy chat's first instinct was to defend the dialog and defer the user's alternative; the right move was to listen. Lesson: listening is part of the halt-protocol. When a sub-task feels right technically but the user pushes on practicality, the spec is what's wrong, not the user.

### Stage 4c refinement: environmental dependencies fight back

Stage 4c hit one full env-corruption incident in sub-task 2: a single `conda install -c conda-forge numpy-stl` (intended as a one-line dep add) dragged in a duplicate numpy + MKL/BLAS/LAPACK stack that broke `numpy.linalg` for every code path in the project. Recovery took ~45 minutes (revision rollback + pip reinstall numpy + VS Code kernel coordination + typing_extensions collateral + final pip install). The recovery was orderly because each step was traceable: the bad transaction was a single conda revision, the rollback was its exact inverse, the kernel-holding-DLL issue had a clean signal (Access denied on the OpenBLAS DLL), and Claude Code refused to kill processes it didn't start — escalating the decision to the user instead of guessing.

Two protocol notes carried forward:
1. **Mixed conda + pip envs have a strict rule:** whichever package manager owns numpy owns every new dependency. Don't mix.
2. **Claude Code's "won't kill processes I didn't start" discipline is correct.** The two Jupyter kernel processes holding the OpenBLAS DLL were unrelated to the failing pip install in isolation, but related in effect. Claude Code surfaced both PIDs with their command lines, recommended Option A (close the notebook), and waited for the user. The user closed it; the pip install completed. If Claude Code had killed the kernel proactively, it would have lost any unsaved notebook state. This pattern repeats whenever an env recovery encounters a process the agent didn't spawn.

### Stage 4c refinement: smoke script is the evidence trail

Stage 4b established the smoke-test capture protocol; Stage 4c extended it into a versioned artifact. `scripts/stage4c_smoke.py` was committed in sub-task 1 with 3 modes (verify | Flat | Gaussian) and grew to 4 modes (added STL) in sub-task 3. The script writes synthetic in-memory STLs to `%TEMP%` when needed, drives MainWindow programmatically, and uses `grabFramebuffer()` to capture each surface state. Strategy chat reviews the captures before greenlight. Pattern that will continue: every GUI-touching sub-task adds (or extends) a smoke mode. The script lives in version control, not just in `%TEMP%` — future contributors should be able to regenerate the visual evidence trail. When Stage 4d lands, this becomes `stage4d_smoke.py` (or extends 4c's). The principle is: GUI commits without visual evidence are missing half their verification.

### Stage 4c refinement: halt-gate output formatting

Three Stage 4c halts (sub-task 2 lift-formula, sub-task 3 blockSignals, sub-task 4 grid-vs-FOV) followed the same output format: numbered ambiguities, each with the choices laid out, Claude Code's lean stated, rationale brief. This format made strategy-chat review fast: each numbered point gets a one-line approval or a substantive response. No reformatting required, no fishing for the actual question. Pattern to lock in: halt-gate output should be **numbered, with options stated explicitly, with Claude Code's pick named**. Open-ended halts ("I'm not sure how to proceed") are worse than picky halts ("Here are three options, I lean B, please confirm").

### Stage 4b close: docs-update protocol clarified

User updates PROJECT_CONTEXT.md and CONVERSATION_SUMMARY.md manually at stage close. Strategy chat drafts the updates — but **must read the existing files first** to preserve prior-stage content. Surgical additions are fine; full-replacement drafts work too, as long as the existing content is read before drafting. Strategy chat memory of "what this chat discussed" is not a substitute for "what the files actually contain." Verification: confirm read happened before drafting.

### Stage 4c close: docs delivered as files, not pasted inline

User preference clarified at Stage 4c close: docs updates are delivered as **complete, openable files** (full PROJECT_CONTEXT.md and CONVERSATION_SUMMARY.md), not as inline code blocks the user has to copy-paste-stitch into the existing files. Strategy chat generates the updated files in `/mnt/user-data/outputs/`, presents them, and the user opens them in VS Code and replaces the originals. This is meaningfully less error-prone than surgical inline edits the user has to apply by hand. Pattern for all future stage closes.

Push and tag happen together at end of stage:

```
git tag stage-Xx-complete
git push origin main
git push origin stage-Xx-complete
```

(No co-authored-by trailers.)

---

*End of summary. For the structured project context, see PROJECT_CONTEXT.md.*
