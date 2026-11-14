"""Check the rain flood + sewer model against past Rome cloudbursts (eval/scenarios/rome_rain_events.json).

For each event and each municipio with reported rain, the model runs with that rain. A reported place
is a hit when a modelled flooded cell (P50 ponding or P50 sewer surcharge) lies within ``--radius`` m of it.
The same is measured for randomly drawn streets of the same municipi, so the hit rate can be read against
chance. A dry check runs an ordinary 10 mm/h shower. ``--efficiency`` repeats it for several sewer
efficiencies (the calibration sweep). Street points come from Roma Capitale's official street-number
locator (WFS, public); nothing personal is fetched.

Usage: python scripts/validate_rain.py [--efficiency 0.15 0.3 0.5 0.8] [--out eval/scenarios/rain_validation.json]
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twin.scenarios import engine, layers, sewer  # noqa: E402
from twin.scenarios.data import ScenarioData  # noqa: E402
from twin.scenarios.geometry import contains  # noqa: E402

WFS = ("https://geoportale.comune.roma.it/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature"
       "&typeNames=DIPCUL:GeoromaCiviciLocator&outputFormat=application/json&propertyName=TOPONIMO,GEOMETRIA"
       "&CQL_FILTER=")
Point = tuple[float, float]


def _wfs(cql: str) -> list[dict[str, Any]]:
    with urllib.request.urlopen(WFS + urllib.parse.quote(cql), timeout=300) as resp:  # noqa: S310 - public WFS
        features: list[dict[str, Any]] = json.load(resp)["features"]
    return features


def _metres(a: Point, b: Point) -> float:
    k = 111_195.0
    return math.hypot((a[0] - b[0]) * k * math.cos(math.radians(a[1])), (a[1] - b[1]) * k)


def street_points(name: str) -> list[Point]:
    feats = _wfs("TOPONIMO='" + name.replace("'", "''") + "'")
    return [(float(f["geometry"]["coordinates"][0]), float(f["geometry"]["coordinates"][1])) for f in feats]


def place_points(place: Mapping[str, Any], stations: Mapping[str, Point]) -> list[Point]:
    if "station" in place:
        return [stations[str(place["station"])]]
    pts = street_points(str(place["street"]))
    if place.get("near"):
        other = street_points(str(place["near"]))
        if not other or not pts:
            return []
        d = [min(_metres(p, o) for o in other) for p in pts]
        best = min(d)
        pts = [p for p, v in zip(pts, d) if v <= best + 150.0]
    return pts


def wet_points(result: Mapping[str, Any]) -> list[Point]:
    """Centres of modelled flooded polygons (ponding P50 and sewer surcharge P50)."""
    out: list[Point] = []
    for key in ("footprint_p50",):
        for poly in (result.get(key) or {}).get("coordinates", []):
            out += [(float(x), float(y)) for x, y in poly[0]]
    for poly in ((result.get("sewer") or {}).get("surcharge_map_p50") or {}).get("coordinates", []):
        out += [(float(x), float(y)) for x, y in poly[0]]
    return out


def hit(points: Sequence[Point], wet: Sequence[Point], radius: float) -> bool:
    if not points or not wet:
        return False
    from scipy.spatial import cKDTree  # type: ignore[import-untyped]

    k = 111_195.0
    c = math.cos(math.radians(41.9))
    tree = cKDTree(np.asarray([(x * k * c, y * k) for x, y in wet]))
    dist, _ = tree.query(np.asarray([(x * k * c, y * k) for x, y in points]))
    return bool(float(np.min(dist)) <= radius)


def municipio_of(point: Point, municipi: Mapping[str, Any]) -> str | None:
    for f in municipi.get("features", []):
        if contains(f["geometry"], point[0], point[1]):
            return str(int(float((f.get("properties") or {}).get("municipio") or 0)))
    return None


def random_streets(municipio: str, n: int, rng: random.Random) -> list[list[Point]]:
    feats = _wfs(f"MUNICIPIO={int(municipio)}")
    by_name: dict[str, list[Point]] = {}
    for f in feats:
        name = str((f.get("properties") or {}).get("TOPONIMO") or "")
        by_name.setdefault(name, []).append((float(f["geometry"]["coordinates"][0]),
                                             float(f["geometry"]["coordinates"][1])))
    names = sorted(by_name)
    return [by_name[s] for s in rng.sample(names, min(n, len(names)))]


def run(municipio: str, mm: float, hours: float) -> dict[str, Any]:
    out = engine.run("rain_flood", f"municipio:{municipio}", {"rain_mm": mm, "duration_h": hours},
                     data=ScenarioData(), use_cache=False, isolate=False)
    if out["status"] != "ok":
        raise RuntimeError(f"municipio {municipio}: {out.get('reason')}")
    result: dict[str, Any] = out["result"]
    return result


def validate(events: Mapping[str, Any], efficiency: float, radius: float, random_n: int) -> dict[str, Any]:
    original = sewer._cfg()["sewer_efficiency"]["value"]
    sewer._cfg()["sewer_efficiency"]["value"] = efficiency
    try:
        municipi = layers.read(layers.find("municipi.geojson"))  # type: ignore[arg-type]
        stations = {str(f["properties"]["nome"]): (float(f["geometry"]["coordinates"][0]),
                                                   float(f["geometry"]["coordinates"][1]))
                    for f in layers.read(layers.find("stations_ports_airports.geojson")).get("features", [])  # type: ignore[arg-type]
                    if (f.get("geometry") or {}).get("type") == "Point"}
        rng = random.Random(5)
        report: dict[str, Any] = {"efficiency": efficiency, "radius_m": radius, "events": []}
        for ev in events["events"]:
            wet: dict[str, list[Point]] = {}
            flooded: dict[str, float] = {}
            for m, r in ev["rain"].items():
                res = run(m, float(r["mm"]), float(r["hours"]))
                wet[m] = wet_points(res)
                flooded[m] = float(res["flooded_km2_p50"])
            places = []
            for place in ev["places"]:
                pts = place_points(place, stations)
                m = municipio_of(pts[len(pts) // 2], municipi) if pts else None
                if m not in wet:
                    places.append({**place, "status": "outside the rain area"})
                    continue
                places.append({**place, "municipio": m, "hit": hit(pts, wet[m], radius)})
            scored = [p for p in places if "hit" in p]
            chance: list[bool] = []
            for m in wet:
                chance += [hit(s, wet[m], radius) for s in random_streets(m, random_n, rng)]
            report["events"].append({
                "id": ev["id"], "flooded_km2_p50": flooded,
                "reported_hit_rate": round(sum(p["hit"] for p in scored) / len(scored), 3) if scored else None,
                "random_street_hit_rate": round(sum(chance) / len(chance), 3) if chance else None,
                "places": places})
        dry = events["dry_check"]
        report["dry_check"] = {m: run(m, float(dry["rain_mm"]), float(dry["hours"]))["flooded_km2_p50"]
                               for m in dry["municipi"]}
        return report
    finally:
        sewer._cfg()["sewer_efficiency"]["value"] = original


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--efficiency", type=float, nargs="+", default=[0.3])
    parser.add_argument("--radius", type=float, default=150.0)
    parser.add_argument("--random", type=int, default=60)
    parser.add_argument("--out", type=Path, default=ROOT / "eval" / "scenarios" / "rain_validation.json")
    args = parser.parse_args(argv)
    events = json.loads((ROOT / "eval" / "scenarios" / "rome_rain_events.json").read_text(encoding="utf-8"))
    reports = [validate(events, e, args.radius, args.random) for e in args.efficiency]
    args.out.write_text(json.dumps(reports, indent=1, ensure_ascii=False), encoding="utf-8")
    for r in reports:
        print(r["efficiency"], [(e["id"], e["reported_hit_rate"], e["random_street_hit_rate"], e["flooded_km2_p50"])
                                for e in r["events"]], "dry", r["dry_check"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
