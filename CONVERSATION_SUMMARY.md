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
- Physical lens length and diameter: **not yet measured** (Stage 4b prep)
- **Confirmed telecentric**. NOTE (Stage 4 clarification): telecentric only locks the lens magnification; the camera body's physical tilt angle is independent. "Telecentric ≠ mounted vertical." Camera arm tilt is a separate parameter (θ_camera in Eq. 2-51).

### Projector: Pico Genie Impact 2.0 Plus Elite (placeholder)
- Identified from "Pico Genie Impact 2 Plus Elite" label on bottom of unit
- DLP projector
- 854 × 480 native, 1.2:1 throw, 16:9 aspect
- 55 × 55 × 55 mm cube
- HDMI input
- Confirmed **NOT** telecentric (consumer DLP)
- Will be replaced with a more advanced projector (telecentric status unknown)

### Geometry measurements taken
- Throw 30 cm → image 25 × 14 cm (matches spec)
- Lens center in body frame: (21, ~1, 45) mm
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

Each stage 4 sub-stage ships as its own tag (`stage-4a-complete`, `stage-4-complete`). Build the useful one first; the pretty one second. Math modules from Stages 2–3 are called by the GUI, not modified (except for the Stage 3.5 pre-task).

### Final slider/control list (locked after long planning discussion)

Mirrored in PROJECT_CONTEXT.md Sec 12. Five controls plus a surface dropdown:

- Surface type (flat / tilt / Gaussian / step / sphere) + per-surface params
- **θ_projector** slider (projector arm tilt from surface normal)
- **θ_camera** slider (camera arm tilt from surface normal — independent of projector)
- Projector distance from surface slider — **lab-design tool only**, does not affect chapter's bias math
- PSI step count dropdown (4 or 8)

Everything else (M, `a`, `p`, camera distance, FOV, throw ratio, λ_eq, model='taylor', resolution) is locked at hardware values and shown in a read-only info panel.

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
- **Projector distance moves projector body in 3D space but doesn't change bias math.** Slider kept for lab-design intuition (becomes live in the unified-scene Stage 4b).
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
| 4e (close) | this commit | Docs update + tag `stage-4a-complete`. |

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

**Professor feedback that shaped task 4d.** After tasks 4a/4b/4c landed, the user showed the GUI to his professor. Professor's feedback: (1) STL-import flow for custom test objects (deferred — see Stage 4a deferred list); (2) the user should be able to see intermediate pipeline stages, not just the final recovered surface. The latter became task 4d — a pipeline stages viewer showing all 5 stages (ground truth → projected fringes → wrapped phase → unwrapped phase → recovered height) as live camera-view heatmaps with equation labels. This was a substantial scope addition that turned out cleanly because `run_pipeline` already computed all the intermediates internally; only the dict-return refactor and the new GUI panel were needed.

### Stage 4b refactor — unified scene supersedes "separate lab view"

Originally planned as a separate 3D view toggled by a button (per PROJECT_CONTEXT Sec 12). During Stage 4a's task-4d planning conversation, the user clarified their actual mental model: they want the lab apparatus (camera body, projector body, cones) **added to the same 3D scene** that shows the recovered surface — not a separate view. Same coordinate frame, same orbital camera, just more items in the scene.

**This is cleaner.** Hardware bodies provide visual reference scale (Z exaggeration can drop further toward honest). Projector-distance slider becomes meaningful (lab-view changes). User sees the recovered surface AND the rig that produced it simultaneously. No mode switching.

The "View Mode" radio toggle from Stage 4a task 4d (3D Scene ↔ Pipeline Stages) stays. Stage 4b just enriches what's in the "3D Scene" page.

