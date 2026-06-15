"""Apply a CameraSettings to a live PySpin camera.

Separated from the acquisition thread so the "how to write each node" concern
lives in one place. Imported lazily by the thread (only when PySpin is present),
so this module may import PySpin at the top level.

Every node is set defensively: a model that lacks a node, or a value it rejects,
is skipped rather than aborting the whole configuration. Call ``configure``
once, before ``BeginAcquisition`` (structural nodes such as pixel format and
region of interest are only writable while not streaming).
"""
from __future__ import annotations

import PySpin

from microprojection.acquisition.camera_settings import CameraSettings


def configure(cam, settings: CameraSettings) -> None:
    """Apply every setting to the camera, in a streaming-safe order."""
    s = settings
    _set_enum(cam, "PixelFormat", s.pixel_format)
    if s.bit_depth:
        _set_enum(cam, "AdcBitDepth", s.bit_depth)
    # Binning before ROI: it changes the sensor's reported max width/height.
    _set_int(cam, "BinningHorizontal", s.binning_horizontal)
    _set_int(cam, "BinningVertical", s.binning_vertical)
    _configure_roi(cam, s)
    _set_bool(cam, "ReverseX", s.reverse_x)
    _set_bool(cam, "ReverseY", s.reverse_y)

    cam.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)

    _set_enum(cam, "ExposureAuto", s.exposure_auto)
    if s.exposure_auto == "Off":
        _set_float(cam, "ExposureTime", s.exposure_time_us)
    _set_enum(cam, "GainAuto", s.gain_auto)
    if s.gain_auto == "Off":
        _set_float(cam, "Gain", s.gain_db)

    _set_bool(cam, "GammaEnable", s.gamma_enable)
    if s.gamma_enable:
        _set_float(cam, "Gamma", s.gamma)

    _set_bool(cam, "AcquisitionFrameRateEnable", s.frame_rate_enable)
    if s.frame_rate_enable:
        try:
            rate = min(s.frame_rate, cam.AcquisitionFrameRate.GetMax())
            _set_float(cam, "AcquisitionFrameRate", rate)
        except PySpin.SpinnakerException:
            pass

    _configure_trigger(cam, s)
    _configure_stream(cam, s)


def _configure_roi(cam, s: CameraSettings) -> None:
    try:
        if s.roi_enable and s.roi_width > 0 and s.roi_height > 0:
            # Zero the offsets first so a larger window is allowed to fit, then
            # size, then offset.
            _set_int(cam, "OffsetX", 0)
            _set_int(cam, "OffsetY", 0)
            _set_int(cam, "Width", s.roi_width)
            _set_int(cam, "Height", s.roi_height)
            _set_int(cam, "OffsetX", s.roi_offset_x)
            _set_int(cam, "OffsetY", s.roi_offset_y)
        else:
            # Full sensor.
            _set_int(cam, "OffsetX", 0)
            _set_int(cam, "OffsetY", 0)
            _set_int(cam, "Width", cam.Width.GetMax())
            _set_int(cam, "Height", cam.Height.GetMax())
    except (PySpin.SpinnakerException, AttributeError):
        pass


def _configure_trigger(cam, s: CameraSettings) -> None:
    try:
        # Disable first so the source/activation can be reconfigured.
        cam.TriggerMode.SetValue(PySpin.TriggerMode_Off)
        if s.trigger_mode == "Off":
            return
        if s.trigger_mode == "Software":
            cam.TriggerSource.SetValue(PySpin.TriggerSource_Software)
        else:
            _set_enum(cam, "TriggerSource", s.trigger_source)
            _set_enum(cam, "TriggerActivation", s.trigger_activation)
        cam.TriggerMode.SetValue(PySpin.TriggerMode_On)
    except (PySpin.SpinnakerException, AttributeError):
        pass


def _configure_stream(cam, s: CameraSettings) -> None:
    # Buffer handling lives on the transport-layer stream node map.
    try:
        snm = cam.GetTLStreamNodeMap()
        node = PySpin.CEnumerationPtr(snm.GetNode("StreamBufferHandlingMode"))
        if PySpin.IsWritable(node):
            entry = node.GetEntryByName(s.stream_buffer_mode)
            if entry:
                node.SetIntValue(entry.GetValue())
    except (PySpin.SpinnakerException, AttributeError):
        pass


def _set_enum(cam, name: str, entry: str) -> None:
    try:
        node = getattr(cam, name)
        if PySpin.IsWritable(node):
            node.SetValue(getattr(PySpin, f"{name}_{entry}"))
    except (PySpin.SpinnakerException, AttributeError):
        pass


def _set_float(cam, name: str, value: float) -> None:
    try:
        node = getattr(cam, name)
        if PySpin.IsWritable(node):
            node.SetValue(min(max(value, node.GetMin()), node.GetMax()))
    except (PySpin.SpinnakerException, AttributeError):
        pass


def _set_int(cam, name: str, value: int) -> None:
    try:
        node = getattr(cam, name)
        if PySpin.IsWritable(node):
            node.SetValue(int(min(max(value, node.GetMin()), node.GetMax())))
    except (PySpin.SpinnakerException, AttributeError):
        pass


def _set_bool(cam, name: str, value: bool) -> None:
    try:
        node = getattr(cam, name)
        if PySpin.IsWritable(node):
            node.SetValue(bool(value))
    except (PySpin.SpinnakerException, AttributeError):
        pass
