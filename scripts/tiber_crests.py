"""Crest elevation of the Tiber embankment walls (muraglioni), Ponte Milvio to Ponte Marconi, from LiDAR.

    python scripts/tiber_crests.py --dtm-dir DIR [--out /mnt/project-files/model/tiber_wall_crests.geojson]

Input: MASE airborne LiDAR DTM tiles, 1 m (CC BY 4.0, survey 2008-2011), fetched with
``scripts/build_lidar.py fetch --bbox 12.452 41.850 12.492 41.938`` (city-model branch).
River centreline: Overture Maps water (OSM, ODbL) "Tevere".

Method, every ``--step`` metres of river: a transect perpendicular to the centreline, sampled
every 1 m up to 130 m on each side. Water level = median of the first 15 m. The wall top is the
first point at least 5 m above the water; the crest is the highest value in the next 40 m,
which spans the lower quay (banchina) and reaches the top of the muraglione at the Lungotevere edge. A bank without such a rise is reported with
``wall_detected: false``.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

MILVIO = (12.4675, 41.9355)
MARCONI = (12.4667, 41.8555)
R = 6_371_008.8


def _xy(lon: Any, lat: Any, lon0: float, lat0: float) -> tuple[Any, Any]:
    return (np.radians(np.asarray(lon) - lon0) * R * math.cos(math.radians(lat0)),
            np.radians(np.asarray(lat) - lat0) * R)


def _lonlat(x: Any, y: Any, lon0: float, lat0: float) -> tuple[Any, Any]:
    return (lon0 + np.degrees(np.asarray(x) / (R * math.cos(math.radians(lat0)))),
            lat0 + np.degrees(np.asarray(y) / R))


def main() -> None:
    import pyarrow.parquet as pq  # type: ignore[import-untyped]
    import rasterio  # type: ignore[import-untyped]
    from rasterio.merge import merge  # type: ignore[import-untyped]
    from shapely import wkb  # type: ignore[import-untyped,unused-ignore]

    p = argparse.ArgumentParser()
    p.add_argument("--dtm-dir", required=True)
    p.add_argument("--water", default="data/raw/overture/water_tiber.parquet")
    p.add_argument("--step", type=float, default=200.0)
    p.add_argument("--out", default="/mnt/project-files/model/tiber_wall_crests.geojson")
    args = p.parse_args()

    rows = pq.read_table(args.water).to_pylist()
    lines = [wkb.loads(r["geometry"]) for r in rows
             if r["names"] and "Tevere" in str((r["names"] or {}).get("primary")) and r["subtype"] == "river"]
    line = max((g for g in lines if g.geom_type == "LineString"), key=lambda g: g.length)
    coords = np.asarray(line.coords)
    lon0, lat0 = MILVIO
    x, y = _xy(coords[:, 0], coords[:, 1], lon0, lat0)
    seg = np.hypot(np.diff(x), np.diff(y))
    chain = np.concatenate([[0.0], np.cumsum(seg)])
    def at(lon: float, lat: float) -> float:
        px, py = _xy(lon, lat, lon0, lat0)
        return float(chain[int(np.argmin(np.hypot(x - px, y - py)))])
    a, b = sorted([at(*MILVIO), at(*MARCONI)])
    upstream_first = at(*MILVIO) <= at(*MARCONI)

    tiles = [rasterio.open(f) for f in sorted(glob.glob(str(Path(args.dtm_dir) / "*.tif*")))]
    dem, transform = merge(tiles, nodata=-9999.0)
    dem = dem[0].astype("float64")
    dem[dem <= -9000] = np.nan
    inv = ~transform

    def sample(px: Any, py: Any) -> Any:
        lon, lat = _lonlat(px, py, lon0, lat0)
        col, row = inv * (lon, lat)
        col, row = np.floor(col).astype(int), np.floor(row).astype(int)
        ok = (row >= 0) & (row < dem.shape[0]) & (col >= 0) & (col < dem.shape[1])
        out = np.full(np.shape(px), np.nan)
        out[ok] = dem[row[ok], col[ok]]
        return out

    feats: list[dict[str, Any]] = []
    for s in np.arange(a, b + 1e-6, args.step):
        cx, cy = float(np.interp(s, chain, x)), float(np.interp(s, chain, y))
        ds = 5.0
        dx = float(np.interp(s + ds, chain, x) - np.interp(s - ds, chain, x))
        dy = float(np.interp(s + ds, chain, y) - np.interp(s - ds, chain, y))
        norm = math.hypot(dx, dy) or 1.0
        tx, ty = dx / norm, dy / norm
        if not upstream_first:
            tx, ty = -tx, -ty
        # hydrographic banks, looking downstream: right = clockwise normal
        for bank, (nx, ny) in (("right", (ty, -tx)), ("left", (-ty, tx))):
            d = np.arange(0.0, 131.0, 1.0)
            h = sample(cx + nx * d, cy + ny * d)
            if np.isnan(h[:15]).all():
                continue
            water = float(np.nanmedian(h[:15]))
            above = np.nonzero(h - water >= 5.0)[0]
            chainage = s - a if upstream_first else b - s
            props: dict[str, Any] = {"bank": bank, "chainage_m": round(float(chainage), 0), "water_m": round(water, 2),
                                     "data_kind": "real", "source": "MASE LiDAR DTM 1 m (CC BY 4.0), 2008-2011",
                                     "sigma_m": 0.3, "vertical_datum": "orthometric heights as delivered by MASE PST "
                                     "(Italian geoid; not EGM2008)"}
            if above.size == 0:
                props.update({"wall_detected": False, "crest_m": None})
                px, py = cx + nx * 60.0, cy + ny * 60.0
            else:
                k0 = int(above[0])
                win = h[k0:k0 + 40]
                k = k0 + int(np.nanargmax(win))
                props.update({"wall_detected": True, "crest_m": round(float(h[k]), 2),
                              "wall_height_m": round(float(h[k]) - water, 2), "distance_from_centreline_m": float(d[k])})
                px, py = cx + nx * d[k], cy + ny * d[k]
            lon, lat = _lonlat(px, py, lon0, lat0)
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(float(lon), 6),
                                                                                           round(float(lat), 6)]},
                          "properties": props})
    out: dict[str, Any] = {"type": "FeatureCollection", "name": "tiber_wall_crests",
           "description": "Tiber embankment crest elevations, Ponte Milvio (chainage 0) to Ponte Marconi, from LiDAR DTM. "
                          "sigma_m = LiDAR vertical accuracy (0.15 m) plus 1 m pixel / parapet ambiguity.",
           "features": feats}
    Path(args.out).write_text(json.dumps(out, indent=1))
    crests = [f["properties"]["crest_m"] for f in feats if f["properties"].get("crest_m") is not None]
    print(f"{len(feats)} points, {len(crests)} with a wall; crest {min(crests):.1f}-{max(crests):.1f} m, "
          f"median {float(np.median(crests)):.1f} m -> {args.out}")


if __name__ == "__main__":
    main()
