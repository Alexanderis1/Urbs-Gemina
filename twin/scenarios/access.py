"""Emergency access: how many residents emergency services can reach within their target time.

Shortest travel times on the district road network (SUMO network built from
OpenStreetMap) from every fire station, police station or emergency hospital,
before and after a change: closed roads, a closed area, or the flood footprint
of a river or rain scenario. Speeds are the road limits times an emergency
factor with an uncertainty range. Targets come from config/thresholds.yaml.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from twin.scenarios import config, impacts, layers
from twin.scenarios.area import Area
from twin.scenarios.data import ScenarioData
from twin.scenarios.exposure import load_census
from twin.scenarios.geometry import centroid, contains
from twin.scenarios.traffic import _closed_edges, network_for_area

M_PER_DEG = 111_195.0
TARGET_KEYS = {"ambulance": "ambulance_urban_min", "fire": "fire_min", "police": "police_min"}


def _cfg() -> dict[str, Any]:
    raw: dict[str, Any] = config.load("scenarios.yaml")["emergency_access"]
    return {k: config.value(raw, k) for k in raw}


def read_graph(net: Path) -> tuple[list[str], list[tuple[str, int, int, float, float]], np.ndarray, np.ndarray]:
    """Junction ids, edges (id, from, to, length m, speed m/s), junction lon and lat."""
    from rasterio.crs import CRS  # type: ignore[import-untyped]
    from rasterio.warp import transform  # type: ignore[import-untyped]

    root = ET.parse(net).getroot()
    loc = root.find("location")
    proj = loc.get("projParameter", "!") if loc is not None else "!"
    if loc is None or proj == "!":
        raise ValueError("this road network has no geographic projection")
    ox, oy = (float(v) for v in loc.get("netOffset", "0,0").split(","))
    junctions: list[str] = []
    index: dict[str, int] = {}
    xs: list[float] = []
    ys: list[float] = []
    for j in root.iter("junction"):
        if j.get("type") == "internal":
            continue
        index[str(j.get("id"))] = len(junctions)
        junctions.append(str(j.get("id")))
        xs.append(float(j.get("x", 0)) - ox)
        ys.append(float(j.get("y", 0)) - oy)
    lon, lat = transform(CRS.from_proj4(proj), "EPSG:4326", xs, ys) if xs else ([], [])
    edges: list[tuple[str, int, int, float, float]] = []
    for e in root.iter("edge"):
        if e.get("function") == "internal" or e.get("from") not in index or e.get("to") not in index:
            continue
        lane = e.find("lane")
        if lane is None:
            continue
        allow, disallow = lane.get("allow", ""), lane.get("disallow", "")
        if (allow and "emergency" not in allow and "passenger" not in allow) or "emergency" in disallow.split():
            continue
        edges.append((str(e.get("id")), index[str(e.get("from"))], index[str(e.get("to"))],
                      float(lane.get("length", 0)), float(lane.get("speed", 13.9))))
    return junctions, edges, np.asarray(lon, dtype=np.float64), np.asarray(lat, dtype=np.float64)


def _times(n: int, edges: Sequence[tuple[str, int, int, float, float]], closed: set[str],
           sources: Sequence[int], cap_m_s: float = math.inf,
           start_s: Sequence[float] | None = None) -> np.ndarray:
    """Fastest time (s) from any source junction; each source can start late by its approach time."""
    from scipy.sparse import csr_matrix  # type: ignore[import-untyped]
    from scipy.sparse.csgraph import dijkstra  # type: ignore[import-untyped]

    if not sources:
        return np.full(n, np.inf)
    start = list(start_s) if start_s is not None else [0.0] * len(sources)
    keep = [(f, t, max(length, 1.0) / max(min(speed, cap_m_s), 0.5))
            for eid, f, t, length, speed in edges if eid not in closed]
    # one virtual start node (index n) linked to every source by its approach time
    keep += [(n, int(src), max(float(t0), 1e-3)) for src, t0 in zip(sources, start)]
    rows, cols, w = zip(*keep)
    graph = csr_matrix((np.asarray(w), (np.asarray(rows), np.asarray(cols))), shape=(n + 1, n + 1))
    dist = dijkstra(graph, directed=True, indices=n)
    out: np.ndarray = np.asarray(dist, dtype=np.float64)[:n]
    return out


def _snap(lon: np.ndarray, lat: np.ndarray, plon: Sequence[float],
          plat: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    """Nearest junction for each point and the straight-line distance to it (m)."""
    from scipy.spatial import cKDTree  # type: ignore[import-untyped]

    c = math.cos(math.radians(float(np.mean(lat)) if lat.size else 41.9))
    tree = cKDTree(np.column_stack([lon * c, lat]))
    deg, idx = tree.query(np.column_stack([np.asarray(plon) * c, np.asarray(plat)]))
    return np.asarray(idx, dtype=np.int64), np.asarray(deg, dtype=np.float64) * M_PER_DEG


def facilities(service: str, data: ScenarioData) -> list[tuple[float, float, str]]:
    """Start points of a service: the first layer found among the service's layers (config order)."""
    if data.facilities is not None:
        return list(data.facilities)
    specs = _cfg()["facilities"].get(service)
    if specs is None:
        raise ValueError(f"Unknown service {service!r}; known: {', '.join(sorted(_cfg()['facilities']))}")
    for spec in specs if isinstance(specs, list) else [specs]:
        path = layers.find(str(spec["file"]))
        if path is not None:
            return _points(path, spec)
    return []


