from dataclasses import dataclass, field

import numpy as np


@dataclass
class CaptureFrame:
    image: np.ndarray  # HxWx3 uint8 RGB
    timestamp: float


@dataclass
class PipelineResult:
    phase_map: np.ndarray  # HxW float64
    height_map: np.ndarray  # HxW float64
    roughness_map: np.ndarray  # HxW float64
    roughness: dict = field(default_factory=dict)  # Sa, Sq, Sz, ...
    processing_time: float = 0.0
