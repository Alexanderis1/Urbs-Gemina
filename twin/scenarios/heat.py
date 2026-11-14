"""Heatwave: where the day and the night get hottest, who lives there, and what more trees would change.

The air temperature forecast (Open-Meteo, about 2 km cells) is read as the
average of its neighbourhood. Local differences are added around it from real
satellite layers: sealed ground (Copernicus imperviousness) warms, tree cover
(Copernicus tree cover density) cools, by coefficients from the literature
kept in config/scenarios.yaml. An ensemble over the forecast error and the
coefficients gives P5/P50/P95. Thresholds come from config/thresholds.yaml.
People are counted per ISTAT census section (residents, children 0-14, 65+).
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from twin.scenarios import config, impacts, layers
from twin.scenarios.area import Area, resolve_area
from twin.scenarios.data import ScenarioData
from twin.scenarios.exposure import load_census
from twin.scenarios.flood import load_dtm_like
from twin.scenarios.geometry import area_km2, centroid
from twin.scenarios.terrain import (FloatArray, Grid, mask_to_geojson, rasterize_index, rasterize_mask, to_utm)

Point = tuple[float, float, float, float, float]  # lon, lat, max °C, min °C, sigma °C


def _cfg() -> dict[str, Any]:
    raw: dict[str, Any] = config.load("scenarios.yaml")["heatwave"]
    return {k: config.value(raw, k) for k in raw}


def _na(reason: str, kinds: Mapping[str, str] | None = None) -> dict[str, Any]:
    return {"result": {"status": "not_available", "reason": reason}, "data_kinds": dict(kinds or {}),
            "sources": [], "synthetic": False, "warnings": [reason]}


def _temperature(change: Mapping[str, Any], data: ScenarioData,
                 sigma_default: float) -> tuple[str | None, list[Point], str]:
    """(day, forecast points, kind). Raises LookupError when no forecast is loaded."""
    if "tmax_c" in change:
        tmax = float(change["tmax_c"])
        tmin = float(change.get("tmin_c", math.nan))
        sigma = float(change.get("sigma_c", 0.0))
        return None, [(math.nan, math.nan, tmax, tmin, sigma)], "hypothetical"
    if change.get("temperature", "forecast") != "forecast":
        raise ValueError("heatwave change needs 'tmax_c' (and 'tmin_c'), or 'temperature': 'forecast'")
    if not data.temperature:
        raise LookupError("No temperature forecast loaded (live_data('heatwave', ...) reads it)")
    days = dict(data.temperature)
    if change.get("day"):
        day = str(change["day"])
        if day not in days:
            raise LookupError(f"No forecast for {day}; available: {', '.join(sorted(days))}")
    else:
        day = max(days, key=lambda d: max(p[2] for p in days[d]) if days[d] else -math.inf)
    points = [(float(a), float(b), float(c), float(d), float(e) or sigma_default) for a, b, c, d, e in days[day]]
    return day, points, "estimated"


def _grid(area: Area, margin_m: float, cell: float) -> Grid:
    w, s, e, n = area.bbox
    xs, ys = to_utm([w, e, w, e], [s, s, n, n])
    x0 = math.floor((min(xs) - margin_m) / cell) * cell
    y1 = math.ceil((max(ys) + margin_m) / cell) * cell
    cols = int(math.ceil((max(xs) + margin_m - x0) / cell))
    rows = int(math.ceil((y1 - (min(ys) - margin_m)) / cell))
    return Grid(np.zeros((rows, cols)), x0, y1, cell, {"id": "heat_grid"})


def _share(grid: Grid, file_key: str, cfg: Mapping[str, Any], warnings: list[str], what: str) -> tuple[FloatArray, str]:
    path = layers.find(str(cfg[file_key]))
    if path is None:
        warnings.append(f"No {what} layer ({cfg[file_key]}): its effect on local temperature is left out.")
        return np.zeros(grid.shape), "not_available"
    values = load_dtm_like(grid, str(path))
    return np.clip(np.nan_to_num(values / 100.0, nan=0.0), 0.0, 1.0), "real"


def _forecast_field(grid: Grid, points: Sequence[Point]) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Nearest forecast point per cell: (max, min, sigma)."""
    if len(points) == 1 or any(math.isnan(p[0]) for p in points):
        p = points[0]
        return np.full(grid.shape, p[2]), np.full(grid.shape, p[3]), np.full(grid.shape, p[4])
    from scipy.spatial import cKDTree  # type: ignore[import-untyped]

    px, py = to_utm([p[0] for p in points], [p[1] for p in points])
    rows, cols = np.indices(grid.shape)
    cx = grid.x0 + (cols.ravel() + 0.5) * grid.cell
    cy = grid.y0 - (rows.ravel() + 0.5) * grid.cell
    _, idx = cKDTree(np.column_stack([px, py])).query(np.column_stack([cx, cy]))
    arr = np.asarray(points, dtype=np.float64)[np.asarray(idx)]
    return (arr[:, 2].reshape(grid.shape), arr[:, 3].reshape(grid.shape), arr[:, 4].reshape(grid.shape))


