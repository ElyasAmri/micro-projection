"""FOV identification: the edge search converges onto a synthetic camera's
view region, skips dark frames, and shrinks when flooded."""
import numpy as np

from backend.fov import FovParams, FovSearch, box_outline, solid_box


def synthetic_camera(pattern: np.ndarray, view) -> np.ndarray:
    """A camera that sees exactly the projector region `view` = (x0, y0, x1, y1),
    one camera pixel per projector pixel."""
    x0, y0, x1, y1 = view
    return pattern[y0:y1, x0:x1]


def run_search(view, proj=(400, 300), iterations=32):
    search = FovSearch(*proj, FovParams(iterations=iterations))
    for _ in range(iterations):
        search.update(synthetic_camera(search.pattern(), view))
    return search


def test_converges_to_camera_view():
    view = (60, 40, 340, 260)
    search = run_search(view)
    x, y, w, h = search.result()
    assert abs(x - view[0]) <= 4 and abs(y - view[1]) <= 4
    assert abs((x + w) - view[2]) <= 4 and abs((y + h) - view[3]) <= 4


def test_off_center_view():
    # The boundary far from an edge's start exercises bracket-before-halve:
    # halving too early would strand the left edge short of x0=250.
    view = (250, 10, 396, 140)
    search = run_search(view)
    x, y, w, h = search.result()
    assert abs(x - view[0]) <= 4 and abs((y + h) - view[3]) <= 4


def test_dark_frame_skipped():
    search = FovSearch(400, 300)
    before = list(search.box)
    assert search.update(np.zeros((200, 280), dtype=np.uint8)) is False
    assert search.box == before


def test_flooded_frame_shrinks_box():
    search = FovSearch(400, 300)
    assert search.update(np.full((200, 280), 255, dtype=np.uint8)) is True
    x0, y0, x1, y1 = search.box
    assert x0 > 0 and y0 > 0 and x1 < 400 and y1 < 300


def test_box_patterns():
    img = solid_box(100, 80, (10, 20, 60, 50))
    assert img[30, 30] == 255 and img[30, 5] == 0 and img.shape == (80, 100)
    out = box_outline(100, 80, (10, 20, 60, 50))
    assert out[20, 30] == 255 and out[35, 35] == 0  # edge lit, interior hollow
