"""Facts from the aerial photo (AGEA, 20-50 cm): roof colour and cover, and shadow lengths.

Pure numpy / scipy on an RGB array plus a raster of building labels (0 = not a building,
i = building i). Thresholds live in config/model.yaml; this module only measures.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

import numpy as np
import numpy.typing as npt
from scipy import ndimage

Array = npt.NDArray[np.float64]


def _hsv(rgb: npt.NDArray[np.uint8]) -> tuple[Array, Array, Array]:
    x = rgb.astype("float64") / 255.0
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    v = x.max(axis=-1)
    c = v - x.min(axis=-1)
    s = np.where(v > 0, c / np.where(v > 0, v, 1), 0.0)
    safe = np.where(c > 0, c, 1)
    h = np.where(v == r, ((g - b) / safe) % 6, np.where(v == g, (b - r) / safe + 2, (r - g) / safe + 4))
    h = np.where(c > 0, h * 60.0, 0.0)
    return h, s, v


#: Defaults for crisp, saturated imagery. Real photos (hazy, pale) override them from config/model.yaml.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "clay_hue_max": 35.0, "clay_sat_min": 0.25, "clay_val_min": 0.3,
    "flat_sat_max": 0.15, "flat_val_min": 0.55,
    "green_exg_min": 0.08,
    "dark_val_max": 0.25,
    "solar_val_max": 0.45, "solar_sat_min": 0.15,
}


def roof_stats(
    rgb: npt.NDArray[np.uint8],
    labels: npt.NDArray[np.integer],
    *,
    n: int,
    thresholds: Optional[Mapping[str, float]] = None,
) -> dict[str, Array]:
    """Per building (1..n): mean colour and the share of roof pixels in each cover type.

    Edges are eroded by one pixel so walls and gutters do not count.
    """
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    lab = np.asarray(labels)
    inner = ndimage.grey_erosion(lab, size=3) == lab
    lab = np.where(inner, lab, 0)
    h, s, v = _hsv(rgb)
    x = rgb.astype("float64")
    exg = (2 * x[..., 1] - x[..., 0] - x[..., 2]) / np.maximum(x.sum(axis=-1), 1.0)
    masks = {
        "share_terracotta": ((h <= t["clay_hue_max"]) | (h >= 345)) & (s >= t["clay_sat_min"]) & (v >= t["clay_val_min"]),
        "share_light_flat": (s < t["flat_sat_max"]) & (v >= t["flat_val_min"]),
        "share_green": (exg > t["green_exg_min"]) & (h >= 60) & (h <= 170),
        "share_dark": v < t["dark_val_max"],
        # Solar panels: dark, slightly blue, a little saturated. Heuristic, verified only by eye (C=50).
        "share_solar_like": (v < t["solar_val_max"]) & (v >= 0.12) & (h >= 190) & (h <= 250) & (s >= t["solar_sat_min"]),
    }
    idx = np.arange(1, n + 1)
    count = ndimage.sum_labels(np.ones_like(lab), lab, idx).astype("float64")
    safe = np.where(count > 0, count, 1.0)
    out: dict[str, Array] = {"n_px": count}
    for k, m in masks.items():
        out[k] = np.where(count > 0, ndimage.sum_labels(m.astype("float64"), lab, idx) / safe, np.nan)
    for i, ch in enumerate("rgb"):
        out[f"mean_{ch}"] = np.where(count > 0, ndimage.mean(x[..., i], lab, idx), np.nan)
    return out


@dataclass(frozen=True)
class ShadowRuns:
    length_px: Array  # median free shadow length per building (NaN = none measured)
    blocked: npt.NDArray[np.bool_]  # most shadow rays hit another building or the image edge
    n_rays: Array


def shadow_runs(
    dark: npt.NDArray[np.bool_],
    labels: npt.NDArray[np.integer],
    *,
    n: int,
    shadow_azimuth_deg: float,
    quantile: float = 0.75,
) -> ShadowRuns:
    """Length of the shadow each building casts on open ground, in pixels.

    ``shadow_azimuth_deg`` is the direction shadows point, clockwise from image-up (north).
    The scene is rotated so shadows point up; then, from each building's shadow-side edge,
    the run of dark, non-building pixels is counted. A run that ends on another building or
    the image edge is blocked (only a lower bound) and is not used.
    """
    lab = np.asarray(labels).astype(np.int64)
    if shadow_azimuth_deg % 360:
        lab = ndimage.rotate(lab, shadow_azimuth_deg, order=0, reshape=True, cval=-1)
        dk = ndimage.rotate(dark.astype(np.uint8), shadow_azimuth_deg, order=0, reshape=True, cval=0).astype(bool)
    else:
        dk = dark.astype(bool)
    rows, cols = lab.shape
    free = dk & (lab == 0)
    run = np.zeros(lab.shape, dtype=np.int32)
    for r in range(1, rows):
        run[r] = np.where(free[r], run[r - 1] + 1, 0)
    run[0] = free[0].astype(np.int32)

    lengths: list[list[int]] = [[] for _ in range(n + 1)]
    blocked_count = np.zeros(n + 1)
    total = np.zeros(n + 1)
    # Shadow-side edge: building pixel whose upper neighbour is not the same building.
    edge = np.zeros(lab.shape, dtype=bool)
    edge[1:] = (lab[1:] > 0) & (lab[:-1] != lab[1:])
    for rc in np.argwhere(edge).tolist():
        r, c = int(rc[0]), int(rc[1])
        b = int(lab[r, c])
        length = int(run[r - 1, c])
        if length == 0:
            continue
        end = r - 1 - length
        total[b] += 1
        if end < 0 or lab[end, c] != 0:
            blocked_count[b] += 1
        else:
            lengths[b].append(length)
    out = np.full(n, np.nan)
    for b in range(1, n + 1):
        if lengths[b]:
            out[b - 1] = float(np.quantile(lengths[b], quantile))
    blocked = (total[1:] > 0) & (blocked_count[1:] > total[1:] / 2)
    return ShadowRuns(out, blocked, total[1:])
