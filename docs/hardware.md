# Hardware integration (projector + camera)

The app drives the rig through a `Backend` (see `app/backend/base.py`). Two
implementations satisfy the same interface, so the UI is identical either way:

- **`SimulationBackend`** — renders the capture stack with Blender and scores
  the reconstruction against a known ground-truth surface.
- **`HardwareBackend`** — projects the fringe on a real projector and grabs
  frames from a real camera. A live target has no ground truth, so it produces
  a height map only.

Swapping between them is a launch-time choice, not a code change.

## Choosing the backend

`MP_BACKEND` selects it:

| value        | behaviour                                                        |
|--------------|------------------------------------------------------------------|
| `sim` (default) | Blender + scored reconstruction                               |
| `hardware`   | real projector + camera                                          |
| `auto`       | hardware **iff** a FLIR camera is attached, else sim             |

```sh
python app/main.py                 # simulation
MP_BACKEND=hardware python app/main.py
MP_BACKEND=auto    python app/main.py   # go live just by plugging the camera in
```

## The projector (used as a second screen)

The projector is driven as an ordinary external display: connect it over HDMI,
extend the desktop (do **not** mirror), and the app puts a borderless,
black-background fullscreen window on the non-primary screen. No projector SDK
is involved — see `app/hardware/projector.py`.

- With no second display attached, projection falls back to a small windowed
  preview on the primary screen so you can still bench-test. Connect the
  projector as a second screen for real use.
- Patterns are generated at the projector screen's native resolution and shown
  pixel-for-pixel (no smoothing), so the sinusoid the camera images is exactly
  the one generated. Press **Esc** on the projection to dismiss it.

macOS note: this is the same "extend, then fullscreen a window on it" approach
the Windows rig used — QScreen exposes the external display identically.

## The camera

`MP_CAMERA` selects the driver (`app/hardware/camera.py`):

| value            | camera                                                        |
|------------------|---------------------------------------------------------------|
| `auto` (default) | FLIR if attached, else the **synthetic** camera               |
| `spinnaker`      | FLIR / Teledyne via PySpin (Mono8)                            |
| `opencv`         | any USB / UVC webcam (bench stand-in)                        |
| `dummy`          | synthetic phase-stepped fringe (no device; tests + demos)    |

The synthetic camera lets the whole project → capture → reconstruct loop run
with no hardware at all (it's what the tests use). `auto` never silently grabs a
laptop webcam — it uses the synthetic camera unless a FLIR is present.

### Installing PySpin (the FLIR SDK)

PySpin ships as a platform-specific wheel from Teledyne, not PyPI. The Windows
build is vendored under `.archive/spinnaker_python-*`; install the matching
wheel for your platform + Python version into the venv:

```sh
pip install <spinnaker_python-4.3.0.189-cp310-...>.whl
```

The app runs fine without it — PySpin is imported lazily and its absence just
means the FLIR backend isn't offered.

## Tuning knobs

| env var                 | default | meaning                                       |
|-------------------------|---------|-----------------------------------------------|
| `MP_CAM_EXPOSURE_US`    | (auto)  | fix the FLIR exposure in µs (recommended for phase-shifting, so every step is imaged at identical brightness) |
| `MP_CAPTURE_SETTLE_MS`  | `200`   | wait per step after the pattern is shown, before grabbing (projector refresh + exposure settle) |
| `MP_BLENDER`            | (auto)  | path to the Blender executable (simulation capture) |

## What still needs the real rig

The reconstruction currently trusts the **nominal** rig geometry
(`simulation/geometry_constants.py`: camera tilt, projector footprint). On
hardware those should come from a calibration, not constants — until then a
real height map is only as accurate as the nominal geometry. Capturing and
reconstruction work today; a pose/geometry calibration step is the next piece.
