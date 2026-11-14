"""Raster sampling for the city model (needs the `model` extra: rasterio, geopandas)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import rasterio
from rasterio.features import rasterize
from rasterio.windows import from_bounds

from twin.model.terrain import ground_from_samples

FloatArray = npt.NDArray[np.float64]


def _read_window(src: Any, bounds: tuple[float, float, float, float]) -> tuple[FloatArray, Any]:
    pad = abs(src.res[0]) * 2
    win = from_bounds(bounds[0] - pad, bounds[1] - pad, bounds[2] + pad, bounds[3] + pad, src.transform)
    win = win.round_offsets().round_lengths()
    data = src.read(1, window=win, boundless=True, fill_value=src.nodata if src.nodata is not None else np.nan)
    arr = data.astype("float64")
    if src.nodata is not None:
        arr[arr == src.nodata] = np.nan
    return arr, src.window_transform(win)


def _point_values(arr: FloatArray, transform: Any, xs: FloatArray, ys: FloatArray) -> FloatArray:
    inv = ~transform
    cols = inv.a * xs + inv.b * ys + inv.c
    rows = inv.d * xs + inv.e * ys + inv.f
    cols = np.floor(cols).astype(int)
    rows = np.floor(rows).astype(int)
    out = np.full(len(xs), np.nan)
    ok = (rows >= 0) & (rows < arr.shape[0]) & (cols >= 0) & (cols < arr.shape[1])
    out[ok] = arr[rows[ok], cols[ok]]
    return out


def sample_polygon_stat(path: Path, frame: Any, statistic: str = "median", *, min_valid: float = 0.0) -> FloatArray:
    """One value per polygon: the statistic of the raster cells whose centres fall inside it.

    Polygons too small to contain a cell centre take the cell under their inner point.
    Cells below ``min_valid`` (e.g. 0 = "not a building" in Urban Atlas) are ignored.
    """
    if statistic not in ("median", "mean", "max", "mode"):
        raise ValueError(f"unsupported statistic {statistic}")
    with rasterio.open(path) as src:
        g = frame.to_crs(src.crs)
        arr, transform = _read_window(src, tuple(g.total_bounds))
    arr = np.where(arr >= min_valid, arr, np.nan)
    labels = rasterize(
        ((geom, i + 1) for i, geom in enumerate(g.geometry)),
        out_shape=arr.shape, transform=transform, fill=0, dtype="int32",
    )
    out = np.full(len(g), np.nan)
    flat_l, flat_v = labels.ravel(), arr.ravel()
    keep = (flat_l > 0) & np.isfinite(flat_v)
    if keep.any():
        lab, val = flat_l[keep], flat_v[keep]
        order = np.lexsort((val, lab))
        lab, val = lab[order], val[order]
        starts = np.flatnonzero(np.r_[True, lab[1:] != lab[:-1]])
        ends = np.r_[starts[1:], len(lab)]
        for s, e in zip(starts, ends):
            chunk = val[s:e]
            if statistic == "median":
                v = float(np.median(chunk))
            elif statistic == "mode":
                uniq, counts = np.unique(chunk, return_counts=True)
                v = float(uniq[np.argmax(counts)])  # ties -> lowest value, deterministic
            elif statistic == "mean":
                v = float(chunk.mean())
            else:
                v = float(chunk.max())
            out[lab[s] - 1] = v
    missing = np.isnan(out)
    if missing.any():
        pts = g.geometry[missing].representative_point()
        out[missing] = _point_values(arr, transform, pts.x.to_numpy(), pts.y.to_numpy())
    return out


def sample_ground(path: Path, frame: Any, *, ring_m: float, percentile: float, n_points: int = 8) -> FloatArray:
    """Ground level per building: low percentile of DEM samples on a ring around its centre.

    ``frame`` must be in a metric CRS; the ring radius is the footprint's own half-size plus ``ring_m``.
    """
    with rasterio.open(path) as src:
        cx = frame.geometry.centroid.x.to_numpy()
        cy = frame.geometry.centroid.y.to_numpy()
        b = frame.geometry.bounds
        half = np.maximum(b.maxx - b.minx, b.maxy - b.miny).to_numpy() / 2.0
        radius = half + ring_m
        ang = np.linspace(0, 2 * np.pi, n_points, endpoint=False)
        xs = (cx[:, None] + radius[:, None] * np.cos(ang)[None, :]).ravel()
        ys = (cy[:, None] + radius[:, None] * np.sin(ang)[None, :]).ravel()
        if src.crs is not None and frame.crs != src.crs:
            from pyproj import Transformer

            tr = Transformer.from_crs(frame.crs, src.crs, always_xy=True)
            xs, ys = tr.transform(xs, ys)
        arr, transform = _read_window(src, (float(np.min(xs)), float(np.min(ys)), float(np.max(xs)), float(np.max(ys))))
    vals = _point_values(arr, transform, np.asarray(xs), np.asarray(ys)).reshape(len(frame), n_points)
    out = np.full(len(frame), np.nan)
    for i in range(len(frame)):
        v = ground_from_samples(vals[i], percentile=percentile, nodata=None)
        if v is not None:
            out[i] = v
    return out
