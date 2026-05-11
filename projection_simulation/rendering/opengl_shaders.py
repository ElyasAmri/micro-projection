from importlib.resources import files


def _read_shader(filename: str) -> str:
    return files(__package__).joinpath("shaders", filename).read_text(encoding="utf-8")


VERTEX_SHADER = _read_shader("projection.vert")
FRAGMENT_SHADER = _read_shader("projection.frag")
