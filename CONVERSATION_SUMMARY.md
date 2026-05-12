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

---

## 3. Hardware Identification (Confirmed via Photos)

### Camera: FLIR Blackfly S BFS-U3-13Y3M-C
- Identified from sticker on the camera body (SN: 26048170)
- Monochrome USB3 machine vision camera
- 1280 × 1024 pixels, 4.8 µm pitch, up to 170 fps, global shutter
- 1/2" sensor (active area 6.14 × 4.92 mm)
- C-mount
- Sold by Edmund Optics as stock #36-451
- Python bindings: PySpin (part of Spinnaker SDK from Teledyne FLIR)

### Lens: Edmund Optics #58-259 (TECHSPEC GoldTL Telecentric)
- Identified from "0.09×" and "58259" markings on the lens body
- 0.09× magnification (modern convention)
- 132–182 mm working distance (focusable)
- < 0.2° telecentricity
- 1/2" sensor format
- **Confirmed telecentric**

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
- Claude Code (in VS Code)
- MATLAB + Image Processing Toolbox + Simulink (for cross-validation)
- Chocolatey, Node.js, Git
- MeshLab + CloudCompare (for 3D mesh viewing later)
- GitHub CLI (authenticated)
- Miniconda

### Pending (add to IT list when needed)
- **Spinnaker SDK + PySpin** — needed for FLIR camera; needs admin install

---

## 5. The System Configuration Decision

### How we got there
Initially user asked whether the system was telecentric or not. Through several rounds of clarification:

1. Camera arm telecentric: ✅ confirmed (Edmund Optics lens, hardware-locked)
2. Projector arm: ❌ Pico Genie is not telecentric
3. Future projector: ❓ unknown until hardware arrives
4. Therefore: **HYBRID** is the only honest description
5. Build code for hybrid; it gracefully degrades to symmetric-telecentric if upgraded projector turns out to be telecentric

### Why this matters
- Chapter 2 §2.3.4 derives all math under the **symmetric** non-telecentric assumption (both arms identical)
- Eq. 2-54 (inverse grating period) was derived under that assumption
- For your hybrid system, Eq. 2-54's exact form isn't quite right — but the **method** still works
- The chapter's Eq. 2-54 isn't used directly anyway. **In practice, the inverse pattern is computed from empirical flat-reference calibration**, not from theoretical formulas. This is what Chapter 4 does.

---

## 6. The Calibration-Based Approach (Chapter 4)

The single most important insight from Chapter 4:

> *"It is difficult to measure the system parameters accurately. Instead, the system is calibrated using a standard VLSI step height."* — Chapter 4 §4.3.1

This means you don't need θ, projection-arm M, or the internal projector parameter `a`. The "tilt-flip trick" of §4.3.1 computes the inverse pattern from calibration data alone:

```
1. Project uniform fringes onto flat reference
2. Capture phase-shifted frames, extract unwrapped phase φ₁
3. Fit a tilted plane:        P(x, y) = m_x·x + m_y·y + c
4. Subtract tilt:             curvature = φ₁ − P
5. Flip sign:                 inverse_curvature = −curvature
6. Add tilt back:             φ₂ = P + inverse_curvature = 2·P − φ₁
```

φ₂ is then used to generate the pre-distorted projection pattern (Eq. 4-5). When projected through the same biased system, the pre-distortion and the system bias cancel. Result: clean uniform fringes (Eq. 4-9), regardless of what the underlying system parameters actually are.

Chapter 4 also covers:
- Repeating the bias measurement 50× with phase offsets and surface position changes for averaging
- Vertical (height) calibration: measure a known step, compute λ_eq empirically
- Lateral (xy) calibration: image a known grid scale, compute µm/pixel

---

## 7. State of the Project Through Stage 2

### Notebook (Stage 1 work, frozen as historical reference)

The user's `Fringe_Projection_Python.ipynb` implements the math and includes the Stage 1 simulation-loop and strengthened validations:
- Phase shifting, unwrapping, tilt fitting, tilt-flip correction, height reconstruction
- Recovers a synthetic Gaussian to ~10⁻⁵ precision
- `project()` function added (Stage 1.1) — Taylor-approximation forward model
- Roadmap validations 1.2 / 1.3 done (consistency check + curvature cancellation on flat reference)
- Strengthened validations 1-S.1 / 1-S.2 / 1-S.3 done (Taylor error bounded, parameter scaling verified, limit cases pass)

