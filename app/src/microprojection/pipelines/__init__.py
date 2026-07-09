"""Acquisition pipelines: orchestrate the projector and camera to capture sets
of frames, then save them.

Each pipeline is a small event-driven state machine (driven by the camera's
frameReady signal, so the UI stays responsive) with the same lifecycle:
ensure the hardware is ready, configure the camera, project/capture in a loop,
then save. See ``base.CapturePipeline``.
"""
from microprojection.pipelines.align import AlignProjectionPipeline
from microprojection.pipelines.base import CapturePipeline
from microprojection.pipelines.fov import FovPipeline
from microprojection.pipelines.noise import NoisePipeline
from microprojection.pipelines.phase_shift import PhaseShiftPipeline

__all__ = ["AlignProjectionPipeline", "CapturePipeline", "FovPipeline",
           "NoisePipeline", "PhaseShiftPipeline"]