def _points(path: Path, spec: Mapping[str, Any]) -> list[tuple[float, float, str]]:
    out: list[tuple[float, float, str]] = []
    for f in layers.read(path).get("features", []):
        props = f.get("properties") or {}
        ok = True
        for key, allowed in (spec.get("filter") or {}).items():
            allowed_list = allowed if isinstance(allowed, list) else [allowed]
            ok &= props.get(key) in allowed_list
        g = f.get("geometry") or {}
        if ok and g.get("type") == "Point":
            out.append((float(g["coordinates"][0]), float(g["coordinates"][1]), str(props.get(spec["field"], ""))))
    return out


def _closed_by_area(edges: Sequence[tuple[str, int, int, float, float]], lon: np.ndarray, lat: np.ndarray,
                    polygons: Sequence[Mapping[str, Any]]) -> set[str]:
    closed: set[str] = set()
    for eid, f, t, _, _ in edges:
        mlon, mlat = (lon[f] + lon[t]) / 2, (lat[f] + lat[t]) / 2
        if any(contains(p, float(mlon), float(mlat)) for p in polygons if p.get("coordinates")):
            closed.add(eid)
    return closed


def run_emergency_access(area: Area, change: Mapping[str, Any], data: ScenarioData) -> dict[str, Any]:
    cfg = _cfg()
    service = str(change.get("service", "ambulance"))
    warnings: list[str] = []
    target_cfg = config.load("thresholds.yaml")["emergency_response"][TARGET_KEYS.get(service, "ambulance_urban_min")]
    target_min = float(change.get("target_min", target_cfg["value"]))
    count_from = str(change.get("count_from", "call"))
    if count_from not in ("call", "departure"):
        raise ValueError("count_from must be 'call' (target includes call handling and dispatch) or 'departure'")
    if "close" not in change and "closed_area" not in change and "flood" not in change:
        raise ValueError("emergency_access change needs 'close' (edges | street), 'closed_area' (GeoJSON polygon) "
                         "or 'flood' ({'kind': 'river_flood' | 'rain_flood', 'change': {...}})")
    sites = facilities(service, data)
    census = load_census(data)
    kinds = {"facilities": "real" if sites else "not_available",
             "census": "real" if census is not None else "not_available", "speeds": "estimated"}
    net = data.road_network
    if net is None:
        try:
            net = network_for_area(area)
        except Exception as exc:  # noqa: BLE001 - Overpass or SUMO missing
            return _na(f"Could not build the road network from OpenStreetMap: {exc}", kinds)
    if not sites:
        return _na(f"No {service} facilities found in the layers.", kinds)
    if census is None:
        return _na("Census sections not available.", kinds)

    try:
        junctions, edges, lon, lat = read_graph(net)
    except (OSError, ET.ParseError, ValueError) as exc:
        return _na(f"Road network unreadable: {exc}", kinds)
    edge_ids = {e[0]: e for e in edges}
    closed: set[str] = set()
    flood_kind = None
    if change.get("close"):
        closed |= set(_closed_edges({"close": change["close"]},
                                    {e: {"name": ""} for e in edge_ids} | _names(net)))
    if change.get("closed_area"):
        closed |= _closed_by_area(edges, lon, lat, [change["closed_area"]])
    if change.get("flood"):
        from twin.scenarios import engine

        spec = change["flood"]
        flood_kind = str(spec.get("kind", "river_flood"))
        flood = engine.run(flood_kind, area.geometry, dict(spec.get("change", {})), data=data, isolate=False)
        if flood.get("status") != "ok":
            return _na(f"Flood scenario not available: {flood.get('reason')}", kinds)
        footprint = flood["result"].get("footprint_p50") or {}
        polys = [{"type": "Polygon", "coordinates": p} for p in footprint.get("coordinates", [])]
        closed |= _closed_by_area(edges, lon, lat, polys)
        kinds["flood"] = "estimated"
        warnings.append(f"Roads inside the likely (P50) {flood_kind.replace('_', ' ')} footprint are closed "
                        f"(flood run {flood['run_id'][:12]}).")

    n = len(junctions)
    cap = float(cfg["urban_speed_cap_kmh"]) / 3.6
    detour = float(cfg["off_network_detour"])
    src, src_m = _snap(lon, lat, [s[0] for s in sites], [s[1] for s in sites])
    start = (src_m * detour / cap).tolist()
    base_s = _times(n, edges, set(), src.tolist(), cap, start)
    var_s = _times(n, edges, closed, src.tolist(), cap, start)

    feats = [f for f in census.get("features", []) if f.get("geometry")]
    cent = [centroid(f["geometry"]) for f in feats]
    inside = [area.contains(c[0], c[1]) for c in cent]
    feats = [f for f, ok in zip(feats, inside) if ok]
    cent = [c for c, ok in zip(cent, inside) if ok]
    if not feats:
        return _na("No census section inside this area.", kinds)
    node, node_m = _snap(lon, lat, [c[0] for c in cent], [c[1] for c in cent])
    last_leg = node_m * detour / cap
    base_s, var_s = base_s[node] + last_leg, var_s[node] + last_leg
    residents = np.asarray([float((f.get("properties") or {}).get("residents") or 0) for f in feats])

    rng = np.random.default_rng(int(cfg["seed"]))
    members = int(cfg["members"])
    factors = float(cfg["speed_factor"]) * np.exp(rng.normal(0.0, float(cfg["speed_sigma_ln"]), members))
    pre_cfg = cfg["pre_travel_min"][service if service in cfg["pre_travel_min"] else "ambulance"]
    pre_s = float(pre_cfg["median"]) * 60.0 * np.exp(rng.normal(0.0, float(pre_cfg["sigma_ln"]), members))
    if count_from == "departure":
        pre_s = np.zeros(members)
    target_s = target_min * 60.0
    beyond: dict[str, list[float]] = {"baseline": [], "variant": []}
    for f, p0 in zip(factors, pre_s):
        beyond["baseline"].append(float(residents[p0 + base_s / f > target_s].sum()))
        beyond["variant"].append(float(residents[p0 + var_s / f > target_s].sum()))
    f50, p50 = float(np.median(factors)), float(np.median(pre_s))
    lost = [(i, (p50 + base_s[i] / f50) / 60, (p50 + var_s[i] / f50) / 60) for i in range(len(feats))
            if p50 + var_s[i] / f50 > target_s >= p50 + base_s[i] / f50]
    lost.sort(key=lambda r: -residents[r[0]])
    worse = [{"sez_id": str((feats[i].get("properties") or {}).get("sez_id", "")), "residents": int(residents[i]),
              "lon": round(cent[i][0], 6), "lat": round(cent[i][1], 6),
              "minutes_before": round(b, 1), "minutes_after": (round(a, 1) if math.isfinite(a) else None)}
             for i, b, a in lost[:50]]
    unreachable = float(residents[~np.isfinite(var_s)].sum())
    reach = np.isfinite(base_s) & (residents > 0)
    travel: dict[str, float | None] = {"median_resident": None, "p75_resident": None}
    if reach.any():
        order = np.argsort(base_s[reach])
        minutes, weight = base_s[reach][order] / f50 / 60, np.cumsum(residents[reach][order])
        for key, q in (("median_resident", 0.5), ("p75_resident", 0.75)):
            travel[key] = round(float(minutes[np.searchsorted(weight, q * weight[-1])]), 1)
    response = {k: (None if v is None else round(v + p50 / 60, 1)) for k, v in travel.items()}
    result = {
        "service": service, "facilities": len(sites), "target_min": target_min,
        "target_source": target_cfg.get("source"), "closed_roads": len(closed & set(edge_ids)),
        "residents_total": int(residents.sum()),
        "residents_beyond_target": {k: impacts.quantiles(v) for k, v in beyond.items()},
        "residents_cut_off": int(unreachable),
        "sections_losing_coverage": len(lost), "sections": worse,
        "travel_min_baseline": travel, "response_min_baseline": response, "count_from": count_from,
        "pre_travel_min": impacts.quantiles((pre_s / 60).tolist()),
        "calibration": str(cfg["calibration"]),
    }
    warnings += [
        f"Travel times use road speed limits (capped at {cfg['urban_speed_cap_kmh']} km/h) times an emergency factor (assumption, config/scenarios.yaml); "
        "live traffic is not included.",
        "Each census section is reached at the road junction nearest its centre; stations outside the district "
        "network and the last stretch to each section add their straight-line distance times a detour factor.",
    ]
    if count_from == "call":
        warnings.append(f"Times run from the call: about {p50 / 60:.1f} minutes of call handling, dispatch and crew "
                        f"departure are added to the road time ({pre_cfg['basis']}).")
    if service == "ambulance":
        warnings.append("Ambulances start from the ARES 118 posts (public list) or, where that layer is missing, from "
                        "emergency hospitals. An ambulance that is busy elsewhere or held at an emergency department "
                        "is not modelled: the nearest post is always taken as free.")
        obs = cfg["observed_response"]
        warnings.append(f"Real 118 responses in Lazio take {obs['lazio_p75_min']} minutes at the 75th percentile "
                        f"({obs['source']}). This model assumes a free ambulance at the nearest post, so read its "
                        "minutes as a best case and its changes (before and after a closure) as the useful signal.")
    kinds["road_network"] = "real"
    return {"result": result, "data_kinds": kinds, "sources": [], "synthetic": False, "warnings": warnings}


def _names(net: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for e in ET.parse(net).getroot().iter("edge"):
        if e.get("function") != "internal":
            out[str(e.get("id"))] = {"name": e.get("name", "")}
    return out


def _na(reason: str, kinds: Mapping[str, str]) -> dict[str, Any]:
    return {"result": {"status": "not_available", "reason": reason}, "data_kinds": dict(kinds), "sources": [],
            "synthetic": False, "warnings": [reason]}
