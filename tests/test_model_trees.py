"""WS2: individual trees from a 1 m canopy height model."""
import numpy as np
import pytest

from twin.model.trees import detect_trees


def _bump(shape: tuple[int, int], cy: int, cx: int, h: float, r: float) -> np.ndarray:
    yy, xx = np.mgrid[0 : shape[0], 0 : shape[1]]
    return h * np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * r**2))


def test_two_trees_are_found_with_their_heights_and_crowns() -> None:
    chm = _bump((60, 60), 15, 15, 12.0, 3.0) + _bump((60, 60), 40, 42, 20.0, 5.0)
    trees = detect_trees(chm, pixel_m=1.0, min_height_m=3.0, window_m=5.0, origin=(1000.0, 2000.0))
    assert len(trees.height_m) == 2
    order = np.argsort(trees.height_m)
    assert trees.height_m[order] == pytest.approx([12.0, 20.0], abs=0.5)
    r_small, r_big = trees.crown_radius_m[order]
    assert 2.0 < r_small < r_big < 12.0
    # Coordinates: origin is the top-left corner, y grows downwards in pixels.
    x, y = trees.x[order[1]], trees.y[order[1]]
    assert x == pytest.approx(1000.0 + 42.5, abs=1.0) and y == pytest.approx(2000.0 - 40.5, abs=1.0)


def test_low_vegetation_and_masked_pixels_are_ignored() -> None:
    chm = _bump((40, 40), 20, 20, 2.5, 3.0)  # a hedge below 3 m
    assert len(detect_trees(chm, pixel_m=1.0, min_height_m=3.0, window_m=5.0, origin=(0, 0)).x) == 0
    chm = _bump((40, 40), 20, 20, 15.0, 3.0)
    mask = np.zeros_like(chm, dtype=bool)
    mask[15:26, 15:26] = True  # a building footprint over the peak
    assert len(detect_trees(chm, pixel_m=1.0, min_height_m=3.0, window_m=5.0, origin=(0, 0), exclude=mask).x) == 0
