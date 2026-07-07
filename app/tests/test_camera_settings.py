"""Camera settings: the shared record, the panel, and the device apply path.

Covers the three layers end to end without hardware: the `camera_config`
defaults (including the MP_CAM_EXPOSURE_US seed), the dialog's form <-> record
round-trip and persistence, and `SpinnakerCamera._apply_settings` against a
fake PySpin -- proving values are clamped to device limits and one unsupported
node doesn't take down the rest of the configuration.
"""
from __future__ import annotations

import types

import pytest
from PySide6.QtCore import QSettings

import hardware.camera as camera_module
import hardware.camera_config as camera_config
from hardware.camera import SpinnakerCamera
from hardware.camera_config import CameraSettings


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch, tmp_path):
    """Each test gets a pristine in-memory record, and persistence goes to a
    throwaway ini file (never the developer's real per-user settings store)."""
    import ui.camera_settings as ui_camera_settings

    monkeypatch.setattr(camera_config, "_current", None)

    def make(*_a, **_k):
        return QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)

    monkeypatch.setattr(ui_camera_settings, "QSettings", make)


# -- camera_config -------------------------------------------------------------


def test_defaults_are_metrology_first(monkeypatch):
    monkeypatch.delenv("MP_CAM_EXPOSURE_US", raising=False)
    s = camera_config.default_camera_settings()
    assert s.exposure_auto and s.gain_auto
    assert not s.gamma_enabled  # linearity: gamma off out of the box


def test_env_var_seeds_fixed_exposure(monkeypatch):
    monkeypatch.setenv("MP_CAM_EXPOSURE_US", "15000")
    s = camera_config.default_camera_settings()
    assert not s.exposure_auto
    assert s.exposure_us == 15000.0


def test_malformed_env_var_falls_back(monkeypatch):
    monkeypatch.setenv("MP_CAM_EXPOSURE_US", "not-a-number")
    assert camera_config.default_camera_settings().exposure_auto


def test_set_get_roundtrip():
    s = CameraSettings(exposure_auto=False, exposure_us=1234.0, gain_db=7.5)
    camera_config.set_camera_settings(s)
    assert camera_config.get_camera_settings() == s


# -- the device apply path (fake PySpin) ----------------------------------------


class _FloatNode:
    """A QuickSpin float feature: a value with device limits."""

    def __init__(self, lo: float, hi: float) -> None:
        self.lo, self.hi = lo, hi
        self.value = None

    def GetMin(self) -> float:
        return self.lo

    def GetMax(self) -> float:
        return self.hi

    def SetValue(self, v: float) -> None:
        self.value = v


class _EnumNode:
    def __init__(self) -> None:
        self.value = None

    def SetValue(self, v) -> None:
        self.value = v


class _RaisingNode:
    """A feature the camera doesn't support."""

    def __init__(self, exc_type) -> None:
        self._exc = exc_type

    def SetValue(self, _v) -> None:
        raise self._exc("node not writable")

    def GetMin(self):
        raise self._exc("node not readable")

    GetMax = GetMin


def _fake_pyspin():
    return types.SimpleNamespace(
        ExposureAuto_Off="exp_off",
        ExposureAuto_Continuous="exp_cont",
        ExposureMode_Timed="timed",
        GainAuto_Off="gain_off",
        GainAuto_Continuous="gain_cont",
        BlackLevelSelector_All="all",
        SpinnakerException=type("SpinnakerException", (Exception,), {}),
    )


def _fake_cam(pyspin) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        ExposureAuto=_EnumNode(),
        ExposureMode=_EnumNode(),
        ExposureTime=_FloatNode(20.0, 30000.0),
        GainAuto=_EnumNode(),
        Gain=_FloatNode(0.0, 47.0),
        GammaEnable=_EnumNode(),
        Gamma=_FloatNode(0.25, 4.0),
        BlackLevelSelector=_EnumNode(),
        BlackLevel=_FloatNode(0.0, 12.0),
    )


def test_apply_clamps_to_device_limits(monkeypatch):
    pyspin = _fake_pyspin()
    monkeypatch.setattr(camera_module, "PySpin", pyspin)
    cam = _fake_cam(pyspin)
    SpinnakerCamera()._apply_settings(cam, CameraSettings(
        exposure_auto=False, exposure_us=999_999.0,   # way past the device max
        gain_auto=False, gain_db=60.0,                # ditto
        gamma_enabled=False, black_level_pct=2.0,
    ))
    assert cam.ExposureAuto.value == "exp_off"
    assert cam.ExposureMode.value == "timed"
    assert cam.ExposureTime.value == 30000.0  # clamped
    assert cam.GainAuto.value == "gain_off"
    assert cam.Gain.value == 47.0  # clamped
    assert cam.GammaEnable.value is False
    assert cam.Gamma.value is None  # disabled: value untouched
    assert cam.BlackLevelSelector.value == "all"
    assert cam.BlackLevel.value == 2.0


def test_apply_auto_modes(monkeypatch):
    pyspin = _fake_pyspin()
    monkeypatch.setattr(camera_module, "PySpin", pyspin)
    cam = _fake_cam(pyspin)
    SpinnakerCamera()._apply_settings(cam, CameraSettings())  # all defaults
    assert cam.ExposureAuto.value == "exp_cont"
    assert cam.ExposureTime.value is None  # auto: no fixed value pushed
    assert cam.GainAuto.value == "gain_cont"
    assert cam.GammaEnable.value is False


def test_unsupported_node_does_not_abort(monkeypatch):
    """A camera without a gain node still gets its gamma/black level set."""
    pyspin = _fake_pyspin()
    monkeypatch.setattr(camera_module, "PySpin", pyspin)
    cam = _fake_cam(pyspin)
    cam.GainAuto = _RaisingNode(pyspin.SpinnakerException)
    SpinnakerCamera()._apply_settings(cam, CameraSettings(
        gain_auto=False, gain_db=5.0, black_level_pct=1.5,
    ))
    assert cam.BlackLevel.value == 1.5  # later features still applied


# -- the panel -------------------------------------------------------------------


def test_dialog_roundtrip_and_apply(qapp):
    from ui.camera_settings import CameraSettingsDialog, saved_camera_settings

    dialog = CameraSettingsDialog()
    dialog.exposure_auto.setChecked(False)
    dialog.exposure_us.setValue(12500.0)
    dialog.gain_auto.setChecked(False)
    dialog.gain_db.setValue(6.0)
    dialog._on_apply()

    live = camera_config.get_camera_settings()
    assert live.exposure_auto is False and live.exposure_us == 12500.0
    assert live.gain_auto is False and live.gain_db == 6.0
    # ...and it persisted: a fresh read returns the same record
    assert saved_camera_settings() == live


def test_dialog_auto_disables_manual_field(qapp):
    from ui.camera_settings import CameraSettingsDialog

    dialog = CameraSettingsDialog()
    dialog.exposure_auto.setChecked(True)
    assert not dialog.exposure_us.isEnabled()
    dialog.exposure_auto.setChecked(False)
    assert dialog.exposure_us.isEnabled()


def test_dialog_restore_defaults_fills_form_only(qapp, monkeypatch):
    from ui.camera_settings import CameraSettingsDialog

    monkeypatch.delenv("MP_CAM_EXPOSURE_US", raising=False)
    dialog = CameraSettingsDialog()
    dialog.gain_auto.setChecked(False)
    dialog.gain_db.setValue(9.0)
    dialog.load_settings(camera_config.default_camera_settings())
    assert dialog.gain_auto.isChecked()  # form reset...
    assert camera_config.get_camera_settings().gain_auto  # ...nothing applied
