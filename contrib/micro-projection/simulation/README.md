# Fringe-projection profilometry simulation

A projector casts sinusoidal fringes onto a surface; a telecentric camera images the deformed pattern; a multi-frequency phase-shifting pipeline recovers the height map. Captures are rendered in Blender (Cycles) so light transport is simulated rather than approximated. All media is hosted as [`media-v1`][rel] release assets.

[rel]: https://github.com/ElyasAmri/micro-projection/releases/tag/media-v1

## Projection setup

![Projection setup overview][setup-gif]

Projector (orange cone) and telecentric camera (blue tube) at 41° from the plane normal. The camera field just exceeds the projected region. [`setup_overview.mp4`][setup-mp4]

## Pipeline

**Project + capture** — three frequencies (768 / 192 / 48 projector px), 16 phase shifts each.

![Projected fringe vs camera capture][fvc-gif]

[`fringe_vs_capture.mp4`][fvc-mp4]

**Phase + unwrap** — N-step PSA per frequency → carrier removal → temporal unwrap (coarse disambiguates fine on a 4× ladder) → unambiguous projector coordinate.

**Triangulate** — photometric depth solve against the known projector/camera geometry → metric height.

**Acquisition loop**

![Reconstruction acquisition loop][rec-gif]

[`reconstruction_loop.mp4`][rec-mp4]

## Results

Metrics on the solved mask eroded by 20 px (standard low-modulation field-boundary exclusion).

| Surface | RMSE | MAE | R² | Max-abs |
| --- | --- | --- | --- | --- |
| `rolling-mound` (default, slope-safe) | 0.67 mm | 0.084 mm | 0.90 | 6.2 mm |
| `ring-crater` (stress test, steep rim) | 0.94 mm | 0.087 mm | 0.94 | 12 mm |

![Rolling-mound reconstruction][gt-rm]

![Ring-crater reconstruction][gt-rc]

`ring-crater`'s max-abs concentrates on a thin arc along the rim — the self-shadow region predicted by the slope budget below. Typical accuracy is otherwise sub-100 µm.

## Roughness (Sa, Sz)

Form/roughness separation with a Gaussian S-filter (ISO 16610-21, λc = 15 mm), ISO 25178 Sa / Sz on the residual. Validated on `rolling-mound-rough` = `rolling-mound` + three superposed sinusoids with computable analytic Sa.

![Form/roughness separation and Sa/Sz validation][roughness]

| Sa source | Sa | Sz |
| --- | --- | --- |
| analytic (formula) | 93 µm | 710 µm |
| filter on truth height | 116 µm | 924 µm |
| **filter on reconstruction** | **128 µm** | 1423 µm |

Reconstruction Sa is within **11 %** of what the same filter extracts from ideal data. Sz is outlier-sensitive (max − min, not an average), so it over-reads more than Sa.

## Surface conditioning

Projector and camera both at 41.4° from the plane normal → **slope budget 48.6°**. A face steeper than that hides the region behind it. Per-surface horizon test:

| Surface             | Max slope | Self-shadowed | Continuous |
| ------------------- | --------- | ------------- | ---------- |
| saddle-ripple       | 16.3°     | 0.00 %        | yes        |
| rolling-mound       | 18.4°     | 0.00 %        | yes        |
| rolling-mound-rough | 26.0°     | 0.00 %        | yes        |
| twin-hills          | 41.1°     | 0.00 %        | yes        |
| dome-ridge          | 52.0°     | 0.00 %        | yes        |
| folded-sheet        | 58.0°     | 1.7 %         | yes        |
| ring-crater         | 65.9°     | 6.6 %         | yes        |
| cross-groove        | 80.9°     | 5.0 %         | no (steps) |
| terrace             | 84.9°     | 7.1 %         | no (steps) |

`rolling-mound` is the default: smooth, slope-bounded to ~18°, ~10 mm relief.

## Gallery

Same rig, different surfaces. `rolling-mound` is in the headline video above.

**`rolling-mound-rough`** — same form + controlled high-frequency texture (Sa/Sz validation surface)
![][rmr-gif]
[`.mp4`][rmr-mp4]

**`dome-ridge`** — broad central dome with horizontal ridge
![][dr-gif]
[`.mp4`][dr-mp4]

**`twin-hills`** — two off-axis mounds with a saddle
![][th-gif]
[`.mp4`][th-mp4]

**`ring-crater`** — steep ring + central pit (stress test)
![][rc-gif]
[`.mp4`][rc-mp4]

## Layout

```
simulation/
  verify_blender_reconstruction.py    CLI + orchestration
  reconstruction.py                   PSA, unwrap, S-filter, Sa/Sq/Sz/Ssk/Sku, similarity
  geometry.py                         world <-> projector/camera transforms
  solver.py                           multi-frequency photometric depth solver
  outputs.py                          capture loaders, write_uint8, colormap
  recording.py                        four-panel acquisition recording
  blender/                            scripts that run inside Blender (import bpy)
  scripts/                            CPU-only figure-generation scripts
  shared/synthetic_surfaces.py        analytic test surfaces
```

## Running

```
cd simulation/
python verify_blender_reconstruction.py --optimized
```

`--optimized` enables the three-frequency / 16-phase preset the numbers above reflect. Without it the default is two-frequency / 8-phase. Reconstruction outputs go to `out/` (git-ignored).

Scripts under `blender/` import `bpy` and must be launched through Blender:

```
blender -b -P simulation/blender/render_setup_overview.py -- --output-dir out/setup_overview
```

Targets Blender 5.1 (Cycles, GPU).

[setup-gif]: https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/setup_overview.gif
[setup-mp4]: https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/setup_overview.mp4
[fvc-gif]: https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/fringe_vs_capture.gif
[fvc-mp4]: https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/fringe_vs_capture.mp4
[rec-gif]: https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/reconstruction_loop.gif
[rec-mp4]: https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/reconstruction_loop.mp4
[gt-rm]: https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/gt_vs_reconstruction_rolling-mound.png
[gt-rc]: https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/gt_vs_reconstruction_ring-crater.png
[roughness]: https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/roughness_rolling-mound-rough.png
[rmr-gif]: https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/setup_rolling-mound-rough.gif
[rmr-mp4]: https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/setup_rolling-mound-rough.mp4
[dr-gif]: https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/setup_dome-ridge.gif
[dr-mp4]: https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/setup_dome-ridge.mp4
[th-gif]: https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/setup_twin-hills.gif
[th-mp4]: https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/setup_twin-hills.mp4
[rc-gif]: https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/setup_ring-crater.gif
[rc-mp4]: https://github.com/ElyasAmri/micro-projection/releases/download/media-v1/setup_ring-crater.mp4
