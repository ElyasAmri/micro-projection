from __future__ import annotations

import numpy as np

from PySide6.QtGui import QImage, QMatrix4x4, QOpenGLContext, QVector3D
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLFramebufferObject,
    QOpenGLFramebufferObjectFormat,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLTexture,
)

from .opengl_shaders import FRAGMENT_SHADER, VERTEX_SHADER
from .render_scene import CameraView, ProjectionScene, ViewportRect

GL_COLOR_BUFFER_BIT = 0x00004000
GL_DEPTH_BUFFER_BIT = 0x00000100
GL_DEPTH_TEST = 0x0B71
GL_BLEND = 0x0BE2
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_FLOAT = 0x1406
GL_TRIANGLES = 0x0004
GL_LINES = 0x0001
GL_TEXTURE0 = 0x84C0
GL_SCISSOR_TEST = 0x0C11


class OpenGLProjectionRenderer:
    def __init__(self) -> None:
        self._program: QOpenGLShaderProgram | None = None
        self._vbo = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
        self._texture: QOpenGLTexture | None = None
        self._texture_key: tuple[int, int, int] | None = None

    def initialize(self) -> None:
        if self._program is not None:
            return
        program = QOpenGLShaderProgram()
        if not program.addShaderFromSourceCode(QOpenGLShader.Vertex, VERTEX_SHADER):
            raise RuntimeError(program.log())
        if not program.addShaderFromSourceCode(QOpenGLShader.Fragment, FRAGMENT_SHADER):
            raise RuntimeError(program.log())
        if not program.link():
            raise RuntimeError(program.log())
        self._program = program
        if not self._vbo.create():
            raise RuntimeError("Failed to create OpenGL vertex buffer.")

    def invalidate_source(self) -> None:
        self._texture_key = None

    def dispose(self) -> None:
        if self._texture is not None:
            self._texture.destroy()
            self._texture = None
        if self._vbo.isCreated():
            self._vbo.destroy()
        self._program = None

    def render(
        self,
        scene: ProjectionScene,
        width: int,
        height: int,
        *,
        device_pixel_ratio: float,
    ) -> None:
        self.initialize()
        functions = QOpenGLContext.currentContext().functions()
        framebuffer_width = max(1, round(width * device_pixel_ratio))
        framebuffer_height = max(1, round(height * device_pixel_ratio))
        functions.glEnable(GL_DEPTH_TEST)
        functions.glEnable(GL_BLEND)
        functions.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        functions.glViewport(0, 0, framebuffer_width, framebuffer_height)
        functions.glClearColor(0.0, 0.0, 0.0, 1.0)
        functions.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self._draw_scene_view(scene, scene.main_view, ViewportRect(0, 0, width, height))

        if scene.minimap_view is not None and scene.minimap_viewport is not None:
            viewport = scene.minimap_viewport
            gl_x = round(viewport.x * device_pixel_ratio)
            gl_y = max(0, round((height - viewport.y - viewport.height) * device_pixel_ratio))
            gl_width = max(1, round(viewport.width * device_pixel_ratio))
            gl_height = max(1, round(viewport.height * device_pixel_ratio))
            functions.glEnable(GL_SCISSOR_TEST)
            functions.glScissor(gl_x, gl_y, gl_width, gl_height)
            functions.glViewport(gl_x, gl_y, gl_width, gl_height)
            functions.glClearColor(0.04, 0.05, 0.07, 1.0)
            functions.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            functions.glDisable(GL_SCISSOR_TEST)
            self._draw_scene_view(
                scene,
                scene.minimap_view,
                viewport,
            )
            functions.glViewport(0, 0, framebuffer_width, framebuffer_height)

    def render_view_to_image(
        self,
        scene: ProjectionScene,
        view: CameraView,
        width: int,
        height: int,
    ) -> QImage:
        self.initialize()
        framebuffer_format = QOpenGLFramebufferObjectFormat()
        framebuffer_format.setAttachment(QOpenGLFramebufferObject.CombinedDepthStencil)
        framebuffer = QOpenGLFramebufferObject(
            max(1, width),
            max(1, height),
            framebuffer_format,
        )
        if not framebuffer.isValid():
            raise RuntimeError("Failed to create OpenGL capture framebuffer.")

        functions = QOpenGLContext.currentContext().functions()
        framebuffer.bind()
        try:
            functions.glEnable(GL_DEPTH_TEST)
            functions.glEnable(GL_BLEND)
            functions.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            functions.glViewport(0, 0, max(1, width), max(1, height))
            functions.glClearColor(0.04, 0.05, 0.07, 1.0)
            functions.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            self._draw_scene_view(scene, view, ViewportRect(0, 0, width, height))
            return framebuffer.toImage()
        finally:
            framebuffer.release()

    def _draw_scene_view(
        self,
        scene: ProjectionScene,
        view: CameraView,
        viewport: ViewportRect,
    ) -> None:
        program = self._program
        if program is None:
            return
        self._ensure_texture(scene.source_image)
        texture = self._texture
        if texture is None:
            return

        program.bind()
        functions = QOpenGLContext.currentContext().functions()
        functions.glActiveTexture(GL_TEXTURE0)
        texture.bind(0)
        _set_uniform(program, "u_source", 0)
        _set_uniform(program, "u_mvp", self._mvp_for_view(view, viewport.width, viewport.height))
        self._set_scene_uniforms(program, scene)

        line_vertices = self._build_line_vertices(scene)
        if line_vertices.size > 0:
            _set_uniform(program, "u_project_projection", 0)
            self._draw_vertices(program, line_vertices, GL_LINES)

        surface_vertices = self._build_surface_vertices(scene)
        if surface_vertices.size > 0:
            _set_uniform(program, "u_project_projection", 1)
            self._draw_vertices(program, surface_vertices, GL_TRIANGLES)

        texture.release()
        program.release()

    def _ensure_texture(self, image: QImage) -> None:
        key = (image.cacheKey(), image.width(), image.height())
        if self._texture is not None and self._texture_key == key:
            return
        if self._texture is not None:
            self._texture.destroy()
        texture_image = image.convertToFormat(QImage.Format_RGBA8888).mirrored(False, True)
        self._texture = QOpenGLTexture(texture_image)
        self._texture.setMinificationFilter(QOpenGLTexture.Linear)
        self._texture.setMagnificationFilter(QOpenGLTexture.Linear)
        self._texture.setWrapMode(QOpenGLTexture.ClampToEdge)
        self._texture_key = key

    def _set_scene_uniforms(
        self,
        program: QOpenGLShaderProgram,
        scene: ProjectionScene,
    ) -> None:
        projector = scene.projector
        _set_uniform(program, "u_projector_origin", _qvec(projector.origin))
        _set_uniform(program, "u_projector_right", _qvec(projector.right))
        _set_uniform(program, "u_projector_up", _qvec(projector.up))
        _set_uniform(program, "u_projector_forward", _qvec(projector.forward))
        _set_uniform(
            program,
            "u_projector_projection",
            float(projector.tan_half_fov),
            float(projector.aspect),
        )
        _set_uniform(program, "u_source_is_fringe", 1 if scene.source_is_fringe else 0)

        scan = scene.scan
        _set_uniform(program, "u_has_scan", 1 if scan is not None else 0)
        if scan is not None:
            _set_uniform(program, "u_scan_origin", _qvec(scan.origin))
            _set_uniform(program, "u_scan_right", _qvec(scan.right))
            _set_uniform(program, "u_scan_up", _qvec(scan.up))
            _set_uniform(program, "u_scan_forward", _qvec(scan.forward))
            _set_uniform(program, "u_scan_half_width", float(scan.half_width))
            _set_uniform(program, "u_scan_half_height", float(scan.half_height))

        fringe = scene.fringe_rect
        _set_uniform(program, "u_has_fringe_rect", 1 if fringe is not None else 0)
        if fringe is not None:
            _set_uniform(program, "u_fringe_origin", _qvec(fringe.origin))
            _set_uniform(program, "u_fringe_normal", _qvec(fringe.normal))
            _set_uniform(program, "u_fringe_right", _qvec(fringe.right))
            _set_uniform(program, "u_fringe_up", _qvec(fringe.up))
            _set_uniform(
                program,
                "u_fringe_bounds",
                float(fringe.u_min),
                float(fringe.u_max),
                float(fringe.v_min),
                float(fringe.v_max),
            )

    def _draw_vertices(
        self,
        program: QOpenGLShaderProgram,
        vertices: np.ndarray,
        primitive: int,
    ) -> None:
        stride = 6 * np.dtype(np.float32).itemsize
        self._vbo.bind()
        self._vbo.allocate(vertices.tobytes(), int(vertices.nbytes))
        position_location = program.attributeLocation("a_position")
        color_location = program.attributeLocation("a_color")
        program.enableAttributeArray(position_location)
        program.enableAttributeArray(color_location)
        program.setAttributeBuffer(position_location, GL_FLOAT, 0, 3, stride)
        program.setAttributeBuffer(color_location, GL_FLOAT, 3 * np.dtype(np.float32).itemsize, 3, stride)
        QOpenGLContext.currentContext().functions().glDrawArrays(primitive, 0, int(vertices.shape[0]))
        program.disableAttributeArray(position_location)
        program.disableAttributeArray(color_location)
        self._vbo.release()

    def _build_surface_vertices(self, scene: ProjectionScene) -> np.ndarray:
        rows: list[tuple[float, float, float, float, float, float]] = []
        for surface in scene.surfaces:
            color = surface.color
            rgb = (color.redF(), color.greenF(), color.blueF())
            corners = surface.corners
            for index in (0, 1, 2, 0, 2, 3):
                x, y, z = corners[index]
                rows.append((x, y, z, rgb[0], rgb[1], rgb[2]))
        if not rows:
            return np.empty((0, 6), dtype=np.float32)
        return np.asarray(rows, dtype=np.float32)

    def _build_line_vertices(self, scene: ProjectionScene) -> np.ndarray:
        rows: list[tuple[float, float, float, float, float, float]] = []
        for line in scene.lines:
            rgb = (line.color.redF(), line.color.greenF(), line.color.blueF())
            for point in (line.start, line.end):
                rows.append((point[0], point[1], point[2], rgb[0], rgb[1], rgb[2]))
        if not rows:
            return np.empty((0, 6), dtype=np.float32)
        return np.asarray(rows, dtype=np.float32)

    def _mvp_for_view(self, view: CameraView, width: int, height: int) -> QMatrix4x4:
        aspect = max(1.0 / 1024.0, float(width) / float(max(1, height)))
        projection = QMatrix4x4()
        if (
            view.orthographic_half_width is not None
            and view.orthographic_half_height is not None
        ):
            projection.ortho(
                -float(view.orthographic_half_width),
                float(view.orthographic_half_width),
                -float(view.orthographic_half_height),
                float(view.orthographic_half_height),
                0.01,
                10000.0,
            )
        else:
            projection.perspective(float(view.fov_deg), aspect, 0.01, 10000.0)
        eye = _qvec(view.camera)
        center = QVector3D(
            float(view.camera[0] + view.forward[0]),
            float(view.camera[1] + view.forward[1]),
            float(view.camera[2] + view.forward[2]),
        )
        view_matrix = QMatrix4x4()
        view_matrix.lookAt(eye, center, _qvec(view.up))
        return projection * view_matrix


def _qvec(value: tuple[float, float, float]) -> QVector3D:
    return QVector3D(float(value[0]), float(value[1]), float(value[2]))


def _set_uniform(
    program: QOpenGLShaderProgram,
    name: str,
    *values: object,
) -> None:
    location = program.uniformLocation(name)
    if location < 0:
        return
    if len(values) == 1:
        program.setUniformValue(location, values[0])
        return
    program.setUniformValue(location, *values)
