"""Road closure / event: SUMO micro-simulation on one district, baseline vs variant.

Demand is synthetic (random trips, fixed seeds) because no open calibrated demand
model of Rome exists. Every result says so. The spread over several demand seeds
gives the range of each indicator.
"""
from __future__ import annotations

import importlib.util
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from twin.scenarios import config
from twin.scenarios.area import Area
from twin.scenarios.data import ScenarioData

SYNTHETIC_DEMAND = ("Synthetic demand: trips are generated, then scaled to real loop counts where they exist. "
                    "Compare variants with each other, not with real counts.")


def sumo_home() -> Path | None:
    env = os.environ.get("SUMO_HOME")
    if env and Path(env).is_dir():
        return Path(env)
    # Locate the pip package (eclipse-sumo) without importing it: importing it sets PROJ_DATA to
    # SUMO's own PROJ database, which breaks rasterio / GDAL in the same process.
    spec = importlib.util.find_spec("sumo")
    if spec is None or not spec.submodule_search_locations:
        return None
    home = Path(list(spec.submodule_search_locations)[0])
    return home if (home / "bin").is_dir() else None


def sumo_binary(name: str) -> str | None:
    home = sumo_home()
    if home is not None and (home / "bin" / name).exists():
        return str(home / "bin" / name)
    return shutil.which(name)


def _cfg() -> dict[str, Any]:
    section = config.load("scenarios.yaml")["road_closure"]
    return {key: config.value(section, key) for key in section}


def _sumo_env() -> dict[str, str]:
    """Environment for SUMO tools only: its own SUMO_HOME and PROJ database (never set in this process)."""
    env = dict(os.environ)
    home = sumo_home()
    if home is not None:
        env.setdefault("SUMO_HOME", str(home))
        if (home / "data" / "proj").is_dir() and not (env.get("PROJ_LIB") or env.get("PROJ_DATA")):
            env["PROJ_LIB"] = env["PROJ_DATA"] = str(home / "data" / "proj")
    return env


def _run(cmd: Sequence[str], env: Mapping[str, str] | None = None, cwd: Path | None = None) -> None:
    proc = subprocess.run(list(cmd), capture_output=True, text=True, env=dict(env) if env else _sumo_env(), cwd=cwd)
    if proc.returncode != 0:
        raise RuntimeError(f"{Path(cmd[0]).name} failed: {proc.stderr.strip()[-800:]}")


def _edges(net: Path) -> dict[str, dict[str, Any]]:
    """Normal (non-internal) edges with their street name and lane count."""
    out: dict[str, dict[str, Any]] = {}
    for edge in ET.parse(net).getroot().iter("edge"):
        if edge.get("function") == "internal":
            continue
        lanes = edge.findall("lane")
        out[str(edge.get("id"))] = {"name": edge.get("name", ""), "lanes": len(lanes),
                                    "shape": lanes[0].get("shape", "") if lanes else ""}
    return out


def build_network(osm_file: Path, out: Path) -> Path:
    """Build a SUMO network for one district from an OpenStreetMap extract (cars and buses)."""
    netconvert = sumo_binary("netconvert")
    if netconvert is None:
        raise RuntimeError("SUMO is not installed (pip install eclipse-sumo)")
    _run([netconvert, "--osm-files", str(osm_file), "-o", str(out),
          "--output.street-names", "true", "--keep-edges.by-vclass", "passenger,bus",
          "--remove-edges.isolated", "true", "--geometry.remove", "true", "--roundabouts.guess", "true",
          "--ramps.guess", "true", "--junctions.join", "true", "--tls.guess-signals", "true",
          "--tls.join", "true", "--no-warnings", "true"])
    return out


def download_osm(bbox: tuple[float, float, float, float], out: Path) -> Path:
    """Road ways of a bounding box from the Overpass API (OpenStreetMap, ODbL)."""
    import urllib.parse
    import urllib.request

    cfg = _cfg()
    w, s_, e, n = bbox
    query = (f'[out:xml][timeout:180];(way["highway"~"^({cfg["osm_highways"]})$"]({s_},{w},{n},{e}););'
             "(._;>;);out body;")
    body = urllib.parse.urlencode({"data": query}).encode()
    request = urllib.request.Request(str(cfg["overpass_url"]), data=body,
                                     headers={"User-Agent": "urbs-gemina-twin/0.1"})
    with urllib.request.urlopen(request, timeout=240) as response:  # noqa: S310 - fixed https endpoint
        out.write_bytes(response.read())
    return out


