# Fringe Projection Project — Context for Claude Code

> **Read this file first at the start of every session.** It captures the full project context, hardware setup, theoretical framework, design decisions, and roadmap. Treat it as the source of truth until told otherwise.

---

## 1. What This Project Is

A **fringe projection 3D measurement system** being built in a research lab. The goal is to recover the height profile of test objects by projecting sinusoidal fringe patterns onto a surface, capturing phase-shifted images with a camera, and processing the captured fringes to extract a height map.

The project is based on **Chapter 2 (theory)** and **Chapter 4 (practical implementation)** of a thesis by Ayman Samara. The thesis lives in the `reference/` folder.

The user's deliverables:
1. A **Python user interface (UI)** that controls the experiment end-to-end (pattern generation, projection, capture, calibration, processing, visualization).
2. The **math/processing core** behind the UI.
3. Eventually: **integration with real hardware** in the lab.

The user has an existing Jupyter notebook (`notebooks/Fringe_Projection_Python.ipynb`) that implements an end-to-end synthetic simulation. **It works** — recovers a Gaussian bump from simulated fringes with mean error ~10⁻⁵ after DC alignment. Stages 1 through 5, plus **Stage 6 Phase A→B.3a** (the inverse-FPP reconstruction pipeline + the physical beyond-Nyquist wall + the headline dynamic-range showcase, see Section 12), have been completed. The notebook is the starting point for refactoring, not a thing to start over.

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

### Incoming projector — Wintech PRO4500 (specs captured; integration is Stage 7)

The upgraded projector (long-awaited) is the **Wintech PRO4500 Production Ready Optical Engine** — a TI DLP LightCrafter 4500-based industrial DLP projector. The physical unit is in the lab (lab-room access pending). The spec brochure (`docs/Wintech_PRO4500_Brochure.pdf`) + the TI DMD datasheet (DLPS028) give us the optical parameters; the swap replaces the Pico Genie's optical specs in the model. **This is Stage 7 work — captured now so nothing is lost; NOT acted on until after Phase B (B.3b/B.4). User input edit: This is a task user will be relaying to teammate Ilyas. since project is in GIT and he has access to the project as well.**

**Solid specs (ready to use at swap):**
- **DMD:** TI DLP4500, 0.45" WXGA, **912 × 1140 micromirrors**, **7.6 µm micromirror pitch**, ±12° mirror tilt, **92% fill factor**, optics optimized 381–650 nm.
- **0% offset optics** — the optical axis is centered (NO throw offset). This *replaces* the Pico Genie's ~12° horizontal-offset guess and **simplifies** the projector-arm geometry (no keystone-inducing offset to model).
- **Field-swappable lenses** with a discrete working-distance → FOV → projected-pixel-size table (460 nm / 3D-measurement column):

  | Working distance | Field of view | Projected pixel size |
  |---|---|---|
  | 92 mm | 65.6 × 41 mm | 50 µm |
  | 184 mm | 131.2 × 82 mm | 100 µm |
  | 700 mm | 400 × 250 mm | 305 µm |

  Throw is *derivable per lens* (FOV width / WD) — better than a single nominal throw ratio.
- **Pattern rates:** 2,880 Hz binary / 120 Hz 8-bit grayscale streaming (mini-HDMI); up to 4,255 Hz binary from 32 MB onboard memory. Relevant to the **real-time closed-loop** framing (the paper's "Real-Time / Adaptive" novelty, Stage 7).
- **Body dimensions:** 210 × 84 × 54 mm.

**RESOLVED — diamond-pixel layout is a non-issue for fringe projection.** The "diamond pixel" array means the columns of each odd row are offset by half a pixel from the even rows (a brick-laid / quincunx stagger), whole array diagonally oriented (TI DLPS028, DLPU011). This stagger is **sub-pixel (½ of 7.6 µm at the DMD)** and matters only for single-pixel-width hard lines (vertical/horizontal/diagonal). A fringe pattern is a smooth low-frequency sinusoid spanning many DMD pixels per cycle, so the half-pixel row stagger **averages out completely** in the projected sinusoid. **Model the PRO4500 as a plain 912 × 1140 rectangular grid** — the diamond stagger does NOT need modelling for fringe projection.

**The swap is mostly MATH-LAYER, not a rewrite (the key realization).** The projector's measurement role is driven by `theta_projector` (the sweep slider — a free GUI parameter, NOT a physical-mount measurement) + the optical specs above. So the optics swap keeps the existing sweep working with no mount data. The swap likely **reparameterizes** the projector controls: the current free `projector_throw_mm` slider becomes a **lens selector** (or a throw constrained to the chosen lens's WD), since the PRO4500 expresses naturally as "pick a lens → that fixes the WD/FOV/pixel triple." Removing the free-throw slider and adding a lens selector is the expected, clean kind of reparameterization the §7.11 (parameters-not-mesh) architecture is built for — "remove what doesn't apply, add new adjustable parameters."

**Two open items — both provisional-now / refine-later, NEITHER blocks the swap:**
1. **Lens choice** — which of the three lenses to run. A *decision* (depends on specimen size / standoff), not a measurement. At swap: pick a sensible provisional default (e.g. 184 mm / 131×82 mm); refine to the final choice with a one-parameter edit whenever decided. The measurement works the whole time; only the FOV/throw/`p` numbers shift on re-pick.
2. **Mount geometry (body-frame lens-center offsets)** — **cosmetic only** (§7.11: where the projector body + cone render in the 3D scene; provably cannot change recovered output). At swap: placeholder body position → sweeps and measures correctly; refine to the real position from a lab measurement (unit in hand, lab-room access pending). Non-blocking.

