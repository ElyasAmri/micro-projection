import math

from .types import Vec3


def vec_subtract(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vec_dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vec_cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def vec_normalize(v: Vec3) -> Vec3 | None:
    length = math.sqrt(vec_dot(v, v))
    if length <= 1e-9:
        return None
    return (v[0] / length, v[1] / length, v[2] / length)
