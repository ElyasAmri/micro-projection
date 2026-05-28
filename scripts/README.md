# scripts

Validation + figure-generation. Reproduce the artefacts in the [simulation README](../README.md). Run from anywhere.

| Script | Reproduces | Cost |
| --- | --- | --- |
| `verify_surface_occlusion.py` | surface-conditioning table | ~10 s, no captures needed |
| `gt_recon_error.py` | `gt_vs_reconstruction_<surface>.png`. `--recording <dir>`, `--erode-px N` (default 20). | ~30 s |
| `roughness_analysis.py` | `roughness_<surface>.png` (form + roughness + Sa/Sz). Defaults: `rolling-mound-rough`, λc = 15 mm, 40-px erosion. | ~30 s |
| `fringe_capture_video.py` | `fringe_vs_capture.mp4` / `.gif` | ~10 s, CPU only |
