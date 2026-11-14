"""Check where the rain flood model floods against ten years of real street-flooding call-outs in Rome.

Roma Capitale's civil-protection event log (DIPPC:300_Eventi_STORICI, 2013-2022) has every street or home
flooding call-out as a dated point. For each municipio the model runs one design cloudburst; a call-out
is a hit when modelled flooding (P50 ponding or sewer surcharge) lies within the radius. The same test on
the centres of the municipio's inhabited census sections gives the chance rate. The ranking skill (AUC)
says how often a real call-out lies closer to modelled flooding than a random inhabited place does.

Usage: PYTHONPATH=. python scripts/validate_rain_log.py [--mm 40 --hours 1 --radius 150]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from validate_rain import municipio_of, place_points, random_streets, run, wet_points  # noqa: E402
from twin.scenarios import layers  # noqa: E402
from twin.scenarios.geometry import centroid  # noqa: E402

FLOOD_TYPES = ("2.03", "2.04")  # street and home flooding; extended flooding
K = 111_195.0
COS = math.cos(math.radians(41.9))


def _xy(points: list[tuple[float, float]]) -> np.ndarray:
    return np.asarray([(x * K * COS, y * K) for x, y in points]) if points else np.zeros((0, 2))


def distances(points: list[tuple[float, float]], wet: list[tuple[float, float]]) -> np.ndarray:
    if not points:
        return np.zeros(0)
    if not wet:
        return np.full(len(points), np.inf)
    from scipy.spatial import cKDTree  # type: ignore[import-untyped]

    dist, _ = cKDTree(_xy(wet)).query(_xy(points))
    out: np.ndarray = np.asarray(dist, dtype=float)
    return out


def auc(pos: np.ndarray, neg: np.ndarray) -> float | None:
    """Chance that a real call-out is closer to modelled flooding than a random place (ties count half)."""
    if not len(pos) or not len(neg):
        return None
    allv = np.concatenate([pos, neg])
    order = np.argsort(-allv, kind="mergesort")  # far = low score
    ranks = np.empty(len(allv))
    ranks[order] = np.arange(1, len(allv) + 1)
    # average ranks for ties
    _, inv, counts = np.unique(-allv, return_inverse=True, return_counts=True)
    sums = np.bincount(inv, weights=ranks)
    ranks = (sums / counts)[inv]
    r_pos = ranks[: len(pos)].sum()
    return round(float((r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))), 3)


def ranking_check(log: list[dict[str, Any]], places: dict[str, list[tuple[float, float]]]) -> dict[str, Any]:
    """Trouble-spot score built from 2013-2017 call-outs, scored on the 2018-2022 call-outs (AUC)."""
    from twin.scenarios import config
    from twin.scenarios.data import ScenarioData
    from twin.scenarios.flood import terrain_for
    from twin.scenarios.susceptibility import trouble_spots

    cfg = config.value(config.load("scenarios.yaml")["rain_flood"], "trouble_spots")
    grid = terrain_for(None, ScenarioData())
    early: list[tuple[float, float]] = []
    late: list[tuple[float, float]] = []
    for f in log:
        props, g = f.get("properties") or {}, f.get("geometry") or {}
        if str(props.get("sottotipol", ""))[:4] in FLOOD_TYPES and g.get("type") == "Point":
            (early if int(props.get("anno") or 0) <= 2017 else late).append(
                (float(g["coordinates"][0]), float(g["coordinates"][1])))
    neg = [p for pts in places.values() for p in pts]
    out: dict[str, Any] = {"history_years": "2013-2017", "scored_years": "2018-2022", "call_outs_scored": len(late)}
    ones = np.ones(grid.shape)
    for name, history in (("low_ground_only", None), ("low_ground_and_history", early)):
        score = trouble_spots(grid, np.ones(grid.shape, bool), ones, history, cfg)["score"]
        sp = grid.sample(score, [p[0] for p in late], [p[1] for p in late])
        sn = grid.sample(score, [p[0] for p in neg], [p[1] for p in neg])
        out[name] = auc(-sp[np.isfinite(sp)], -sn[np.isfinite(sn)])
    return out


def events_check(random_n: int = 40) -> dict[str, Any]:
    """Trouble-spot score (full 2013-2022 history) at the places reported flooded in the named cloudbursts
    (eval/scenarios/rome_rain_events.json; all outside the log years) against random streets of the same
    municipi: AUC per event, each place or street taking its highest-scoring address point."""
    import random

    from twin.scenarios import config
    from twin.scenarios.data import ScenarioData
    from twin.scenarios.flood import terrain_for
    from twin.scenarios.susceptibility import load_call_outs, trouble_spots

    cfg = config.value(config.load("scenarios.yaml")["rain_flood"], "trouble_spots")
    grid = terrain_for(None, ScenarioData())
    score = trouble_spots(grid, np.ones(grid.shape, bool), np.ones(grid.shape),
                          load_call_outs(str(cfg["call_out_file"])), cfg)["score"]
    events = json.loads((ROOT / "eval" / "scenarios" / "rome_rain_events.json").read_text(encoding="utf-8"))
    stations_path, municipi_path = layers.find("stations_ports_airports.geojson"), layers.find("municipi.geojson")
    if stations_path is None or municipi_path is None:
        return {}
    stations = {str(f["properties"]["nome"]): (float(f["geometry"]["coordinates"][0]), float(f["geometry"]["coordinates"][1]))
                for f in layers.read(stations_path)["features"] if (f.get("geometry") or {}).get("type") == "Point"}
    municipi = layers.read(municipi_path)

    def best(pts: list[tuple[float, float]]) -> float | None:
        if not pts:
            return None
        v = grid.sample(score, [q[0] for q in pts], [q[1] for q in pts])
        v = v[np.isfinite(v)]
        return float(v.max()) if len(v) else None

    rng = random.Random(5)
    out: dict[str, Any] = {}
    for ev in events["events"]:
        pos: list[float] = []
        for place in ev["places"]:
            pts = place_points(place, stations)
            if pts and municipio_of(pts[len(pts) // 2], municipi) in ev["rain"] and (b := best(pts)) is not None:
                pos.append(b)
        neg = [b for m in ev["rain"] for street in random_streets(m, random_n, rng) if (b := best(street)) is not None]
        out[ev["id"]] = {"places": len(pos), "auc": auc(-np.asarray(pos), -np.asarray(neg))}
        print(ev["id"], out[ev["id"]], flush=True)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    p.add_argument("--mm", type=float, default=40.0)
    p.add_argument("--hours", type=float, default=1.0)
    p.add_argument("--radius", type=float, default=150.0)
    p.add_argument("--municipi", nargs="*", default=[str(m) for m in range(1, 16)])
    p.add_argument("--log", type=Path, default=Path("/mnt/project-files/data/processed/civil_protection_events.geojson"))
    p.add_argument("--out", type=Path, default=ROOT / "eval" / "scenarios" / "rain_log_validation.json")
    p.add_argument("--ranking-only", action="store_true", help="only the trouble-spot ranking check (no model runs)")
    args = p.parse_args(argv)

    log = json.loads(args.log.read_text(encoding="utf-8"))["features"]
    calls: dict[str, list[tuple[float, float]]] = {}
    for f in log:
        props, g = f.get("properties") or {}, f.get("geometry") or {}
        if str(props.get("sottotipol", ""))[:4] in FLOOD_TYPES and g.get("type") == "Point":
            calls.setdefault(str(props.get("municipi")), []).append((float(g["coordinates"][0]), float(g["coordinates"][1])))
    census_path = layers.find("census_sections.geojson")
    if census_path is None:
        sys.exit("census_sections.geojson is needed")
    places: dict[str, list[tuple[float, float]]] = {}
    for f in layers.read(census_path)["features"]:
        props = f.get("properties") or {}
        if f.get("geometry") and float(props.get("residents") or 0) > 0:
            m = str(int(float(props.get("municipio") or 0))) if props.get("municipio") is not None else None
            if m:
                places.setdefault(m, []).append(centroid(f["geometry"]))

    report: dict[str, Any] = {"storm": {"mm": args.mm, "hours": args.hours}, "radius_m": args.radius,
                              "source": "Roma Capitale civil protection event log DIPPC:300_Eventi_STORICI 2013-2022, "
                                        "types 2.03 and 2.04 (flooding call-outs)", "municipi": {}}
    all_pos, all_neg = [], []
    if args.ranking_only:
        old = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else {}
        report = {**old, "ranking": ranking_check(log, places), "events_ranking": events_check()}
        args.out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        print(json.dumps(report["ranking"]))
        return 0
    for m in args.municipi:
        pts = calls.get(m, [])
        if not pts:
            continue
        res = run(m, args.mm, args.hours)
        wet = wet_points(res)
        d_pos, d_neg = distances(pts, wet), distances(places.get(m, []), wet)
        unique = list({(round(x, 3), round(y, 3)) for x, y in pts})  # about 100 m cells: each hotspot once
        d_uni = distances(unique, wet)
        all_pos.append(d_pos)
        all_neg.append(d_neg)
        report["municipi"][m] = {
            "call_outs": len(pts), "hotspots": len(unique), "flooded_km2_p50": res.get("flooded_km2_p50"),
            "call_out_hit_rate": round(float(np.mean(d_pos <= args.radius)), 3),
            "hotspot_hit_rate": round(float(np.mean(d_uni <= args.radius)), 3),
            "chance_rate": round(float(np.mean(d_neg <= args.radius)), 3) if len(d_neg) else None,
            "auc": auc(d_pos, d_neg)}
        print(m, report["municipi"][m], flush=True)
    pos, neg = np.concatenate(all_pos), np.concatenate(all_neg)
    report["all"] = {"call_outs": int(len(pos)), "call_out_hit_rate": round(float(np.mean(pos <= args.radius)), 3),
                     "chance_rate": round(float(np.mean(neg <= args.radius)), 3), "auc": auc(pos, neg)}
    report["ranking"] = ranking_check(log, places)
    report["events_ranking"] = events_check()
    report["types"] = dict(Counter(str(f["properties"].get("sottotipol", ""))[:4] for f in log))
    args.out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report["all"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
