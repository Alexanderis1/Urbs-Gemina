"""Individual trees from a canopy height model (CHM): position, height, crown radius.

Local maxima of the smoothed CHM are tree tops; every canopy pixel is given to its nearest
top, and the crown radius is that area's equivalent circle. Deterministic, no learning.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import numpy.typing as npt
from scipy import ndimage

Array = npt.NDArray[np.float64]


@dataclass(frozen=True)
class Trees:
    x: Array  # metric CRS of the CHM, cell centre
    y: Array
    height_m: Array
    crown_radius_m: Array


def detect_trees(
    chm: npt.NDArray[np.floating],
    *,
    pixel_m: float,
    min_height_m: float,
    window_m: float,
    origin: tuple[float, float],
    exclude: Optional[npt.NDArray[np.bool_]] = None,
    max_crown_m: float = 10.0,
) -> Trees:
    """``origin`` is the (x, y) of the top-left corner; rows go south."""
    h = np.nan_to_num(np.asarray(chm, dtype="float64"), nan=0.0)
    if exclude is not None:
        h = np.where(exclude, 0.0, h)
    smooth = ndimage.gaussian_filter(h, sigma=1.0)
    size = max(3, int(round(window_m / pixel_m)) | 1)
    peaks = (smooth == ndimage.maximum_filter(smooth, size=size)) & (h >= min_height_m)
    # Plateaus give several equal maxima: keep one per connected group.
    labels, n = ndimage.label(peaks)
    if n == 0:
        e = np.zeros(0)
        return Trees(e, e, e, e)
    rows_f, cols_f = np.array(ndimage.center_of_mass(peaks, labels, range(1, n + 1))).T
    rows, cols = np.round(rows_f).astype(int), np.round(cols_f).astype(int)
    height = np.array(ndimage.maximum(h, labels, range(1, n + 1)), dtype="float64")

    # Crown: canopy pixels (>= half the threshold) assigned to the nearest tree top.
    markers = np.zeros(h.shape, dtype=np.int64)
    markers[rows, cols] = np.arange(1, n + 1)
    dist, (ir, ic) = ndimage.distance_transform_edt(markers == 0, return_indices=True)
    owner = markers[ir, ic]
    canopy = (h >= min_height_m * 0.66) & (dist * pixel_m <= max_crown_m)
    area = np.bincount(owner[canopy], minlength=n + 1)[1:] * pixel_m**2
    radius = np.minimum(np.sqrt(area / np.pi), max_crown_m)

    x0, y0 = origin
    return Trees(
        x=x0 + (cols + 0.5) * pixel_m,
        y=y0 - (rows + 0.5) * pixel_m,
        height_m=height,
        crown_radius_m=radius,
    )
