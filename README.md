# Micro-Projection

Monorepo for an optical surface-metrology project.

- **[`simulation/`](simulation/)** — Blender (Cycles) fringe-projection profilometry simulation. See [`simulation/README.md`](simulation/README.md) for the report.
- **[`app/`](app/)** — PySide6 instrument GUI (camera, projector, processing, calibration). The FLIR Spinnaker (PySpin) SDK wheel is hosted as a [release asset](https://github.com/ElyasAmri/micro-projection/releases/tag/spinnaker-sdk).

## Branches

`main` is the integrated view; `app` and `simulation` are also maintained as standalone branches, checked out as git worktrees under `.worktrees/` for parallel development. `git log main` reaches both histories.