The notebook is frozen as the source of truth for the regression fixture `tests/regression_data.npz`, which Stage 2 modules are tested against.

### Validation philosophy arrived at during Stage 1

The user pushed back hard on tests that compare two quantities both derived from the same analytical formula — correctly identifying that such tests can't fail in simulation regardless of whether the underlying physics is right. Key insight:

> *Simulation validation can only catch bugs where the test path uses different logic than the thing being tested. Tests that share the same formula on both sides are tautological.*

This led to:
- Recognition that Stage 1.2 (`project(uniform) == phi1`) is operationally a typo-guard, not a physics test (still kept because the roadmap requires it).
- Recognition that an originally drafted Stage 1-S.4 cell (end-to-end recovery via explicit `project()` chain) was redundant with what cells 14–20 already validate, since the same analytical bias formula appears on both sides of the cancellation in simulation. **It was deliberately omitted.** The strongest possible test of this kind requires real hardware (Stage 6), where the projector's actual bias may differ from the calibration-extracted bias.
- The Stage 1-S markdown summary explicitly documents this omission so a thesis examiner doesn't wonder if the test was forgotten.

Real validation comes from (a) cross-implementation comparison (MATLAB, Three.js), (b) real hardware, or (c) analytical limit checks. Stage 1 covers (c). Stage 2's regression test will start (a). Stage 6 brings (b).

### Stage 2 — Refactor into Python modules (Complete)

Six task-prompts handled one at a time; one module per commit (plus chores). Final state: 12 tests, all passing, closing commit `b5b7342` tagged `stage-2-complete`.

| Task | Module(s) | What landed |
|---|---|---|
| 2.1 | `geometry.py` + scaffolding | `Geometry` Protocol, `HybridGeometry` (default), `SymmetricGeometry` (cross-check). All-arg constructors. Regression fixture script + `tests/regression_data.npz`. |
| 2.2 | `synthetic_fringes.py` | `project(input_phase, geometry, model='taylor')` + `synthesize_psi_stack`. Architectural lock: `project()` does not read `λ_eq`. |
| 2.3 | `phase_shifting.py` + `unwrapping.py` | Generalized N-step PSI via `arctan2(-Σ I sin δ, Σ I cos δ)`. Operational `unwrap_2d` (row-then-column np.unwrap) + alternative `unwrap_2d_skimage`. |
| 2.4 | `calibration.py` | `fit_tilt_plane` (2D lstsq), `compute_inverse_phase` (tilt-flip, Eq. 4-7). |
| 2.5 | `reconstruction.py` | `phase_to_height` (dispatcher to geometry), `recover_object_height` (full pipeline composition). |
| 2.5b | `calibration.py` (hotfix) | Added `fit_tilt_line_1d` to lift inline polyfit out of test code; documented 1D-vs-2D use-case split. |
| 2.6 | `tests/test_pipeline_synthetic.py` | End-to-end integration test through public APIs only. `std_err < 2 × BASELINE_STD` and `H_rec0` matches fixture to `ATOL_PIPELINE`. |

### Stage 2 architectural decisions

These were made during refactor and bind future stages (also mirrored in PROJECT_CONTEXT.md Section 12):

- **Module order swapped from PROJECT_CONTEXT Section 11**: calibration before reconstruction, so tests follow data flow.
- **`project()` is `λ_eq`-independent**, locked by `test_project_is_lambda_eq_independent` (`atol=1e-15`). Both Geometry types produce bit-identical bias output. Stage 3's exact-form forward model must preserve this.
- **Two non-interchangeable tilt fits in `calibration.py`**: `fit_tilt_plane` (2D, flat refs) vs `fit_tilt_line_1d` (1D, object self-cal). Diverge by ~4e-5 in height on off-center bumps.
- **`recover_object_height` is operand-agnostic on `phi_calibration`** — caller decides self-cal vs cross-cal.
- **Integration test does NOT close the inverse-grating loop.** Same tautology limit as Stage 1's omitted 1-S.4. Real validation needs cross-impl or hardware.

### Tooling / housekeeping in Stage 2