def _ages(census: Mapping[str, Any], cfg: Mapping[str, Any]) -> dict[str, int] | None:
    feats = census.get("features", [])
    if feats and all("elderly_65_plus" in (f.get("properties") or {}) for f in feats):
        return {str(f["properties"]["sez_id"]): int(f["properties"]["elderly_65_plus"] or 0) for f in feats}
    path = layers.find(str(cfg["ages_file"]))
    if path is None:
        return None
    with Path(path).open(encoding="utf-8") as fh:
        return {row["sez_id"]: int(row["elderly_65_plus"] or 0) for row in csv.DictReader(fh)}


def _where(spec: Mapping[str, Any], area: Area, data: ScenarioData) -> dict[str, Any]:
    where = spec.get("where")
    if where is None:
        return dict(area.geometry)
    resolved = resolve_area(where, lookup=data.area_lookup or layers.default_area_lookup)
    return dict(resolved.geometry)


def _section_means(index: np.ndarray, n: int, fields: Sequence[FloatArray],
                   fallback_cells: Sequence[tuple[int, int]]) -> list[FloatArray]:
    inside = index >= 0
    count = np.bincount(index[inside], minlength=n).astype(np.float64)
    out: list[FloatArray] = []
    for field in fields:
        total = np.bincount(index[inside], weights=field[inside], minlength=n)
        mean = np.divide(total, count, out=np.zeros(n), where=count > 0)
        for i in np.flatnonzero(count == 0).tolist():
            r, c = fallback_cells[i]
            mean[i] = field[r, c] if r >= 0 else math.nan
        out.append(mean)
    return out


