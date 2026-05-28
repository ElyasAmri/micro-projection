"""Side-by-side video: projected fringe phase (left) vs camera capture (right).

For each frequency (coarse -> fine) sweeps the phase-shift sequence, showing the
ideal projected fringe alongside what the telecentric camera captures of that
fringe deformed onto (and shadow-masked by) the surface.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[2]
# verify module lives at simulation/ after the PySide6 cleanup flatten.
sys.path.insert(0, str(REPO_ROOT / "simulation"))
import verify_blender_reconstruction as V

BASE = REPO_ROOT / "out" / "blender_reconstruction_rolling-mound-rough"
PERIODS = [("period_768p0", "coarse"), ("period_192p0", "medium"), ("period_48p0", "fine")]
PANEL_H = 540
GAP, MARGIN = 30, 30
TITLE_H, LABEL_H, FOOT_H = 54, 32, 44
FG, DIM, ACCENT = (235, 238, 244), (150, 158, 172), (90, 200, 255)
DEG = chr(176)
OUT = REPO_ROOT / "out" / "fringe_vs_capture.mp4"


def _font(size: int, bold: bool = False):
    name = "arialbd.ttf" if bold else "arial.ttf"
    try:
        return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
    except OSError:
        return ImageFont.load_default()


def _to_rgb(frame: np.ndarray) -> Image.Image:
    # _load_sequence returns 0..255 for RGB inputs (its mean(axis=2) promotes to
    # float, skipping the integer-normalise branch) but 0..1 for grayscale; detect.
    arr = frame * 255.0 if float(frame.max()) <= 1.0 else frame
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="L").convert("RGB")


def _centered(draw, cx, y, text, font, fill):
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    draw.text((cx - (r - l) / 2, y), text, font=font, fill=fill)


def main() -> None:
    f_title, f_label, f_small = _font(26, True), _font(20, True), _font(17)

    # Resize each panel to a common height; widths follow each source aspect.
    fringe_w = round(PANEL_H * 1024 / 768)
    object_w = round(PANEL_H * 1028 / 752)
    left_x = MARGIN
    right_x = MARGIN + fringe_w + GAP
    canvas_w = right_x + object_w + MARGIN
    canvas_w += canvas_w % 2  # even dims for yuv420p
    panel_top = TITLE_H + LABEL_H
    canvas_h = panel_top + PANEL_H + FOOT_H
    canvas_h += canvas_h % 2

    tmp = Path(tempfile.mkdtemp(prefix="fringe_cap_"))
    n = 0
    for period_dir, tier in PERIODS:
        pdir = BASE / period_dir
        md = json.loads((pdir / "metadata.json").read_text())
        period_px = float(md["fringe_period_px"])
        pitch_mm = V._fringe_pitch_mm(md, period_px)
        phases = list(md.get("phases_deg", []))
        fringes = V._load_sequence(pdir / "fringes", "fringe")
        objects = V._load_sequence(pdir / "object", "object")
        steps = min(len(fringes), len(objects))
        for i in range(steps):
            phase = phases[i] if i < len(phases) else i * 360.0 / steps
            canvas = Image.new("RGB", (canvas_w, canvas_h), (14, 17, 23))
            d = ImageDraw.Draw(canvas)
            _centered(d, canvas_w / 2, 12,
                      f"Fringe acquisition  -  period {period_px:.0f} px  "
                      f"({pitch_mm:.2f} mm pitch)  -  {tier}",
                      f_title, FG)
            lp = _to_rgb(fringes[i]).resize((fringe_w, PANEL_H), Image.BILINEAR)
            rp = _to_rgb(objects[i]).resize((object_w, PANEL_H), Image.BILINEAR)
            canvas.paste(lp, (left_x, panel_top))
            canvas.paste(rp, (right_x, panel_top))
            d.rectangle([left_x, panel_top, left_x + fringe_w, panel_top + PANEL_H],
                        outline=(60, 66, 78), width=1)
            d.rectangle([right_x, panel_top, right_x + object_w, panel_top + PANEL_H],
                        outline=(60, 66, 78), width=1)
            _centered(d, left_x + fringe_w / 2, TITLE_H + 4, "Projected fringe", f_label, ACCENT)
            _centered(d, right_x + object_w / 2, TITLE_H + 4, "Camera capture", f_label, ACCENT)
            _centered(d, left_x + fringe_w / 2, panel_top + PANEL_H + 12,
                      f"phase shift = {phase:.0f}{DEG}", f_small, DIM)
            _centered(d, right_x + object_w / 2, panel_top + PANEL_H + 12,
                      "fringe deformed by surface; object shadow masks the plane", f_small, DIM)
            n += 1
            canvas.save(tmp / f"frame_{n:04d}.png")

    print(f"composited {n} frames -> {tmp}")
    subprocess.run([
        "ffmpeg", "-y", "-framerate", "8", "-i", str(tmp / "frame_%04d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(OUT),
    ], check=True)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