- Two-tier regression tolerance: `ATOL_ANALYTICAL = 1e-12` for analytical arrays, `ATOL_PIPELINE = 1e-8` for unwrap-pass-through outputs. Stops NumPy minor-version drift from breaking the suite spuriously.
- `.npz` (not pickle) for regression fixtures — version-portable.
- `.gitattributes` with `* text=auto eol=lf` to suppress Windows CRLF warnings.
- `environment.yml` pins runtime + dev dependencies (Python 3.10, NumPy 2.2.6, pytest, etc.).
- Two git-history rewrites at Stage 2 close: (a) purge `FPP Thesis/` PDFs from history (kept on disk, gitignored — Claude Code reads them locally, never pushed); (b) change commit authorship from auto-derived HBKU institutional identity to `Husam Al Ardah <152923640+HusamArdah@users.noreply.github.com>` (personal GitHub no-reply alias). Repo pushed to private GitHub: `HusamArdah/fringe-projection-3d`.

---

## 8. Open Questions for Supervisor

Non-blocking — proceed on best assumptions and ask in parallel.

1. Is the upgraded projector telecentric?
2. **Still open:** What's the simplified λ_eq formula for the hybrid case (telecentric viewing + non-telecentric projection)? Eq. 2-51 reduces to `Mp / tan(θ_projector)` when θ_camera → 0. Or skip the formula entirely and use empirical step-height calibration per Chapter 4 §4.3.1.
3. Software post-correction or hardware pre-correction?
4. Number of phase-shift steps (4 vs. 8)?
5. Calibration artifacts available in lab?
6. GUI framework preference?

---

## 9. Theoretical Insights From the Walkthrough

The user worked through the chapter step by step and these were the conceptual landmarks:

- **u₃ in Eq. 2-41 is a sensor-side displacement** caused by object height. We don't measure u₃ directly — we measure phase, which is a sensor-side displacement encoded as a cosine argument shift.

- **The /M factor in Eq. 2-49 is simple specifically because the system is telecentric** — telecentric magnification is constant everywhere, so position-dependent stretching factors collapse. In non-telecentric systems, M varies with position; the chapter handles this with the `(1 − x₁·tan θ/a)` factor.

- **`x₁` is a coordinate on the projector's grating plane**. For a digital projector (DLP), x₁ is just the column index of each pixel relative to the optical axis.

- **Once the system is set up, θ is fixed.** Only x₁ varies across the projected pattern, and h(x₁) varies across the surface. This is why p₂(x₁) varies across the inverse grating but everything else is constant.

- **Eq. 4-7 is structurally Eq. 4-2 with the curvature sign flipped** — that's literally what the tilt-flip trick does.

- **Custom grating is needed for this project** because the projector is non-telecentric. Telecentric viewing only handles the camera side; projector-side bias requires either a telecentric projector or the inverse grating method.

### Additional insights added during Stage 1 walkthrough

- **The notebook's `phi1` vs `phi1_unwrapped` parallel structure** — `phi1` (analytical) is the ground truth; `phi1_unwrapped` (intensity → PSI → wrap → unwrap) is the simulated measurement. Cell 8 compares them. This pattern repeats for the object: `phi3` (analytical) vs. recovered phase from cells 17–18.

- **Best-fit tilt absorbs both real tilt and a bit of curvature** — `np.polyfit(x, phi1, 1)` does not recover the analytical `2π/p₁` slope; it returns whatever slope minimizes squared error across the whole biased profile. The resulting `bias_2d` and `phi2` therefore have linear residuals that are not strictly the "true tilt," but the curvature is captured correctly, which is the only part that matters for the inverse-grating cancellation. Downstream tilt removal absorbs any linear residual.

- **The `λ_eq = (p1·M) / (4π sin θ)` formula in cell 14 is the symmetric form (Eq. 4-11), not the hybrid form.** The strict hybrid formula (Eq. 2-51 with θ_camera = 0) gives `Mp / tan(θ_projector)`. The simulation still converges to ~10⁻⁵ recovery because one consistent θ is used everywhere — the recovery is self-consistent, not physically faithful to the hybrid hardware. This will be corrected in Stage 2.

- **Cell 14's `K` constant implicitly assumes a telecentric receiver.** No `capture()` function exists to mirror `project()`. The camera arm is treated as a perfect pass-through, which is correct for the Edmund Optics telecentric lens but should be made explicit in Stage 2 docstrings.