def run_heatwave(area: Area, change: Mapping[str, Any], data: ScenarioData) -> dict[str, Any]:
    cfg = _cfg()
    limits = config.load("thresholds.yaml")["heat"]
    hot_c = float(limits["hot_day_tmax_c"]["value"])
    night_c = float(limits["tropical_night_tmin_c"]["value"])
    warnings: list[str] = []
    try:
        day, points, t_kind = _temperature(change, data, float(cfg["forecast_sigma_c"]))
    except LookupError as exc:
        return _na(str(exc), {"temperature": "not_available"})
    census = load_census(data)
    if census is None:
        return _na("Census sections not available.", {"temperature": t_kind, "census": "not_available"})

    cell = float(cfg["cell_m"])
    scale = float(cfg["forecast_scale_m"])
    grid = _grid(area, scale / 2 + cell, cell)
    imp, imp_kind = _share(grid, "impervious_file", cfg, warnings, "imperviousness")
    trees, tree_kind = _share(grid, "tree_cover_file", cfg, warnings, "tree cover")
    from scipy.ndimage import uniform_filter  # type: ignore[import-untyped]

    k = max(1, int(round(scale / cell)) | 1)
    imp_nb = uniform_filter(imp, size=k, mode="nearest")
    trees_nb = uniform_filter(trees, size=k, mode="nearest")

    # what-if: more trees and / or less sealed ground in a place
    imp2, trees2 = imp.copy(), trees.copy()
    what_if: dict[str, Any] = {}
    plant = change.get("plant_trees")
    if isinstance(plant, Mapping):
        mask = rasterize_mask(grid, [_where(plant, area, data)], all_touched=False)
        add = float(plant.get("cover_added_pct", 10)) / 100.0
        if not 0 < add <= 1:
            raise ValueError("cover_added_pct must be between 0 and 100")
        trees2 = np.where(mask, np.minimum(trees + add, 1.0), trees)
        added_m2 = float((trees2 - trees)[mask].sum()) * grid.cell_area
        what_if["trees_added"] = int(round(added_m2 / float(cfg["crown_area_m2"])))
        what_if["planted_area_km2"] = round(area_km2(_where(plant, area, data)), 3)
        what_if["planted_mask"] = mask
    depave = change.get("depave")
    if isinstance(depave, Mapping):
        mask_d = rasterize_mask(grid, [_where(depave, area, data)], all_touched=False)
        cut = float(depave.get("impervious_removed_pct", 10)) / 100.0
        imp2 = np.where(mask_d, np.maximum(imp - cut, 0.0), imp)
        what_if.setdefault("planted_mask", mask_d)
    has_what_if = bool(what_if)

    tmax_fc, tmin_fc, sigma = _forecast_field(grid, points)
    has_night = not bool(np.isnan(tmin_fc).all())
    d_imp, d_trees = imp - imp_nb, trees - trees_nb
    d_imp2, d_trees2 = imp2 - imp_nb, trees2 - trees_nb

    # census sections inside the area
    feats = [f for f in census.get("features", []) if f.get("geometry")]
    cents = [centroid(f["geometry"]) for f in feats]
    keep = [area.contains(c[0], c[1]) for c in cents]
    feats = [f for f, ok in zip(feats, keep) if ok]
    cents = [c for c, ok in zip(cents, keep) if ok]
    if not feats:
        return _na("No census section inside this area.", {"temperature": t_kind})
    n = len(feats)
    index = rasterize_index(grid, [f["geometry"] for f in feats])
    rr, cc = grid.rowcol([c[0] for c in cents], [c[1] for c in cents])
    fallback = list(zip(rr.tolist(), cc.tolist()))
    fields = [tmax_fc, tmin_fc, sigma, d_imp, d_trees, d_imp2, d_trees2, imp, trees]
    s_tmax, s_tmin, s_sig, s_dimp, s_dtree, s_dimp2, s_dtree2, s_imp, s_trees = _section_means(
        index, n, fields, fallback)
    props = [f.get("properties") or {} for f in feats]
    residents = np.asarray([float(p.get("residents") or 0) for p in props])
    children = np.asarray([float(p.get("children_0_14") or 0) for p in props])
    ages = _ages(census, cfg)
    elderly = (np.asarray([float(ages.get(str(p.get("sez_id")), 0)) for p in props]) if ages is not None else None)
    if elderly is None:
        warnings.append("Residents aged 65+ not loaded (census_ages.csv): run scripts/fetch_heat_layers.py.")

    # ensemble
    rng = np.random.default_rng(int(cfg["seed"]))
    members = int(cfg["members"])
    coef = cfg["coefficients"]

    def draw(pair: Sequence[float]) -> FloatArray:
        out: FloatArray = np.maximum(rng.normal(float(pair[0]), float(pair[1]), members), 0.0)
        return out

    a_d, b_d = draw(coef["day"]["impervious"]), draw(coef["day"]["trees"])
    a_n, b_n = draw(coef["night"]["impervious"]), draw(coef["night"]["trees"])
    eps = rng.normal(0.0, 1.0, members)

    groups = {"residents": residents, "children_0_14": children}
    if elderly is not None:
        groups["elderly_65_plus"] = elderly
    hot_counts: dict[str, list[float]] = {g: [] for g in groups}
    night_counts: dict[str, list[float]] = {g: [] for g in groups}
    hot2: list[float] = []
    relieved: list[float] = []
    cooling: list[float] = []
    sec_tmax = np.empty((n, members))
    sec_tmin = np.empty((n, members))
    p_hot = np.zeros(grid.shape)
    planted = what_if.get("planted_mask")
    for m in range(members):
        tx = s_tmax + eps[m] * s_sig + a_d[m] * s_dimp - b_d[m] * s_dtree
        sec_tmax[:, m] = tx
        hot = tx >= hot_c
        for g, counts in groups.items():
            hot_counts[g].append(float(counts[hot].sum()))
        if has_night:
            tn = s_tmin + eps[m] * s_sig + a_n[m] * s_dimp - b_n[m] * s_dtree
            sec_tmin[:, m] = tn
            for g, counts in groups.items():
                night_counts[g].append(float(counts[tn >= night_c].sum()))
        grid_tx = tmax_fc + eps[m] * sigma + a_d[m] * d_imp - b_d[m] * d_trees
        p_hot += grid_tx >= hot_c
        if has_what_if:
            tx2 = s_tmax + eps[m] * s_sig + a_d[m] * s_dimp2 - b_d[m] * s_dtree2
            hot_2 = tx2 >= hot_c
            hot2.append(float(residents[hot_2].sum()))
            relieved.append(float(residents[hot & ~hot_2].sum()))
            delta = (a_d[m] * (d_imp - d_imp2) - b_d[m] * (d_trees - d_trees2))
            cooling.append(float(delta[planted].mean()) if planted is not None and planted.any() else 0.0)
    p_hot /= members

    area_mask = (np.ones(grid.shape, dtype=bool) if area.kind == "city"
                 else rasterize_mask(grid, [area.geometry], all_touched=False))
    hot_map = (p_hot >= float(cfg["hot_probability"])) & area_mask

    def block(counts: Mapping[str, list[float]], threshold: float, source: str) -> dict[str, Any]:
        out: dict[str, Any] = {"threshold_c": threshold, "source": source}
        out.update({g: impacts.quantiles(v) for g, v in counts.items()})
        return out

    # hottest places where people live
    order = np.argsort(-np.where(residents > 0, np.median(sec_tmax, axis=1), -np.inf))[:50]
    order = order[residents[order] > 0]
    sections: list[dict[str, Any]] = []
    for i in order.tolist():
        row: dict[str, Any] = {
            "sez_id": str(props[i].get("sez_id", "")), "residents": int(residents[i]),
            "elderly_65_plus": (int(elderly[i]) if elderly is not None else None),
            "lon": round(cents[i][0], 6), "lat": round(cents[i][1], 6),
            "tmax_c": impacts.quantiles(sec_tmax[i].tolist()),
            "impervious_pct": round(float(s_imp[i]) * 100, 1), "tree_cover_pct": round(float(s_trees[i]) * 100, 1)}
        if has_night:
            row["tmin_c"] = impacts.quantiles(sec_tmin[i].tolist())
        sections.append(row)

    result: dict[str, Any] = {
        "day": day,
        "forecast_tmax_c": round(float(np.median([p[2] for p in points])), 1),
        "forecast_tmin_c": (round(float(np.median([p[3] for p in points])), 1) if has_night else None),
        "hot_day": block(hot_counts, hot_c, str(limits["hot_day_tmax_c"]["source"])),
        "tropical_night": (block(night_counts, night_c, str(limits["tropical_night_tmin_c"]["source"]))
                           if has_night else None),
        "sections": sections,
        "hot_map_p50": mask_to_geojson(grid, hot_map),
        "hot_area_km2": round(float(hot_map.sum()) * grid.cell_area / 1e6, 2),
        "sensitive_sites": impacts.sensitive_sites(grid, np.where(area_mask, p_hot, 0.0),
                                                   float(cfg["hot_probability"])),
        "calibration": "uncalibrated",
    }
    if has_what_if:
        result["what_if"] = {
            "hot_day_residents": impacts.quantiles(hot2),
            "residents_no_longer_hot": impacts.quantiles(relieved),
            "cooling_day_c": impacts.quantiles(cooling),
            **{k: v for k, v in what_if.items() if k != "planted_mask"},
        }
    kinds = {"temperature": t_kind, "impervious": imp_kind, "tree_cover": tree_kind, "census": "real",
             "local_temperature": "estimated"}
    if elderly is not None:
        kinds["elderly"] = "real"
    warnings += [
        "Local temperatures are the forecast plus differences from sealed ground and tree cover, with coefficients "
        "from the literature (assumption C=40, config/scenarios.yaml); not yet checked against Rome street sensors.",
        "The forecast is read as the average of its 2 km neighbourhood; buildings' shade and wind are not modelled.",
        "Tree and sealed-ground layers are Copernicus 2018: newer parks or buildings are not included.",
    ]
    if t_kind == "hypothetical":
        warnings.append("Temperatures are the values you entered (hypothetical), not a forecast.")
    sources: list[dict[str, str]] = [{"id": "copernicus_hrl_tree_cover", "file": str(cfg["tree_cover_file"])},
               {"id": "copernicus_hrl_imperviousness", "file": str(cfg["impervious_file"])}]
    if t_kind == "estimated":
        sources.append({"id": "open_meteo_forecast", "day": str(day)})
    return {"result": result, "data_kinds": kinds, "sources": sources, "synthetic": False, "warnings": warnings}
