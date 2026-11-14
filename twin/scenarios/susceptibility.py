"""Rain trouble spots: where flooding call-outs are most likely, from low ground and past call-outs.

Checked on Roma Capitale's civil-protection log (4,577 street and home flooding call-outs, 2013-2022):
ground lower than its surroundings within about 1 km, plus the number of earlier call-outs within 150 m,
ranks the 2018-2022 call-outs above random inhabited places 71 % of the time (AUC 0.71) using only the
2013-2017 history. The pond-and-sewer model alone reaches 0.54 on the same test, so this ranking is
the one to use for "where to send pumps and patrols first" (scripts/validate_rain_log.py).
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from twin.scenarios import layers
from twin.scenarios.terrain import BoolArray, FloatArray, Grid

FLOOD_TYPES = ("2.03", "2.04")  # street and home flooding; extended flooding


def load_call_outs(file_name: str) -> list[tuple[float, float]] | None:
    """Flooding call-out points from the civil-protection event log, or None when the layer is missing."""
    path = layers.find(file_name)
    if path is None:
        return None
    out: list[tuple[float, float]] = []
    for f in layers.read(path).get("features", []):
        props, g = f.get("properties") or {}, f.get("geometry") or {}
        if str(props.get("sottotipol", ""))[:4] in FLOOD_TYPES and g.get("type") == "Point":
            out.append((float(g["coordinates"][0]), float(g["coordinates"][1])))
    return out


def _disc_sum(counts: FloatArray, radius_cells: float) -> FloatArray:
    from scipy.ndimage import convolve  # type: ignore[import-untyped]

    r = int(np.ceil(radius_cells))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    kernel = (np.hypot(yy, xx) <= radius_cells + 1e-9).astype(float)
    out: FloatArray = convolve(counts, kernel, mode="constant", cval=0.0)
    return out


def trouble_spots(grid: Grid, in_area: BoolArray, sealed: FloatArray,
                  call_outs: Sequence[tuple[float, float]] | None, cfg: Mapping[str, Any]) -> dict[str, Any]:
    """Top places by low ground and past call-outs, spread at least ``spacing_m`` apart."""
    from scipy.ndimage import uniform_filter

    z = grid.z
    valid = ~np.isnan(z)
    fill = np.where(valid, z, np.nanmean(z) if valid.any() else 0.0)
    size = max(1, int(round(float(cfg["tpi_window_m"]) / grid.cell)))
    tpi = fill - uniform_filter(fill, size=size, mode="nearest")
    ref = cfg["reference"]
    score = -(tpi - float(ref["tpi_mean"])) / float(ref["tpi_sd"])
    past: FloatArray | None = None
    if call_outs is not None:
        counts = np.zeros(grid.shape)
        if call_outs:
            rows, cols = grid.rowcol([p[0] for p in call_outs], [p[1] for p in call_outs])
            ok = rows >= 0
            np.add.at(counts, (rows[ok], cols[ok]), 1.0)
        past = np.rint(_disc_sum(counts, float(cfg["history_radius_m"]) / grid.cell))
        score = score + float(cfg["history_weight"]) * (np.log1p(past) - float(ref["history_mean"])) / float(ref["history_sd"])
    ok_cells = valid & in_area & (np.nan_to_num(sealed) >= float(cfg["min_sealed"]))
    flat = np.where(ok_cells, score, -np.inf).ravel()
    spacing = float(cfg["spacing_m"]) / grid.cell
    chosen: list[tuple[int, int]] = []
    for idx in np.argsort(-flat, kind="stable"):
        if not np.isfinite(flat[idx]) or len(chosen) >= int(cfg["listed"]):
            break
        r, c = divmod(int(idx), grid.shape[1])
        if all(np.hypot(r - r0, c - c0) >= spacing for r0, c0 in chosen):
            chosen.append((r, c))
    spots: list[dict[str, Any]] = []
    if chosen:
        rr, cc = np.asarray([p[0] for p in chosen], dtype=np.int64), np.asarray([p[1] for p in chosen], dtype=np.int64)
        lons, lats = grid.lonlat(rr, cc)
        for k, (r, c) in enumerate(chosen):
            spots.append({"lon": round(lons[k], 6), "lat": round(lats[k], 6),
                          "low_ground_m": round(float(tpi[r, c]), 1),
                          "past_call_outs": None if past is None else int(past[r, c]),
                          "score": round(float(score[r, c]), 2)})
    return {"spots": spots, "history": "not_available" if past is None else "real",
            "low_ground": tpi, "past": past, "score": score}