- **OpenCV is not needed for the fringe analysis math** — PSI, unwrap, tilt fitting, height conversion all live in NumPy. OpenCV's role will be image I/O, ROI masking, lateral calibration (grid detection), and display helpers. `skimage.restoration.unwrap_phase` is the recommended robust unwrap option per the roadmap.

---

## 10. Project Conversations Note

- User had a friend building a separate **Three.js 3D simulation** of the lab geometry (separate from the Python pipeline). The `Projector_Geometry_Summary.docx` was prepared for that collaborator. The Three.js work is **complementary**, not duplicative — it's a geometric visualization of the physical setup; the Python work is the operational measurement pipeline.
- User plans to add a virtual representation of the setup (live sliders for θ, a, M, etc. that drive the simulation and update results) at the end of the roadmap. Stage 4's PyQt6 GUI provides the foundation; the live-update slider tabs are a natural extension built after Stage 4 with mock hardware in place.
- User plans to add a **test-surface library** (`src/test_surfaces.py`) as part of the slider GUI work. Pure heightmap generators: flat, tilt, Gaussian, step, sphere cap, multi-bump, file-loaded, and crucially a **solder-bump-array generator** (Chapter 5 application). The architecture already supports this — the pipeline consumes any `(H, W)` heightmap via `geometry.height_to_phase`. Decision deferred to Stage 4+.

---

## 11. Resolved During the Conversation

- Identified all hardware (camera, lens, projector models)
- Confirmed system is **hybrid** (telecentric viewing, non-telecentric projection)
- Confirmed inverse grating method (§2.3.4.3 / Chapter 4) is the project's chosen approach
- Measured projector lens position; ~0° vertical optical offset confirmed
- Computed practical FOV, pixel pitch, magnification numbers
- Identified the gap in the existing notebook (missing `project()` function) — **closed in Stage 1**
- Established that hardware-free development is the right starting approach until mounting hardware arrives
- Built a roadmap (Stages 0–6) with this-week to-do items
- **Stage 0, Stage 1, and Stage 2 completed.** Notebook has the `project()` function, all roadmap-mandated validations, and three independent strengthened validations. Stage 2 refactored the notebook into 6 tested src/ modules with a 12-test regression suite plus end-to-end integration test; closing commit `b5b7342` tagged `stage-2-complete` and pushed to private GitHub remote.
- Validation philosophy formalized: simulation-only validation has fundamental limits (tautology if same formula appears on both sides); meaningful end-to-end testing requires hardware or cross-implementation.

---

## 12. Tone & Style Notes

The user prefers:
- **Short concrete answers** over long expositions
- Step-by-step physical reasoning, not equation walls
- Honest disagreement when something's hand-wavy
- One thing at a time
- Practical code suggestions kept minimal

The user pushes back when something feels redundant or tautological. This is a strength — Stage 1 ended up with a smaller, cleaner validation suite than originally proposed because of it.

---

## 13. Working Model with Claude Code (Established During Stage 2)

The handoff pattern that worked across Stage 2's six tasks:

1. **Strategy chat (this assistant) drafts the prompt.** Includes the architectural constraints, the exact tests to write, and the binding decisions Claude Code shouldn't relitigate.
2. **User reviews and pastes into Claude Code (terminal).**
3. **Claude Code summarizes back what it understands before writing code.** Catches misunderstandings cheaply.
4. **Claude Code implements, runs tests, commits.** One module per commit. Surfaces deviations from spec inline with magnitude estimates rather than silently picking defaults.
5. **User pastes Claude Code's diff + test output back to strategy chat for review.** Strategy chat flags architectural smells, scope creep, or weak tests.
6. **User decides on adjustments.** Sometimes leads to follow-up commits (e.g., Stage 2.5b lifted inline test logic into `calibration.py`).

Belt-and-suspenders verifications the user does in their own terminal (not Claude Code's) before any destructive operation:
- Independent verification of git rewrites with own queries.
- Confirmation that working-tree files match expectations after history operations.

This separation kept Stage 2 honest: every commit was reviewed twice (Claude Code self-checks during implementation, strategy chat second-pass), and every destructive operation had a manual confirmation step before authorization.

---

*End of summary. For the structured project context, see PROJECT_CONTEXT.md.*