**Implementation approach:** schematic primitives with measured proportions and physically-accurate light/viewing cones. Not photorealistic STL imports (those don't necessarily exist for the actual hardware models, and photo-realistic textures add nothing pedagogical).

Camera body lens dimensions need measurement before Stage 4b (PROJECT_CONTEXT Sec 8 item 8). 5 minutes with a ruler.

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
8. **Stage 4b prep — physical dimensions to measure:** camera lens length, camera lens outer diameter, projector lens diameter. Body sizes and lens optical-axis positions are already documented (Projector_Geometry_Summary.docx).

---

## 9. Theoretical Insights From the Walkthrough

The user worked through the chapter step by step and these were the conceptual landmarks:

- **u₃ in Eq. 2-41 is a sensor-side displacement** caused by object height. We don't measure u₃ directly — we measure phase, which is a sensor-side displacement encoded as a cosine argument shift.

- **The /M factor in Eq. 2-49 is simple specifically because the system is telecentric** — telecentric magnification is constant everywhere, so position-dependent stretching factors collapse. In non-telecentric systems, M varies with position; the chapter handles this with the `(1 − x₁·tan θ/a)` factor.

- **`x₁` is a coordinate on the projector's grating plane**. For a digital projector (DLP), x₁ is just the column index of each pixel relative to the optical axis.

- **Once the system is set up, θ is fixed.** Only x₁ varies across the projected pattern, and h(x₁) varies across the surface. This is why p₂(x₁) varies across the inverse grating but everything else is constant.

- **Eq. 4-7 is structurally Eq. 4-2 with the curvature sign flipped** — that's literally what the tilt-flip trick does.

- **Custom grating is needed for this project** because the projector is non-telecentric.

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

- **A slider that doesn't affect the science view is still valuable** if it serves a real lab-design purpose. The projector-distance slider is the case in point — inert in 4a, becomes live in 4b's unified scene.

- **Telecentric ≠ vertical mount.** This is the most important Stage 4 discovery. Telecentric only locks the lens magnification; the arm's tilt angle relative to the surface is an independent mechanical parameter. Stage 2 Decision 3's `λ_eq = Mp / tan(θ_projector)` was wrong because it assumed θ_camera = 0°, derived from this conflation. Stage 3.5 corrected it by using Eq. 2-51's full two-angle form.

- **Both arms vertical = no triangulation = no height info.** The degenerate case `tan θ_proj + tan θ_cam = 0` makes λ_eq infinite. This is correct physics: triangulation needs angular separation between the projector beam and the camera view direction. Stage 4a task 4c implements this as a warning banner with the textbook Eq. 2-51.

### Additional insights added during Stage 4a execution

- **The math layer and the info panel use different unit systems.** Math layer is in notebook pixel-space (M=1, p in pixels, a in pixels); info panel is in mm-space hardware values. They coexist as parallel descriptions; the math layer's recovery output is correct in pixel-space units. Reconciliation deferred to Stage 5/6.

- **The code's `equivalent_wavelength()` returns `λ_textbook / (2π)`, not the textbook's λ_eq directly.** The `× ψ/(2π)` factor from Eq. 2-51 is pre-folded into the wavelength constant. Pipeline output matches Eq. 2-51 exactly. Only the *naming* is potentially confusing to a reader cross-referencing the chapter.

- **Self-cal recovery is structurally λ-cancellation-immune.** The pipeline tests pass at atol=1e-8 because the tilt-fit step removes the same `H_obj/λ` term that gets multiplied back by λ in `phase_to_height`. This means **the integration tests cannot catch a factor-of-2π scaling bug in λ_eq.** Real magnitude validation needs cross-implementation comparison or hardware.

- **Pyqtgraph documentation drift is a real maintenance risk.** Pyqtgraph 0.14.0's `GLSurfacePlotItem.setData(colors=...)` docstring claims `(W, H, 4)` but the data goes straight to `MeshData.setVertexColors` which wants flat `(N_vertices, 4)`. Discovered during task 3's first smoke test (raised IndexError). Workaround documented inline in `surface_preview.py`. Worth checking on future pyqtgraph upgrades.

---

## 10. Project Conversations Note

- User had a friend building a separate **Three.js 3D simulation** of the lab geometry. The `Projector_Geometry_Summary.docx` was prepared for that collaborator. The Three.js work is **complementary**, not duplicative. The user **explicitly rejected** embedding the Three.js work into the Stage 4 GUI; lab view is native PyQt6 (now Stage 4b's unified scene).
- User added a virtual representation of the test object with live sliders during Stage 4a. The intermediate-stages viewer (task 4d) was added based on the user's professor's feedback after seeing the digital twin in action.
- User added a **test-surface library** (`src/test_surfaces.py`) as part of Stage 4a task 1. Pure heightmap generators: flat, tilt, Gaussian, step, sphere.
- **STL import flow is the user's eventual goal** for arbitrary test objects. Architecturally enabled by Stage 4a's `(shape, pixel_size_mm) → (H, W) float64 mm` contract; any STL importer that produces this shape plugs into the GUI with zero math-layer changes. Implementation deferred to a later stage (after Stage 4b lands the unified scene, and ideally after real hardware lets us calibrate Z-range realistically).
- User clarified during Stage 3 and reaffirmed in Stage 4 planning that **the chapters in the reference folder are the math basis for the inverse fringe projection method, not a template for a thesis the user is writing.** Current deliverable is a working simulation that uses real hardware parameters.
- User wants **the GUI to be updatable with real hardware specs once they arrive.** The architecture supports this cleanly. This is the user's most important Stage 4 acceptance criterion.
- **User raised wanting to mount projector vertical (per professor preference).** Strategy chat surfaced that this requires non-vertical camera to preserve triangulation. Both-angles-as-sliders design supports this exploration and any other configuration the user/prof eventually decides on.

---

## 11. Resolved During the Conversation

- Identified all hardware (camera, lens, projector models)
- Confirmed system is **hybrid in lens type** (telecentric viewing lens, non-telecentric projector lens); arm angles are independent of lens type
- Confirmed inverse grating method (§2.3.4.3 / Chapter 4) is the project's chosen approach
- Measured projector lens position; ~0° vertical optical offset confirmed
- Computed practical FOV, pixel pitch, magnification numbers
- Identified the gap in the existing notebook (missing `project()` function) — **closed in Stage 1**
- Established that hardware-free development is the right starting approach
- Built a roadmap (Stages 0–6) with this-week to-do items
- **Stage 0, Stage 1, Stage 2, Stage 3, Stage 3.5, and Stage 4a completed.**
- Validation philosophy formalized: simulation-only validation has fundamental limits.
- **Stage 4 plan locked at the strategy-chat level.** Five sliders + surface dropdown, locked values, build sequence (3.5 → 4a → 4b), 3D viewer backend (PyQtGraph), resolution (480×640), MockCamera/Projector deferred.
- **Stage 3.5 pre-task executed:** math layer upgrade to two-angle λ_eq (Eq. 2-51), supersedes Stage 2 Decision 3. Commit `658f331`, pushed (not tagged).
- **Stage 4a executed:** 7 task commits + close. Tag `stage-4a-complete`. Full PyQt6 digital twin with surface library, pipeline integration, error overlay, warning banner, and intermediate-stages viewer. 70 tests passing.
- **λ_eq naming convention clarified** during Stage 4a task 4c. Code's `lambda_eq` = `λ_textbook / (2π)`; no physics bug, only naming. Warning banner displays textbook form for user clarity.
- **Stage 4b redesigned** from a "separate lab view" to a "unified 3D scene with hardware bodies added to the existing recovered-surface scene." Cleaner architecture; hardware bodies will provide reference scale.

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

**The user is also good at asking questions whose answers force the strategy chat to catch its own mistakes.** The "telecentric = vertical?" question that surfaced Stage 2 Decision 3's hidden assumption was an example. So was the lab-view redesign question during Stage 4a planning ("isn't the lab view just my recovered view dressed up?") — which surfaced that the strategy chat had been describing two views as if they would be separate, when the user's mental model was always one unified scene. Strategy chat should treat user pushback as a diagnostic, not as resistance.

---

## 13. Working Model with Claude Code (Refined Through Stages 2, 3, 3.5, and 4a)

The handoff pattern that worked across Stage 2's six tasks, Stage 3's two tasks, Stage 3.5, and Stage 4a's seven tasks:

1. **Strategy chat (this assistant) drafts the prompt.** Includes the architectural constraints, the exact tests to write, and the binding decisions Claude Code shouldn't relitigate.
2. **User reviews and pastes into Claude Code (terminal).**
3. **Claude Code summarizes back what it understands before writing code.**
4. **Claude Code implements, runs tests, commits.** One module per commit. Surfaces deviations from spec inline. Magnitude sanity checks before commit when the math output is user-visible.
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

### Stage 4 fresh-session bootstrap

When a new strategy chat or Claude Code session starts after a stage closes:

- Strategy chat: re-upload latest PROJECT_CONTEXT.md and CONVERSATION_SUMMARY.md. Open chat with state-handoff message.
- Claude Code: open a fresh terminal. First prompt: "Read PROJECT_CONTEXT.md and CONVERSATION_SUMMARY.md. Summarize back what we're building, where we are, and what's binding for [Stage X]. Don't write code yet."

The two .md files carry all the context. A handoff .md is redundant when the context files are current.

---

*End of summary. For the structured project context, see PROJECT_CONTEXT.md.*
