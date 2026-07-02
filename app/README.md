# Micro-Projection Control

Desktop control application for the fringe-projection profilometry rig, rebuilt
from scratch (PySide6). The shell is a tabbed **canvas** (Projected Image /
Captured Surface / Reconstructed Surface) with a **sidebar** docked on the left
and a **console** docked along the bottom.

Until the real hardware is available, the app drives the sibling `simulation/`
as a virtual rig (a `SimulationBackend` behind the UI): project a fringe,
capture it with Blender, and reconstruct the height map.

Only the `microprojection.maestro` connector is carried over from the previous
app; it lets a maestro agent drive this Qt UI (register kind `qt`, address
widgets by `objectName`, `invoke` named commands).

## Run

```bash
# from this directory, using the repo's shared venv (PySide6 already installed)
../.venv/bin/python -m microprojection
```

## Headless screenshot

```bash
QT_QPA_PLATFORM=offscreen ../.venv/bin/python -m microprojection --screenshot ui.png
```

## Layout

- `microprojection/app.py`: entry point; builds the app, attaches maestro.
- `microprojection/ui/main_window.py`: assembles the tabbed canvas + docks, wires the sidebar to the backend, and exposes the maestro command surface.
- `microprojection/ui/canvas.py`: one viewport (renders images once given one).
- `microprojection/ui/sidebar.py`: specimen selector + Project / Capture / Reconstruct.
- `microprojection/ui/console.py`: bottom log view plus a stdlib-logging bridge.
- `microprojection/ui/process_runner.py`: QProcess wrapper that streams a child process's output (used for the Blender capture).
- `microprojection/ui/styles.py`: the dark theme (palette + stylesheet).
- `microprojection/backend/simulation.py`: the virtual rig; delegates capture to Blender and reconstruction to the simulation.
- `microprojection/maestro/`: copied connector (unchanged).

The simulation is located by path (`MP_SIMULATION_DIR`, else the sibling
`simulation/`) and imported lazily, so app startup never depends on it.

## Tests

```bash
../.venv/bin/python -m pytest -q
```
