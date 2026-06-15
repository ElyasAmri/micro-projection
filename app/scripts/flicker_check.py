"""One-off: measure flat-field temporal noise at the old vs flicker-safe exposure.

Projects a uniform field on the LightCrafter projector, then captures two frame
sets from the Blackfly. one at 20 ms (the exposure that flickered) and one at
the exposure snapped to whole projector frames. Reports per-pixel temporal std
and the whole-frame brightness swing for each so the fix can be confirmed.
"""
import sys
import time

import numpy as np
import PySpin
from PySide6.QtWidgets import QApplication

sys.path.insert(0, "app/src")
from microprojection.acquisition import camera_config
from microprojection.acquisition.camera_settings import (
    CameraSettings,
    flicker_safe_exposure,
)
from microprojection.patterns import flat_field
from microprojection.ui.projector_window import ProjectorWindow

N = 300          # frames per variant
SETTLE = 12      # frames discarded after (re)configuring


def capture(cam, settings, app):
    camera_config.configure(cam, settings)
    cam.BeginAcquisition()
    count = 0
    mean = m2 = None
    frame_means = []
    grabbed = 0
    while grabbed < N + SETTLE:
        img = cam.GetNextImage(2000)
        if img.IsIncomplete():
            img.Release()
            continue
        arr = img.GetNDArray().astype(np.float64)
        img.Release()
        grabbed += 1
        if grabbed <= SETTLE:
            continue
        if mean is None:
            mean = np.zeros_like(arr)
            m2 = np.zeros_like(arr)
        count += 1
        delta = arr - mean
        mean += delta / count
        m2 += delta * (arr - mean)
        frame_means.append(float(arr.mean()))
        if grabbed % 30 == 0:
            app.processEvents()  # keep the projector window painted
    cam.EndAcquisition()
    std = np.sqrt(m2 / (count - 1))
    fm = np.array(frame_means)
    return {
        "std_mean": float(std.mean()),
        "std_median": float(np.median(std)),
        "std_max": float(std.max()),
        "frame_mean_avg": float(fm.mean()),
        "frame_pp": float(fm.max() - fm.min()),
        "frame_pp_pct": 100.0 * (fm.max() - fm.min()) / fm.mean(),
    }


def main():
    app = QApplication([])
    screens = app.screens()
    projector = next((s for s in screens if "LCr" in s.name() or "4500" in s.name()),
                     screens[-1])
    hz = float(projector.refreshRate())
    print(f"projector: {projector.name()} @ {hz:.2f} Hz")

    win = ProjectorWindow()
    win.move_to_screen(projector)
    w, h = win.target_size()
    win.update_pattern(flat_field(w, h, level=128))
    for _ in range(20):
        app.processEvents()
        time.sleep(0.05)
    time.sleep(1.0)

    base = CameraSettings(
        exposure_auto="Off", gain_auto="Off", gain_db=0.0,
        pixel_format="Mono16", frame_rate_enable=True, frame_rate=30.0,
        stream_buffer_mode="NewestOnly", trigger_mode="Off",
    )
    snapped = flicker_safe_exposure(20000.0, hz)
    variants = [("unsynced 20.000 ms", 20000.0),
                ("flicker-safe %.3f ms" % (snapped / 1000.0), snapped)]

    system = PySpin.System.GetInstance()
    cam_list = system.GetCameras()
    cam = cam_list[0]
    results = {}
    try:
        cam.Init()
        for label, exp in variants:
            from dataclasses import replace
            s = replace(base, exposure_time_us=exp)
            print(f"\ncapturing: {label} ({N} frames)...")
            results[label] = capture(cam, s, app)
    finally:
        try:
            cam.DeInit()
        except PySpin.SpinnakerException:
            pass
        del cam
        cam_list.Clear()
        system.ReleaseInstance()
        win.close()

    print("\n=== results ===")
    for label, r in results.items():
        print(f"\n{label}")
        print(f"  per-pixel temporal std: mean {r['std_mean']:.2f}  "
              f"median {r['std_median']:.2f}  max {r['std_max']:.2f} counts")
        print(f"  whole-frame mean: {r['frame_mean_avg']:.0f} counts, "
              f"swing {r['frame_pp']:.0f} ({r['frame_pp_pct']:.2f}% peak-to-peak)")


if __name__ == "__main__":
    main()