**TENTATIVE mounting plan (NOT finalized) — projector at 0°, camera at the angle.** The likely physical arrangement inverts the current sim: **projector directly above the surface at 0°** (minimizes projection-arm perspective curvature → less to correct) with the **telecentric camera arm carrying the triangulation angle**. ⚠️ **Flag for the swap chat:** the entire inverse-FPP/nulling story (§7.14) is premised on the *projector* carrying the bias the inverse grating corrects. If the projector goes to 0° and the camera carries the angle, the bias-source shifts arms — re-examine whether/how the inverse-grating correction still applies (it may simplify, or move). Revisit when the placement is finalized; do not lock the model to either arrangement before then.

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
│   ├── pattern_generator.py        # Stage 6 A.1 — inverse_grating_phase (reuses calibration.compute_inverse_phase, the fixture-locked tilt-flip). No longer a stub.
│   ├── sampling.py                 # Stage 6 A.0.2 — pixel-area sampling model: contrast_envelope(phase, fill_factor) → sinc fade on local |∇φ|/2π (cycles/pixel). Pure NumPy.
│   ├── pipeline.py                # Stage 4a — end-to-end pipeline composition; Stage 6 added run_inverse_fpp (A.2) + run_straight_fringe (B.1), selfcal_fit param (B.2), noise_sigma/rng (A.4)
│   ├── io_utils.py
│   ├── test_surfaces.py           # Stage 4a — heightmap generators; Stage 6 B.3a added make_steep_dome (math-pixel convention, crosses Nyquist)
│   ├── scene.py                   # Stage 4b — mesh + wireframe builders (pure NumPy)
│   ├── scene_compose.py           # Stage 4b — pose composition layer (arm transforms); Stage 5 (4d.10) added y_offset_mm + recess_mm to cone_local_to_world_transform
│   ├── stl_loader.py              # Stage 4c — STL → heightmap loader (pure NumPy, peer of test_surfaces.py)
│   └── gui/                       # Stage 4a/4b — PyQt6 GUI package
│       ├── __init__.py
│       ├── __main__.py            # `python -m src.gui` entry
│       ├── app.py
│       ├── main_window.py         # Stage 5 added: lab-view XOR toggle, Hardware Coordinates panel, numeric slider entry (LabeledFloatSlider spinbox), Recovered Surface tab wiring, error-UI migration
│       ├── surface_preview.py     # SurfacePreview + HardwareScene host + ErrorColorbar; Stage 5 (4d.4) render core extracted to surface_render.py
│       ├── surface_render.py      # Stage 5 (4d.4) — shared render core (pure: centered_coords, apply_heightmap, error_colors, ERROR_COLORMAP). Both SurfacePreview and RecoveredComparisonView call it.
│       ├── coordinate_grid.py     # Stage 5 (4d.3) — labeled XYZ mm grid (pure compute_axis_ticks + thin CoordinateGrid class)
│       ├── comparison_view.py     # Stage 5 (4d.4) — RecoveredComparisonView: solid recovered + translucent ground-truth over the labeled grid
│       ├── hardware_scene.py      # Stage 4b — HardwareScene class + compute_arm_transforms; Stage 5 (4d.10) projector lens-anchor + ProjectorLensOffset; (4d.11) arm_lens_front_world helper
│       ├── clip_detection.py      # Stage 4b — pure NumPy clip-detection; Stage 5 (4d.12) 6th check (cross-arm optical obstruction) + bounded point-in-volume predicates
│       ├── stages_view.py         # 2×3 grid of pipeline-stage images
│       └── stl_browser.py         # Stage 4d — Browser tab (whole-STL + minimap + windowed slice + FOV overlay); Stage 5 (4d.7) panel swap (whole-STL big-right, slice small-bottom-left)
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
│   ├── test_hardware_scene.py     # Stage 4b — arm transforms integration; Stage 5 (4d.10/4d.11) lens-anchor + arm_lens_front_world tests (12 cases)
│   ├── test_clip_detection.py     # Stage 4b — collision + coverage advisories; Stage 5 (4d.12) obstruction + bounded-predicate tests
│   ├── test_stl_loader.py         # Stage 4c — 14 cases (synthetic in-memory meshes via tmp_path)
│   ├── test_stl_loader_full_scale.py # Stage 4d — full-scale loader (oversized STL → (heightmap, origin))
│   ├── test_main_window.py        # Stage 4d sub-task 1.5 — module-level invariants (no GUI construction)
│   ├── test_main_window_stl.py    # Stage 4c+4d — GUI-level tests; Stage 5 added lab-view-toggle, Recovered-Surface-tab, color-by-error-gating, panel-swap tests
│   ├── test_coordinate_grid.py    # Stage 5 (4d.3) — 27 cases (pure tick logic + GL-assembly)
│   ├── test_surface_render.py     # Stage 5 (4d.4) — render-core helpers (centered_coords, apply_heightmap, error_colors)
│   ├── test_comparison_view.py    # Stage 5 (4d.4) — RecoveredComparisonView construction + visibility toggles
│   ├── test_labeled_float_slider.py # Stage 5 (4d.9) — numeric spinbox entry, snap/clamp, slider↔spinbox sync
│   ├── test_hardware_coords_cli.py  # Stage 5 (4d.11) — CLI prints the same numbers as arm_lens_front_world
│   ├── regression_data.npz
│   └── conftest.py
├── scripts/                       # standalone runnable scripts
│   ├── stage4c_smoke.py           # Stage 4c — GUI smoke harness (verify | Flat | Gaussian | STL). Verify mode asserts Gaussian amp cap == 120.0.
│   ├── stage5_grid_smoke.py       # Stage 5 (4d.3) — coordinate-grid legibility smoke (grid | surface)
│   ├── stage5_comparison_smoke.py # Stage 5 (4d.4) — comparison-view smoke (both-on | recovered-only | gt-only)
│   └── hardware_coords.py         # Stage 5 (4d.11) — CLI: print camera + projector lens-center world coords
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
| **4c** | **STL import for arbitrary specimens: surface dropdown reduced to (Flat, Gaussian, STL file...); pure-NumPy STL→heightmap loader; QFileDialog flow; hard-reject for oversized STLs** | No | ✅ Done |
| **4d** | **STL Browser for full-scale specimens: windowed FOV selection on oversized parts via minimap + draggable cyan FOV rectangle; live windowed-slice preview; Commit FOV; QTabWidget refactor (3D Scene / Pipeline Stages / STL Browser)** | No | ✅ Done |
| **4d follow-ups** | **GUI review pass: STL lift convention reset to visible-envelope, off-part edge-extend with masked output, SAT body-overlap, 2 mm cone-coverage tolerance, ABSURDLY_LARGE_MM raised to (500, 500, 120).** | No | ✅ Done |
| **5** | **Lab-view + Recovered-Surface refactor + hardware-coordinate readout + cross-arm obstruction advisory. 11 commits (4d.2–4d.12). Lab-view ground-truth/recovered XOR toggle; new "Recovered Surface" 4th tab (solid recovered + translucent ground-truth over a labeled XYZ mm grid, error stats/colormap migrated here); STL Browser panel swap; numeric slider entry; projector lens-center anchored at origin-when-vertical; live Hardware Coordinates panel + CLI; cross-arm optical-obstruction advisory.** | No | ✅ Done |
| **6 (A→B.3a)** | **Inverse-FPP reconstruction + physical beyond-Nyquist wall + headline showcase. Phase A: scale bridge (A.0.1), pixel-area sampling fade (A.0.2), real inverse-grating generator (A.1), closed inverse-FPP loop (A.2/A.2b), additive read-noise model (A.4). Phase B: flat-reference nulling before/after on the Recovered Surface tab (B.1), golden-part reference + 2D self-cal (B.2), beyond-Nyquist steep-dome headline showcase (B.3a). 9 commits, 322 tests passing at close.** | No | ✅ Done |
| 6 (B.3b) | Steep STL part — the realistic AM demonstration (B.3a's headline on a believable part) | No | — |
| 6 (B.4) | Deterministic, serializable reference the hardware phase validates against | No | — |
| 7 | Real hardware integration with mounting + new projector (Camera/Projector protocols + mocks → PySpin/RealProjector; real-time closed loop = the paper's novelty) | Yes | — |

> **Stage numbering note:** the Stage 5 commits are prefixed `Stage 5 (4d.X)` for X = 2…12. The `4d.` is a historical continuation of the Stage 4d sub-task numbering (Stage 5 grew directly out of the Stage 4d follow-up parking lot); the stage itself is **Stage 5**, tagged `stage-5-complete`. Hardware familiarization/integration shifted to Stages 6/7.


> **Sequencing decision (post-Stage-5): web port DEFERRED until hardware integration is complete.** The web port (parking-lot #6 — HTML/Three.js re-implementation for larger screens and shareability) is explicitly held off until the PyQt6 reference model is finalized against real hardware. Rationale: the web port is a re-implementation of a *reference*; finalizing the reference first means porting it once, not porting a moving target. The new projector is arriving sooner than expected, which makes hardware integration (Stages 6/7) the immediate priority — it will touch geometry, possibly the math constants, and the mock→real arm path, all of which the web port would otherwise have to absorb mid-port. **Order is therefore: Stage 6/7 (hardware familiarization + integration) → THEN web port → aesthetics last.** Nothing in the model changes until the projector is physically in hand; this is a sequencing note, not a code change.
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

**Stage 5 extension:** `src/gui/surface_render.py` (render core) and `src/gui/coordinate_grid.py` (pure `compute_axis_ticks`) and `hardware_scene.arm_lens_front_world` continue this — the pure pieces are headlessly unit-tested; the Qt assembly is a thin layer on top. The `arm_lens_front_world` helper in particular is pure NumPy and is the single source of truth shared by the GUI Hardware Coordinates panel and the `scripts/hardware_coords.py` CLI.

### 7.3 — Hardware behind a thin interface
When hardware is added, define abstractions like:

```python
class Camera(Protocol):
    def capture(self, exposure_ms: float) -> np.ndarray: ...

class Projector(Protocol):
    def display(self, pattern: np.ndarray) -> None: ...
```

Initial implementations: `MockCamera` (returns synthetic frames), `MockProjector` (saves PNGs / writes to extended display). Real implementations: `FLIRCamera` (PySpin wrapper), `RealProjector` (extended display).

**Note (Stage 4 deferral):** the `Camera` / `Projector` protocols and their mock implementations are deliberately deferred to Stage 6/7, not Stage 4/5. The Stage 4a/4b/5 GUI calls math modules directly. Rationale: the hardware shape isn't finalized (upgraded projector pending), so designing protocols against unknown specs is premature. When real hardware arrives, the protocols get designed against actual SDK calls and frame formats.

### 7.4 — Honest scale in the 3D scene (Stage 4b)

`Z_EXAGGERATION = 1.0` in `surface_preview.py`. The 3D scene renders the recovered surface at real geometric scale alongside the hardware bodies (also at real scale). This makes the visual scene a **geometric ruler** — when the user sees the surface touch the (graying) lens, that literally means the surface height equals the clip-detection threshold. Any exaggeration would desync the visual from the clip math.

Trade-off accepted: sub-mm specimens visually vanish in the 3D dome at 1×. The error overlay (diverging colormap, on the Recovered Surface tab since Stage 5) is the tool for fine surface variation; the 3D dome conveys macro shape only.

### 7.5 — Banner vs gray semantics (Stage 4b, extended Stage 5)

The clip-detection system distinguishes two failure modes:

- **Gray hardware override** = physical collision (camera/projector lens intersects surface plane, or assemblies overlap). Pose is not physically buildable.
- **Banner only, no gray** = measurement incompleteness or obstruction. Pose is buildable, but reconstruction is compromised.

The math pipeline keeps running in both cases. The user sees the warning but the simulation produces a heightmap regardless. This is by design — the digital twin should let users explore "silly" rigs and see what the math does in those poses.

**Stage 5 (4d.12) added a third banner-only category:** cross-arm optical obstruction (one arm's hardware sits in the other arm's optical volume between the lens and the surface). Like the coverage advisories, it is banner-only — the rig is buildable; the measurement is just obstructed. See 7.9.

### 7.6 — Lift convention: visible envelope, not global mesh (Stage 4d follow-up)

`stl_loader.load_stl_heightmap()` and `load_stl_heightmap_full_scale()` lift the rasterized heightmap so the **lowest camera-VISIBLE point** sits at z=0, not the global mesh minimum. The visible point is the minimum of the per-pixel max-z upper envelope — the lowest surface a fringe-projection camera would actually see from above.

Rationale: FPP only measures the visible top surface. A closed solid's bottom shell is discarded by the max-z envelope (camera can't see it), so using the global mesh minimum to define z=0 puts the visible surface artificially above the stage. The visible-envelope convention places the part's visible base flush with z=0, matching what a real measurement would produce.

Consequence: a flat-topped box collapses to a single z=0 plane (zero relief), which is honest. A closed sphere recovers as a half-dome with the equator at z=0 and apex at radius R (not diameter 2R as the earlier convention produced).

The earlier convention (lift by global mesh-Z minimum) was set in Stage 4c sub-task 2 and reset to visible-envelope minimum in the Stage 4d follow-up GUI review.

### 7.7 — Browser-mode off-part padding contract (Stage 4d follow-up)

In Browser mode, the FOV slice (`_extract_fov_slice`) fills cells outside the part's XY footprint with 0.0 (bare stage). For the math pipeline, this creates a discontinuity at the part edge that contaminates the self-cal tilt fit.

The fix (commit `fb19e0c`): **feed the pipeline an edge-extended heightmap, then mask the recovered output's off-part cells back to 0.0 before display.** The user sees physical truth (off-part = flat stage at 0) while the math sees a smooth input. Browser mode only; small-part direct STL, Flat, and Gaussian are unaffected.

### 7.8 — Clip-detection tolerance philosophy (Stage 4d follow-up)

- **Projector-cone coverage check:** 2 mm advisory tolerance (`_CONE_COVERAGE_TOLERANCE_MM`). Real projectors have gradual edge falloff vs. the math's sharp boundary.
- **Camera viewing-prism check:** stays exact (no tolerance). A parallel-sided telecentric prism doesn't soften at its bounds.
- **Body-overlap check:** exact OBB intersection via SAT (no tolerance). Strict separation, no epsilon — touching counts as collision.

### 7.9 — Cross-arm optical obstruction (Stage 5, 4d.12)

A sixth clip-detection check, banner-only. Fires when one arm's hardware sits inside the **other** arm's optical volume **between the lens and the surface** — blocking the beam / line of sight even though the bodies are not touching (a distinct failure mode from body-overlap collision). Two independent directional advisories:
- `camera_in_projector_cone` — camera assembly (body + lens) blocks the projected light.
- `projector_in_camera_fov` — projector assembly blocks the camera's line of sight.

Three design points, all in `clip_detection.py`:
- **Edge-sampling, not corner-only.** A long thin box (the 200 mm camera lens) can spear a convex volume with all 8 corners outside but the middle inside. The check samples ~7 points along each of the 12 box edges (both volumes are convex, so interior edge samples reliably catch a spearing box). Corner-only would silently miss the camera-lens case.
- **Along-axis bound.** Only hardware between the lens and the surface obstructs. Prism: `0 ≤ s ≤ WD`. Cone: `0 ≤ s ≤ throw`. This excludes hardware *behind* the lens or *beyond* the surface, which is laterally inside the (unbounded) coverage volume but does not actually block anything. Implemented by extracting the per-point INSIDE mask into bounded predicates (`_points_in_prism` / `_points_in_cone`, `axial_max` param); the coverage checks (4–5) call them with `axial_max=inf` and are behavior-preserving.
- **Cross-only pairing.** Camera assembly → projector cone; projector assembly → camera prism. Never an arm against its own volume (its own lens sits at the apex/origin of its own volume and would always self-trigger).

### 7.10 — Lab view vs Recovered Surface tab: live exploration vs quantitative comparison (Stage 5)

The 3D Scene tab (lab view) and the Recovered Surface tab serve two different purposes, deliberately separated:

- **Lab view (3D Scene tab)** = "what the camera sees, in the physical rig." Shows the hardware bodies + cones + one surface at a time. In STL mode a two-radio XOR toggle picks **ground truth** or **recovered** (never both, never neither; defaults to ground truth — "honest by default"). No XYZ grid. Live exploration while adjusting setup.
- **Recovered Surface tab** = "quantitative comparison of one measurement." Solid opaque recovered surface + translucent ground-truth overlay, both over a **labeled XYZ mm grid** (unique to this tab). Tab-local checkboxes toggle each surface; a "Color by error" checkbox recolors the recovered surface by signed error (CET-D1 blue-white-red) and render-suppresses the ground-truth overlay. Error stats (mean/std/max-abs/RMS) + colorbar live here. Input is any `(H, W) float64 mm` heightmap — synthetic now, real hardware capture later.

Rationale: the recovered surface is a math output that legitimately changes when angles/parameters change; defaulting the lab view to ground truth keeps it honest about "what the camera sees," while the 4th tab is the dedicated home for "what the math produced vs. what it should have."

### 7.11 — Visualization layer is decoupled from the math pipeline (confirmed Stage 5)

The hardware bodies, arm transforms, lens positions, cones, and clip-detection are the **visualization / scene layer**. The math pipeline (forward model, λ_eq, phase recovery, recovered heightmap, pipeline stages) is driven by **slider VALUES** (θ_projector, θ_camera, distances), NOT by mesh placement. The two paths from the sliders never cross. This was relied on explicitly in Stage 5 (4d.10): moving the projector body 17.5 mm to anchor its lens at the origin is purely cosmetic and cannot change the recovered output. Any future change to body/lens/cone placement is visualization-only.

### 7.12 — The object-space scale bridge is labeling-only (Stage 6 A.0.1)

The simulation core runs in **notebook pixel-space** (`p`, `M`, `a`, the carrier, `X = arange(W)` are all pixel-unit; live values `M=1`, `p=40`, `a=2000`). The scale bridge is three canonical constants in `geometry.py` — `CAMERA_PIXEL_PITCH_UM = 4.8`, `CAMERA_MAGNIFICATION = 0.09`, `OBJECT_SPACE_UM_PER_PIXEL = 4.8/0.09 ≈ 53.33` — that exist **solely to convert pixel counts to microns for human display** (e.g. "the ~2-px sampling wall sits at ~107 µm object-space"). They are **never read by any math path** (carrier, λ_eq, `project()`, `synthesize_psi_stack`). An enforceable no-leak test (`test_no_leak_scale_bridge.py`) forbids these constant names from appearing in `synthetic_fringes.py`, `pipeline.py`, or `sampling.py` — so µm cannot silently leak into the math.

**Why a bridge, not a native-metric rewrite (the recon-settled decision):** the height-boundary core (λ_eq, `height_to_phase`, `phase_to_height`) is already unit-polymorphic — it scales cleanly with whatever unit `p` carries. But the `(2π/p)·X` carrier couples `p` to the integer pixel grid `X`, so going native-metric would require changing the X grid, which invalidates every `arange`-based closed-form expected value and **reopens the full 271-passing core + regenerates the regression fixtures**. The bridge touches **zero** existing tests (purely additive). Reopening a validated core to avoid carrying one documented px↔µm scale is a bad trade; the bridge is the project's standing approach. (The dead `pixel_pitch_um = 53.0` field on both geometries was retired and redirected to the canonical constant — one source of truth, value now the derived 53.33.)

### 7.13 — The physical beyond-Nyquist wall: sampling fade × read noise (Stage 6 A.0.2 + A.4)

A real camera pixel integrates light over its finite area; it does not point-sample a continuous sinusoid. `sampling.contrast_envelope(phase, fill_factor)` models this as a **sinc contrast envelope keyed off the LOCAL phase gradient** `f_local = |∇φ|/(2π)` in cycles/pixel (computed from the full 2D gradient magnitude, so height-warped/steep regions fade, not just a fine carrier). It is wired into `synthesize_psi_stack` as `A + B·env·cos(...)`, **off by default** (`fill_factor=None` → byte-identical point-sampled path). At fill=1.0 the first sinc null is at a 1-px fringe period; contrast is still ~64% at the 2-px Nyquist period — an **honest soft roll-off, not a hard cliff**.

**Critical two-part mechanism (both required, surfaced by recon):**
1. The envelope alone is **transparent to noiseless recovery** — it attenuates contrast `B·env` *identically across the N phase shifts*, so it divides straight out of `extract_phase`'s `arctan2`. A faded fringe recovers *perfectly* until contrast hits exactly zero (the degenerate `arctan2(0,0)` → a defined-but-meaningless constant, not the true phase). So the fade by itself does NOT produce a gradual wall.
2. **Additive read noise (A.4)** is what gives the fade teeth. Drawn **per-frame-independent, shape (H,W,N)** (a k-common (H,W) map would cancel in arctan2 just like the envelope — the (H,W,N) shape is the load-bearing line), added at the sensor stage *after* the envelope. Because noise is independent per frame while `B·env` is common, it does NOT cancel: low contrast + fixed σ = low SNR = phase error scaling as `σ_φ ∝ σ/(B·env·√N)`. This is the gradual beyond-Nyquist wall. The `1/√N` term means **N=8 recovers ~√2 deeper into the fade than N=4** (measured 0.707, exactly 1/√2 — finding #2 made physically real). Noise requires an explicit seeded `rng` (`noise_sigma>0` with `rng=None` raises); the seed is serialized, not the Generator (reproducibility / future hardware-reference requirement).

### 7.14 — Inverse-FPP nulling: the tilt-flip nulls a golden part (Stage 6 A.1/A.2/B.2)

The inverse grating is the **fixture-locked tilt-flip** `φ_inverse = 2·P − φ_ref`, `P = fit_tilt_plane(φ_ref)` (`calibration.compute_inverse_phase`, reused — single source of truth). `pattern_generator.inverse_grating_phase` is the projector-side wrapper. The closed loop is `pipeline.run_inverse_fpp(reference, object, geometry, deltas, ...)`: reference capture → inverse grating → project onto object → recover. Because `project()` is **affine in its phase argument** (bias independent of phase), the projector's quadratic bias cancels exactly — the inverse grating makes `project()`-on-the-object safe (without it, the bias blows recovery up ~6 orders).

**Golden-part generalization (recon-settled, B.2):** the *same* tilt-flip nulls a genuinely 2D-curved golden part — it does NOT only work for flat references. The algebra: flipping curvature about the fitted plane produces `−C[h_golden]`, so `recovered = C[part − golden]` (a matching part nulls to the carrier; a defect survives as the deviation's curvature). B.1 (flat golden) is the special case. `run_inverse_fpp` is loop-wrappable by construction (height-in/height-out) so the deferred closed-loop iteration wraps it without a rewrite.

**Two honest bounds, pinned in code + tests (must not be over-claimed):**
- **Curvature only:** `recovered = C[part − golden]` recovers the deviation's *curvature*; a purely **linear tilt difference** between part and golden is removed by self-cal and NOT recovered. This is the inherent single-carrier-FPP self-cal limitation — fine for **defect/local-deviation detection** (bumps, dents, cracks — the AM in-situ framing), NOT absolute global-tilt metrology.
- **Defect's own Nyquist:** inverse-FPP decouples the *golden's* gradient from the wall (the matching shape can be arbitrarily steep), but a **defect whose own gradient exceeds Nyquist is not fully recovered** (~61% at own-f 0.81). The grating un-crushes the golden's contribution everywhere; it cannot un-crush a defect that is itself beyond-Nyquist.

### 7.15 — Self-cal fit follows the reference's structure (Stage 6 B.2)

`run_inverse_fpp`/`run_straight_fringe` take `selfcal_fit: Callable = fit_tilt_line_1d` (the default preserves all prior behavior byte-for-byte; the H_rec0 fixture's ~4e-5 1D-vs-2D divergence stays on the default, sealed fixture never reopened). **Rule: the self-cal follows the reference's structure.** A genuinely 2D golden needs `fit_tilt_plane` (2D) — the 1D row-mean fit (forces m_y=0) cannot remove a y-tilt in the reference phase and **leaks a linear y-ramp** into the deviation map (negligible for a centered/symmetric golden, ~3px for an asymmetric one, enough to bury a small defect). The recon proved the leak is **purely linear (never curvature corruption)** and that the 2D fit removes it completely (off-center matching null 3.12px → 6.7e-13). For y-invariant data the two fits agree, so 2D-vs-1D only matters when the reference carries real 2D structure. The GUI golden path passes `fit_tilt_plane`; the straight-fringe baseline in the same comparison uses the same fit so the before/after differs only by the inverse grating.

### 7.16 — The two showcases: synthetic steep dome (validation) vs steep STL (realism) (Stage 6 B.3a; B.3b pending)

The headline — inverse-FPP recovers steep features straight-fringe loses to the Nyquist wall — has two demonstrations doing different jobs:
- **Synthetic steep dome (B.3a, done):** a `make_steep_dome` golden in the **math-pixel convention** (amplitude ~6000, σ ~60 px) whose flanks push the observed fringe frequency past 0.5 cyc/px. This is the **controlled validation gate** — extreme, tunable, reproducible (seeded), produces clean headline numbers: **decoupling ~42–135×** (observed-frequency reduction in the steep region) and a **steep-region recovery-error improvement of ~10⁴–10¹⁵×** depending on steepness. Both surface as a live "Steep-region: decoupling Nx, error ratio Mx" readout on the Recovered Surface tab (convention-agnostic ratios; the dual-run cost is gated to the steep-dome surface only). Demonstrated via the existing toggles: Inverse-FPP OFF → steep flanks alias (RMS error ~hundreds of mm), ON → recovers to the ~1mm noise floor; Sensor noise makes it the realistic regime; Inject demo defect (pixel-convention amplitude, sub-Nyquist own-gradient) pops a defect out of the quiet null.
- **Steep STL part (B.3b, pending):** the *realistic* version — a real AM-relevant part with steep walls at sensible millimetre heights that crosses the wall by geometry, not by a cranked amplitude. Renders as a believable object and reads as in-situ AM metrology. The dome proves the method; the STL shows it on something believable.

**Known GUI limitation (B.3 polish item, found in hands-on review):** the steep-dome **3D render is dominated by the unit-seam spike** (Z≈6000 "units" — the §7.12 cosmetic consequence) and is effectively unusable for the showcase; the result reads only via the Error Statistics box + the dynamic-range readout. A polish pass should normalize/cap the steep-dome Z render or auto-enable Color-by-error so the payoff is visible, not just numeric. The steep **Gaussian** (e.g. amp ~22mm/σ8mm) is the more *legible* near-wall demonstration — it renders as a recognizable bump that visibly mangles with correction off and snaps clean with it on — and may be the better default showcase surface than the dome.

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

- **Projector body frame**: origin at front-bottom-left corner of cube; +X right, +Y into body, +Z up. Measured lens center on the front face: 21 mm along face-X, 45 mm up face-vertical, recessed ~1.5 mm. Relative to the face CENTER that is (face_x = −6.5, face_vertical = +17.5, recess = 1.5) mm — encoded as `ProjectorLensOffset` in `hardware_scene.py` (Stage 5, 4d.10).
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

### Projector lens anchoring & hardware coordinate frame (Stage 5)

Stage 5 (4d.10) anchored the projector **lens center** (not the body center) over world (X, Y) = (0, 0) when the projector points straight down (θ = 0). The body therefore hangs off-axis at (+6.5, +17.5) when vertical; the lens lands on the optical axis. The camera lens is centered (no offset), already at (0, 0, WD) when vertical.

- **Axis mapping at θ = 0** (from the arm transform `T(0,0,d) @ R_x(π)`): body-local face-X → world +X; face-vertical → world **−Y**; optical axis → world −Z (straight down). The arm swings about world-Y (`R_y(θ)`), so the face-vertical offset stays purely in Y at every angle (never mixes into X/Z); anchoring at θ = 0 anchors at all θ.
- **FACE-VERTICAL SIGN UNVERIFIED:** the +17.5 "up the face" → world −Y mapping reflects the sim's current orientation convention. The physical rig is not built yet and the projector will be replaced. Confirm the sign against the real projector at mount time and flip if the lens sits on the opposite world-Y side. Magnitude (17.5) and the anchoring behavior are correct regardless. (Flagged in `hardware_scene.py`.)
- **Hardware coordinate readout (4d.11):** `arm_lens_front_world(theta_cam, theta_proj, proj_dist, cam_dist)` returns each arm's lens-front world (x, y, z) in this frame; surfaced live in the GUI "Hardware Coordinates" panel and via `scripts/hardware_coords.py`. This is the instrument for cross-checking the simulation against the real mounts during the hardware phase. With both arms swinging about world-Y, the y-coordinate stays ~0 as angles change (the projector's fixed face-vertical offset is zeroed out by the anchoring).

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
| Strict-correctness FOV check (no tolerance) | Hairline triggers happen only at extreme synthetic surfaces (amp=100mm) that won't exist in real fringe projection use. Tolerance would hide real coverage failures and require a magic threshold. **Stage 4d follow-up note:** the projector-cone check (5) gained a 2 mm tolerance because real projectors have gradual edge falloff vs. the math's sharp boundary; the camera-prism check (4) stays exact (telecentric parallel-sided prism doesn't soften at its bounds). |
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
- **Stage 4d follow-up:** `_CONE_COVERAGE_TOLERANCE_MM = 2.0` advisory tolerance widening cone lateral half-extents for the coverage point-in-volume test. Real projector edge falloff vs. the math's sharp cone boundary. Camera prism check stays exact (no tolerance).

All clip-detection geometry constants are derived from the cone builders themselves at module load, so the math tracks `scene.py` rather than duplicating spec numbers.

### Stage 4c — Done (STL import for arbitrary specimens)

**Goal achieved.** The surface dropdown collapses to three honest options: Flat (calibration reference + zero-height smoke test), Gaussian (known-answer validator), and STL file... (real CAD specimens). Tilt, Step, and Sphere are deleted end-to-end. STL files load through a `QFileDialog`, get rasterized to the existing `(shape, pixel_size_mm) → (H, W) float64 mm` contract via projected-barycentric rasterization, and feed the unchanged math layer with zero pipeline changes.

**Stage 4c sub-task table:**

| # | Commit | What landed |
|---|---|---|
| 1 | `eecaeac` | Dropdown reduction (Flat, Gaussian) + Gaussian amplitude cap 100→55 mm. `make_tilt`, `make_step`, `make_sphere` generators, their tests, their slider widgets, page builders, and dispatch branches all deleted. Net −223 lines. Surviving slider inventory: Flat (none); Gaussian (amplitude 0–55 mm, sigma 1–30 mm). `tests/test_clip_detection.py:256` left at amplitude=100 (Gaussian-based coverage case; `make_gaussian` has no internal cap, math layer free). New `scripts/stage4c_smoke.py` smoke harness (verify \| Flat \| Gaussian). 122 tests. |
| 2 | `db0cd21` | `src/stl_loader.py` (pure NumPy peer of `test_surfaces.py`): `load_stl_heightmap(path, shape, pixel_size_mm)` and `get_stl_bbox_mm(path)`. Projected-barycentric rasterization, per-pixel max-z upper envelope (camera-visible top surface; closed-solid bottom discarded). Lift convention at the time of this commit: by global mesh-Z minimum across all triangles. **This convention was reset to visible-envelope minimum in the Stage 4d follow-up GUI review** — see "Stage 4d follow-up commits" below. 14 new tests covering cube, pyramid, tilted triangle, closed UV sphere, vertical-walls-only, empty mesh, offset cube, bbox extents — all synthetic in-memory via `tmp_path`. `numpy-stl==3.2.0` added to `environment.yml` pip block (NOT conda-forge — see "Stage 4c environmental lessons" below). 136 tests. |
| 3 | `2c73955` | STL wired into the surface dropdown as `"STL file..."`. `_build_stl_page` with inner `QStackedWidget` (placeholder ↔ `STL: <basename> [Change...]` row, full path as tooltip). `_on_surface_combo_changed` slot inserted between page-swap and refresh in `currentIndexChanged` connection order. `_load_stl_from_path(path) → bool` is the no-dialog hook used by the `QFileDialog` flow, the Change button, the smoke script, and the tests. Cache lives for the window's lifetime; switching to Flat/Gaussian and back to STL re-renders the cache without re-importing. `_revert_stl_dropdown` carries a maintainer comment explaining why both the combo AND the surface_pages stacked widget need manual `setCurrentIndex` under `blockSignals`. Temporary `QMessageBox.warning` bbox guard (replaced in sub-task 4). 6 new GUI tests in `tests/test_main_window_stl.py` (monkeypatched `QFileDialog`/`QMessageBox`). Smoke harness extended with STL mode (synthetic 30 mm cube). 142 tests. |
| 4 | `286ebb3` | Finalize the bbox guard: hard-reject only. `QMessageBox.warning` text rewritten to explain why oversized STLs are rejected and point at Stage 4d's STL Browser. The earlier draft of sub-task 4 (custom `QDialog`, `rescale_mesh_uniform`, `truncate_heightmap_z`) was **dropped during planning** — rescale and truncate both distort the geometry being measured. Five stale "sub-task 4" forward-references in `src/stl_loader.py` comments cleaned up to point at where the bbox check actually landed (`main_window.py`'s `_load_stl_from_path`). Text-only commit; 142 tests unchanged. |
| 5 (close) | this commit | Docs update + tag `stage-4c-complete`. |

**Key design decisions locked during Stage 4c:**

| Decision | Rationale |
|---|---|
| Surface dropdown collapses to (Flat, Gaussian, STL file...) | Tilt/step/sphere were synthetic surfaces with no calibration role; Flat (zero-height ref) and Gaussian (known-answer) cover all the smoke-test use cases. STL covers real specimens. Three is the right number. |
| Gaussian amplitude cap 100 → 55 mm | Matches the 55 mm Z component of the working volume so the GUI can't drive the surface beyond what the camera FOV honestly supports. `make_gaussian` itself has no internal cap; the bound is GUI-only. (Raised again to 120 mm in Stage 4d sub-task 2.5.) |
| `numpy-stl` in the pip block, NOT conda-forge | Installing `numpy-stl` via conda-forge dragged in MKL/BLAS/LAPACK and a duplicate numpy build that broke `numpy.linalg` at the ABI level. Pip is clean because this env's numpy is pip-installed; matching the install mechanism avoids ABI conflicts. Documented in `environment.yml` comment. |
| Projected-barycentric rasterization (not z-buffer search) | Scales O(N_triangles × pixels-per-triangle), not O(N_pixels × N_triangles). CAD STLs have 10k+ triangles; the projected-barycentric path is the only one fast enough to feel interactive. |
| Per-pixel max-z upper envelope | Matches what a single-viewpoint FPP camera actually sees: the top surface, not the closed solid's interior or bottom. Documented in the loader docstring. |
| ~~Lift by global mesh-Z min, not envelope-min~~ **Superseded by Stage 4d follow-up:** lift by visible-envelope minimum (the lowest camera-VISIBLE point). The original global-mesh-min convention put a closed solid's full diameter above the stage, but a real FPP camera only measures the visible top surface, so the visible base — not the discarded bottom shell — should define z=0. The reset closed three visible symptoms in the Stage 4d GUI review: floating-part appearance, 15 mm step at FOV-bbox boundary, angle-dependent recovered shape from straddling-FOV-induced phase-unwrap branch differences. See "Stage 4d follow-up commits" below for the diagnostic chain and consequences. |
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

- **Halt-and-confirm gates earned their cost three times in Stage 4c.** Sub-task 2's halt caught the lift-formula contradiction (envelope-min vs global-min, which itself was later reset to envelope-min in the Stage 4d follow-up — see below). Sub-task 3's halt confirmed connection-ordering risk with `blockSignals`. Sub-task 4's halt-and-pivot replaced a substantial dialog implementation with a 24-line message edit. None of these would have been caught by the test suite — they're all "prompt vs. actual code intent" mismatches that only surface in summarize-back.

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

### Stage 4 controls (locked as of Stage 4d follow-up)

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

**Clip-detection warning banner (new in 4b, refined in Stage 4d follow-up):**
- 5 advisory checks (3 collision + 2 coverage). Collisions gray the offending hardware bodies + cones; coverage advisories show banner only.
- Body-overlap check (collision #3) upgraded from world-AABB approximation to exact OBB intersection via SAT in the Stage 4d follow-up. Eliminated documented false positives of 22–32 mm true clearance at ordinary and extreme poses.
- Projector-cone coverage check (advisory #5) gained a 2 mm advisory tolerance in the Stage 4d follow-up. Sub-mm hairline triggers from the cone math's sharp-boundary idealization no longer fire; spills of > 2 mm still warn.
- Camera viewing-prism coverage check (advisory #4) stays exact — telecentric parallel-sided prism.
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
| close | `stage-4d-complete` | Docs update + tag `stage-4d-complete`. |

**Key design decisions locked during Stage 4d:**

| Decision | Rationale |
|---|---|
| Math grid reconciled to exact 68×55 mm patch ((550, 680) at 0.1 mm/px) | Sub-task 1.5. Stage 4a chose (480, 640) at 0.1 mm/px = 48×64 mm grid, which never honestly matched the advertised 68×55 mm camera FOV. Stage 4d's Browser couldn't proceed with that mismatch — the FOV rectangle on the minimap is the user's mental model of what the camera sees, and it has to match the math grid bit-for-bit. |
| Three-way bbox classification: direct / Browser / hard-reject | Sub-task 2. Two thresholds (`WORKING_VOLUME_MM`, `ABSURDLY_LARGE_MM`) give three buckets. The direct path stays for parts that fit; the Browser path activates for oversized-but-bounded XY; absurd-sized XY hard-rejects with the same memory-bound + usability ceiling reasoning as Stage 4c's hard-reject. Threshold raised to (500, 500, 120) in Stage 4d follow-up. |
| Z cap raised 55 → 120 mm (placeholder backed by empirical observation) | Sub-task 2.5. Stage 4c chose 55 mm to match the camera FOV Y extent — a coincidence-equal value, not a derived hardware constraint. User's bench testing showed 100 mm parts cleared the hardware without contact. 120 mm = 100 mm specimen + 20 mm safety margin. Real Z constraint (projector focus depth, phase unambiguity range, triangulation lateral-spill) is a Stage 5/6 derivation. |
| `Z_EXAGGERATION` permanently locked at 1.0 (honest scale) — **DOCTRINE** | Stage 4b locked Z=1.0 at honest scale; Stage 4d makes this permanent. The lab view's job is to show the part as the system sees it — at true scale, in proper proportion to camera/projector/stage. Exaggerating Z would lie about the geometry the rest of the simulation is designed to measure honestly. A 50 µm bump shouldn't look like a 5 mm bump because the visualization would then communicate different information than the math is computing. **Configurable Z exaggeration is NOT on the roadmap; do not add it.** |
| Lab view shows only the committed FOV slice (3D mesh with depth) | Sub-task 6. The slice is itself a heightmap, so the lab view renders it as a 3D mesh with full Z relief — user can orbit around to read the depth profile. Whole-part-with-FOV-cone visualization is deferred to Stage 5/6 (depends on real hardware-mounting geometry to set the relative scale of part vs apparatus). **Parking-lot item from Stage 4d follow-up:** the next refactor will make lab view show ground truth by default with an opt-in recovered-surface overlay toggle, and add a dedicated "Recovered Surface" tab for quantitative comparison. See "Stage 4d follow-up parking lot" below. |
| Drag updates Panel 3 + Panel 1 highlight only; lab view + Pipeline Stages wait for commit | Sub-tasks 5 + 5.5 + 6. Re-running the math pipeline at 60 Hz drag rate would be unacceptably laggy. Two NumPy slices + two GPU uploads per drag tick is the cheap path; pipeline + tab-render is the expensive path. The Commit FOV button is the latency boundary. |
| Browser tab placeholder always visible; panels shown only when Browser-mode STL active | Sub-task 3. The QTabWidget always shows "STL Browser" as a tab — clicking it shows either the placeholder ("Load an oversized STL to use the Browser") or the three-panel layout. Tab-disable was rejected as worse UX (the user can't see what the tab does until they try). |
| FOV highlight color matches minimap rectangle cyan exactly | Sub-task 5.5. Visual continuity — "the same region" across two panels reinforces the FOV selection metaphor. Bright cyan `(0, 220, 255)` is high-contrast against grayscale minimap content and unused elsewhere in the GUI color vocabulary. |
| FOV highlight opaque (alpha=1.0), not translucent | Sub-task 5.5. Pyqtgraph 0.14.0 alpha-rendering bug forces alpha=1.0 — translucency was a nice-to-have, not load-bearing. Panel 3 (windowed preview) shows the FOV contents directly anyway; the highlight's job is "show WHICH region" not "show through to underlying contour." |
| Implicit refresh chain via `_open_stl_dialog`, not explicit auto-commit in `_load_stl_browser` | Sub-task 6. `_open_stl_dialog` already calls `_refresh_surface_preview` after `_load_stl_browser` returns. Adding an explicit auto-commit would be a redundant 2nd/3rd refresh per load — a real perf cost (large parts can be 10s of MB heightmaps × pipeline run) for hypothetical future-caller decoupling we don't have a concrete use case for. The implicit chain is the load-bearing contract, documented in `_load_stl_browser`'s docstring. Future direct callers would invoke `_refresh_surface_preview` themselves. |
| Two-method update API for Browser content (`update_whole_stl` + `update_windowed_slice` separate, not unified) | Sub-task 4. Sub-task 5's drag handler calls `update_windowed_slice` on every mouse-move tick; redoing Panel 1's whole-STL mesh on every drag would be wasted GPU work. Separation is the perf path. |
| Panel 1 distance scales to part bbox; Panel 3 distance fixed at 200 mm | Sub-task 4. Panel 1's content size varies with the part (100×80 → 500×500 mm); a fixed distance would over-zoom small parts or under-zoom large ones. `1.5 × max(W, H)` keeps the part filling ~30% of frame width across the range. Panel 3 always shows a fixed 68×55 mm slice, so fixed distance is fine. |
| Minimap initial view padded by full-FOV on each side | Sub-task 5. Half-FOV padding (the original spec) clipped the rectangle at extreme off-part drag positions, surfaced by the C3 capture. Full-FOV padding keeps the rectangle visible across all drag positions including worst-case dragged-fully-off-part. Cosmetic cost: part appears ~30% of minimap width instead of ~60%. The silent-failure mode of "I dragged my rectangle and now I can't see it" loses to the cosmetic-failure mode of "part looks smaller." |
| FOV rectangle: 2 px cyan outline, no fill | Sub-task 5. Outline-only keeps the part's grayscale content visible inside the rectangle, which is the region the user is about to measure. Adding fill would compete with the part content the user wants to see. |

**Architectural decisions worth carrying forward from Stage 4d:**

- **`Z_EXAGGERATION = 1.0` is a permanent design tenet, not a "for now" value.** The lab view IS the real-scale view of the measurement geometry. Exaggerating Z would desync the visual from the math. If a part's features look subtle at honest scale, that's information about the part, not a deficiency in the visualization.

- **The lab view shows only the committed FOV slice, not the whole part.** Whole-part context lives in the Browser's Panel 1 (whole-STL 3D preview, rotatable from any angle). The "whole part on stage with FOV cone highlighting the measured region" visualization is deferred to Stage 5/6 when real hardware-mounting geometry determines the relative scale of part vs apparatus.

- **Drag-vs-commit separation is the core interaction discipline.** Drag updates the cheap previews (Panel 3 windowed slice, Panel 1 surface-following highlight). Commit promotes to the expensive paths (lab view, Pipeline Stages, math pipeline). The Commit FOV button is the latency boundary between exploration and measurement.

- **The math layer never knew Browser mode existed.** Sub-tasks 1.5 through 6 added zero lines to `src/pipeline.py`, `src/geometry.py`, `src/synthetic_fringes.py`, `src/calibration.py`, `src/reconstruction.py`. The math layer continues to receive one 68×55 mm heightmap and produces one 68×55 mm recovered surface. The Browser is a UI for choosing which 68×55 mm patch the math sees, nothing more. **Stage 4d follow-up extends this:** edge-extend pre-processing and recovered-output masking both live in the GUI layer (`main_window.py`), not in `pipeline.py`. The math layer still doesn't know Browser mode exists.

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

**Diagnostic-prompt-before-decision.** When strategy chat catches itself about to recommend a decision built on guesses about library internals, code-not-yet-read, or environment-specific quirks, the right move is to pause and write a **read-only diagnostic prompt** for Claude Code to investigate first. Evidence drives the next recommendation. The pattern surfaced repeatedly in sub-task 5.5's cyan-vs-maroon investigation — the original recommendation (try per-vertex layout) was strategy-chat guessing at pyqtgraph 0.14.0's color-binding API. Replacing it with "investigate first, then decide" caught two wrong recommendation cycles before they landed in code. **The Stage 4d follow-up GUI review extended this pattern aggressively:** every fix in that review pass was preceded by a read-only diagnostic prompt, including ones where the strategy-chat prediction turned out to be wrong (the byte-identical θ=15°/30° pipeline finding, see "Stage 4d follow-up commits" below).

**Two failure modes to watch for:**

1. Confident-sounding recommendations built on guesses about library behavior or unread code. These sound identical to recommendations built on evidence. When strategy chat notices "I'm not sure what pyqtgraph 0.14.0 actually does here, but I think..." — that's the signal to write a diagnostic prompt instead of finishing the sentence.

2. Treating "make the symptom go away" workarounds as equivalent to fixing the underlying bug without diagnosing it. In sub-task 5.5, the first two "fixes" (per-vertex layout swap, then setColor switch) both failed because the actual bug was alpha-rendering, not what strategy chat hypothesized. Each fix attempt without diagnosis cost a cycle. The pattern is **"fix attempt → diagnose if it doesn't work" not "fix attempt → different fix attempt."**

**Prompt-assumption catches.** Three times during Stage 4d, halt-gate summarize-back caught strategy-chat prompt assumptions that were factually wrong about the codebase:

1. Sub-task 2.5: prompt said "55 doesn't appear in `src/stl_loader.py`" — it actually appears at lines 23 and 185 in docstrings. Honoring the prompt's "Do NOT touch stl_loader.py" rule would have left stale documentation.
2. Sub-task 2.5: prompt omitted `scripts/stage4c_smoke.py` from the in-scope-to-edit list — but the script has a hard-coded `amp_max == 55.0` assertion that the bump would break.
3. Sub-task 6: prompt said "the lab view doesn't show the FOV at load time" — it actually does, via the implicit refresh chain through `_open_stl_dialog`. Strategy chat's proposed explicit auto-commit would have been a redundant 2nd/3rd refresh.

The pattern: when strategy chat writes "X doesn't appear in module Y" or "Currently the system doesn't do Z," that's a claim about state the strategy chat doesn't have direct access to. Halt-gate summarize-back's grep-level read catches the discrepancy before code lands. The fix is to grep first, claim second. **The Stage 4d follow-up GUI review made this an explicit pre-greenlight ritual:** every halt-gate summary started with "grep-check the prompt's core assumption" and frequently corrected the prompt (e.g., the Z=55→120 catch in the ABSURDLY_LARGE_MM bump, where the prompt's stated Z value was a stale recollection from before sub-task 2.5).

### Stage 4d follow-up commits — Hands-on visual GUI review

After Stage 4d closed at tag `stage-4d-complete`, the user opened a hands-on visual review session. The workflow was: launch the GUI, exercise real STL files and slider configurations, catch any cosmetic or behavioral issue that didn't surface during programmatic smoke-testing. Five focused commits landed during this review pass, all unpushed at session close.

The review framing locked in early: **PyQt6 fixes that lock in UX targets the web port must match are worth doing in this session; PyQt6 tweaks that fight pyqtgraph-specific quirks are not.** All five commits below fall in the first bucket.

**Stage 4d follow-up commit table:**

| # | Commit | What landed |
|---|---|---|
| 1 | `9480b94` | **STL lift convention: visible-envelope minimum, not global mesh minimum.** `tris[:, :, 2].min() → acc[finite].min()` in both `load_stl_heightmap` and `load_stl_heightmap_full_scale`. Variable rename `z_min_mesh → z_min_visible`. Docstrings rewritten in both functions to describe the new convention. Five existing tests' assertions updated to match the new behavior: cube and full-scale box collapse to z=0 (flat-topped boxes have no relief under envelope-min lift); sphere peak ≈ R, not 2R (visible equator at z=0); pyramid and sphere tolerances loosened to cover the discretization offset of the visible base (the captured base edge sits a fraction above the true geometric base). One new regression test won't be added in this commit; the pre-existing tests' updated assertions document the contract. 181 tests in, 181 tests out (assertion changes only). Five stale lift-convention claims in PROJECT_CONTEXT.md and CONVERSATION_SUMMARY.md flagged in commit body for a later docs pass; not edited in this commit. |
| 2 | `fb19e0c` | **Off-part edge-extend into pipeline, mask recovered output to 0.** Three new helpers in `main_window.py`: `_browser_offpart_window` (rectangle in FOV-slice coords containing the on-part region, derived from `_extract_fov_slice`'s clamped-window arithmetic, value-independent), `_browser_offpart_mask` (boolean mask of off-part cells), `_edge_extend_offpart` (column-then-row edge copy, pure NumPy, ~5 lines). `_refresh_surface_preview` gains gated padding before `run_pipeline` (Browser mode only) and masking-to-zero of the recovered output after. The Pipeline Stages tab's ground-truth panel shows the ORIGINAL slice (off-part = 0) — not the edge-extended pipeline input — to preserve physical truth in the input panel; the phase panels still reflect the padded input the math actually processed. One new GUI test (`test_browser_commit_masks_offpart_preserves_onpart`) using a synthetic X-ramp full heightmap to verify both that fully-on-part is byte-identical to the unmodified pipeline AND that straddling masks off-part to exactly 0.0 while on-part keeps real recovered relief. 181 → 182 tests. |
| 3 | `e3c14bb` | **SAT body-overlap (OBB intersection) replaces assembly-AABB.** New `_obb_overlap(transform_a, local_corners_a, transform_b, local_corners_b)` in `clip_detection.py`: pure NumPy SAT testing 15 candidate axes (3 local axes per box + 9 pairwise cross products), strict no-epsilon separation (any positive gap clears), cross-axis degeneracy threshold 1e-9. The body-overlap block in `detect_clips` replaced from a single union-AABB-vs-union-AABB test to four pairwise OBB tests (body-vs-body, body-vs-lens, lens-vs-body, lens-vs-lens) with `any()` aggregation. Removed `_world_aabb` and `_aabb_overlap` (zero callsites remain). Module docstring updated: the AABB-trade-off note (lines 49-56) replaced with a SAT description; `Section 13.1` summary updated. One new regression test locking both documented false-positive poses (θ_cam=-13°, θ_proj=-45°, throw=200, WD=180 with 31.6 mm OBB clearance; θ_cam=30°, θ_proj=30°, throw=50, WD=132 with 22.3 mm OBB clearance). All four existing body-overlap tests kept their assertions — verified by SAT verification probe before the edit. 182 → 183 tests. Closes the §13.8 deferred-OBB note. |
| 4 | `079cde4` | **2 mm advisory tolerance on projector-cone coverage check.** New constant `_CONE_COVERAGE_TOLERANCE_MM = 2.0` placed after `_CONE_HALF_V_PER_L`. `_surface_exceeds_cone` widens per-depth lateral half-extents by the tolerance (`hw = _CONE_HALF_U_PER_L * s + _CONE_COVERAGE_TOLERANCE_MM`; same for `hh`); axial `s >= 0` check is NOT relaxed (axial spill is a different failure mode). Camera prism check stays exact (parallel-sided telecentric prism doesn't soften at its bounds). Function docstring + module docstring updated to describe the new tolerance and its asymmetry with the camera prism check. One new regression test locking the documented 0.40 mm hairline false positive at θ_cam=0°, θ_proj=-41°, throw=149, WD=157 with a flat 15 mm slab (no STL fixture needed; the synthetic surface places the diagnosed corners at the same world points). 183 → 184 tests. The existing throw=50 cone test spills 22 mm — far beyond 2 mm — so it still fires; lockstep verification probe confirmed no existing assertions need updating. |
| 5 | `48efdc4` | **ABSURDLY_LARGE_MM raised to (500, 500, 120) for 450×450 mm specimens.** XY raised from (272, 220) to (500, 500); Z kept at 120 (Stage 4d sub-task 2.5's empirical raise + the lockstep invariant `WORKING_VOLUME_MM[2] == ABSURDLY_LARGE_MM[2]`). Memory footprint at 0.1 mm/px: 200 MB per heightmap, vs. 48 MB at the old threshold — user accepted the trade-off explicitly. `stl_browser.py`'s `_PLACEHOLDER_TEXT` updated from "272 × 220 mm" to "500 × 500 mm" (hardcoded string, not data-driven). `main_window.py` memory-footprint comment updated from "5.98M pixels / 48 MB" to "25M pixels / ~200 MB". One existing reject test (`test_absurd_xy_rejected`) updated: box size 300×250 → 550×550, message assertions "300.0"→"550.0" and "272"→"500". One comment update on `test_browser_mode_populates_full_cache`. Bug-bait grep for "272"/"220" classified all hits into related-vs-unrelated buckets; only the related four sites edited. Headline catch in halt-gate: the original prompt requested target (500, 500, 55), but Z was already 120 — setting Z=55 would have silently regressed sub-task 2.5 and broken `test_z_cap_matches_absurd_z`. The grep-check before the edit caught it. 184 tests in, 184 tests out (lockstep edits only). |

**Five-commit branch state at session close:** all unpushed on `main`. Suite count progression: 181 → 181 → 182 → 183 → 184 → 184. No tag updates yet — the docs commit covering the stale claims and the parking-lot items (see below) lands as a sixth commit, then the full six-commit stack gets tagged and pushed together.

**Key design decisions locked during Stage 4d follow-up:**

| Decision | Rationale |
|---|---|
| Lift convention = visible-envelope minimum (Section 7.6) | Three visible symptoms in the GUI review all traced to the same root: the global-mesh-minimum lift convention from Stage 4c sub-task 2 placed the visible part above the stage. Real FPP can't measure the bottom shell of a closed solid, so the visible base — not the discarded bottom — should define z=0. The fix resolved floating-part appearance, 15 mm FOV-bbox-boundary step, and angle-sensitive recovered shape (the downstream consequence of phase unwrap encountering the 15 mm discontinuity at the part edge). |
| Off-part padding = edge-extend, output masking = back to 0 (Section 7.7) | The user objected (correctly) that edge-extending off-part cells creates "phantom" geometry that lies about the physical reality of bare stage beyond the part. The compromise: edge-extend ONLY inside the math pipeline (where the discontinuity-free input keeps the unwrap and self-cal clean), then mask back to 0 in the recovered output before display (so the user sees physical truth: off-part = flat stage at z=0). One commit, not two — the masking lives in the same code block as the padding because they're inseparable parts of one contract. |
| SAT body-overlap (full Option 1), not cylinder approximation (Option 2) | A comparative diagnostic probe tested three options against the false-positive pose plus three control poses. Option 3 (per-component AABB) didn't resolve the false positive — the 200 mm camera lens's own world-AABB still dominated. Options 1 (SAT) and 2 (cylinder) both resolved the tested poses, but Option 2 retains an axis-aligned body-body test that would itself become a false-positive vector at high-tilt close-distance body-body pairs. Option 1 (full SAT) closes the body-body weak spot too. Two extra strict-no-epsilon design notes: touching counts as collision (correct boundary for an advisory check); adding positive tolerance would re-inflate exactly what the upgrade removes. |
| Cone-coverage tolerance = 2 mm (Section 7.8) | The user reported a single-pose hairline cone trigger (0.40 mm spill at FOV-patch corners). Diagnostic confirmed structurally exact angular test, not an inflation bug; the trigger was honest geometric reporting that real projector edge falloff would cover. 2 mm tolerance silences sub-mm hairlines AND minor (1-2 mm) edge-case spills without hiding real coverage failures (which are typically 5+ mm). Camera-prism check stays exact for a different physical reason (parallel-sided telecentric prism doesn't soften). |
| ABSURDLY_LARGE_MM Z stays at 120 (not 55 as user-prompt requested) | The lockstep invariant `WORKING_VOLUME_MM[2] == ABSURDLY_LARGE_MM[2]` was locked by `test_z_cap_matches_absurd_z` in Stage 4d sub-task 2.5. Halt-gate caught the stale Z value in the user's prompt and corrected it before the edit. Memory footprint at 200 MB per heightmap acknowledged explicitly; user accepted the trade-off. |

**Architectural decisions worth carrying forward from Stage 4d follow-up:**

- **Lift convention is the visible-envelope minimum (Section 7.6 doctrine).** The Stage 4c global-mesh-minimum convention is gone. Any future surface-rasterization code that joins the surface library must follow the visible-envelope convention or document why it diverges.

- **Off-part contract in Browser mode: padded internally, masked externally (Section 7.7 doctrine).** Any future GUI code that feeds the math pipeline a Browser-mode slice must use the same edge-extend-then-mask pattern. The math layer remains agnostic; the contract is enforced by the GUI layer (`_refresh_surface_preview`).

- **Clip-detection tolerance philosophy (Section 7.8 doctrine).** Future coverage / collision checks follow the same asymmetry: physical-boundary-soft checks get an advisory tolerance (cone); physical-boundary-hard checks stay exact (prism, body-overlap). Strict no-epsilon for collision checks; positive advisory tolerance for soft-boundary advisories where real-world physics covers the math's idealization.

- **Diagnostic-before-decision discipline matured into the default workflow.** Every Stage 4d follow-up commit was preceded by at least one read-only diagnostic probe. Multiple probes were required for the lift fix (lift-formula, off-part fill, cyan-slab attribution), the recovery angle-sensitivity investigation (initial threshold probe, asymmetric sweep, fine threshold sweep — the asymmetric sweep overturned the prediction that recovered output would be byte-identical across angles, surfacing the >50° unwrap-branch divergence as a real-but-physically-correct phenomenon), and the body-overlap fix (initial AABB-vs-OBB probe quantifying the 31.6 mm false positive, then the three-option comparative probe that ruled out per-component AABB and made the case for full SAT over cylinder). **The discipline saved at least two fix attempts that would have shipped wrong**: the off-part angle-sensitivity that turned out to be the input-discontinuity bug not a recovery bug; the SAT-vs-cylinder decision that would have left the body-body weak spot if Option 2 had been picked from intuition.

- **Halt-gate grep-check-the-prompt is a hard ritual.** Three times during the follow-up the halt-gate summary corrected prompt assumptions: the lift Z value (already 120, prompt said 55), the bug-bait around "272"/"220" classification, the at-risk same-side-stack test for SAT (verified True under SAT before the commit instead of trusting strategy-chat's prediction). The grep-first discipline catches things that even careful strategy-chat reasoning misses.

- **Test-suite progression as a sanity check.** 181 → 184 across the five commits. Each commit's halt-gate predicted the expected pass count and any lockstep assertion changes; each commit hit the prediction exactly. The discipline of "verify the suite-count prediction in halt-gate" caught at least one wrong assertion early (the over-tight pyramid/sphere tolerances in commit 1's first pytest run, which the halt-gate had assumed would pass but the discretization-offset measurement showed needed loosening before re-running).

### Stage 4d follow-up parking lot — design inputs for next session

> **STAGE 5 RESOLUTION (update):** Items #1 (lab-view ground-truth/recovered toggle), #2 (Recovered Surface 4th tab), #4 (hardware coordinate readout), and #5 (STL Browser panel swap) were all DELIVERED in Stage 5 — see "Stage 5 — Done" below. Item #5's panel swap was implemented in the REVERSE sense of the wording below: the user's actual preference was whole-STL-context (with the cyan FOV highlight) in the BIG RIGHT panel and the windowed slice in the small bottom-left — see Stage 5 (4d.7). Item #3 (empty Pipeline Stages 6th slot) remains deliberately empty. Of item #7's smaller items: the **extreme-angle warning banner is still DEFERRED** (explicitly parked by the user during Stage 5); load-time progress indicator, STEP file support, and the console mojibake dash also remain deferred. A NEW item beyond this list — the cross-arm optical-obstruction advisory — was added and delivered in Stage 5 (4d.12).

The next strategy chat (Stage 5 prep / lab-view refactor) needs to absorb these accumulated design inputs:

1. **Lab view refactor: ground truth by default, recovered as opt-in overlay.** Lab view (in the 3D Scene tab) defaults to showing the **ground-truth FOV slice** alongside the hardware bodies. A toggle checkbox enables an additional **recovered-surface overlay** (translucent or wireframe, depending on pyqtgraph alpha-bug resolution) drawn from the same origin in a contrasting color so the user can see real-time geometric divergence as angle / distance sliders change. Both can be off, either can be on, or both visible simultaneously. NO xyz coordinate grid in lab view — that's the 4th tab's job (see #2). Rationale: the recovered surface is a math output that legitimately changes when angles/parameters change; defaulting to ground truth keeps lab view honest about "what the camera sees," and the toggle lets the user opt into "what the math produces from what it sees" for live exploration. This also separates "live exploration while adjusting setup" (lab view) from "quantitative analysis of one captured measurement" (4th tab).

2. **New 4th tab: "Recovered Surface" (or similar) — the quantitative comparison view.** A dedicated tab next to STL Browser containing:
   - Rotatable 3D view of the recovered heightmap (matching SurfacePreview's interaction model)
   - **Translucent (or wireframe, depending on pyqtgraph alpha-bug resolution) ground-truth overlay drawn from the same origin in a contrasting color**, both visible by default (this is the dedicated comparison view). Overlay is constrained to the FOV-slice region, NOT the whole STL — the overlay's job is "show me what the system *should* have measured for the region it actually measured."
   - **X/Y/Z coordinate grid with labeled scales in mm** — measurement-grade visualization rather than just shape rendering. THIS GRID IS UNIQUE TO THIS TAB, NOT IN LAB VIEW.
   - Existing error stats panel (mean/std/max-abs/RMS) migrates here from the left pane.
   - Existing error-colormap overlay toggle migrates here.
   - Contract: input is a `(H, W) float64 mm` heightmap from any source — synthetic pipeline OR real hardware capture. The view doesn't care about the source. This future-proofs the tab for hardware integration in Stage 5/6.
   - Known landmine: pyqtgraph 0.14.0 alpha-rendering bug (Stage 4d sub-task 5.5) may force the ground-truth overlay to be wireframe rather than translucent solid. Wireframe is arguably better for comparison anyway (clear truth-cage on top of recovered surface). Same constraint applies to the lab view overlay in #1.
   - **The lab view (#1) and this tab share the same overlay-rendering code path**, with the only differences being: (a) default visibility (lab view = ground truth only by default with recovered opt-in; this tab = both by default); (b) the xyz grid (lab view absent; this tab present); (c) error stats and error overlay (lab view absent; this tab present).

3. **Pipeline Stages 6th slot stays empty.** Slot 5 (recovered height, 2D top-down heatmap) already covers the recovered-output-as-2D representation; adding a second view of the same data in slot 6 would be redundant. Empty for now as a future placeholder for whatever turns out to be useful.

4. **Hardware coordinate readout.** Display the camera and projector physical positions in world coordinates relative to the surface origin (z=0 = stage). Reference points:
   - **Camera position** = center of the lens front face (the bottom circle of the front lens element — the optical entry pupil reference for the imaging side). For a telecentric lens, this is the practical mounting reference.
   - **Projector position** = center of the projector lens exit pupil / front face. For the Pico Genie, this accounts for the documented `PROJECTOR_LENS_X_OFFSET_MM = -6.5` body-frame offset.
   - Output: (x, y, z) triple per arm in mm in the surface-anchored world frame.
   - Could ship as a "Show coordinates" panel in the GUI info section, a CLI script in `scripts/` taking slider values and printing positions, or both.

5. **STL Browser panel swap.** Currently bottom-left = windowed slice 3D preview (Panel 3); big right panel = whole-STL 3D preview with cyan highlight (Panel 1); bottom-left of the layout = minimap (Panel 2). **Proposal:** swap Panels 1 and 3 — windowed slice (what the camera will actually see) takes the big right real estate; whole-STL context becomes the smaller bottom-left view. Minimap stays exactly where it is. Rationale: the windowed slice is the primary thing the user cares about (it's the measurement target); whole-STL context is reference geometry, less central to the interaction.

6. **Web port as final design surface.** Once the GUI refactor above lands cleanly in PyQt6, port the whole thing to HTML for larger screens, shareability without a Python installation, and more visual real estate. The PyQt6 implementation is the **reference implementation** — every UX target validated in PyQt6 becomes a requirement for the web port.

7. **Smaller items also on the parking lot:**
   - **Extreme-angle warning banner** (advisory like the degenerate-λ_eq one, fires when `peak_height / λ_eq` exceeds a safe threshold — say 2π for borderline, π for full safety margin). Closes the UX gap from the recovery angle-sensitivity diagnostic: at >50° projector angles on tall parts, the unwrap fails and the recovered output diverges by 30+ mm. The math is correct; the user just needs to know when they've crossed into "math expects to fail" territory.
   - **Load-time progress indicator** for large STLs. At 500×500 mm 0.1 mm/px = ~200 MB heightmap, rasterization can take 5-20 s and the GUI appears frozen during load. A loading indicator (modal dialog or progress bar) is the obvious palliative.
   - **STEP file support.** The user has STEP-format CAD files; currently must convert to STL externally before loading. Adding a STEP loader requires a new peer module `step_loader.py` (probably backed by `cadquery` or `pythonocc-core`) producing the same `(shape, pixel_size_mm) → (H, W) float64 mm` contract. Real work; deserves its own planning conversation.
   - **Body-overlap design history.** The §13.8 OBB upgrade was deferred from Stage 4b "unless real false positives surface." Real false positives surfaced (22.3 mm and 31.6 mm at ordinary and extreme poses, respectively). The SAT upgrade closes the deferral. Worth recording the AABB → SAT trade-off rationale in this section so it doesn't get re-derived if ever revisited.
   - **Console mojibake dash** in `MSG_SURFACE_OUTSIDE_CONE` (the em-dash gets cp1252-mangled in stdout but renders fine in the Qt banner). Cosmetic; console-only.

### Deferred from Stage 4 (still deferred)

- **MockCamera, MockProjector, Camera/Projector protocols** → Stage 5/6.
- **Taylor/exact model toggle in GUI** → adds two lines later; not v1.
- **Resolution toggle (480×640 vs 1280×1024)** → adds a "Compute at full res" button later. Note: math grid is now (550, 680) post-Stage-4d-sub-task-1.5.
- **Three.js embed for lab view** → explicitly rejected; lab view is native PyQt6 (now part of unified scene). Note: the web port (Stage 4d follow-up parking lot #6) is the appropriate venue for browser-based 3D rendering, not an embed within PyQt6.
- **Object position offset** → locked at center.
- **`equivalent_wavelength()` → `height_per_radian()` rename** → cosmetic; documented in code instead.
- **Unit reconciliation between info panel mm-values and math-layer pixel-values** → Stage 5/6 when real hardware arrives.
- **Click-and-drag scene manipulation (rotate/translate hardware bodies + surface via mouse, sync back to sliders)** → still deferred. The FOV-rectangle drag in Stage 4d's Browser was a concrete instance of mouse-event handling, but it's specialized to a 2D ImageItem + RectROI in a `pg.PlotItem`, not the 3D scene manipulation problem. No shared abstraction was extracted; YAGNI until a second concrete use case appears.
- **Multi-FOV stitching / batch capture** → not in any planned stage yet. Would let the user queue several FOV positions and process them in sequence, producing a stitched result. Out of scope for the simulation; possibly relevant when real hardware lands with motorized stages.
- **Persistence (save/load FOV positions, save committed slices, export results)** → not in any planned stage yet. The simulation is currently stateless across runs.
- **Robust STL ingestion (degenerate triangles, non-manifold meshes, very large files)** → handled to a basic standard (empty mesh raises `ValueError`, XY-degenerate returns zeros). Hardening against pathological inputs is deferred.

### When real hardware arrives (Stage 6 prep)

- Update `HybridGeometry` defaults to real measured values (`a`, `p`, θ_projector_actual, θ_camera_actual, distances) — in physically-consistent units after deciding the unit story.
- Reconcile the math-layer pixel-space constants with the info-panel mm-space display.
- Empirically calibrate `λ_eq` against a step gauge; override formula-derived value if needed.
- `test_project_is_lambda_eq_independent` must still pass after the update — `HybridGeometry` and `SymmetricGeometry` defaults must change in lockstep.
- Scene primitives in `src/scene.py` (Stage 4b) update to reflect real lab layout. Projector lens dimensions (~20mm dia × 5mm protrusion) refined from lab measurement.
- **Re-derive the STL Z cap from hardware** — the 120 mm value is a placeholder backed by bench observation + safety margin. Real value depends on projector focus depth, phase unambiguity range, and triangulation lateral-spill, none of which map to a clean single number until measured against real hardware. `WORKING_VOLUME_MM[2]` and `ABSURDLY_LARGE_MM[2]` must update in lockstep (locked by `test_z_cap_matches_absurd_z`).
- **Re-derive the XY ABSURDLY_LARGE_MM ceiling from real specimens.** The (500, 500) value is a placeholder backed by user-needed specimen size + memory-cost trade-off. Real ceiling depends on the largest specimen geometry the lab actually measures.
- **The new "Recovered Surface" tab's heightmap-from-any-source contract becomes the integration point.** Real hardware capture feeds the same recovery view that synthetic simulation feeds. The translucent ground-truth overlay (when truth is the CAD model) becomes especially valuable here — quantify spatially where the system disagrees with truth on a real measurement.
- **Whole-part-with-FOV-cone visualization in the lab view** becomes viable once the lab view refactor (parking-lot #1) lands. Currently the lab view shows only the committed FOV slice because hardware-mounting geometry isn't finalized — the relative scale of part vs apparatus depends on real mounting. Once real mounting is in AND the refactor makes ground truth the lab view default (with opt-in recovered overlay), the lab view can show the whole part on the stage with the camera/projector cones highlighting the active FOV region. Significant lab view refactor; planned as a Stage 5/6 sub-task.

### Future-stage hooks deferred during Stages 2–4

- **`pattern_generator.py`** (Stage 2 Decision 7): empty stub. Stage 5+.
- **`io_utils.py`**: empty stub. Adds frame I/O when capture loop lands.
- **`scripts/compare_forward_models.py`**: deliberately not created.
- **`MockCamera` / `MockProjector` / Camera-Projector protocols**: deferred to Stage 5/6.

---

## 13. Clip-detection geometry reference (NEW in Stage 4b, refined in Stage 4d follow-up)

This section documents the precise 3D math used in `src/gui/clip_detection.py`. Self-contained: a fresh chat / future maintainer can reconstruct the geometric reasoning from here alone.

### 13.1 Five checks at a glance

`detect_clips(transforms, *, heightmap_mm, surface_pixel_size_mm, camera_distance_mm, projector_distance_mm, viewing_cone_world, projection_cone_world)` returns a `ClipState` with five booleans:

**Collision checks** (gray-override on offending hardware + warning banner):
1. `camera_clipping_surface` — camera lens-front disc dips below z=0 plane
2. `projector_clipping_surface` — projector lens-front disc dips below z=0 plane
3. `bodies_overlapping` — camera assembly oriented bounding box overlaps projector assembly OBB (4 pairwise tests via SAT)

**Coverage advisories** (banner only, no gray):
4. `surface_outside_camera_fov` — any 3D surface sample is outside the camera viewing prism volume (exact test, no tolerance)
5. `surface_outside_projector_cone` — any 3D surface sample is outside the projector cone volume (2 mm advisory tolerance)

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

**No tolerance on this check** — a parallel-sided telecentric prism doesn't have gradual edge falloff. The camera either sees a point or it doesn't.

### 13.4 Projection cone (projector) — 3D point-in-volume

The Pico Genie is **non-telecentric**: the cone diverges linearly from the lens. At axial distance `s` from the apex, the cone's cross-section half-extents are:

```
hw(s) = (s / 1.2) / 2 = s / 2.4
hh(s) = hw(s) * 9 / 16
```

These derive from the 1.2:1 throw ratio (width = throw / 1.2) and 16:9 aspect.

**Stage 4d follow-up: 2 mm advisory tolerance applied.** The cone math models an idealized projection volume with a sharp boundary; real projectors have gradual edge falloff at the cone's geometric bounds. The tolerance widens the per-depth lateral half-extents:

```
hw(s) = (s / 2.4) + _CONE_COVERAGE_TOLERANCE_MM  # 2.0 mm
hh(s) = (s / 2.4) * 9/16 + _CONE_COVERAGE_TOLERANCE_MM
```

The axial `s >= 0` check is NOT relaxed — points behind the apex are a different failure mode, not a near-edge spill.

Test: is a world-frame 3D point `P` inside the cone (post-tolerance)?

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

hw = _CONE_HALF_U_PER_L * s + _CONE_COVERAGE_TOLERANCE_MM
hh = _CONE_HALF_V_PER_L * s + _CONE_COVERAGE_TOLERANCE_MM
inside = (s >= 0) and (abs(lu) <= hw) and (abs(lv) <= hh)
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

### 13.7 Hairline-trigger behavior (refined in Stage 4d follow-up)

At extreme synthetic surface heights (e.g., Gaussian amp=100 mm with camera tilted -20° at WD=157, where the 100mm peak's tip sits 0.25 mm outside the FOV `u_proj = +34.248 mm > 34.0 mm`), the camera-prism advisory will fire on a single sample at the boundary.

This is honest geometric reporting for the camera prism, which stays exact (no tolerance). For the projector cone, sub-mm hairline triggers no longer fire — the 2 mm advisory tolerance (Section 13.4) silences them. The cone math has a sharp idealized boundary; real projectors have gradual edge falloff that covers the sub-2-mm range.

Alternatives considered and rejected for both checks:
- **Sample-count threshold** (e.g., flag only if > K of 121 samples outside): depends on grid resolution; magic threshold; same flaw on both checks.
- **Universal tolerance margin on the camera prism** (similar to the cone): rejected because the prism is parallel-sided with sharp physical boundaries; there's no real-world softening to model.

### 13.8 Body-overlap: SAT oriented-box intersection (Stage 4d follow-up)

Check 3 (`bodies_overlapping`) uses **exact OBB intersection via the Separating Axis Theorem**. Each arm assembly is two oriented boxes (body + lens), giving four pairwise OBB tests: body-vs-body, body-vs-lens (×2), lens-vs-lens. The check returns True if any pair intersects.

SAT tests 15 candidate axes per pair: 3 face normals per box (6 total) + 9 cross products of pairs of face normals. Two boxes are separated iff any axis projection has positive gap; otherwise they intersect.

```python
def _obb_overlap(transform_a, local_corners_a, transform_b, local_corners_b):
    # Extract box center, half-extents, and local axes from transform + corners
    # Build 15 candidate axes (3 + 3 + 9 cross products, skip degenerate < 1e-9)
    # For each axis: project both boxes; if abs(t·axis) > sum_radii, return False
    # Otherwise return True (no axis separates them).
```

**Strict separation, no epsilon:** any positive gap clears; gap-zero (touching) counts as collision. Adding positive tolerance would re-inflate exactly the false-positive surface the SAT upgrade was designed to remove.

**Cross-axis degeneracy threshold 1e-9:** cross products of nearly-parallel axes produce near-zero vectors; skipping them is correct SAT behavior because the parallel-axes case is already covered by the box-local axis tests.

**Why SAT and not AABB:** the earlier AABB approximation (world-frame axis-aligned bounding boxes of rotated bodies, replaced in commit `e3c14bb`) inflated rotated body footprints into large diagonal volumes and false-positive'd up to 31.6 mm of true clearance at ordinary and extreme poses. SAT is exact for boxes, so a long camera lens tilted in world frame no longer over-reports.

---

## 14. Known cosmetic issues

**pyqtgraph 0.14.0 destructor noise** — harmless `RuntimeError` on shutdown from pyqtgraph's GraphicsView teardown. Upstream issue; safe to ignore.

**Banners and grabFramebuffer** — QLabel banners sit above the GL viewport in the Qt widget stack. They DO appear in the live GUI, but `grabFramebuffer()` captures only the GL surface and misses them. Smoke tests verify banner state programmatically (read `.isVisible()` and `.text()` in Python) rather than visually.

**pyqtgraph 0.14.0 colormap availability** — doesn't bundle 'gray' or 'hsv'. Workarounds: manual 2-stop black-to-white `ColorMap` for the fringe-frame panel; `CET-C1` (perceptually-uniform cyclic) for wrapped-phase panel. Documented in `stages_view.py`.

**pyqtgraph 0.14.0 `GLSurfacePlotItem.setData(colors=...)` docstring is wrong** — claims `(width, height, 4)`, actually needs flat `(N_vertices, 4)`. Workaround documented in `surface_preview.py`.

**pyqtgraph 0.14.0 `GLSurfacePlotItem` alpha-rendering bug (Stage 4d sub-task 5.5)** — `alpha < 1.0` on a `GLSurfacePlotItem` produces inverted-complement colors in the rendered output, regardless of shader (`shaded`, `None`, or any other), regardless of color-input path (per-vertex `colors=` or uniform `setColor()`), regardless of sibling-item presence, regardless of `glOptions`. Empirical formula: `output_X ≈ 127 - 44 · input_X` for `alpha=0.5`. Six diagnostic experiments ran during sub-task 5.5 (single-item, white-on-white, pure-RGB inputs, shader=None, alpha=1.0) before isolating alpha as the trigger. Root cause undiagnosed analytically — would require Qt OpenGL driver source-level inspection. **Workaround: use `alpha=1.0` (opaque)** anywhere `GLSurfacePlotItem` color matters. Full diagnostic chain captured in the comment above `_FOV_HIGHLIGHT_COLOR_RGBA` in `stl_browser.py`. **Note for Stage 4d follow-up parking-lot item #2:** the proposed translucent ground-truth overlay on the new Recovered Surface tab will hit this bug if attempted with `alpha < 1.0`. The fallback is wireframe-mesh overlay (which arguably reads better as a reference cage anyway).

**pyqtgraph 0.14.0 sibling `GLSurfacePlotItem` GL state hazard (Stage 4d sub-task 5.5)** — two `GLSurfacePlotItem`s in the same `GLViewWidget` using different `a_color` GL paths (one with constant-attribute `glVertexAttrib4f`, the other with buffer-backed `glVertexAttribPointer`) introduces unreliable GL state transitions. Discovered as a candidate hypothesis during the maroon-vs-cyan investigation (eventually superseded by the alpha-rendering finding above — but the hazard is real even after the alpha workaround). `SurfacePreview` works because it has one `GLSurfacePlotItem` per view. Browser Panel 1 has two, and both must now use the constant-attribute path via `setColor()` at construction. Documented in `stl_browser.py`'s `update_panel1_highlight` docstring.

**Console mojibake dash in clip-detection messages (Stage 4d follow-up)** — `MSG_SURFACE_OUTSIDE_CONE` uses a Unicode em-dash that gets cp1252-mangled when the message is printed to stdout (e.g., during probe scripts or `print(state.messages)` debugging). The Qt banner renders the message correctly; only the console is affected. Cosmetic; non-blocking. Possible future fix: replace the em-dash with an ASCII hyphen in the constant string.

**Load-time freeze for large STLs (Stage 4d follow-up)** — at the (500, 500, 120) absurd limit, rasterization can take 5-20 seconds for ~50k-triangle parts producing ~200 MB heightmaps. The GUI appears frozen during the load; no progress indicator currently exists. Flagged as a parking-lot item; not blocking.

---

### Stage 5 — Done (Lab-view + Recovered-Surface refactor, hardware-coordinate readout, cross-arm obstruction)

**Goal achieved.** Stage 5 grew directly out of the Stage 4d follow-up parking lot. It split the "what the camera sees" (lab view) from "what the math produced vs. what it should have" (a new Recovered Surface tab), added a shared render core, anchored the projector lens geometry correctly, added a live hardware-coordinate readout (the instrument for hardware anchoring), and added a cross-arm optical-obstruction advisory. 11 commits, 271 tests passing at close.

**Stage 5 sub-task table:**

| # | Commit | What landed |
|---|---|---|
| 4d.2 | `68173e5` | **Lab-view ground-truth/recovered XOR toggle.** Two-radio exclusive selector in the Display Mode group; STL-mode scoped (disabled + resting on recovered in Flat/Gaussian); defaults to ground truth in STL ("honest by default"). Error overlay render-suppressed (not state-mutated) when ground truth is shown. +8 tests. |
| 4d.3 | `9fa6266` | **Labeled XYZ mm coordinate grid component** (`src/gui/coordinate_grid.py`). Pure `compute_axis_ticks` (nice-step 1/2/5, headlessly tested) + thin `CoordinateGrid` GL-assembly class. Deterministic opaque labels for dark-bg legibility; adaptive Z tick density + lateral label offset for the short honest-scale Z axis. +27 tests. Smoke `scripts/stage5_grid_smoke.py` kept. |
| 4d.4 | `cff19e3` | **`RecoveredComparisonView`** (`src/gui/comparison_view.py`) + **shared render core** (`src/gui/surface_render.py`: `centered_coords`, `apply_heightmap`, `error_colors`, `ERROR_COLORMAP`). Solid opaque recovered + translucent ground-truth over the grid, independent visibility toggles. The pyqtgraph alpha bug did NOT reproduce on pyqtgraph 0.14.0 / Qt 6.11.0 — §14 amended in this commit. `SurfacePreview` now calls the shared helper (byte-unchanged render). +14 tests. |
| 4d.5 | `b385eb1` | **Wired the comparison view into the 4th "Recovered Surface" tab** (`RECOVERED_TAB_INDEX = 3`). `_build_recovered_surface_page` + tab-local recovered/ground-truth visibility checkboxes. New `_refresh_surface_preview` branch feeds the honest off-part=0 arrays. Rides the existing `currentChanged` refresh, no extra pipeline cost. +6 tests. |
| 4d.6 | `eda7ec6` | **Error stats + colormap + colorbar migrated** off the left panel / 3D Scene tab onto the Recovered Surface tab. New "Color by error" mode (recolors recovered by signed error, render-suppresses the ground-truth overlay). `error_colors` + `ERROR_COLORMAP` factored into `surface_render`. `show_error_overlay` deleted from the 3D Scene tab. Error UI reparented to the tab page for structural cross-tab isolation. +7 tests. |
| 4d.7 | `b6c6e2b` | **STL Browser panel swap.** Whole-STL context (with cyan FOV highlight) → big right; windowed slice → small bottom-left under the minimap. Layout-only; highlight stays bound to `_whole_stl_view`. (This is the REVERSE of parking-lot #5's wording — the user's actual preference.) +1 layout-lock test (asserts splitter structure). |
| 4d.8 | `d42c29e` | **"Color by error" gated on "Recovered surface".** `_on_show_recovered_toggled`: enables color-by-error when recovered is shown; unticking recovered force-unchecks + disables it (one cascade refresh restores solid recovered / GT / hidden colorbar); re-ticking re-enables but leaves it off. +4 tests. |
| 4d.9 | `b6e2bbd` | **Numeric entry on all sliders.** Extended `LabeledFloatSlider`: read-only value label replaced with an editable `QDoubleSpinBox`, bidirectionally synced (blockSignals-guarded, no feedback loop). No step/increment changes — spinbox matches each slider's existing precision; off-grid entry snaps to nearest step, out-of-range clamps, commit on Enter/focus-out. `value()/set_value()/valueChanged` contract preserved (zero external rewiring). +7 tests. |
| 4d.10 | `26b2a7c` | **Projector lens center anchored at origin-when-vertical.** Added the missing face-vertical lens offset + a recess term; body shifts by the negative of the in-face offset so the LENS anchors on the optical axis (body hangs off-axis at (+6.5, +17.5)). `PROJECTOR_LENS_X_OFFSET_MM` promoted to a signed `ProjectorLensOffset(face_x=-6.5, face_vertical=17.5, recess=1.5)` NamedTuple (face-vertical sign flagged UNVERIFIED pending physical mount; backward-compat scalar alias kept). `cone_local_to_world_transform` gained `y_offset_mm` + `recess_mm` (defaulted, camera call unchanged). Visualization-layer only. Cone better-centered when vertical → coverage banner fires less. +4 tests, 3 updated. |
| 4d.11 | `abfbb3e` | **Hardware coordinate readout.** Shared pure helper `arm_lens_front_world(...)` → `{camera, projector}` lens-center world (x,y,z) mm; extracted `_camera_cone_world` / `_projector_cone_world` so `update_pose` and the helper share one cone-placement source. New "Hardware Coordinates" GUI group after Geometry (live in `_on_pose_changed`). CLI `scripts/hardware_coords.py` reuses the helper. Projector reads (0,0,~throw), camera (0,0,WD) when vertical. +4 tests. |
| 4d.12 | `a266c8c` | **Cross-arm optical-obstruction advisory.** Banner-only 6th check: camera assembly in projector cone / projector assembly in camera prism. Extracted bounded per-point predicates (`_points_in_prism` / `_points_in_cone` with `axial_max`); coverage functions now call them with `axial_max=inf` (behavior-preserving). Edge-sampling (7 pts × 12 box edges) catches a long box spearing a convex volume (the 200 mm camera lens). Axial bound (0..throw / 0..WD) excludes behind-lens / beyond-surface hardware. Cross-only pairing. +5 tests. |
| 5 (close) | this commit | Docs update (PROJECT_CONTEXT.md + CONVERSATION_SUMMARY.md) + tag `stage-5-complete`. |

**Key design decisions locked during Stage 5:**

| Decision | Rationale |
|---|---|
| Lab view = ground-truth/recovered XOR (STL mode), defaults to ground truth | Recovered is a math output that changes with angles; defaulting to ground truth keeps lab view honest about "what the camera sees." Flat/Gaussian rest on recovered (toggle disabled — moot for those modes). |
| Recovered Surface tab = solid recovered + translucent ground-truth over labeled grid | Translucent-over-solid reads divergence well for smooth parts; the migrated error colormap + stats are the quantitative readout for blocky parts where the stacked solids interpenetrate. The two are complementary, both available on the tab. |
| Single shared render core (`surface_render.py`) | The pyqtgraph axis/colors transpose quirk + error-color normalization must not diverge between `SurfacePreview` and `RecoveredComparisonView`. One source of truth, dependency-light (no HardwareScene drag-in). |
| Translucent ground-truth via `GLSurfacePlotItem` + `setGLOptions("translucent")` | A throwaway probe (sub-task 1) established the alpha bug does NOT reproduce on this stack; `setGLOptions("translucent")` is the load-bearing call. Built so the render style is swappable to wireframe if it ever inverts on other hardware. |
| Projector lens CENTER anchored at origin-when-vertical (not body center) | The user's measured lens offset (face_x −6.5, face_vertical +17.5, recess) must place the lens — the optical reference — over (0,0). The body shift is the negative of the in-face offset. Visualization-only; the math reads slider angles, not mesh placement. |
| `ProjectorLensOffset` parameterized triple | A projector swap (new unit, different/zero offsets) becomes a one-line constant edit, not a geometry rewrite. Face-vertical sign left UNVERIFIED for physical confirmation. |
| Hardware coordinate readout shares one pure helper for GUI + CLI | `arm_lens_front_world` is the single source of truth; the CLI is tested to print the same numbers as the GUI panel. It is the cross-check instrument for the hardware-anchoring phase. |
| Optical obstruction = banner-only advisory (not gray-out) | The rig is buildable; the measurement is obstructed — same category as coverage. Edge-sampling (not corner-only) is a correctness requirement, not a nicety: the 200 mm camera lens can spear the cone with all corners outside. The axial bound is what kills behind-lens / beyond-surface false positives. |
| Numeric slider entry matches existing slider steps (no finer) | The user chose exact-landing within current granularity over sub-step precision. Spinbox precision = slider step; off-grid snaps to nearest. |

**Architectural decisions worth carrying forward from Stage 5 (especially for the web port):**

- **The 4-tab right pane is the reference UX:** 3D Scene (lab view) / Pipeline Stages / STL Browser / Recovered Surface. The web port must mirror this structure. Lab-view-vs-Recovered-Surface-tab is the deliberate split between live exploration and quantitative comparison (see §7.10).
- **`surface_render.py` is the shared render core.** Any new surface-rendering code (web port included) follows the same heightmap→surface convention (centered coords, the transpose quirk, the error-color normalization) from this one source.
- **The comparison-view pattern** — solid opaque recovered + translucent ground-truth over a labeled XYZ mm grid, with a "color by error" mode — is the validated quantitative-comparison UX. The translucent overlay reads well for smooth parts; the error colormap is the better tool for blocky/tall parts where the surfaces interpenetrate (a user-observed limitation, deliberately complemented rather than replaced).
- **Visualization is decoupled from the math** (§7.11) — confirmed and relied on in 4d.10. The web port's 3D rendering can be rebuilt freely without touching the recovered-surface math.
- **The hardware-coordinate readout** (`arm_lens_front_world` + panel + CLI) is the instrument for the upcoming hardware-anchoring phase. The web port should carry it forward.
- **Diagnostic-before-decision held throughout Stage 5:** the translucent-primitive probe (settled the alpha-bug question before architecting around it), the projector-geometry recon (caught the missing face-vertical offset + confirmed the math-untouched blast radius before any edit), the obstruction-check recon (caught the corner-vs-edge sensitivity + the axial-bound false-positive before building). Each read-only recon prevented a wrong build.

**Carry-forward flags for the hardware phase (Stages 6/7):**

- **FACE-VERTICAL SIGN UNVERIFIED** (4d.10): confirm the projector lens's world-Y side against the real projector at mount time; flip the `ProjectorLensOffset.face_vertical` sign if needed. Magnitude and anchoring are correct regardless.
- **World frame is a logical convention, not yet physically anchored.** The intended anchor: the point directly below a lens when its arm points straight down is world (0,0); z=0 is the stage. This becomes the physical anchor when the new projector arrives and the rig is finalized. The hardware-coordinate readout reports in this frame and is the tool to match the physical setup to it.
- **Deferred mm-vs-pixel unit reconciliation** (still Stage 6/7, unchanged from §9): the math layer uses notebook pixel-space units; the info panel shows mm. Reconcile when real hardware arrives.
- **`Camera` / `Projector` protocols + mocks** still deferred to Stage 6/7 (§7.3).
- **Extreme-angle warning banner** deliberately parked (user's call during Stage 5); the >50° unwrap divergence is correct physics, not a bug — a future advisory would just flag the regime.

### Stage 6 (Phase A → B.3a) — Done (Inverse-FPP pipeline + physical beyond-Nyquist wall + headline showcase)

**Goal achieved.** This phase turned the simulation from one that recovers everything perfectly (no limit in it, so it could demonstrate nothing) into one that contains the **physical beyond-Nyquist wall a real system has** and demonstrates **inverse-FPP beating it**. Before this phase, the live recovery was bias-free (`carrier + height_to_phase`, no `project()`, no fade, no noise) — recovered ≈ ground truth always. The Recovered Surface tab now routes through the projector bias + the sampling fade + optional read noise, so steep features genuinely fail unless inverse-FPP corrects them. 9 commits, 322 tests passing at close, tag `stage-6-b3a-complete`.

**The arc (each commit byte-identical on its default/off path — the sealed core's `[pipeline] std_err` stays 1.764505e-05 throughout):**

| # | Commit | What landed |
|---|---|---|
| A.0.1 | `0f08396` | **Object-space scale bridge.** Canonical `CAMERA_PIXEL_PITCH_UM=4.8`, `CAMERA_MAGNIFICATION=0.09`, `OBJECT_SPACE_UM_PER_PIXEL≈53.33` in `geometry.py`, labeling-only (§7.12). Retired the dead duplicate `pixel_pitch_um=53.0`, redirected to the canonical constant. +2 tests. (No-leak guard owed-and-delivered in A.0.2.) |
| A.0.2 | `9b83479` | **Pixel-area sampling model.** `sampling.contrast_envelope(phase, fill_factor)` — sinc fade on local `\|∇φ\|/2π` cycles/pixel, wired into `synthesize_psi_stack` off-by-default. Gate test binds to a STEEP/height-modulated case (not a uniform carrier) so it can support the headline. + enforceable no-leak guard (`test_no_leak_scale_bridge.py`). +14 tests. |
| A.1 | `db463fe` | **`pattern_generator.py` made real.** `inverse_grating_phase(reference_phase)` reuses the fixture-locked `compute_inverse_phase` tilt-flip (single source of truth). The A.1-deferred 2D question flagged in-code. +4 tests. |
| A.2 | `99a4101` | **Closed the inverse-FPP loop.** `run_inverse_fpp` — reference → inverse grating → project → recover, as ONE wrappable callable (height-in/height-out, so closed-loop later wraps it). Bias-cancellation contrast asserted both sides (naive blows up ~6 orders; corrected meets the bar). Honest tautology label: closure proves CONSISTENCY, not physics (physics = the hardware phase). +5 tests. |
| A.2b | `b55365c` | **Fade live through the loop.** No production logic change (fill_factor already flowed); pins the noiseless truth in docstring + tests: the envelope is **transparent to recovery** (divides out of arctan2), collapses only at the env→0 null. The gradual wall REQUIRES noise — deferred to A.4. +4 tests. |
| A.4 | `b355dd7` | **Additive read-noise model — the fade finally bites.** Gated `noise_sigma`/`rng` in `synthesize_psi_stack`, drawn per-frame-independent (H,W,N). Threaded through `run_inverse_fpp`. Wall bites: faded-region RMS 3.9× flat. Finding #2 measured: N=8/N=4 error ratio 0.707 = 1/√2. Per-frame-independence guard test (fails if ever broadcast). Seeded for reproducibility; `noise_sigma>0` + `rng=None` raises. +6 tests. |
| B.1 | `6460db0` | **Flat-reference nulling before/after on the Recovered Surface tab.** `run_straight_fringe` (failing baseline: project()-on-object, no grating) as a sibling with parameter parity. "Inverse-FPP correction" checkbox (default ON, honest-by-default). Visualization-layer only (§7.11); guardrail held (no GUI test byte-pinned the array). +4 tests. |
| B.2 | `6f01b95` | **Golden-part reference + 2D self-cal.** `selfcal_fit` callable param (default 1D, 308 preserved); golden path uses `fit_tilt_plane` (2D) to remove the y-ramp leak. GUI: golden = current surface, "Inject demo defect" checkbox (visible, default ON); ground-truth stays the golden, error map = deviation-from-golden. C[part−golden] caveat pinned. +6 tests. |
| B.3a | `3987189` | **Beyond-Nyquist headline showcase.** `make_steep_dome` (math-pixel convention — the only convention that crosses Nyquist, §7.16). "Sensor noise" checkbox (fixed σ/seed, threaded identically to both producers). Dynamic-range readout (decoupling + steep-region error ratio, gated dual-run). Convention-aware demo defect. Tests: headline (>100×), decoupling (>10×), defect-on-steep survives, beyond-Nyquist-defect bound, reproducibility. One conscious test update (surface-list enumeration, 4th surface). +8 tests. |
| close | this commit | Docs update (PROJECT_CONTEXT.md + CONVERSATION_SUMMARY.md) + tag `stage-6-b3a-complete`. |

**Key design decisions locked (cross-referenced to §7):**

| Decision | Rationale |
|---|---|
| Scale bridge, not native-metric rewrite (§7.12) | Core is unit-polymorphic but the carrier/X coupling means native-metric reopens the 271-passing core + regenerates fixtures. Bridge touches zero tests. |
| Sampling fade keys off LOCAL gradient, not carrier period (§7.13) | A carrier-period fade would pass a uniform-fine gate but never degrade steep object regions — the headline needs the steep-region fade, which is `\|∇(carrier+height_phase)\|`. |
| Both fade AND noise required for the wall (§7.13) | Noiselessly the envelope divides out of arctan2 (transparent). Only `σ/(B·env·√N)` SNR loss makes a gradual wall. This was the second hidden prerequisite the phase surfaced. |
| Noise per-frame-independent (H,W,N), seeded, explicit rng (§7.13) | A k-common map cancels like env; per-frame is the mechanism. Seed (not Generator) serialized for reproducibility — the future hardware-reference requirement. |
| Tilt-flip nulls a 2D golden; B.1 is the special case (§7.14) | Recon overturned the A.1 worry: flipping curvature about the plane produces −C[h_golden] exactly. `recovered = C[part−golden]`. |
| Self-cal follows the reference's structure (§7.15) | 1D leaks a linear y-ramp on a 2D golden (never curvature); 2D removes it. Default stays 1D so the sealed fixture is untouched. |
| Two honest bounds pinned in code+tests (§7.14) | curvature-only (no absolute tilt) + defect-own-Nyquist degradation. Keeps the showcase from over-claiming; the curvature-only bound IS the AM defect-detection framing. |
| Steep dome = validation gate; steep STL = realism (§7.16) | Dome is extreme/tunable/reproducible for clean numbers; STL is believable AM geometry. Different jobs. |

**Carry-forward flags (open after this close):**

- **B.3b — steep STL part:** the realistic AM demonstration. The dome's headline on a believable part rendered at sensible scale. Reuses the STL Browser plumbing.
- **B.4 — deterministic serializable reference:** formalize the (already-seeded, reproducible) B.3a config into a saved/reloadable reference artifact + serialized headline numbers, as the thing the hardware phase validates against. Smaller than first scoped, because B.3a is already seeded and parameterized.
- **A.3 — independent-route consistency check (deferred, validation hygiene):** derive the inverse by a route that does NOT reuse `project()`'s closed-form, so a test fails if either formula is wrong rather than passing because it's the same line twice. The A.2 bias-cancellation test + the per-frame guard already cover regression; A.3 is added-rigour, not a blocker. Add before the paper if a reviewer angle demands it.
- **GUI polish (B.3 pass):** the steep-dome 3D render is dominated by the unit-seam spike — unusable for the showcase, reads only via the error stats + readout. Normalize/cap the steep-dome Z render or auto-enable Color-by-error. Consider defaulting the legible steep **Gaussian** as the showcase surface (§7.16).
- **Wire `fill_factor` into the live `run_pipeline`** (the bias-free other-tabs path) is deliberately NOT done — only the Recovered Surface tab carries the bias+fade+noise showcase; the 3D Scene / Pipeline Stages tabs keep the original bias-free `run_pipeline` (the "recovered ≈ ground truth always" behaviour the user remembers).
- **The closed-loop iteration (real-time adaptive nulling)** still nests on A.2's single-step `run_inverse_fpp` — the paper's "Real-Time" / "Adaptive" novelty lives in the hardware phase (Stage 7), simulatable as a loop-with-convergence-rule beforehand if desired.
- **Incoming projector (Wintech PRO4500) — specs captured in Section 2.** Optics swap is mostly math-layer (keeps the existing sweep slider; reparameterizes free-throw → lens selector); diamond-pixel resolved (rectangular approx fine); two provisional-now items (lens choice, mount geometry) neither blocking; tentative projector-at-0°/camera-at-angle placement flagged for the bias-arm re-examination. **Integration is Stage 7, after Phase B.**

**The honest framing for the paper (settled this phase):** the nulling *concept* is already in Samara Ch.3 (confirmed by thesis reading) — so the **sim work is the validation gate**, and the genuine extensions are (a) the measured-golden-part reference (over the thesis's 0.1×-scaled-OPD shortcut), and (b) the real-time DLP hardware closed loop + the AM/in-situ application framing, which is the Stage 7 novelty. B.3a's beyond-Nyquist result is reproduced/validated in sim; the headline result the abstract claims is realised on hardware and validated against the (forthcoming) B.4 reference.

---

### Web port (next phase, planned)

Parking-lot #6: port the PyQt6 GUI to HTML/web for larger screens, shareability without a Python install, and more visual real estate. **The PyQt6 implementation is the reference implementation** — every UX target validated in PyQt6 (the 4-tab layout, the lab-view XOR toggle, the comparison view, the labeled grid, the hardware-coordinate readout, the clip/coverage/obstruction advisories) becomes a requirement for the web port. The math layer (pure NumPy) is reused as-is or reimplemented to match; the visualization layer is rebuilt for the browser (Three.js or similar — note the earlier "no Three.js embed inside PyQt6" rejection does NOT apply here; the web port is the appropriate venue for browser-based 3D). Hardware integration (Stages 6/7) follows the web port.

---

*End of context. Ask the user for clarification before starting work.*
