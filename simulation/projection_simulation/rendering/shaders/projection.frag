uniform sampler2D u_source;
uniform vec3 u_projector_origin;
uniform vec3 u_projector_right;
uniform vec3 u_projector_up;
uniform vec3 u_projector_forward;
uniform vec2 u_projector_projection;
uniform int u_source_is_fringe;
uniform int u_project_projection;
uniform int u_has_scan;
uniform vec3 u_scan_origin;
uniform vec3 u_scan_right;
uniform vec3 u_scan_up;
uniform vec3 u_scan_forward;
uniform float u_scan_half_width;
uniform float u_scan_half_height;
uniform int u_has_fringe_rect;
uniform vec3 u_fringe_origin;
uniform vec3 u_fringe_normal;
uniform vec3 u_fringe_right;
uniform vec3 u_fringe_up;
uniform vec4 u_fringe_bounds;

varying vec3 v_world;
varying vec3 v_color;

bool insideUnitUv(vec2 uv) {
    return uv.x >= 0.0 && uv.x <= 1.0 && uv.y >= 0.0 && uv.y <= 1.0;
}

bool insideScan(vec3 point) {
    if (u_has_scan == 0) {
        return true;
    }
    vec3 rel = point - u_scan_origin;
    float depth = dot(rel, u_scan_forward);
    if (depth <= 0.00001) {
        return false;
    }
    float lateral_x = dot(rel, u_scan_right);
    float lateral_y = dot(rel, u_scan_up);
    return abs(lateral_x) <= u_scan_half_width + 0.00001
        && abs(lateral_y) <= u_scan_half_height + 0.00001;
}

bool fringeUvForWorld(vec3 point, out vec2 uv) {
    vec3 ray = point - u_projector_origin;
    float denom = dot(ray, u_fringe_normal);
    if (abs(denom) <= 0.000001) {
        return false;
    }
    float t = dot(u_fringe_origin - u_projector_origin, u_fringe_normal) / denom;
    if (t <= 0.000001) {
        return false;
    }
    vec3 plane_point = u_projector_origin + ray * t;
    vec3 rel = plane_point - u_fringe_origin;
    float u = dot(rel, u_fringe_right);
    float v = dot(rel, u_fringe_up);
    float u_min = u_fringe_bounds.x;
    float u_max = u_fringe_bounds.y;
    float v_min = u_fringe_bounds.z;
    float v_max = u_fringe_bounds.w;
    float span_u = u_max - u_min;
    float span_v = v_max - v_min;
    if (span_u <= 0.000001 || span_v <= 0.000001) {
        return false;
    }
    if (u < u_min || u > u_max || v < v_min || v > v_max) {
        return false;
    }
    uv = vec2((u - u_min) / span_u, 1.0 - ((v - v_min) / span_v));
    return true;
}

bool projectorUvForWorld(vec3 point, out vec2 uv, out vec3 projected_point) {
    vec3 rel = point - u_projector_origin;
    float depth = dot(rel, u_projector_forward);
    if (depth <= 0.00001) {
        return false;
    }
    float tan_half_fov = u_projector_projection.x;
    float aspect = u_projector_projection.y;
    float x = dot(rel, u_projector_right) / (depth * aspect * tan_half_fov);
    float y = dot(rel, u_projector_up) / (depth * tan_half_fov);
    uv = vec2((x + 1.0) * 0.5, (1.0 - y) * 0.5);
    projected_point = point;
    return insideUnitUv(uv);
}

void main() {
    vec3 base = v_color;
    if (u_project_projection == 0) {
        gl_FragColor = vec4(base, 1.0);
        return;
    }
    vec2 uv = vec2(0.0);
    vec3 mask_point = v_world;
    bool lit = projectorUvForWorld(v_world, uv, mask_point);

    if (lit) {
        vec3 projected = texture2D(u_source, uv).rgb;
        gl_FragColor = vec4(projected, 1.0);
    } else {
        gl_FragColor = vec4(base, 1.0);
    }
}
