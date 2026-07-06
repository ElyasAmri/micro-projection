# Micro-Projection Control

Desktop control application for the fringe-projection profilometry rig, rebuilt
from scratch (PySide6). The shell is a tabbed **canvas** (Projected / Captured /
Reconstructed / Noise / Roughness / Rig) with a **sidebar** docked on the left
and a **console** docked along the bottom. The Rig tab shows an annotated
Blender overview of the scene geometry (`simulation/rig_preview.py`) with the
lab's hardware modeled to vendor dimensions -- the PRO4500 projection engine,
the FLIR + GoldTL telecentric camera assembly in its mounting clamp, and the
125 mm Z-stage under the specimen, all on the vertical breadboard bench
(24"x24" base + 48"x24" upright, coupled by right-angle brackets) -- rendered
on demand via the sidebar's
"Render Rig View"; drag on it to orbit the viewpoint (a centered gizmo tracks
the drag, the re-render fires on release) and scroll to zoom.

Until the real hardware is available, the app drives the sibling `simulation/`
as a virtual rig (a `SimulationBackend` behind the UI): project a fringe,
capture it with Blender, and reconstruct the height map.

Only the `maestro` connector is carried over from the previous app; it lets a
maestro agent drive this Qt UI (register kind `qt`, address widgets by
`objectName`, `invoke` named commands).

## Run

```bash
# from the micro-projection repo root, using the shared venv (PySide6 installed)
.venv/bin/python app/main.py
```

## Headless screenshot

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python app/main.py --screenshot app/ui.png
```

## Layout

Flat under `app/` (no wrapper package), matching the sibling `simulation/`:

- `main.py`: entry point; builds the app, attaches maestro.
- `ui/main_window.py`: assembles the tabbed canvas + docks, wires the sidebar to the backend, and exposes the maestro command surface.
- `ui/canvas.py`: one viewport (renders images once given one).
- `ui/sidebar.py`: specimen selector + Project / Capture / Reconstruct.
- `ui/console.py`: bottom log view plus a stdlib-logging bridge.
- `ui/process_runner.py`: QProcess wrapper that streams a child process's output (used for the Blender capture).
- `ui/styles.py`: the dark theme (palette + stylesheet).
- `backend/simulation.py`: the virtual rig; delegates capture to Blender and reconstruction to the simulation.
- `maestro/`: copied connector (unchanged apart from its import paths).

The simulation is located by path (`MP_SIMULATION_DIR`, else the sibling
`simulation/`) and imported lazily, so app startup never depends on it.

## Tests

```bash
.venv/bin/python -m pytest app/tests -q
```
