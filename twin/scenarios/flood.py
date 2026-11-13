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
from functools import lru_cache
from typing import Any, Mapping

import numpy as np

from twin.providers.base import BBox
from twin.scenarios import config, impacts, layers
from twin.scenarios.area import Area
from twin.scenarios.data import ScenarioData
from twin.scenarios import hydro
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
        return _cached_dtm(bbox_city, float(config.value(config.load("scenarios.yaml")["terrain"], "cell_m")))  # type: ignore[arg-type]
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


def _rise(change: Mapping[str, Any], data: ScenarioData, warnings: list[str]) -> tuple[str, float, float, str]:
    """(river, rise above ordinary level in m, sigma m, kind of the level)."""
    cfg = _cfg("river_flood")
    gauges: Mapping[str, Any] = cfg["gauges"]
    gauge = change.get("gauge")
    if gauge is not None and gauge not in gauges:
        raise ValueError(f"Unknown gauge {gauge!r}; known: {', '.join(sorted(gauges))}")
    river = str(change.get("river") or (gauges[gauge]["river"] if gauge else "tevere"))
    if "rise_m" in change:
        return river, float(change["rise_m"]), float(cfg["stage_sigma_m"]), "hypothetical"
    if gauge is None:
        raise ValueError("river_flood change needs 'rise_m', or 'gauge' with 'level_m' or 'live': true")
    normal = float(gauges[gauge]["normal_level_m"])
    warnings.append(f"Ordinary level at {gauge} taken as {normal} m ({gauges[gauge]['basis']}).")
    if "level_m" in change:
        return river, float(change["level_m"]) - normal, float(cfg["stage_sigma_m"]), "hypothetical"
    if change.get("live"):
        reading = data.river_levels.get(str(gauge))
        if reading is None:
            raise LookupError(f"No live reading for gauge {gauge}")
        return river, float(reading[0]) - normal, float(reading[1]), "real"
    raise ValueError("river_flood change needs 'rise_m', or 'gauge' with 'level_m' or 'live': true")


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


def run_river_flood(area: Area, change: Mapping[str, Any], data: ScenarioData) -> dict[str, Any]:
    warnings: list[str] = []
    try:
        river, rise, stage_sigma, level_kind = _rise(change, data, warnings)
    except LookupError as exc:
        return _not_available(str(exc), {"river_level": "not_available"})
    cfg = _cfg("river_flood")
    grid = terrain_for(None, data)
    river_mask, river_kind = _river_cells(grid, river, data, warnings)
    if not river_mask.any():
        return _not_available(f"No river cells for '{river}' inside this area.", {"rivers": "not_available"})
    hand, _ = hydro.height_above_river(grid.z, river_mask)
    from scipy import ndimage  # type: ignore[import-untyped]

    distance = ndimage.distance_transform_edt(~river_mask) * grid.cell
    near = (distance <= float(cfg["max_distance_from_river_m"])) & ~np.isnan(grid.z)
    in_area = _area_mask(grid, area)
    sigma = math.hypot(float(grid.source.get("vertical_sigma_m", 2.0)), stage_sigma)

    def extent(stage: float) -> BoolArray:
        wet = near & (np.nan_to_num(hand, nan=np.inf) <= stage)
        return hydro.connected_to(wet, river_mask) & in_area

    z95 = 1.6448536269514722
    footprints = {"p5": extent(rise - z95 * sigma), "p50": extent(rise), "p95": extent(rise + z95 * sigma)}
    probability = np.where(near & in_area, _normal_cdf((rise - np.nan_to_num(hand, nan=1e6)) / sigma), 0.0)
    probability = np.where(footprints["p95"], probability, 0.0)
    baseline = extent(0.0)  # ordinary flow: the river itself and the ground at its level

    result: dict[str, Any] = {
        "model": "height_above_nearest_river",
        "calibration": "uncalibrated",
        "river": river, "rise_m": round(rise, 2), "sigma_m": round(sigma, 2),
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
    if official is None:
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
    keep = {h["label"]: i for i, h in enumerate(hollows)}

    rng = np.random.default_rng(int(cfg["seed"]))
    members = int(cfg["members"])
    rel = float(cfg["rain_relative_sigma"])
    sigma_rain = math.sqrt(math.log(1 + rel * rel))
    drain_cfg, infil_cfg = config.load("scenarios.yaml")["rain_flood"]["drainage_capacity_mm_h"], \
        config.load("scenarios.yaml")["rain_flood"]["infiltration_mm_h"]
    flat_rain = rain.ravel()
    flat_sealed = sealed.ravel()
    valid = ~np.isnan(z)
    depth = np.zeros((members, len(hollows)))
    wet_area = np.zeros((members, len(hollows)))
    overflow = np.zeros((members, len(hollows)))
    for m in range(members):
        r_mult = math.exp(rng.normal(-sigma_rain ** 2 / 2, sigma_rain))
        drain = float(drain_cfg["value"]) * math.exp(rng.normal(0.0, float(drain_cfg["sigma_ln"])))
        infil = float(infil_cfg["value"]) * math.exp(rng.normal(0.0, float(infil_cfg["sigma_ln"])))
        r = flat_rain * r_mult
        runoff_mm = flat_sealed * np.clip(r - drain * duration, 0, None) + \
            (1 - flat_sealed) * np.clip(r - infil * duration, 0, None)
        volume = np.bincount(pit_label[valid], weights=runoff_mm[valid] / 1000.0 * grid.cell_area,
                             minlength=dep.count + 1)
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
                         "underpasses": _near(under, lons[0], lats[0], 150.0)})
    hotspots.sort(key=lambda h: -h["max_depth_m"]["p50"])
    wet_p50 &= in_area
    probability = np.where(in_area, probability, 0.0)
    totals = depth.sum(axis=1)
    result: dict[str, Any] = {
        "model": "fill_and_spill_no_cascade", "calibration": "uncalibrated",
        "rain_mm_mean": round(float(np.nanmean(np.where(in_area, rain, np.nan))), 1), "duration_h": duration,
        "members": members, "hollows_modelled": len(hollows),
        "hotspots_count": len(hotspots), "hotspots": hotspots[: int(cfg["hotspots_listed"])],
        "flooded_km2_p50": round(float(wet_p50.sum()) * grid.cell_area / 1e6, 3),
        "total_depth_index": impacts.quantiles(totals.tolist()),
        "footprint_p50": mask_to_geojson(grid, wet_p50),
    }
    result["residents"] = impacts.residents(grid, data, {"p50": wet_p50})
    result["sensitive_sites"] = impacts.sensitive_sites(grid, probability, 0.2)
    kinds = {"terrain": str(grid.source.get("kind", "estimated")), "rain": rain_kind, "imperviousness": sealed_kind,
             "drainage": "estimated", "census": "real" if result["residents"] is not None else "not_available",
             "sensitive_sites": "real" if result["sensitive_sites"] is not None else "not_available"}
    warnings += [
        "Drain capacity and infiltration are assumptions (config/scenarios.yaml); no sewer network data is open.",
        "Water that overflows a full hollow is not passed on downhill (no cascade), so downstream hotspots can be understated.",
        f"Terrain at {grid.cell:g} m resolves streets and squares, not single underpasses: treat hotspots as areas to check.",
    ]
    if under is None:
        warnings.append("Underpass layer not loaded yet: hotspots are not matched to underpasses.")
    return {"result": result, "data_kinds": kinds, "sources": _terrain_source(grid), "synthetic": False,
            "warnings": warnings}


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
