from dataclasses import dataclass

from PySide6.QtGui import QColor, QImage

from ..core.types import Vec3


@dataclass(frozen=True)
class RenderSurface:
    name: str
    corners: tuple[Vec3, Vec3, Vec3, Vec3]
    color: QColor


@dataclass(frozen=True)
class RenderLine:
    start: Vec3
    end: Vec3
    color: QColor


@dataclass(frozen=True)
class ProjectorView:
    origin: Vec3
    right: Vec3
    up: Vec3
    forward: Vec3
    tan_half_fov: float
    aspect: float


@dataclass(frozen=True)
class TelecentricScan:
    origin: Vec3
    right: Vec3
    up: Vec3
    forward: Vec3
    half_width: float
    half_height: float


@dataclass(frozen=True)
class FringeRect:
    origin: Vec3
    normal: Vec3
    right: Vec3
    up: Vec3
    u_min: float
    u_max: float
    v_min: float
    v_max: float


@dataclass(frozen=True)
class CameraView:
    camera: Vec3
    right: Vec3
    up: Vec3
    forward: Vec3
    fov_deg: float
    orthographic_half_width: float | None = None
    orthographic_half_height: float | None = None


@dataclass(frozen=True)
class ViewportRect:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class ProjectionScene:
    source_image: QImage
    source_is_fringe: bool
    surfaces: tuple[RenderSurface, ...]
    lines: tuple[RenderLine, ...]
    main_view: CameraView
    projector: ProjectorView
    scan: TelecentricScan | None
    fringe_rect: FringeRect | None
    minimap_view: CameraView | None
    minimap_viewport: ViewportRect | None
