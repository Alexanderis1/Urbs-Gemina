"""Independent accuracy check of the permit context distances (replaces the hand-measured QGIS checks).

    python scripts/check_permit_accuracy.py [--out docs/permit_accuracy.md]

Three real cases from the processed context layers. The tool's own distance
(twin.tools.context_check.distance_to_geometry_m, local tangent plane on a sphere)
is compared with two independent references:
  * the WGS84 ellipsoid geodesic (pyproj.Geod, Karney's algorithm) for point features;
  * shapely in UTM zone 33N (EPSG:32633, pyproj transform) for polygon edges.
Tolerance: 1 m or 0.5%, whichever is larger (a 300 m radius needs metre accuracy).
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from twin.tools.context_check import distance_to_geometry_m

LAYERS = Path("/mnt/project-files/data/processed")
# Real query points: a candidate antenna site a short distance from a real feature.
CASES: list[dict[str, Any]] = [
    {"name": "school (point) about 180 m north-east of a state school", "layer": "schools_state.geojson",
     "feature": 0, "offset_m": (130.0, 125.0)},
    {"name": "hospital (point) about 260 m south-west of a hospital", "layer": "hospitals.geojson",
     "feature": 5, "offset_m": (-200.0, -170.0)},
    {"name": "UNESCO site boundary (polygon edge), point about 150 m outside", "layer": "unesco.geojson",
     "feature": None, "offset_m": (0.0, 0.0)},
]


def _offset(lon: float, lat: float, east: float, north: float) -> tuple[float, float]:
    r = 6_371_008.8
    return lon + math.degrees(east / (r * math.cos(math.radians(lat)))), lat + math.degrees(north / r)


def reference_m(lon: float, lat: float, geometry: dict[str, Any]) -> tuple[float, str]:
    from pyproj import Geod, Transformer
    from shapely.geometry import Point, shape  # type: ignore[import-untyped,unused-ignore]
    from shapely.ops import transform  # type: ignore[import-untyped,unused-ignore]

    if geometry["type"] == "Point":
        g = Geod(ellps="WGS84")
        _, _, d = g.inv(lon, lat, *geometry["coordinates"][:2])
        return float(d), "WGS84 geodesic (pyproj.Geod)"
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32633", always_xy=True).transform
    shp = transform(to_utm, shape(geometry))
    pt = transform(to_utm, Point(lon, lat))
    # UTM scale factor near Rome (about 0.9996-0.9997): convert grid metres to ground metres
    k = 0.9996 * (1 + ((pt.x - 500_000.0) ** 2) / (2 * 6_378_137.0 ** 2))
    return float(shp.exterior.distance(pt) if shp.geom_type == "Polygon" else shp.boundary.distance(pt)) / k, \
        "shapely in UTM 33N (EPSG:32633), scale-corrected"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="docs/permit_accuracy.md")
    args = p.parse_args()
    rows = []
    for case in CASES:
        fc = json.loads((LAYERS / str(case["layer"])).read_text())
        if case["feature"] is None:
            from shapely.geometry import shape  # type: ignore[import-untyped,unused-ignore]

            geom = max(fc["features"], key=lambda f: shape(f["geometry"]).area)["geometry"]
            # a point 150 m outside the boundary: from the most eastern vertex, go 150 m east
            ring = geom["coordinates"][0][0] if geom["type"] == "MultiPolygon" else geom["coordinates"][0]
            east = max(ring, key=lambda c: c[0])
            lon, lat = _offset(east[0], east[1], 150.0, 0.0)
        else:
            geom = fc["features"][int(case["feature"])]["geometry"]
            c = geom["coordinates"]
            lon, lat = _offset(c[0], c[1], *case["offset_m"])
        tool = distance_to_geometry_m(lon, lat, geom)
        ref, method = reference_m(lon, lat, geom)
        diff = tool - ref
        ok = abs(diff) <= max(1.0, 0.005 * ref)
        rows.append({"case": case["name"], "point": [round(lon, 6), round(lat, 6)], "tool_m": round(tool, 2),
                     "reference_m": round(ref, 2), "difference_m": round(diff, 2), "reference": method, "pass": ok})
        print(rows[-1])
    lines = ["# Permit tool accuracy: independent distance checks", "",
             "The three hand-measured QGIS checks were replaced by an automated, independent check (the same "
             "geometry measured by different software and a different Earth model). A hand measurement in QGIS by "
             "an officer is still welcome as a fourth check.", "",
             "| Case | Tool (m) | Reference (m) | Difference (m) | Reference method | Pass |", "|---|---|---|---|---|---|"]
    lines += [f"| {r['case']} | {r['tool_m']} | {r['reference_m']} | {r['difference_m']} | {r['reference']} | "
              f"{'yes' if r['pass'] else 'NO'} |" for r in rows]
    lines += ["", "Tolerance: 1 m or 0.5%, whichever is larger. Query points are listed in the JSON below.", "",
              "```json", json.dumps(rows, indent=2), "```", ""]
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
