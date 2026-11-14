"""Flooding: river (Tiber, Aniene) and localized rain flooding, baseline vs variant with ranges.

River: the water rises ``rise_m`` above its ordinary level; ground lower than that,
connected to the river, floods (height above nearest river, HAND). Terrain error
turns the edge into a probability. Official PGRA hazard areas are reported beside it.

Rain: rain minus drainage and infiltration runs off down the terrain and fills the
hollows it reaches (fill-and-spill without cascade). An ensemble over rainfall,
drain capacity and infiltration gives each hotspot's P5 / P50 / P95 depth.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any, Mapping, Sequence

import numpy as np
import numpy.typing as npt

from twin.providers.base import BBox
from twin.scenarios import config, impacts, layers
from twin.scenarios.area import Area
from twin.scenarios.data import ScenarioData
from twin.scenarios import hydro, sewer, susceptibility
from twin.scenarios.terrain import BoolArray, FloatArray, Grid, load_dtm, mask_to_geojson, rasterize_mask


def _cfg(section: str) -> dict[str, Any]:
    raw: dict[str, Any] = config.load("scenarios.yaml")[section]
    return {k: config.value(raw, k) for k in raw}


@lru_cache(maxsize=4)
def _cached_dtm(bbox: BBox, cell: float) -> Grid:
    return load_dtm(bbox, cell)


def terrain_for(area: Area | None, data: ScenarioData, margin_m: float = 0.0) -> Grid:
    """Terrain around the area; ``None`` means the whole city (rivers need their whole valley)."""
    if isinstance(data.dtm, Grid):
        return data.dtm
    if area is None:
        bbox_city = tuple(float(v) for v in config.load("areas.yaml")["city"]["bbox"])
        return _cached_dtm(bbox_city, float(config.value(config.load("scenarios.yaml")["terrain"], "cell_m")))
    w, s, e, n = area.bbox
    dlat = margin_m / 111_195.0
    dlon = dlat / max(math.cos(math.radians((s + n) / 2)), 0.2)
    bbox = (round(w - dlon, 4), round(s - dlat, 4), round(e + dlon, 4), round(n + dlat, 4))
    return _cached_dtm(bbox, float(config.value(config.load("scenarios.yaml")["terrain"], "cell_m")))


def _area_mask(grid: Grid, area: Area) -> BoolArray:
    if area.kind == "city":
        return ~np.isnan(grid.z)
    return rasterize_mask(grid, [area.geometry], all_touched=False) & ~np.isnan(grid.z)


def _normal_cdf(x: FloatArray) -> FloatArray:
    from scipy.special import ndtr  # type: ignore[import-untyped]

    out: FloatArray = np.asarray(ndtr(x), dtype=np.float64)
    return out


# --------------------------------------------------------------------------- river


def _river_cells(grid: Grid, river: str, data: ScenarioData, warnings: list[str]) -> tuple[BoolArray, str]:
    cfg = _cfg("river_flood")
    if data.rivers is not None:
        collection: Mapping[str, Any] | None = data.rivers
    else:
        path = layers.find(str(cfg["rivers_file"]))
        collection = layers.read(path) if path is not None else None
    if collection is not None:
        names = [n.casefold() for n in cfg["river_names"].get(river, [river])]
        lines = [f["geometry"] for f in collection.get("features", [])
                 if f.get("geometry") and str((f.get("properties") or {}).get("name", "")).casefold() in names]
        if lines:
            mask = rasterize_mask(grid, lines) & ~np.isnan(grid.z)
            if mask.any():
                return mask, "real"
        warnings.append(f"River '{river}' not found in the rivers layer inside this area.")
    derived = cfg["derived_rivers"].get(river)
    if derived is None:
        return np.zeros(grid.shape, dtype=bool), "not_available"
    warnings.append(f"Rivers layer not available: the {river} is traced from the terrain as the channel draining "
                    f"{derived['min_km2']:g} km2 or more past its gauge (estimated).")
    acc = np.nan_to_num(_accumulation(grid), nan=0.0)
    channel = (acc >= float(derived["min_km2"]) * 1e6) & (acc < float(derived["max_km2"]) * 1e6)
    gauge = cfg["gauges"][derived["gauge"]]
    rows, cols = grid.rowcol([float(gauge["lon"])], [float(gauge["lat"])])
    seed = np.zeros(grid.shape, dtype=bool)
    if rows[0] >= 0:
        reach = int(1000 / grid.cell)
        seed[max(0, rows[0] - reach):rows[0] + reach + 1, max(0, cols[0] - reach):cols[0] + reach + 1] = True
    return hydro.connected_to(channel, seed), "estimated"


_ACC: dict[int, FloatArray] = {}


def _accumulation(grid: Grid) -> FloatArray:
    key = id(grid.z)
    if key not in _ACC:
        _ACC.clear()
        _ACC[key] = hydro.flow_accumulation(grid.z, grid.cell)
    return _ACC[key]


@dataclass(frozen=True)
class Stage:
    river: str
    rise_m: float
    sigma_m: float
    kind: str  # hypothetical | real | estimated
    gauge: str | None = None
    level_m: dict[str, float] | None = None  # P5 / P50 / P95 on the gauge
    discharge_m3s: float | None = None
    alerts: dict[str, float] | None = None  # probability of reaching each official alert level
    return_period_years: int | None = None
    scenario: str | None = None  # plain label of a named what-if, e.g. "200-year flood ..."


def _rating(gauge: Mapping[str, Any], discharge: FloatArray, noise: bool = True) -> FloatArray:
    """Level (m on the gauge) for each discharge; the fitted curve adds its own scatter unless ``noise`` is off."""
    power = gauge.get("rating_power")
    if power is not None:
        q = np.maximum(np.asarray(discharge, dtype=np.float64), 0.0)
        levels: FloatArray = float(power["h0"]) + np.power(q / float(power["a"]), 1.0 / float(power["b"]))
        if noise:
            levels = levels + np.random.default_rng(29).normal(0.0, float(power["sigma_m"]), levels.shape)
        return levels
    curve = np.asarray(gauge["rating"], dtype=np.float64)
    out: FloatArray = np.interp(discharge, curve[:, 0], curve[:, 1],
                                left=float(curve[0, 1]), right=None)
    # beyond the last point: extend the last slope
    slope = (curve[-1, 1] - curve[-2, 1]) / (curve[-1, 0] - curve[-2, 0])
    high = discharge > curve[-1, 0]
    out[high] = curve[-1, 1] + slope * (discharge[high] - curve[-1, 0])
    return out


def _alerts(gauge_id: str, levels: FloatArray) -> dict[str, float] | None:
    stations = config.load("thresholds.yaml").get("river_gauges", {}).get("stations", {})
    station = stations.get(gauge_id)
    if not station:
        return None
    return {key.removesuffix("_m"): round(float((levels >= float(v)).mean()), 3)
            for key, v in station.items() if key.endswith("_m")}


def _pick_forecast(series: Sequence[tuple[str, float, float]], day: str) -> tuple[str, float, float]:
    if not series:
        raise LookupError("No discharge forecast available")
    if day == "peak":
        return max(series, key=lambda item: item[1])
    for item in series:
        if item[0][:10] == day[:10]:
            return item
    raise LookupError(f"No discharge forecast for {day}; available: {', '.join(i[0][:10] for i in series)}")


def _stage(change: Mapping[str, Any], data: ScenarioData, warnings: list[str]) -> Stage:
    cfg = _cfg("river_flood")
    gauges: Mapping[str, Any] = cfg["gauges"]
    gauge_id = change.get("gauge")
    if gauge_id is not None and gauge_id not in gauges:
        raise ValueError(f"Unknown gauge {gauge_id!r}; known: {', '.join(sorted(gauges))}")
    river = str(change.get("river") or (gauges[gauge_id]["river"] if gauge_id else "tevere"))
    stage_sigma = float(cfg["stage_sigma_m"])
    if "rise_m" in change:
        return Stage(river, float(change["rise_m"]), stage_sigma, "hypothetical")
    if "return_period_years" in change:
        return _return_period_stage(change, str(gauge_id or cfg["return_periods"]["default_gauge"]), warnings)
    if gauge_id is None:
        raise ValueError("river_flood change needs 'rise_m', or 'gauge' with 'level_m', 'discharge_m3s', "
                         "'forecast_day' (YYYY-MM-DD or 'peak') or 'live': true")
    gauge = gauges[gauge_id]
    normal = float(gauge["normal_level_m"])
    warnings.append(f"Ordinary level at {gauge_id} taken as {normal} m ({gauge['basis']}).")
    rng = np.random.default_rng(11)
    if "level_m" in change or change.get("live"):
        if change.get("live"):
            reading = data.river_levels.get(str(gauge_id))
            if reading is None:
                raise LookupError(f"No live reading for gauge {gauge_id}: the Region's real-time gauges need a login")
            level, sigma, kind = float(reading[0]), float(reading[1]), "real"
        else:
            level, sigma, kind = float(change["level_m"]), stage_sigma, "hypothetical"
        levels = rng.normal(level, max(sigma, 1e-6), 400)
        return Stage(river, level - normal, sigma, kind, str(gauge_id), impacts.quantiles(levels.tolist()),
                     None, _alerts(str(gauge_id), levels))
    if "discharge_m3s" in change or "forecast_day" in change:
        if "discharge_m3s" in change:
            q, q_sigma, kind = float(change["discharge_m3s"]), 0.1 * float(change["discharge_m3s"]), "hypothetical"
        else:
            day, q, q_sigma = _pick_forecast(data.river_discharge.get(str(gauge_id), []), str(change["forecast_day"]))
            kind = "estimated"
            warnings.append(f"Discharge {q:.0f} +/- {q_sigma:.0f} m3/s on {day[:10]} from the GloFAS forecast (estimated).")
        flows = np.clip(rng.normal(q, max(q_sigma, 1e-6), 400), 0.0, None)
        levels = _rating(gauge, flows)
        warnings.append(f"Discharge turned into a level with a rough rating curve ({gauge['basis']}).")
        rise = float(np.median(levels)) - normal
        sigma = math.hypot(float(np.std(levels)), stage_sigma)
        return Stage(river, rise, sigma, kind, str(gauge_id), impacts.quantiles(levels.tolist()), q,
                     _alerts(str(gauge_id), levels))
    raise ValueError("river_flood change needs 'rise_m', or 'gauge' with 'level_m', 'discharge_m3s', "
                     "'forecast_day' (YYYY-MM-DD or 'peak') or 'live': true")


def _return_period_stage(change: Mapping[str, Any], gauge_id: str, warnings: list[str]) -> Stage:
    """A named what-if: the flood expected once in T years, from the official discharge quantiles."""
    cfg = _cfg("river_flood")
    table: Mapping[str, Any] = cfg["return_periods"]["discharge_m3s"]
    years = int(change["return_period_years"])
    known = table.get(gauge_id) or {}
    if years not in {int(k) for k in known}:
        raise ValueError(f"return_period_years for {gauge_id} must be one of "
                         f"{', '.join(str(int(k)) for k in known) or 'none'}")
    q = float({int(k): v for k, v in known.items()}[years])
    inner = dict(change)
    inner.pop("return_period_years")
    stage = _stage({**inner, "gauge": gauge_id, "discharge_m3s": q}, ScenarioData(), warnings)
    label = f"{years}-year flood ({q:,.0f} m3/s at {gauge_id})"
    warnings.insert(0, f"Scenario, not a forecast: the {label}, the flood expected on average once in {years} "
                       f"years ({cfg['return_periods']['source']}).")
    return replace(stage, return_period_years=years, scenario=label)


def _official(grid: Grid, data: ScenarioData) -> dict[str, BoolArray] | None:
    cfg = _cfg("river_flood")
    path = layers.find(str(cfg["hazard_file"]))
    if path is None:
        return None
    by_class: dict[str, list[Mapping[str, Any]]] = {}
    for f in layers.read(path).get("features", []):
        cls = str((f.get("properties") or {}).get("hazard", "")).upper()
        if f.get("geometry") and cls:
            by_class.setdefault(cls, []).append(f["geometry"])
    return {cls: rasterize_mask(grid, geoms, all_touched=False) for cls, geoms in sorted(by_class.items())}


def _along_river_m(grid: Grid, river_mask: BoolArray, start: int) -> FloatArray:
    """Distance (m) along the river cells from ``start`` (flat index of a river cell); inf off the river."""
    from scipy.sparse import coo_matrix  # type: ignore[import-untyped]
    from scipy.sparse.csgraph import dijkstra  # type: ignore[import-untyped]

    cells = np.flatnonzero(river_mask.ravel())
    index = np.full(river_mask.size, -1, dtype=np.int64)
    index[cells] = np.arange(cells.size)
    rows, cols = np.divmod(cells, grid.shape[1])
    src: list[npt.NDArray[np.int64]] = []
    dst: list[npt.NDArray[np.int64]] = []
    wts: list[FloatArray] = []
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        r2, c2 = rows + dr, cols + dc
        ok = (r2 >= 0) & (r2 < grid.shape[0]) & (c2 >= 0) & (c2 < grid.shape[1])
        j = np.full(cells.size, -1, dtype=np.int64)
        j[ok] = index[r2[ok] * grid.shape[1] + c2[ok]]
        good = j >= 0
        src.append(np.flatnonzero(good))
        dst.append(j[good])
        wts.append(np.full(int(good.sum()), grid.cell * (math.sqrt(2.0) if dr and dc else 1.0)))
    i_all, j_all, w_all = np.concatenate(src), np.concatenate(dst), np.concatenate(wts)
    graph = coo_matrix((w_all, (i_all, j_all)), shape=(cells.size, cells.size)).tocsr()
    dist = dijkstra(graph, directed=False, indices=int(index[start]))
    out = np.full(river_mask.size, np.inf)
    out[cells] = dist
    return out.reshape(grid.shape)


def _sea_taper(grid: Grid, river: str, river_mask: BoolArray, nearest: npt.NDArray[np.int64],
               warnings: list[str]) -> FloatArray:
    """Share of the gauge's rise felt at each cell: 1 upstream of the gauge, falling to 0 at the mouth.

    The flood surface between the gauge and the sea is taken as a straight line along the river
    (distance from the mouth over the gauge's distance from the mouth).
    """
    cfg = _cfg("river_flood")
    spec = cfg["sea_taper"].get(river)
    if spec is None:
        return np.ones(grid.shape)
    gauge = cfg["gauges"][spec["gauge"]]
    pts_r, pts_c = grid.rowcol([float(gauge["lon"]), float(spec["mouth"][0])],
                               [float(gauge["lat"]), float(spec["mouth"][1])])
    if (pts_r < 0).any():
        return np.ones(grid.shape)
    from scipy import ndimage  # type: ignore[import-untyped]

    _, (ri, ci) = ndimage.distance_transform_edt(~river_mask, return_indices=True)
    snap = [int(ri[r, c] * grid.shape[1] + ci[r, c]) for r, c in zip(pts_r.tolist(), pts_c.tolist())]
    along = _along_river_m(grid, river_mask, snap[1])
    d_gauge = float(along.ravel()[snap[0]])
    if not math.isfinite(d_gauge) or d_gauge <= 0:
        return np.ones(grid.shape)
    d_cell = along.ravel()[nearest].reshape(grid.shape)
    warnings.append(f"Towards the sea the rise shrinks linearly along the river (full at {spec['gauge']}, "
                    f"none at the mouth, {d_gauge / 1000:.0f} km downstream; validated against PGRA maps).")
    out: FloatArray = np.clip(np.nan_to_num(d_cell / d_gauge, nan=1.0, posinf=1.0), 0.0, 1.0)
    return out


def _normal_level(river: str) -> float:
    cfg = _cfg("river_flood")
    for gauge in cfg["gauges"].values():
        if gauge["river"] == river:
            return float(gauge["normal_level_m"])
    return 0.0


def _defended_river(grid: Grid, river: str, river_mask: BoolArray, normal: float) -> tuple[FloatArray, list[str]]:
    """Freeboard (m above ordinary water) of each walled river cell; NaN where the bank is not walled.

    Measured LiDAR crests (WS2, crest_m - water_m per point, same datum so the geoid offset cancels)
    are used where they exist; elsewhere in the walled reach, the single design crest from config.
    """
    freeboard = np.full(grid.shape, np.nan)
    notes: list[str] = []
    cfg = _cfg("river_flood")
    for name, d in cfg["defences"].items():
        if d["river"] != river:
            continue
        w, s_, e, n = (float(v) for v in d["reach_bbox"])
        rows, cols = grid.rowcol([w, e], [n, s_])
        if rows.min() < 0:
            continue
        reach = np.zeros(grid.shape, dtype=bool)
        reach[rows[0]:rows[1] + 1, cols[0]:cols[1] + 1] = True
        cells = river_mask & reach
        freeboard[cells] = float(d["crest_level_m"]) - normal
        measured = _measured_crests(grid, cells, str(cfg["crests_file"]), float(cfg["crest_search_m"]))
        if measured is not None:
            got = ~np.isnan(measured)
            freeboard[got] = measured[got]
            notes.append(f"Defence '{name}': measured LiDAR wall crests on {int(got.sum())} river cells (WS2, real, "
                         f"sigma 0.3 m); design crest {d['crest_level_m']} m on {d['gauge']} elsewhere in the reach.")
        else:
            notes.append(f"Defence '{name}': the walled reach only spills above {d['crest_level_m']} m at "
                         f"{d['gauge']} (design crest, C=75); below that, water reaches land only from unwalled reaches.")
    return freeboard, notes


def _measured_crests(grid: Grid, cells: BoolArray, file_name: str, search_m: float) -> FloatArray | None:
    """Lowest measured freeboard (crest - water) within ``search_m`` of each river cell."""
    path = layers.find(file_name, dirs=config.value(config.load("scenarios.yaml")["terrain"], "search_dirs"))
    if path is None:
        return None
    pts = [(float(f["geometry"]["coordinates"][0]), float(f["geometry"]["coordinates"][1]),
            float(f["properties"]["crest_m"]) - float(f["properties"]["water_m"]))
           for f in layers.read(path).get("features", [])
           if f.get("geometry") and (f.get("properties") or {}).get("crest_m") is not None
           and (f.get("properties") or {}).get("wall_detected", True)]
    if not pts:
        return None
    rows, cols = grid.rowcol([p[0] for p in pts], [p[1] for p in pts])
    out = np.full(grid.shape, np.nan)
    rr, cc = np.nonzero(cells)
    radius = search_m / grid.cell
    for r_, c_ in zip(rr.tolist(), cc.tolist()):
        d = np.hypot(rows - r_, cols - c_)
        ok = (d <= radius) & (rows >= 0)
        if ok.any():
            out[r_, c_] = min(p[2] for p, flag in zip(pts, ok.tolist()) if flag)
    return out


def _channel(river_mask: BoolArray, seeds: BoolArray) -> BoolArray:
    """River cells that cannot spill (behind walls): water may not travel along them to the floodplain."""
    out: BoolArray = river_mask & ~seeds
    return out


def run_river_flood(area: Area, change: Mapping[str, Any], data: ScenarioData) -> dict[str, Any]:
    warnings: list[str] = []
    try:
        stage = _stage(change, data, warnings)
    except LookupError as exc:
        return _not_available(str(exc), {"river_level": "not_available"})
    river, rise, stage_sigma, level_kind = stage.river, stage.rise_m, stage.sigma_m, stage.kind
    cfg = _cfg("river_flood")
    grid = terrain_for(None, data)
    river_mask, river_kind = _river_cells(grid, river, data, warnings)
    if not river_mask.any():
        return _not_available(f"No river cells for '{river}' inside this area.", {"rivers": "not_available"})
    hand, nearest = hydro.height_above_river(grid.z, river_mask)
    from scipy import ndimage

    distance = ndimage.distance_transform_edt(~river_mask) * grid.cell
    near = (distance <= float(cfg["max_distance_from_river_m"])) & ~np.isnan(grid.z)
    in_area = _area_mask(grid, area)
    sigma = math.hypot(float(grid.source.get("vertical_sigma_m", 2.0)), stage_sigma)

    z95 = 1.6448536269514722
    normal = _normal_level(river)
    freeboard, defence_notes = _defended_river(grid, river, river_mask, normal)
    taper = _sea_taper(grid, river, river_mask, nearest, warnings)

    def extent(stage: float) -> BoolArray:
        # a walled river cell holds while the local rise stays below its freeboard
        holds = ~np.isnan(freeboard) & (stage * taper < np.nan_to_num(freeboard, nan=np.inf))
        seeds = river_mask & ~holds
        holding = _channel(river_mask, seeds)
        # land whose nearest river cell is behind holding walls stays dry: HAND has no water slope,
        # so without this rule the upstream floodplain would 'flow' behind the walls at the same height
        protected = holding.ravel()[nearest].reshape(grid.shape)
        wet = near & (np.nan_to_num(hand, nan=np.inf) <= stage * taper) & ~protected
        return hydro.connected_to(wet & ~holding, seeds) & in_area | (river_mask & in_area)

    footprints = {"p5": extent(rise - z95 * sigma), "p50": extent(rise), "p95": extent(rise + z95 * sigma)}
    probability = np.where(near & in_area, _normal_cdf((rise * taper - np.nan_to_num(hand, nan=1e6)) / sigma), 0.0)
    probability = np.where(footprints["p95"] & ~river_mask, probability, 0.0)
    baseline = river_mask & in_area  # ordinary flow: the river channel only
    for k in footprints:
        footprints[k] = footprints[k] & ~river_mask
    warnings += defence_notes

    result: dict[str, Any] = {
        "model": "height_above_nearest_river",
        "calibration": str(_cfg("river_flood")["calibration"]),
        "river": river, "rise_m": round(rise, 2), "sigma_m": round(sigma, 2),
        "gauge": stage.gauge, "gauge_level_m": stage.level_m, "discharge_m3s": stage.discharge_m3s,
        "alert_probability": stage.alerts,
        "return_period_years": stage.return_period_years, "scenario": stage.scenario,
        "flooded_km2": {k: round(float(m.sum()) * grid.cell_area / 1e6, 3) for k, m in footprints.items()},
        "baseline_flooded_km2": round(float(baseline.sum()) * grid.cell_area / 1e6, 3),
        "footprint_p50": mask_to_geojson(grid, footprints["p50"]),
        "footprint_p95": mask_to_geojson(grid, footprints["p95"]),
    }
    people = impacts.residents(grid, data, {**footprints, "baseline": baseline})
    result["residents"] = people
    result["sensitive_sites"] = impacts.sensitive_sites(grid, probability, 0.05)
    official = _official(grid, data)
    if official is not None:
        result["official_hazard"] = {
            cls: {"km2": round(float((m & in_area).sum()) * grid.cell_area / 1e6, 3),
                  "residents": (impacts.residents(grid, data, {cls: m & in_area}) or {}).get(cls)}
            for cls, m in official.items()}
    kinds = {"terrain": str(grid.source.get("kind", "estimated")), "rivers": river_kind,
             "river_level": level_kind, "census": "real" if people is not None else "not_available",
             "sensitive_sites": "real" if result["sensitive_sites"] is not None else "not_available",
             "official_hazard": "real" if official is not None else "not_available"}
    if people is None:
        warnings.append("Census sections not available: residents not counted.")
    if official is None:  # noqa: SIM102
        warnings.append("Official PGRA flood hazard areas not loaded yet: no comparison with the official maps.")
    warnings.append(str(cfg["walls_note"]))
    warnings.append(f"Terrain {grid.source.get('id')}: vertical error about {grid.source.get('vertical_sigma_m')} m; "
                    "the edge of the flood is a probability, not a line.")
    return {"result": result, "data_kinds": kinds, "sources": _terrain_source(grid), "synthetic": False,
            "warnings": warnings}


# --------------------------------------------------------------------------- rain


def _impervious(grid: Grid, warnings: list[str]) -> tuple[FloatArray, str]:
    cfg = _cfg("rain_flood")
    path = layers.find(str(cfg["impervious_file"]))
    if path is not None:
        sampled = load_dtm_like(grid, str(path))
        return np.clip(np.nan_to_num(sampled, nan=0.0) / 100.0, 0.0, 1.0), "real"
    fallback = cfg["impervious_fallback"]
    urban_path = layers.find(str(cfg["urban_file"]))
    if urban_path is None:
        warnings.append("No imperviousness or urban-area layer: one sealed share is used everywhere (assumption).")
        return np.full(grid.shape, float(fallback["urban"])), "estimated"
    urban = rasterize_mask(grid, [f["geometry"] for f in layers.read(urban_path).get("features", [])
                                  if f.get("geometry")], all_touched=False)
    warnings.append("Imperviousness raster not loaded yet: sealed share set from the PTPR urbanised areas (assumption).")
    return np.where(urban, float(fallback["urban"]), float(fallback["other"])), "estimated"


def load_dtm_like(grid: Grid, path: str) -> FloatArray:
    """Resample any raster onto ``grid`` (average)."""
    import rasterio  # type: ignore[import-untyped]
    from rasterio.warp import Resampling, reproject  # type: ignore[import-untyped]

    from twin.scenarios.terrain import CRS

    dst = np.full(grid.shape, np.nan)
    with rasterio.open(path) as src:
        reproject(rasterio.band(src, 1), dst, dst_transform=grid.transform(), dst_crs=CRS, dst_nodata=np.nan,
                  src_nodata=src.nodata, resampling=Resampling.average)
    return dst


def _rain_field(grid: Grid, change: Mapping[str, Any], data: ScenarioData) -> tuple[FloatArray, float, str]:
    """(rain depth mm per cell, duration h, kind)."""
    duration = float(change.get("duration_h", 1.0))
    if duration <= 0:
        raise ValueError("duration_h must be positive")
    if "rain_mm" in change:
        rain = float(change["rain_mm"])
        if rain < 0:
            raise ValueError("rain_mm cannot be negative")
        return np.full(grid.shape, rain), duration, "hypothetical"
    if change.get("source") in ("radar", "forecast"):
        obs = data.rain_mm.get(str(change["source"]))
        if not obs:
            raise LookupError(f"No {change['source']} rainfall available")
        lons, lats, mm = zip(*obs)
        rows, cols = grid.rowcol(lons, lats)
        from scipy import ndimage

        seeds = np.zeros(grid.shape, dtype=bool)
        values = np.zeros(grid.shape)
        ok = rows >= 0
        seeds[rows[ok], cols[ok]] = True
        values[rows[ok], cols[ok]] = np.asarray(mm)[ok]
        if not seeds.any():
            raise LookupError(f"No {change['source']} rainfall cell inside this area")
        _, (ri, ci) = ndimage.distance_transform_edt(~seeds, return_indices=True)
        kind = "real" if change["source"] == "radar" else "estimated"
        return values[ri, ci], duration, kind
    raise ValueError("rain_flood change needs 'rain_mm' (and 'duration_h'), or 'source': 'radar' | 'forecast'")


def run_rain_flood(area: Area, change: Mapping[str, Any], data: ScenarioData) -> dict[str, Any]:
    warnings: list[str] = []
    cfg = _cfg("rain_flood")
    grid = terrain_for(area, data, margin_m=500.0)
    try:
        rain, duration, rain_kind = _rain_field(grid, change, data)
    except LookupError as exc:
        return _not_available(str(exc), {"rain": "not_available"})
    in_area = _area_mask(grid, area)
    sealed, sealed_kind = _impervious(grid, warnings)

    dep = hydro.depressions(grid.z, float(cfg["min_depth_m"]))
    receiver = hydro.steepest_descent(grid.z, grid.cell)
    end = hydro.terminal(receiver)
    pit_label = dep.label.ravel()[end]  # depression each cell finally drains into (0 = flows away)

    labels = dep.label.ravel()
    z = grid.z.ravel()
    spill = dep.spill.ravel()
    order = np.argsort(labels, kind="stable")
    bounds = np.searchsorted(labels[order], np.arange(1, dep.count + 2))
    hollows: list[dict[str, Any]] = []
    for k in range(1, dep.count + 1):
        idx = order[bounds[k - 1]:bounds[k]]
        if idx.size == 0:
            continue
        zs = np.sort(z[idx])
        level = float(spill[idx].max())
        capacity = grid.cell_area * float((level - zs).clip(min=0).sum())
        if capacity < float(cfg["min_capacity_m3"]):
            continue
        n = np.arange(zs.size)
        breaks = grid.cell_area * (n * zs - np.concatenate([[0.0], np.cumsum(zs)[:-1]]))
        hollows.append({"label": k, "cells": idx, "zs": zs, "breaks": breaks, "level": level,
                        "capacity": capacity})
    channels = np.nan_to_num(_accumulation(grid), nan=0.0) >= float(cfg["channel_min_area_km2"]) * 1e6
    channel_flat = channels.ravel()
    before = len(hollows)
    hollows = [h for h in hollows if not channel_flat[h["cells"]].any()]
    if before > len(hollows):
        warnings.append(f"{before - len(hollows)} hollows on river or stream beds were left to the river scenario.")

    rng = np.random.default_rng(int(cfg["seed"]))
    members = int(cfg["members"])
    rel = float(cfg["rain_relative_sigma"])
    sigma_rain = math.sqrt(math.log(1 + rel * rel))
    infil_cfg = config.load("scenarios.yaml")["rain_flood"]["infiltration_mm_h"]
    flat_rain = rain.ravel()
    flat_sealed = np.nan_to_num(sealed.ravel())
    valid = ~np.isnan(z)

    # sewers: Rome design rules on the terrain, outfalls, and the river when one is given
    net = sewer.network(grid, sealed, channels)
    stage: Stage | None = None
    if isinstance(change.get("river"), Mapping):
        try:
            stage = _stage(dict(change["river"]), data, warnings)
        except LookupError as exc:
            return _not_available(str(exc), {"river_level": "not_available"})
    outfalls = sewer.load_outfalls(stage.river if stage is not None else None)
    sink_outfall = sewer.outfall_sinks(grid, net, outfalls or [])
    served = sorted({int(k) for k in sink_outfall[sink_outfall >= 0].tolist()})
    blocked = np.zeros((members, len(outfalls or [])), dtype=bool)
    if stage is not None and outfalls:
        rises = np.random.default_rng(int(cfg["seed"]) + 1).normal(stage.rise_m, max(stage.sigma_m, 1e-6), members)
        taper = sewer.outfall_taper(grid, outfalls, _normal_level(stage.river))
        blocked = sewer.blocked_outfalls(rises, taper, np.random.default_rng(int(cfg["seed"]) + 2))
    eff = sewer.efficiency(members, rng)
    inlet = sewer.inlet_rate_mm_h(grid.cell_area)
    pipe_m3 = sewer.rain_capacity_m3(net, grid.cell_area, duration)
    r_mult = np.exp(rng.normal(-sigma_rain ** 2 / 2, sigma_rain, members))
    infil = float(infil_cfg["value"]) * np.exp(rng.normal(0.0, float(infil_cfg["sigma_ln"]), members))

    depth = np.zeros((members, len(hollows)))
    wet_area = np.zeros((members, len(hollows)))
    overflow = np.zeros((members, len(hollows)))
    surcharge_total = np.zeros(members)
    surcharge_mean = np.zeros(z.size)
    surcharge_seen = np.zeros(z.size)
    in_area_flat = in_area.ravel()
    chunk = 8
    for start in range(0, members, chunk):
        ms = list(range(start, min(start + chunk, members)))
        caught = np.zeros((len(ms), z.size))
        pipe_cap = np.zeros((len(ms), z.size))
        surface = np.zeros((len(ms), z.size))
        factor = sewer.capacity_factor(net, sink_outfall, blocked[ms])
        for k, m in enumerate(ms):
            r = flat_rain * r_mult[m]
            into_drains = np.minimum(r, eff[m] * inlet * duration)
            caught[k] = np.where(valid, flat_sealed * into_drains / 1000.0 * grid.cell_area, 0.0)
            runoff_mm = flat_sealed * (r - into_drains) + (1 - flat_sealed) * np.clip(r - infil[m] * duration, 0, None)
            surface[k] = np.where(valid, runoff_mm / 1000.0 * grid.cell_area, 0.0)
            pipe_cap[k] = eff[m] * pipe_m3 * factor[k]
        surcharge, _ = sewer.route(net.receiver, net.order, net.sink, caught, pipe_cap)
        surcharge_mean += surcharge.sum(axis=0) / members
        surcharge_seen += (surcharge > 1.0).sum(axis=0) / members
        for k, m in enumerate(ms):
            surcharge_total[m] = float(surcharge[k][in_area_flat].sum())
            to_pits = surface[k] + surcharge[k]
            volume = np.bincount(pit_label[valid], weights=to_pits[valid], minlength=dep.count + 1)
            for i, h in enumerate(hollows):
                v = float(volume[h["label"]])
                if v <= 0:
                    continue
                if v >= h["capacity"]:
                    lvl = h["level"]
                    overflow[m, i] = v - h["capacity"]
                else:
                    # between two breakpoints the volume grows linearly with the level
                    j = int(np.searchsorted(h["breaks"], v, side="right")) - 1
                    lvl = float(h["zs"][j] + (v - h["breaks"][j]) / (grid.cell_area * (j + 1)))
                depth[m, i] = lvl - float(h["zs"][0])
                wet_area[m, i] = float((h["zs"] < lvl).sum()) * grid.cell_area

    wet_p50 = np.zeros(grid.shape, dtype=bool)
    probability = np.zeros(grid.shape)
    hotspots: list[dict[str, Any]] = []
    under = _underpasses()
    for i, h in enumerate(hollows):
        q = impacts.quantiles(depth[:, i].tolist())
        if q["p95"] <= 0:
            continue
        deepest = h["cells"][np.argmin(z[h["cells"]])]
        r_, c_ = divmod(int(deepest), grid.shape[1])
        if not in_area[r_, c_]:
            continue
        p50_level = float(h["zs"][0]) + q["p50"]
        cells_r, cells_c = np.divmod(h["cells"], grid.shape[1])
        wet_cells = z[h["cells"]] < p50_level
        wet_p50[cells_r[wet_cells], cells_c[wet_cells]] = True
        levels = depth[:, i] + float(h["zs"][0])
        probability[cells_r, cells_c] = (levels[:, None] > z[h["cells"]][None, :]).mean(axis=0)
        lons, lats = grid.lonlat(np.asarray([r_], dtype=np.int64), np.asarray([c_], dtype=np.int64))
        hotspots.append({"lon": round(lons[0], 6), "lat": round(lats[0], 6),
                         "max_depth_m": q, "flooded_m2": impacts.quantiles(wet_area[:, i].tolist()),
                         "overflow_m3_p50": round(float(np.percentile(overflow[:, i], 50)), 1),
                         "probability_over_30cm": round(float((depth[:, i] > 0.3).mean()), 3),
                         "check": ("deep hollow: may be a railway cutting, quarry or terrain error"
                                   if float(h["level"] - h["zs"][0]) > float(cfg["deep_hollow_m"]) else None),
                         "underpasses": _near(under, lons[0], lats[0], 150.0)})
    hotspots.sort(key=lambda h: -h["max_depth_m"]["p50"])
    ts_cfg = cfg["trouble_spots"]
    call_outs = susceptibility.load_call_outs(str(ts_cfg["call_out_file"]))
    spots = susceptibility.trouble_spots(grid, in_area, sealed, call_outs, ts_cfg)
    for h in hotspots:
        hr, hc = grid.rowcol([h["lon"]], [h["lat"]])
        h["low_ground_m"] = round(float(spots["low_ground"][hr[0], hc[0]]), 1) if hr[0] >= 0 else None
        h["past_call_outs"] = (int(spots["past"][hr[0], hc[0]]) if spots["past"] is not None and hr[0] >= 0
                               else None)
    wet_p50 &= in_area
    probability = np.where(in_area, probability, 0.0)
    totals = depth.sum(axis=1)
    result: dict[str, Any] = {
        "model": "fill_and_spill_no_cascade", "calibration": str(cfg["calibration"]),
        "rain_mm_mean": round(float(np.nanmean(np.where(in_area, rain, np.nan))), 1), "duration_h": duration,
        "members": members, "hollows_modelled": len(hollows),
        "hotspots_count": len(hotspots), "hotspots": hotspots[: int(cfg["hotspots_listed"])],
        "flooded_km2_p50": round(float(wet_p50.sum()) * grid.cell_area / 1e6, 3),
        "total_depth_index": impacts.quantiles(totals.tolist()),
        "footprint_p50": mask_to_geojson(grid, wet_p50),
        "trouble_spots": {"spots": spots["spots"], "method": str(ts_cfg["method"])},
    }
    result["sewer"] = _sewer_summary(grid, in_area_flat, eff, inlet, served, blocked, outfalls,
                                     surcharge_total, surcharge_mean, surcharge_seen)
    result["residents"] = impacts.residents(grid, data, {"p50": wet_p50})
    result["sensitive_sites"] = impacts.sensitive_sites(grid, probability, 0.2)
    kinds = {"terrain": str(grid.source.get("kind", "estimated")), "rain": rain_kind, "imperviousness": sealed_kind,
             "drainage": "estimated", "outfalls": "real" if outfalls is not None else "not_available", "census": "real" if result["residents"] is not None else "not_available",
             "sensitive_sites": "real" if result["sensitive_sites"] is not None else "not_available",
             "call_out_history": spots["history"]}
    warnings += [
        "Sewer capacity follows Rome's design rules on the terrain (Comune di Roma 2000) times an efficiency "
        "assumption (C=35); the real pipe map is not open, so pipes are taken to follow the terrain.",
        "Water that overflows a full hollow is not passed on downhill (no cascade), so downstream hotspots can be understated.",
        f"Terrain at {grid.cell:g} m resolves streets and squares, not single underpasses: treat hotspots as areas to check.",
    ]
    if under is None:
        warnings.append("Underpass layer not loaded yet: hotspots are not matched to underpasses.")
    warnings.append("Which street floods: the pond-and-sewer map has weak street-level skill against 10 years of "
                    "real call-outs; use 'trouble_spots' (low ground plus past call-outs) to choose where to send "
                    "pumps and patrols first.")
    if call_outs is None:
        warnings.append("Civil-protection call-out log not loaded: trouble spots use low ground only.")
    if outfalls is None:
        warnings.append("Sewer outfall layer not loaded (scripts/fetch_sewer_layers.py): river backflow is left out.")
    if stage is not None:
        kinds["river_level"] = stage.kind
        warnings.append(f"River {stage.river} raised {stage.rise_m:.2f} m (sigma {stage.sigma_m:.2f} m): outfalls under "
                        "water keep only part of their basin's capacity (assumption, config/scenarios.yaml).")
    return {"result": result, "data_kinds": kinds, "sources": _terrain_source(grid), "synthetic": False,
            "warnings": warnings}


def _sewer_summary(grid: Grid, in_area: npt.NDArray[np.bool_], eff: FloatArray, inlet: float, served: list[int],
                   blocked: npt.NDArray[np.bool_], outfalls: list[sewer.Outfall] | None, surcharge_total: FloatArray,
                   surcharge_mean: FloatArray, surcharge_seen: FloatArray) -> dict[str, Any]:
    n_blocked = blocked[:, served].sum(axis=1) if served else np.zeros(blocked.shape[0])
    top = np.argsort(-np.where(in_area, surcharge_mean, 0.0))[:15]
    points: list[dict[str, Any]] = []
    for i in top.tolist():
        if surcharge_mean[i] <= 1.0 or not in_area[i]:
            continue
        r, c = divmod(i, grid.shape[1])
        lons, lats = grid.lonlat(np.asarray([r], dtype=np.int64), np.asarray([c], dtype=np.int64))
        points.append({"lon": round(lons[0], 6), "lat": round(lats[0], 6), "mean_m3": round(float(surcharge_mean[i]), 1),
                       "probability": round(float(surcharge_seen[i]), 3)})
    return {
        "model": "rome_design_rules",
        "efficiency": impacts.quantiles(eff.tolist()),
        "street_drain_rate_mm_h": impacts.quantiles((eff * inlet).tolist()),
        "outfalls_considered": len(served),
        "outfalls_blocked": impacts.quantiles(n_blocked.astype(float).tolist()),
        "blocked": sewer.summary(outfalls or [], blocked, served),
        "surcharge_m3": impacts.quantiles(surcharge_total.tolist()),
        "surcharge_points": points,
        "surcharge_map_p50": mask_to_geojson(grid, (surcharge_seen >= 0.5).reshape(grid.shape)
                                             & in_area.reshape(grid.shape)),
    }


def _underpasses() -> list[tuple[float, float, str]] | None:
    path = layers.find(str(_cfg("rain_flood")["underpasses_file"]))
    if path is None:
        return None
    out: list[tuple[float, float, str]] = []
    for f in layers.read(path).get("features", []):
        g = f.get("geometry") or {}
        coords = g.get("coordinates")
        if not coords:
            continue
        pts = [coords] if g.get("type") == "Point" else (coords if g.get("type") == "LineString" else [])
        if pts:
            mid = pts[len(pts) // 2]
            out.append((float(mid[0]), float(mid[1]), str((f.get("properties") or {}).get("name") or "")))
    return out


def _near(points: list[tuple[float, float, str]] | None, lon: float, lat: float, radius_m: float) -> list[str] | None:
    if points is None:
        return None
    k = 111_195.0
    c = math.cos(math.radians(lat))
    return sorted({name or "unnamed" for plon, plat, name in points
                   if math.hypot((plon - lon) * k * c, (plat - lat) * k) <= radius_m})[:5]


def _terrain_source(grid: Grid) -> list[dict[str, Any]]:
    src = {k: v for k, v in grid.source.items() if k in ("id", "file", "url")}
    return [src] if src else []


def _not_available(reason: str, kinds: Mapping[str, str]) -> dict[str, Any]:
    return {"result": {"status": "not_available", "reason": reason}, "data_kinds": dict(kinds), "sources": [],
            "synthetic": False, "warnings": [reason]}
