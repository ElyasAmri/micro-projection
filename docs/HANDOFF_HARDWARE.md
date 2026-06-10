# Handoff — Hardware Integration

> **Phase 2 direction doc (hardware track).** This file carries *where the hardware
> work stands and what to do next* — it is the running state-of-play for a
> hardware-focused strategy chat. For *what the GUI simulation does and the math
> behind it*, read `GUI_SIMULATION_ANALYSIS.md` (the frozen state reference). For
> deep Phase 1 build history, the archived `PROJECT_CONTEXT.md` /
> `CONVERSATION_SUMMARY.md` remain in the repo.
>
> **Companion file:** `HANDOFF_LITREVIEW.md` (the lit-review / abstract-proposal
> track). The two tracks run in parallel; this chat focuses on hardware. Update this
> file at the close of any hardware-focused chat.
>
> **As-of:** Phase 1 complete (GUI digital twin done, commit `7cadaad`+). Hardware
> integration **not yet started.**

---

## 1. How we work (stable — read first)

The workflow is **conditional on the task**, not a fixed pipeline. Pick the mode by
where you are in the process:

- **Pure hardware, no code** — aiming/focusing the projector, mounting, physical
  alignment, taking measurements at the bench, interpreting what you see. This is a
  **direct conversation** with the strategy chat: reason through the setup together,
  no Claude Code, no prompts, no commits.
- **Hardware + code** — interfacing the FLIR camera (PySpin/Spinnaker), driving the
  PRO4500, writing capture / calibration / integration code. This uses the **two-role
  workflow**: the strategy chat plans, scopes, and drafts halt-and-confirm prompts in
  fenced blocks; a separate **Claude Code** terminal executes against the repo; the
  user gatekeeps every commit.

You decide which mode you're in. When code *is* involved, the Phase 1 discipline
still holds:

- **Recon before build** — read-only recon pass (grep-first, `file:line`) before any
  build prompt; summarize-back before coding; halt-and-confirm gates; screenshot/GUI
  gate before commit where the GUI is involved.
- **Sealed core** — `[pipeline] std_err` byte-identical at **1.764505e-05**; changes
  additive / off-by-default; one concept per commit; stage-prefixed commit messages;
  **no Co-Authored-By trailers**; push/tag only at stage close on the user's explicit
  call. (Hardware capture code is downstream of the math core, like the viz layer —
  it must not perturb the seal. See `GUI_SIMULATION_ANALYSIS.md` §1.3 / §6.1.)
- **Two-role separation** — the strategy chat plans and never reconstructs docs from
  memory (it reads existing files before drafting updates); Claude Code executes and
  halts for approval; the user is the only one who commits/pushes.

The strategy-chat ⇄ Claude-Code passdown substrate for Phase 2 is **this file** plus
`GUI_SIMULATION_ANALYSIS.md`. Keep this file current as the hardware loop progresses.

---

## 2. The goal of this track

Take the simulation-validated inverse-FPP method to **real hardware** and recover the
surface topography of a physical test object, comparing the result against ground
truth.

The end-to-end target:
1. Physically set up the camera + projector arms at a known geometry.
2. Project real fringe patterns from the PRO4500; capture real phase-shifted frames
   with the FLIR.
3. Run the captured frames through the **same math core** the sim already validates
   (the only thing that changes is the *source* of the N intensity images — synthetic
   → real; the recovery path is identical).
4. Recover the height map / deviation, and compare against a measured ground truth.
5. Eventually: the real-time adaptive-nulling closed loop (project an inverse grating,
   re-capture, null the projector bias live) — the paper's headline novelty.

**The B.4 serializable reference is the designated validation oracle.** The sim froze
a deterministic reference (`tests/fixtures/b4_reference/`); the hardware phase
validates against a real projector whose bias is **not** the analytic Taylor model —
which is what turns the sim's end-to-end *consistency* proof into a real *physics*
test (see `GUI_SIMULATION_ANALYSIS.md` §3.3, §3.4).

