"""Road closure / event: SUMO micro-simulation on one district, baseline vs variant.

Demand is synthetic (random trips, fixed seeds) because no open calibrated demand
model of Rome exists. Every result says so. The spread over several demand seeds
gives the range of each indicator.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
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
    try:
        import sumo  # type: ignore[import-untyped,import-not-found,unused-ignore]  # pip: eclipse-sumo
    except ImportError:
        return None
    return Path(str(sumo.SUMO_HOME))


def sumo_binary(name: str) -> str | None:
    home = sumo_home()
    if home is not None and (home / "bin" / name).exists():
        return str(home / "bin" / name)
    return shutil.which(name)


def _cfg() -> dict[str, Any]:
    section = config.load("scenarios.yaml")["road_closure"]
    return {key: config.value(section, key) for key in section}


def _run(cmd: Sequence[str], env: Mapping[str, str] | None = None, cwd: Path | None = None) -> None:
    proc = subprocess.run(list(cmd), capture_output=True, text=True, env=dict(env) if env else None, cwd=cwd)
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
    close = change.get("close")
    if not isinstance(close, Mapping) or not (close.get("edges") or close.get("street")):
        raise ValueError("road_closure change needs 'close': {'edges': [...]} or {'street': 'Via ...'}")


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
    speed: dict[str, float] = {}
    for edge in ET.parse(edgedata).getroot().iter("edge"):
        eid = str(edge.get("id"))
        entered[eid] = entered.get(eid, 0.0) + float(edge.get("entered", 0))
        if edge.get("speed") is not None:
            speed[eid] = float(edge.get("speed", 0))
    n = max(len(durations), 1)
    return {"completed": len(durations), "mean_travel_time_s": sum(durations) / n,
            "mean_time_loss_s": sum(losses) / n, "vehicle_hours_lost": sum(losses) / 3600.0, "entered": entered,
            "speed": speed}


def _random_trips(home: Path, net: Path, out: Path, seed: int, density: float, cfg: Mapping[str, Any],
                  env: Mapping[str, str], work: Path) -> None:
    _run([sys.executable, str(home / "tools" / "randomTrips.py"), "-n", str(net), "-o", str(out),
          "--seed", str(seed), "-b", "0", "-e", str(cfg["duration_s"]),
          "--insertion-density", f"{density:.4f}",
          "--min-distance", str(cfg["min_trip_distance_m"]), "--fringe-factor", str(cfg["fringe_factor"]),
          "--validate"], env=env, cwd=work)


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
    _validate(change)
    kinds = {"road_network": data.road_network_kind if data.road_network else "not_available",
             "traffic_demand": "simulated"}
    reason = None
    if data.road_network is None or not data.road_network.exists():
        reason = "No road network is loaded for this area; build one from OpenStreetMap first."
    elif sumo_binary("sumo") is None or sumo_binary("netconvert") is None or sumo_home() is None:
        reason = "SUMO is not installed on this server (pip install eclipse-sumo)."
    if reason is not None:
        return {"result": {"status": "not_available", "reason": reason}, "data_kinds": kinds,
                "sources": [], "synthetic": True, "warnings": [reason, SYNTHETIC_DEMAND]}

    cfg = _cfg()
    net = data.road_network
    assert net is not None
    edges = _edges(net)
    closed = _closed_edges(change, edges)
    home = sumo_home()
    assert home is not None
    env = {**os.environ, "SUMO_HOME": str(home)}

    unknown = sorted(set(data.loop_counts_veh_per_h) - set(edges))
    loops = {e: float(v) for e, v in data.loop_counts_veh_per_h.items() if e in edges}
    with tempfile.TemporaryDirectory(prefix="urbs_sumo_") as tmp:
        work = Path(tmp)
        scale, used_loops = (_demand_scale(home, net, loops, cfg, env, work) if loops else (1.0, 0))
        density = float(cfg["insertion_density_veh_per_h_per_lane_km"]) * scale
        variant_net = work / "variant.net.xml"
        netconvert = sumo_binary("netconvert")
        assert netconvert is not None
        _run([netconvert, "-s", str(net), "--remove-edges.explicit", ",".join(closed), "-o", str(variant_net)])
        geo_net = None
        if _is_geo(net):
            geo_net = work / "geo.net.xml"
            _run([netconvert, "-s", str(net), "--proj.plain-geo", "true", "-o", str(geo_net)])
        midpoints = _midpoints(geo_net)

        runs: dict[str, list[dict[str, Any]]] = {"baseline": [], "variant": []}
        dropped = 0
        for r in range(int(cfg["replicates"])):
            seed = int(cfg["seed"]) + r
            raw, trips = work / f"raw{r}.trips.xml", work / f"trips{r}.xml"
            _random_trips(home, net, raw, seed, density, cfg, env, work)
            dropped = _filter_trips(raw, trips, set(closed))
            runs["baseline"].append(_simulate(net, trips, seed, work, f"b{r}", cfg))
            runs["variant"].append(_simulate(variant_net, trips, seed, work, f"v{r}", cfg))

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
    return {
        "result": {
            "status": "ok", "engine": "sumo", "calibration": "uncalibrated",
            "closed_edges": closed, "replicates": n, "trips_left_out": dropped,
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
