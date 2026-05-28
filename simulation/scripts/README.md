# simulation/scripts

Validation and figure-generation scripts that reproduce the artefacts shown in
the simulation [README report](../README.md). Each consumes the captures and
metrics produced by `verify_blender_reconstruction.py` (under `out/`) and
writes a figure or video back into `out/`.

Run from anywhere; each script resolves its paths from `__file__`.

| Script | Reproduces | Notes |
| --- | --- | --- |
| `verify_surface_occlusion.py` | The surface-conditioning table (max slope, self-shadow %, relief) for every entry in `SURFACE_KINDS`. | Fast (~10 s). No captures required. |
| `gt_recon_error.py` | The `gt_vs_reconstruction_<surface>.png` figures (3D top-front GT vs reconstruction + signed and absolute error). Takes `--recording <per-capture-dir>` and `--erode-px N` (default 20, matching the README). | Recomputes the reconstruction from existing captures; no Blender re-render. ~30 s. |
| `roughness_analysis.py` | The `roughness_<surface>.png` figure (form/roughness separation + Sa/Sz vs analytic ground truth). Defaults target the `rolling-mound-rough` recording with `lambda_c = 15 mm` and 40-px erosion. | Same recompute cost as `gt_recon_error.py`. |
| `fringe_capture_video.py` | The `fringe_vs_capture.mp4` / `.gif` (projected fringe vs camera capture, three frequencies, 48 phase frames). | Pure CPU (PIL + ffmpeg). ~10 s. |
