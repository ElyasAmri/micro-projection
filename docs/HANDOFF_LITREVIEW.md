# Handoff — Literature Review & Abstract-Proposal Model

> **Phase 2 direction doc (lit-review / abstract-proposal track).** This file carries
> *where the literature review and the state-of-the-art proposal model stand, and what
> to do next* — the running state-of-play for a lit-review-focused strategy chat. For
> *what the GUI simulation does and the math behind it*, read
> `GUI_SIMULATION_ANALYSIS.md` (the frozen state reference). For deep Phase 1 build
> history, the archived `PROJECT_CONTEXT.md` / `CONVERSATION_SUMMARY.md` remain in the
> repo.
>
> **Companion file:** `HANDOFF_HARDWARE.md` (the hardware-integration track). The two
> tracks run in parallel; this chat focuses on the lit review + proposal model. Update
> this file at the close of any lit-review-focused chat.
>
> **As-of:** Phase 1 complete (GUI digital twin done, commit `7cadaad`+). Literature
> review **not yet started.**

---

## 1. How we work (stable — read first)

The workflow is **conditional on the task**, not a fixed pipeline. Lit-review and
proposal-model work is **mostly direct conversation** with the strategy chat —
surveying the field, positioning the novelty, drafting paper text, deciding what the
proposed model needs. No Claude Code, no commits for that work.

When the proposal model gets **implemented in the GUI** (a future step — building the
state-of-the-art model into the simulation), the standard two-role workflow applies:
the strategy chat plans and drafts halt-and-confirm prompts in fenced blocks; a
separate **Claude Code** terminal executes against the repo; the user gatekeeps every
commit. At that point the Phase 1 discipline holds:

- **Recon before build** — read-only recon (grep-first, `file:line`) before any build
  prompt; summarize-back before coding; halt-and-confirm gates.
- **Sealed core** — `[pipeline] std_err` byte-identical at **1.764505e-05**; changes
  additive / off-by-default; one concept per commit; stage-prefixed commit messages;
  **no Co-Authored-By trailers**; push/tag only at stage close on the user's explicit
  call. (Any new model is additive to the validated core — see
  `GUI_SIMULATION_ANALYSIS.md` §1.3 / §6.1.)

For literature work itself, two conventions:
- **Citations / sources** — when surveying the field, prefer original sources
  (peer-reviewed papers, the thesis, manufacturer spec sheets) over aggregators; record
  what each source actually establishes, in your own words.
- **Decisions get recorded here** — when a framing or model-design decision is settled
  (e.g. "the novelty is X, not Y"), capture it in §4 so it isn't re-litigated next chat.

The passdown substrate for this track is **this file** plus `GUI_SIMULATION_ANALYSIS.md`.

---

## 2. The goal of this track

Two linked deliverables:

1. **Literature review** — survey the state of the art in fringe-projection
   profilometry, in-situ metrology for additive manufacturing, and real-time /
   adaptive fringe projection, to position the paper's contribution and ground the
   Introduction + theory framing.
2. **The abstract-proposal model** — the state-of-the-art model described in the
   paper's abstract: real-time adaptive digital nulling via inverse fringe projection
   for high-resolution in-situ metrology in AM. After the lit review defines it, it
   gets implemented in the GUI (validation in simulation), then on hardware.

The target paper: *"Adaptive Digital Nulling via Real-Time Inverse Fringe Projection
for High-Resolution In-Situ Metrology in Additive Manufacturing."*

---

## 3. The novelty framing (current Phase 1 framing — don't casually discard, but the lit review may sharpen or challenge it)

This is the load-bearing positioning decision as it stands from Phase 1. Treat it as
the working framing to build on — **not** as immune to evidence. The whole point of
the lit review is to test it against the actual field: if a published method turns out
closer to this approach than expected (e.g. real-time adaptive FPP with a curved
reference), that is a genuine prior-art finding to surface and reckon with, **not**
something to downplay to stay consistent with this doc. Refine §3 if the review
warrants it.

- **The thesis (Samara) already simulates nulling on a flat reference.** That is prior
  art within the project's own lineage — it is **not** the paper's novel contribution.
- **The genuine novelty is two things:** (a) the **real-time DLP closed loop** — using
  a *curved golden-part reconstruction* as the nulling reference (not a flat plane),
  driven live through the PRO4500's fast pattern streaming; and (b) the **AM / in-situ
  application framing** — turning the nulling method into in-situ defect detection on
  additively-manufactured parts.
- **The simulation's role is a validation/reproduction gate, not the headline.** The
  GUI proves the method is *consistent* end-to-end (composition, sign, unwrap,
  self-cal, the exact bias cancellation); the headline result is the live closed loop
  on real hardware against a curved golden reference. (See `GUI_SIMULATION_ANALYSIS.md`
  §3.3–§3.4 on why sim closure is consistency, not physics.)

What the sim *already establishes* and the paper can lean on: the inverse grating
`φ = 2P − φ_ref` nulls a genuinely 2D-curved golden part, recovering `C[part − golden]`
(curvature of deviation = defect signal); the honest bounds (a defect whose own
gradient exceeds Nyquist recovers ~61%; pure linear tilt differences are not
recovered); the dynamic-range win (the seeded 219× decoupling / 37691× error-ratio
headline). All detailed in `GUI_SIMULATION_ANALYSIS.md` §2c, §3.

---

## 4. Current status

**Not started.** No literature review conducted yet; the abstract-proposal model is
defined only at the abstract / framing level (§3), not as a concrete simulation or
mathematical specification beyond the thesis baseline.

Paper writing is deferred until simulation proofs and hardware results exist — beyond
the Introduction / theory framing, the paper is not yet ready to write. When this
section has content, keep it as a running log: what was surveyed, what gaps/positioning
the review established, and what the proposal model needs next.

---

## 5. Open items & known unknowns

- **The lit review hasn't scoped its own boundaries yet** — which subfields to cover
  (FPP fundamentals, telecentric FPP, in-situ AM monitoring, real-time/adaptive fringe
  methods, DLP-based structured light), and how deep, is itself a first-chat task.
- **The proposal model is abstract-level only.** Turning "real-time adaptive nulling
  with a curved golden reference" into a concrete mathematical spec + a GUI
  implementation plan is the bridge from this track to a future build. The math
  baseline is the thesis (Ch.2/4) + the inverse-FPP already in the sim; the *new* part
  is the closed-loop / curved-reference dynamics.
- **Sequencing.** Paper sections beyond Introduction/theory wait on (a) simulation
  proofs of the proposed model and (b) hardware results. Don't draft results/discussion
  prematurely.
- **The mathematical reference** is the Samara thesis, Chapters 2–4 (theory + inverse
  grating). The GUI's math is faithful to it (`GUI_SIMULATION_ANALYSIS.md` §2).

---

*End of lit-review / abstract-proposal handoff. Update at the close of each
lit-review-focused chat. For the GUI's capabilities and math, see
`GUI_SIMULATION_ANALYSIS.md`; for the hardware-integration track, see
`HANDOFF_HARDWARE.md`.*