def network_for_area(area: Area) -> Path:
    """SUMO network for an operating area: built once from OpenStreetMap, then cached."""
    cfg = _cfg()
    cache_dir = config.ROOT / str(cfg["network_cache_dir"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() else "_" for ch in area.id)
    net = cache_dir / f"{safe}.net.xml"
    if net.exists():
        return net
    osm = download_osm(area.bbox, cache_dir / f"{safe}.osm")
    return build_network(osm, net)


def street_names(net: Path) -> set[str]:
    return {str(e["name"]) for e in _edges(net).values() if e["name"]}


def _is_geo(net: Path) -> bool:
    loc = ET.parse(net).getroot().find("location")
    return loc is not None and loc.get("projParameter", "!") != "!"


def _closed_edges(change: Mapping[str, Any], edges: Mapping[str, Mapping[str, Any]]) -> list[str]:
    close = change.get("close") or {}
    wanted = [str(e) for e in close.get("edges", [])]
    street = close.get("street")
    unknown = [e for e in wanted if e not in edges]
    if unknown:
        raise ValueError(f"Road segments not in the district network: {', '.join(unknown)}")
    if street:
        named = [eid for eid, e in edges.items() if str(e["name"]).casefold() == str(street).casefold()]
        if not named:
            raise ValueError(f"No road named {street!r} in the district network")
        wanted += named
    return sorted(set(wanted))


def _validate(change: Mapping[str, Any]) -> None:
    close, works, event = change.get("close"), change.get("roadworks"), change.get("event")
    ok_close = isinstance(close, Mapping) and bool(close.get("edges") or close.get("street"))
    ok_works = isinstance(works, Sequence) and not isinstance(works, str) and len(works) > 0
    ok_event = isinstance(event, Mapping) and float(event.get("attendees", 0)) > 0
    if close is not None and not ok_close:
        raise ValueError("'close' needs {'edges': [...]} or {'street': 'Via ...'}")
    if not (ok_close or ok_works or ok_event):
        raise ValueError("traffic change needs 'close': {'edges' | 'street'}, 'roadworks': [{'edges' | 'street', "
                         "'lanes_closed', 'speed_kmh'}] and/or 'event': {'lon', 'lat' (or 'edges'), 'attendees'}")


def _select(spec: Mapping[str, Any], edges: Mapping[str, Mapping[str, Any]]) -> list[str]:
    return _closed_edges({"close": spec}, edges)


def _roadworks_patch(change: Mapping[str, Any], edges: Mapping[str, Mapping[str, Any]],
                     closed: set[str]) -> tuple[str, list[dict[str, Any]]]:
    """Plain-XML edge patch: fewer lanes and/or a lower speed on the works edges."""
    rows: list[str] = []
    applied: list[dict[str, Any]] = []
    for works in change.get("roadworks") or []:
        lanes_closed = int(works.get("lanes_closed", 0))
        speed = works.get("speed_kmh")
        for eid in _select(works, edges):
            if eid in closed:
                continue
            lanes = int(edges[eid]["lanes"])
            left = max(1, lanes - lanes_closed)
            attrs = f' numLanes="{left}"' if left != lanes else ""
            if speed is not None:
                attrs += f' speed="{float(speed) / 3.6:.2f}"'
            if attrs:
                rows.append(f'<edge id="{eid}"{attrs}/>')
                applied.append({"edge": eid, "lanes": [lanes, left],
                                "speed_kmh": float(speed) if speed is not None else None})
    return "<edges>" + "".join(rows) + "</edges>", applied


def _percentiles(values: Sequence[float]) -> dict[str, float]:
    """Nearest-rank P5 / P50 / P95 over the replicates (min / median / max for five)."""
    ordered = sorted(values)
    n = len(ordered)

    def rank(q: float) -> float:
        return ordered[min(n - 1, max(0, int(round(q * (n - 1)))))]

    return {"p5": round(rank(0.05), 2), "p50": round(rank(0.5), 2), "p95": round(rank(0.95), 2)}


def _simulate(net: Path, trips: Path, seed: int, work: Path, tag: str, cfg: Mapping[str, Any]) -> dict[str, Any]:
    tripinfo, edgedata, add = work / f"{tag}.tripinfo.xml", work / f"{tag}.edges.xml", work / f"{tag}.add.xml"
    add.write_text(f'<additional><edgeData id="e" file="{edgedata.name}"/></additional>', encoding="utf-8")
    binary = sumo_binary("sumo")
    assert binary is not None
    _run([binary, "-n", str(net), "-r", str(trips), "-a", str(add), "--tripinfo-output", str(tripinfo),
          "--seed", str(seed), "--ignore-route-errors", "true", "--no-step-log", "true",
          "--duration-log.disable", "true", "--no-warnings", "true",
          "--time-to-teleport", str(cfg["time_to_teleport_s"]),
          "--device.rerouting.probability", "1", "--device.rerouting.period", str(cfg["rerouting_period_s"]),
          "--end", str(int(cfg["duration_s"]) * 4)])
    durations, losses = [], []
    for trip in ET.parse(tripinfo).getroot().iter("tripinfo"):
        durations.append(float(trip.get("duration", 0)))
        losses.append(float(trip.get("timeLoss", 0)))
    entered: dict[str, float] = {}
    lost: dict[str, float] = {}
    speed: dict[str, float] = {}
    for edge in ET.parse(edgedata).getroot().iter("edge"):
        eid = str(edge.get("id"))
        entered[eid] = entered.get(eid, 0.0) + float(edge.get("entered", 0))
        lost[eid] = lost.get(eid, 0.0) + float(edge.get("timeLoss", 0))
        if edge.get("speed") is not None:
            speed[eid] = float(edge.get("speed", 0))
    n = max(len(durations), 1)
    return {"completed": len(durations), "mean_travel_time_s": sum(durations) / n,
            "mean_time_loss_s": sum(losses) / n, "vehicle_hours_lost": sum(losses) / 3600.0, "entered": entered,
            "speed": speed, "lost": lost}


def _random_trips(home: Path, net: Path, out: Path, seed: int, density: float, cfg: Mapping[str, Any],
                  env: Mapping[str, str], work: Path) -> None:
    _run([sys.executable, str(home / "tools" / "randomTrips.py"), "-n", str(net), "-o", str(out),
          "--seed", str(seed), "-b", "0", "-e", str(cfg["duration_s"]),
          "--insertion-density", f"{density:.4f}",
          "--min-distance", str(cfg["min_trip_distance_m"]), "--fringe-factor", str(cfg["fringe_factor"]),
          "--validate"], env=env, cwd=work)
    if not out.exists():
        raise RuntimeError("randomTrips wrote no trips: duarouter did not run. In a container, SUMO needs the "
                           "system libraries libX11, libXext, libXrender and libGL (see deploy/scenarios_worker.py).")


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0


def _demand_scale(home: Path, net: Path, loops: Mapping[str, float], cfg: Mapping[str, Any],
                  env: Mapping[str, str], work: Path) -> tuple[float, int]:
    """One pilot run at the configured density; scale = median(observed / simulated) on loop edges."""
    density = float(cfg["insertion_density_veh_per_h_per_lane_km"])
    pilot = work / "pilot.trips.xml"
    _random_trips(home, net, pilot, int(cfg["seed"]), density, cfg, env, work)
    run = _simulate(net, pilot, int(cfg["seed"]), work, "pilot", cfg)
    per_hour = 3600.0 / float(cfg["duration_s"])
    ratios = [obs / (run["entered"][eid] * per_hour) for eid, obs in loops.items()
              if run["entered"].get(eid, 0.0) > 0.0]
    if not ratios:
        return 1.0, 0
    low, high = (float(v) for v in cfg["demand_scale_bounds"])
    return min(high, max(low, _median(ratios))), len(ratios)


def _event_destinations(event: Mapping[str, Any], edges: Mapping[str, Mapping[str, Any]],
                        midpoints: Mapping[str, tuple[float, float]], radius_default: float) -> list[str]:
    if event.get("edges") or event.get("street"):
        return _select(event, edges)
    if "lon" not in event or "lat" not in event:
        raise ValueError("'event' needs 'lon' and 'lat', or 'edges' / 'street'")
    if not midpoints:
        raise ValueError("this road network has no coordinates: give the event's 'edges' instead of lon / lat")
    lon, lat = float(event["lon"]), float(event["lat"])
    radius = float(event.get("radius_m", radius_default))
    k, c = 111_195.0, math.cos(math.radians(lat))
    near = [eid for eid, (elon, elat) in midpoints.items()
            if math.hypot((elon - lon) * k * c, (elat - lat) * k) <= radius]
    if not near:
        raise ValueError(f"No road within {radius:.0f} m of the event location")
    return near


def _add_event_trips(src: Path, dst: Path, origins: Sequence[str], destinations: Sequence[str], vehicles: int,
                     window: tuple[float, float], seed: int) -> None:
    """Append event trips (random origins -> venue roads) to a trips file, departures sorted."""
    rng = random.Random(seed)
    tree = ET.parse(src)
    root = tree.getroot()
    for i in range(vehicles):
        depart = rng.uniform(*window)
        trip = ET.SubElement(root, "trip", {"id": f"event_{i}", "depart": f"{depart:.1f}",
                                            "from": rng.choice(list(origins)), "to": rng.choice(list(destinations))})
        trip.tail = "\n"
    trips = sorted(root.findall("trip"), key=lambda t: float(t.get("depart", 0)))
    for t in root.findall("trip"):
        root.remove(t)
    root.extend(trips)
    tree.write(dst)


def _filter_trips(src: Path, dst: Path, closed: set[str]) -> int:
    tree = ET.parse(src)
    root = tree.getroot()
    dropped = 0
    for trip in list(root.findall("trip")):
        if trip.get("from") in closed or trip.get("to") in closed:
            root.remove(trip)
            dropped += 1
    tree.write(dst)
    return dropped


def _midpoints(geo_net: Path | None) -> dict[str, tuple[float, float]]:
    if geo_net is None:
        return {}
    out: dict[str, tuple[float, float]] = {}
    for eid, edge in _edges(geo_net).items():
        pts = [p.split(",") for p in str(edge["shape"]).split()]
        if pts:
            mid = pts[len(pts) // 2]
            out[eid] = (round(float(mid[0]), 6), round(float(mid[1]), 6))
    return out


def run_road_closure(area: Area, change: Mapping[str, Any], data: ScenarioData) -> dict[str, Any]:
    """Alias kept for the original 'road_closure' kind."""
    return run_traffic_event(area, change, data)


def run_traffic_event(area: Area, change: Mapping[str, Any], data: ScenarioData) -> dict[str, Any]:
    """Closures, roadworks (fewer lanes, lower speed) and big events (extra trips to a venue), with SUMO."""
    _validate(change)
    kinds = {"road_network": data.road_network_kind if data.road_network else "not_available",
             "traffic_demand": "simulated"}
    reason = None
    if sumo_binary("sumo") is None or sumo_binary("netconvert") is None or sumo_home() is None:
        reason = "SUMO is not installed on this server (pip install eclipse-sumo)."
    elif data.road_network is None and bool(_cfg()["auto_network"]):
        try:
            data = replace(data, road_network=network_for_area(area), road_network_kind="real",
                           road_network_source={"id": "osm_overpass", "url": str(_cfg()["overpass_url"]),
                                                "licence": "ODbL"})
        except Exception as exc:  # noqa: BLE001 - network or Overpass down
            reason = f"Could not build the road network from OpenStreetMap: {exc}"
    if reason is None and (data.road_network is None or not data.road_network.exists()):
        reason = "No road network is loaded for this area; build one from OpenStreetMap first."
    kinds["road_network"] = data.road_network_kind if data.road_network else "not_available"
    if reason is not None:
        return {"result": {"status": "not_available", "reason": reason}, "data_kinds": kinds,
                "sources": [], "synthetic": True, "warnings": [reason, SYNTHETIC_DEMAND]}

    cfg = _cfg()
    net = data.road_network
    assert net is not None
    edges = _edges(net)
    closed = _closed_edges(change, edges) if change.get("close") else []
    patch, works = _roadworks_patch(change, edges, set(closed))
    event = change.get("event")
    home = sumo_home()
    assert home is not None
    env = _sumo_env()

    unknown = sorted(set(data.loop_counts_veh_per_h) - set(edges))
    loops = {e: float(v) for e, v in data.loop_counts_veh_per_h.items() if e in edges}
    with tempfile.TemporaryDirectory(prefix="urbs_sumo_") as tmp:
        work = Path(tmp)
        scale, used_loops = (_demand_scale(home, net, loops, cfg, env, work) if loops else (1.0, 0))
        density = float(cfg["insertion_density_veh_per_h_per_lane_km"]) * scale
        variant_net = work / "variant.net.xml"
        netconvert = sumo_binary("netconvert")
        assert netconvert is not None
        cmd = [netconvert, "-s", str(net), "-o", str(variant_net)]
        if closed:
            cmd += ["--remove-edges.explicit", ",".join(closed)]
        if works:
            (work / "works.edg.xml").write_text(patch, encoding="utf-8")
            cmd += ["-e", str(work / "works.edg.xml")]
        _run(cmd)
        geo_net = None
        if _is_geo(net):
            geo_net = work / "geo.net.xml"
            _run([netconvert, "-s", str(net), "--proj.plain-geo", "true", "-o", str(geo_net)])
        midpoints = _midpoints(geo_net)
        event_info: dict[str, Any] | None = None
        if isinstance(event, Mapping):
            destinations = [e for e in _event_destinations(event, edges, midpoints, float(cfg["event_radius_m"]))
                            if e not in closed]
            share = float(event.get("car_share", cfg["event_car_share"]))
            occupancy = float(event.get("occupancy", cfg["event_car_occupancy"]))
            vehicles = int(round(float(event["attendees"]) * share / occupancy))
            window = (float(event.get("arrive_from_s", 0.0)),
                      float(event.get("arrive_to_s", cfg["duration_s"])))
            origins = [e for e, info in edges.items() if e not in closed and e not in destinations and info["lanes"]]
            event_info = {"vehicles": vehicles, "destination_edges": len(destinations), "car_share": share,
                          "occupancy": occupancy, "arrival_window_s": list(window)}

        runs: dict[str, list[dict[str, Any]]] = {"baseline": [], "variant": []}
        dropped = 0
        for r in range(int(cfg["replicates"])):
            seed = int(cfg["seed"]) + r
            raw, trips = work / f"raw{r}.trips.xml", work / f"trips{r}.xml"
            _random_trips(home, net, raw, seed, density, cfg, env, work)
            dropped = _filter_trips(raw, trips, set(closed))
            variant_trips = trips
            if event_info is not None:
                variant_trips = work / f"event{r}.xml"
                _add_event_trips(trips, variant_trips, origins, destinations, int(event_info["vehicles"]),
                                 (window[0], window[1]), seed)
            runs["baseline"].append(_simulate(net, trips, seed, work, f"b{r}", cfg))
            runs["variant"].append(_simulate(variant_net, variant_trips, seed, work, f"v{r}", cfg))

    indicators = ("mean_travel_time_s", "mean_time_loss_s", "vehicle_hours_lost", "completed")
    sides = {side: {k: _percentiles([run[k] for run in rs]) for k in indicators} for side, rs in runs.items()}

    #: paired difference: same demand seed with and without the closure
    sides["difference"] = {k: _percentiles([v[k] - b[k] for b, v in zip(runs["baseline"], runs["variant"])])
                           for k in indicators}
    n = len(runs["baseline"])
    change_by_edge: dict[str, float] = {}
    for b, v in zip(runs["baseline"], runs["variant"]):
        for eid in set(b["entered"]) | set(v["entered"]):
            change_by_edge[eid] = change_by_edge.get(eid, 0.0) + (v["entered"].get(eid, 0.0) -
                                                                  b["entered"].get(eid, 0.0)) / n
    lost_by_edge: dict[str, float] = {}
    for b, v in zip(runs["baseline"], runs["variant"]):
        for eid in set(b["lost"]) | set(v["lost"]):
            lost_by_edge[eid] = lost_by_edge.get(eid, 0.0) + (v["lost"].get(eid, 0.0) -
                                                              b["lost"].get(eid, 0.0)) / n / 3600.0
    hot = sorted((e for e in lost_by_edge if e not in closed and lost_by_edge[e] > 0),
                 key=lambda e: -lost_by_edge[e])
    congestion = []
    for eid in hot[: int(cfg["top_changed_roads"])]:
        point: dict[str, Any] = {"edge": eid, "name": edges.get(eid, {}).get("name", ""),
                                 "extra_vehicle_hours_lost": round(lost_by_edge[eid], 2)}
        if eid in midpoints:
            point["lon"], point["lat"] = midpoints[eid]
        congestion.append(point)
    top = sorted((e for e in change_by_edge if e not in closed), key=lambda e: -abs(change_by_edge[e]))
    changed = []
    for eid in top[: int(cfg["top_changed_roads"])]:
        row: dict[str, Any] = {"edge": eid, "name": edges.get(eid, {}).get("name", ""),
                               "vehicles_change_per_run": round(change_by_edge[eid], 1)}
        if eid in midpoints:
            row["lon"], row["lat"] = midpoints[eid]
        changed.append(row)

    speed_check = None
    observed = {e: float(v) for e, v in data.observed_speeds_m_per_s.items() if e in edges}
    if observed:
        errors = []
        for eid, obs in observed.items():
            sim = [run["speed"][eid] for run in runs["baseline"] if eid in run["speed"]]
            if sim:
                errors.append(sum(sim) / len(sim) - obs)
        if errors:
            speed_check = {"edges": len(errors),
                           "mean_abs_error_m_per_s": round(sum(abs(e) for e in errors) / len(errors), 2),
                           "bias_m_per_s": round(sum(errors) / len(errors), 2)}
            kinds["bus_speeds"] = "real"

    warnings = [SYNTHETIC_DEMAND,
                f"Ranges are the spread over {n} demand seeds, not a calibrated uncertainty.",
                "Buses (GTFS) are not in the simulation yet."]
    if used_loops:
        kinds["loop_counts"] = data.loop_counts_kind
        warnings.append(f"Demand scaled by {scale:.2f} to match {used_loops} loop stations "
                        f"({data.loop_counts_kind}).")
    else:
        warnings.append("No loop counts on this network: demand density is the configured assumption.")
    if unknown:
        warnings.append(f"{len(unknown)} loop stations are not on this network and were ignored.")
    if speed_check is None:
        warnings.append("No real bus speeds to check the baseline against.")
    if dropped:
        warnings.append(f"{dropped} trips starting or ending on the closed road were left out of both runs.")
    if event_info is not None:
        warnings.append(f"Event traffic: {event_info['vehicles']} cars from {event_info['car_share']:.0%} of attendees "
                        f"arriving by car, {event_info['occupancy']} per car (assumptions unless given).")
    return {
        "result": {
            "status": "ok", "engine": "sumo", "calibration": "uncalibrated",
            "closed_edges": closed, "roadworks": works, "event": event_info,
            "replicates": n, "trips_left_out": dropped, "congestion_points": congestion,
            "baseline": sides["baseline"], "variant": sides["variant"], "difference": sides["difference"],
            "changed_roads": changed,
            "demand_anchor": {"loop_stations": used_loops, "scale": round(scale, 3),
                              "insertion_density_veh_per_h_per_lane_km": round(density, 2)},
            "speed_check": speed_check,
        },
        "data_kinds": kinds,
        "sources": [s for s in [data.road_network_source] if s],
        "synthetic": True,
        "warnings": warnings,
    }
