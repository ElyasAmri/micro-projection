# Micro-Projection (monorepo)

Two related lines of work on optical surface metrology, consolidated into one
repository as separate subprojects:

- **[`simulation/`](simulation/)** - a physically-based Blender (Cycles) simulation
  of fringe-projection profilometry: a projector casts sinusoidal fringes, a
  telecentric camera images the deformed pattern, and a multi-frequency
  phase-shifting pipeline reconstructs the surface height map. See
  [`simulation/README.md`](simulation/README.md) for the full report, including
  rendered setup, fringe-vs-capture, reconstruction, and accuracy media.

- **[`app/`](app/)** - the PySide6 instrument application: camera acquisition
  (FLIR/PySpin), the live processing pipeline, and parameter controls for driving
  a real projector/camera rig.

## Layout

```
app/         instrument GUI (acquisition + processing on real hardware)
simulation/  Blender simulation + reconstruction pipeline (the report lives here)
```

Each subproject keeps its own `.gitignore`, dependencies, and entry points.

## Branches and worktrees

`main` is the integrated view (this branch, with both subprojects). The two lines
are also maintained as standalone branches, each developed in its own subfolder of
the repo (files at the branch root rather than under a subdirectory):

- `app` - the instrument application line.
- `simulation` - the simulation line.

These are checked out as git worktrees under `.worktrees/` (git-ignored), so both
can be worked on at once:

```
.worktrees/app/         <- the `app` branch
.worktrees/simulation/  <- the `simulation` branch
```

`main` was formed by merging both branches (preserving each line's full history),
so `git log main` shows the complete history of both subprojects.