---

## 3. The rig (what's in the lab)

**Camera — FLIR Blackfly S BFS-U3-13Y3M-C** (SN 26048170). Mono, USB3 Vision, global
shutter, 1280×1024 @ 4.8 µm, up to 170 fps, 1/2" sensor. C-mount. Body 29×29×30 mm.
**SDK: Spinnaker / PySpin** (Python bindings) — this is the interface code's entry
point when capture wiring starts.

**Camera lens — Edmund #58-259 TECHSPEC GoldTL telecentric.** 0.09× mag, 132–182 mm
WD (focusable), <0.2° telecentricity. Geometry verified against the official GoldTL
spec table (200 mm length; 76/59/65 mm sections; 110/55 mm diameters). Telecentric =
M constant regardless of object distance; does **not** force a vertical camera mount.

**Projector — Wintech PRO4500** (TI DLP LightCrafter 4500 optical engine). Physical
unit in the lab. DMD 912×1140 @ 7.6 µm, 0% offset optics, ±12° mirror tilt. Body
84×54×145 mm + a 30 mm-dia × 65 mm protruding lens barrel (210 mm total reach).
Field-swappable lenses; **the 184 mm-WD lens is the one physically attached** (full
camera coverage), with the 92 mm lens also available. Pattern rates up to 2,880 Hz
binary / 120 Hz 8-bit grayscale (mini-HDMI) — the basis for the real-time closed-loop
framing. The Pico Genie is the retired placeholder.

**Pending hardware (gates real measurements):**
- **Mounting hardware** — kinematic stages / rigid mounts. Until this exists, stable
  repeatable geometry (and therefore calibration) isn't viable.
- **Optical breadboard** for stable component layout.

---

## 4. Current status

**Not started.** Phase 1 (the GUI digital twin) is complete and the method is
sim-validated end-to-end. No physical capture, calibration, or hardware interface
code exists yet.

When this section has content, keep it as a running log: what was set up / measured /
wired, what the captured data showed, and what's immediately next.

---

## 5. Open items & known unknowns

- **`Camera` / `Projector` protocol + mocks (deferred since Stage 4).** The capture
  abstraction (a hardware-interface protocol with a mock for testing) was intentionally
  deferred until the real SDK was in hand. Designing it against PySpin/Spinnaker (and
  the PRO4500's pattern-streaming interface) is the natural first coding task of this
  track.
- **Mounting geometry → calibration.** Real (θ_projector, θ_camera), working distance,
  and the pixel/µm scale must be *measured*, not assumed. The sim's scale bridge
  (4.8/0.09 µm/px) is a display-only label; the real values come from calibration
  artifacts (flat reference, step-height standard, calibrated grid).
- **The likely default test setup** is projector at 0° (vertical, minimizes
  projection-arm perspective curvature) with the **camera at the triangulation angle**.
  The telecentric camera adds **no** perspective bias when tilted — θ_camera is a
  triangulation angle in λ_eq (Eq. 2-51), not a bias term; the non-telecentric
  projector remains the sole bias source the inverse grating corrects. (Full reasoning
  in `GUI_SIMULATION_ANALYSIS.md` §2b.)
- **Sim-perfect-null vs hardware residual.** The sim nulls to machine precision because
  the same analytic model builds and corrects; real hardware will leave residual. Don't
  over-claim the sim result as a hardware result — this is exactly what the hardware
  phase exists to measure.
- **Teammate coordination (Ilyas).** Ilyas runs a parallel projector hardware-integration
  branch off `projector-wintech-husam`; keep his work in separate `_build_*` methods,
  never blind-merge (watch for `scene.py` conflicts).

---

*End of hardware handoff. Update at the close of each hardware-focused chat. For the
GUI's capabilities and math, see `GUI_SIMULATION_ANALYSIS.md`; for the lit-review /
abstract-proposal track, see `HANDOFF_LITREVIEW.md`.*
