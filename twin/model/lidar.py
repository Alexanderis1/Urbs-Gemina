"""Heights from the MASE airborne LiDAR (1 m DSM First and DTM, CC BY 4.0, flown 2008-2011).

Pure helpers: download-API payloads, per-footprint heights from DSM - DTM, and replacing
the fused height with the measured one where LiDAR saw the building.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence, TypeVar
from urllib.parse import urlsplit

import geopandas as gpd
import numpy as np
import numpy.typing as npt
from scipy import ndimage

Array = npt.NDArray[np.float64]
T = TypeVar("T")

API_PREFIX = "/core/api/esri"


def public_download_url(raw: str, backend: str) -> str:
    """The API hands out links on its internal gateway; the browser app re-hosts them on the backend."""
    base = backend.rstrip("/")
    if raw.startswith(base + API_PREFIX):
        return raw
    path = urlsplit(raw).path
    return f"{base}{API_PREFIX}{path}"


def chunked(items: Sequence[T], size: int) -> list[list[T]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def tile_payload(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Grid rows (QU_LiDAR_Griglia_1x1) to the download API's tile list; only surveyed tiles."""
    out = []
    for r in rows:
        if int(r.get("risoluzion") or 0) < 1:
            continue
        out.append({k: str(r.get(k, "")).strip() for k in ("fid", "tavola", "regione", "contratto")})
    return out


def footprint_heights(
    ndsm: Array,
    dtm: Array,
    labels: npt.NDArray[np.integer],
    *,
    n: int,
    quantile: float,
    min_px: int,
) -> tuple[Array, Array, Array]:
    """Per building 1..n: a high quantile of DSM - DTM (roof height), median DTM (ground), pixel count.

    Footprints are eroded by one pixel so walls and neighbouring ground do not count.
    NaN pixels (no data) are ignored. A building with fewer than ``min_px`` pixels gets NaN.
    """
    lab = np.asarray(labels).astype(np.int64)
    inner = ndimage.grey_erosion(lab, size=3) == lab
    lab = np.where(inner & np.isfinite(ndsm) & np.isfinite(dtm), lab, 0)
    flat = lab.ravel()
    sel = flat > 0
    ids = flat[sel]
    h = np.full(n, np.nan)
    g = np.full(n, np.nan)
    count = np.bincount(ids, minlength=n + 1)[1 : n + 1].astype("float64")
    if ids.size:
        hv = np.asarray(ndsm, dtype="float64").ravel()[sel]
        gv = np.asarray(dtm, dtype="float64").ravel()[sel]
        order = np.lexsort((hv, ids))
        ids_s, hv_s = ids[order], hv[order]
        starts = np.searchsorted(ids_s, np.arange(1, n + 1), side="left")
        ends = np.searchsorted(ids_s, np.arange(1, n + 1), side="right")
        gorder = np.lexsort((gv, ids))
        gv_s = gv[gorder]
        for b in np.nonzero(ends - starts >= min_px)[0]:
            s, e = starts[b], ends[b]
            h[b] = float(np.quantile(hv_s[s:e], quantile))
            g[b] = float(np.median(gv_s[s:e]))
    return h, g, count


def apply_lidar(
    model: gpd.GeoDataFrame,
    h_lidar: Array,
    *,
    sd_m: float,
    min_height_m: float,
    survey: str,
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """Use the LiDAR height where LiDAR saw a building; keep the fused height elsewhere.

    A footprint where LiDAR measured almost nothing (below ``min_height_m``) was probably
    built after the survey, so it keeps the fused height and is flagged.
    """
    out = model.copy()
    h = np.asarray(h_lidar, dtype="float64")
    seen = np.isfinite(h)
    use = seen & (h >= min_height_m)
    newer = seen & (h < min_height_m)
    out["h_lidar"] = h
    out["lidar_missing_building"] = newer
    out.loc[use, "height_m"] = h[use]
    out.loc[use, "height_sd_m"] = sd_m
    out.loc[use, "height_source"] = "lidar"
    out.loc[use, "data_kind"] = "real"
    if "height_conflict" in out:
        out.loc[use, "height_conflict"] = False
    out.attrs = dict(model.attrs)
    stats = {"covered": int(seen.sum()), "replaced": int(use.sum()), "newer_than_survey": int(newer.sum()), "survey": survey,
             "min_height_m": min_height_m}
    return out, stats


@dataclass(frozen=True)
class LinearFit:
    intercept: float
    slope: float
    sd_m: float  # robust residual spread (1.4826 x MAD)
    n: int

    def apply(self, x: Array) -> Array:
        return self.intercept + self.slope * np.asarray(x, dtype="float64")

    def as_dict(self) -> dict[str, float]:
        return {"intercept_m": self.intercept, "slope": self.slope, "sd_m": self.sd_m, "n": self.n}


def fit_linear(x: Array, y: Array, *, iterations: int = 20) -> LinearFit:
    """Robust straight line y = a + b x (iteratively reweighted least squares, Tukey biweight).

    Used to correct the fused height where LiDAR did not see the building: the other sources
    under-estimate tall historic buildings by a share of their height, not a fixed offset.
    """
    x = np.asarray(x, dtype="float64")
    y = np.asarray(y, dtype="float64")
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    w = np.ones_like(x)
    a = b = 0.0
    scale = 1.0
    for _ in range(iterations):
        sw = w.sum()
        mx, my = (w * x).sum() / sw, (w * y).sum() / sw
        b = float((w * (x - mx) * (y - my)).sum() / max((w * (x - mx) ** 2).sum(), 1e-12))
        a = float(my - b * mx)
        r = y - (a + b * x)
        scale = float(1.4826 * np.median(np.abs(r - np.median(r)))) or 1e-6
        u = r / (4.685 * scale)
        w = np.where(np.abs(u) < 1, (1 - u**2) ** 2, 0.0)
    return LinearFit(a, b, scale, int(x.size))


def holdout_correction(x: Array, y: Array, cells: npt.NDArray[np.integer]) -> dict[str, float]:
    """Fit the correction on even spatial cells, score it on odd ones (mean absolute error before/after)."""
    x = np.asarray(x, dtype="float64")
    y = np.asarray(y, dtype="float64")
    ok = np.isfinite(x) & np.isfinite(y)
    train = ok & (np.asarray(cells) % 2 == 0)
    test = ok & ~train
    fit = fit_linear(x[train], y[train])
    before = np.abs(x[test] - y[test])
    after = np.abs(fit.apply(x[test]) - y[test])
    return {
        "mae_before_m": float(before.mean()), "mae_after_m": float(after.mean()),
        "within3_before": float((before <= 3).mean()), "within3_after": float((after <= 3).mean()),
        "n_test": int(test.sum()), **{f"train_{k}": float(v) for k, v in fit.as_dict().items()},
    }
