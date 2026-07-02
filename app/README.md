# Micro-Projection Control

Desktop control application for the fringe-projection profilometry rig, rebuilt
from scratch (PySide6). The shell is a tabbed **canvas** (Projected Image /
Captured Surface / Reconstructed Surface) with a **sidebar** docked on the left
and a **console** docked along the bottom.

Only the `microprojection.maestro` connector is carried over from the previous
app; it lets a maestro agent drive this Qt UI (register kind `qt`, address
widgets by `objectName`, `invoke` named commands).

## Run

```bash
# from this directory, using the repo's shared venv (PySide6 already installed)
PYTHONPATH=src ../.venv/bin/python -m microprojection
```

## Headless screenshot

```bash
PYTHONPATH=src QT_QPA_PLATFORM=offscreen ../.venv/bin/python -m microprojection --screenshot ui.png
```

## Layout

- `src/microprojection/app.py`: entry point; builds the app, attaches maestro.
- `src/microprojection/ui/main_window.py`: assembles the tabbed canvas + docks and the command surface.
- `src/microprojection/ui/canvas.py`: one empty viewport (renders images once given one).
- `src/microprojection/ui/sidebar.py`: left panel (empty for now).
- `src/microprojection/ui/console.py`: bottom log view plus a stdlib-logging bridge.
- `src/microprojection/ui/styles.py`: the dark theme (palette + stylesheet).
- `src/microprojection/maestro/`: copied connector (unchanged).

## Tests

```bash
PYTHONPATH=src ../.venv/bin/python -m pytest -q
```
