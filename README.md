# Micro-Projection: Fringe-Projection Profilometry Simulation

A physically-based simulation of structured-light surface metrology. A projector
casts sinusoidal fringe patterns onto a surface, a telecentric camera images the
deformed fringes, and a multi-frequency phase-shifting pipeline reconstructs the
surface height map. The optical capture is rendered in Blender (Cycles) so that the
light transport - projection, shading, shadowing, foreshortening - is simulated
rather than approximated.

All media below is rendered straight from the pipeline and hosted as
[release assets](https://github.com/ElyasAmri/micro-projection/releases/tag/media-v1),
so this README doubles as a living report that updates as the simulation evolves.

## Projection setup

![Projection setup overview](https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/setup_overview.gif)

The projector (orange cone) throws a fringe pattern onto the surface; the
telecentric camera (blue parallel tube) images it from the opposite side. Both sit
at 41 degrees from the surface normal, forming a real triangulation rig: the object
deforms the fringe and casts a shadow that masks the plane behind it. The camera's
field is sized to just exceed the projected region.

Full-quality video:
[setup_overview.mp4](https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/setup_overview.mp4)

## How it works

Fringe-projection profilometry recovers depth from how a known pattern bends when
it lands on a 3D surface. Where the surface is closer to the projector the fringes
shift; measuring that shift at every pixel yields a height map.

### 1. Project and capture

![Projected fringe vs camera capture](https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/fringe_vs_capture.gif)

Left: the projected sinusoidal fringe at a given phase. Right: the telecentric
camera's view of that fringe deformed by the surface relief, with the object's
shadow masking the plane. The sweep runs three frequencies - coarse (768 px),
medium (192 px), and fine (48 px) on the projector - each labeled with its physical
pitch on the measurement plane in millimetres.

Full-quality video:
[fringe_vs_capture.mp4](https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/fringe_vs_capture.mp4)

### 2. Phase extraction and unwrapping

- N-step phase-shifting algorithm (PSA): 16 equally spaced phase shifts per
  frequency are combined with sin/cos accumulators into a wrapped phase via
  `atan2`.
- Carrier removal then temporal unwrapping: the coarse frequency gives an
  unambiguous (but noisy) phase that disambiguates the next finer frequency, down a
  geometric 4x ladder (768 -> 192 -> 48), so the fine frequency keeps its
  sensitivity without 2-pi ambiguity.
- The unwrapped phase maps to projector coordinate, and triangulation against the
  known projector/camera geometry yields height.

### 3. Reconstruction loop

![Reconstruction acquisition loop](https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/reconstruction_loop.gif)

The acquisition loop in motion: each capture is folded into the running height
estimate (capture -> apply -> shift -> repeat), refining from the coarse model to
the final fine-frequency surface.

Full-quality video:
[reconstruction_loop.mp4](https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/reconstruction_loop.mp4)

## Results

Each panel set: ground truth and reconstruction (3D, viewed top-front and grounded
on the base plane) alongside the signed error (GT - reconstruction) and an
absolute-error heatmap. Heights are in millimetres. Metrics are reported on the
solved mask eroded by 20 pixels to exclude low-modulation field-boundary artifacts
(standard practice in optical metrology).

### Well-conditioned case: `rolling-mound` (default)

![Rolling-mound reconstruction](https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/gt_vs_reconstruction_rolling-mound.png)

On the slope-safe default surface the reconstruction reaches RMSE **0.67 mm**,
MAE **0.084 mm**, R2 **0.90**. The error panels are essentially zero across the
whole interior - the system reaches sub-100-um typical accuracy when the surface
stays within the projector's grazing budget.

### Stress test: `ring-crater` (intentionally steep rim)

![Ring-crater reconstruction](https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/gt_vs_reconstruction_ring-crater.png)

For comparison, the deliberately demanding `ring-crater` (max slope 65.9 deg,
above the 48.6 deg budget): RMSE **0.94 mm**, MAE **0.087 mm**, R2 **0.94**. The
typical accuracy is the same sub-100-um as rolling-mound, but the signed-error
panel reveals a thin arc following the steep rim - precisely where self-shadowing
hides the surface from the projector. Max-abs error there reaches 12 mm. This is
the failure mode predicted by the slope-budget analysis below, and the reason
`rolling-mound` is the well-conditioned default.

## Surface conditioning (no self-occlusion)

A surface scanned by an angled projector must not shadow itself: any face steeper
than the projector's grazing angle hides the region behind it, leaving no fringe
data there. With both devices at 41.4 degrees from the normal the slope budget is
about 48.6 degrees. Test surfaces are checked against this budget with a directional
horizon test:

| Surface       | Max slope | Self-shadowed | Continuous |
| ------------- | --------- | ------------- | ---------- |
| rolling-mound | 18.4 deg  | 0.00 %        | yes        |
| saddle-ripple | 16.3 deg  | 0.00 %        | yes        |
| twin-hills    | 41.1 deg  | 0.00 %        | yes        |
| dome-ridge    | 52.0 deg  | 0.00 %        | yes        |
| folded-sheet  | 58.0 deg  | 5.4 %         | yes        |
| ring-crater   | 65.9 deg  | 13.4 %        | yes        |
| cross-groove  | 80.9 deg  | 9.9 %         | no (steps) |
| terrace       | 84.9 deg  | 14.2 %        | no (steps) |

`rolling-mound` is the default scanned surface: a smooth sum of broad Gaussians and
a low-frequency undulation, single-valued, continuous in every cross-section, and
slope-bounded so it never self-occludes the projection while keeping ~10 mm of
relief.

## Repository layout

Scripts at the simulation root drive the full pipeline:

- `blender_projector_capture.py` - builds the projector/telecentric scene in
  Blender and renders the fringe captures.
- `verify_blender_reconstruction.py` - orchestrates rendering, runs the solver,
  and writes metrics and the comparison outputs.
- `render_setup_overview.py` - renders the projection-setup overview video.
- `benchmark_blender_reconstruction_improvements.py` - sweeps surfaces and
  settings to benchmark reconstruction quality.
- `reconstruction.py` - the reconstruction core: PSA, unwrapping, calibration,
  and similarity metrics.
- `shared/synthetic_surfaces.py` - analytic ground-truth test surfaces.

## Running

Render and reconstruct with Blender (defaults to the slope-safe `rolling-mound`
surface):

```
python verify_blender_reconstruction.py --optimized
```

Render the projection-setup overview video:

```
python render_setup_overview.py --output-dir out/setup_overview
```

Dependencies are in `requirements.txt` (NumPy, OpenCV, imageio). The Blender
scripts target Blender 5.1 (Cycles, GPU); the verify script invokes `blender.exe`
as a subprocess. Reconstruction outputs are written under `out/` (git-ignored).
