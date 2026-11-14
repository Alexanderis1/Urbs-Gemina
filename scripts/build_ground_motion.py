"""Ground motion per building from Sentinel-1 Persistent Scatterers (Regione Lazio).

Downloads the ascending and descending point layers tile by tile (WFS, CSV), keeps coherent
points, takes the median velocity of the points on each building (footprint + buffer) and,
where both tracks see a building, splits the motion into vertical and east-west.
Run from the project root:  python scripts/build_ground_motion.py [--bbox W S E N]
Output: data/processed/model/ground_motion.parquet (one row per building id).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from twin.providers.base import ROME_BBOX, BBox  # noqa: E402

RAW = ROOT / "data" / "raw" / "insar"
OUT = ROOT / "data" / "processed" / "model"
CRS = "EPSG:32633"


def fetch_tile(wfs: str, layer: str, tile: BBox, dst: Path) -> Path:
    if dst.exists():
        return dst
    w, s, e, n = tile
    frames: list[str] = []
    start, page = 0, 100_000
    while True:
        q = urllib.parse.urlencode({
            "service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": layer,
            "outputFormat": "csv", "propertyName": "vel,coher,geom", "srsName": "EPSG:4326",
            "bbox": f"{s},{w},{n},{e},urn:ogc:def:crs:EPSG::4326", "count": page, "startIndex": start,
            "sortBy": "id",
        })
        for attempt in range(4):
            try:
                with urllib.request.urlopen(f"{wfs}?{q}", timeout=300) as r:
                    text = r.read().decode("utf-8")
                break
            except OSError:
                if attempt == 3:
                    raise
                time.sleep(2 ** (attempt + 1))
        lines = text.splitlines()
        frames.append("\n".join(lines[1:]) if frames else text)
        if len(lines) - 1 < page:
            break
        start += page
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(f for f in frames if f), encoding="utf-8")
    return dst


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bbox", nargs=4, type=float, default=list(ROME_BBOX))
    ap.add_argument("--tile-deg", type=float, default=0.04)
    ap.add_argument("--buildings", type=Path, default=OUT / "buildings_lod1.parquet")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    cfg = yaml.safe_load(open(ROOT / "config" / "model.yaml", encoding="utf-8"))["ground_motion"]

    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import shapely

    from twin.model.insar import decompose, los_unit_vector

    t0 = time.time()
    b = gpd.read_parquet(args.buildings, columns=["id", "geometry"])
    w, s, e, n = args.bbox
    b = b.cx[w:e, s:n]
    sindex = b.sindex
    tiles = []
    for x in np.arange(w, e, args.tile_deg):
        for y in np.arange(s, n, args.tile_deg):
            t = (round(float(x), 4), round(float(y), 4), round(min(x + args.tile_deg, e), 4), round(min(y + args.tile_deg, n), 4))
            if len(sindex.query(shapely.box(*t))):
                tiles.append(t)
    print(f"{len(tiles)} tiles with buildings", flush=True)

    metric = b.to_crs(CRS).reset_index(drop=True)
    buffered = gpd.GeoDataFrame({"id": metric["id"]}, geometry=metric.buffer(cfg["buffer_m"]), crs=CRS)
    per_track: dict[str, pd.DataFrame] = {}
    for track, layer in cfg["layers"].items():
        parts = []
        for i, t in enumerate(tiles):
            path = fetch_tile(cfg["wfs"], layer, t, RAW / track / f"{t[0]}_{t[1]}.csv")
            df = pd.read_csv(path)
            if len(df):
                parts.append(df)
            if (i + 1) % 20 == 0:
                print(f"{track}: {i + 1}/{len(tiles)} tiles, {sum(len(p) for p in parts):,} points", flush=True)
        pts = pd.concat(parts, ignore_index=True).drop_duplicates("FID")
        pts = pts[pts["coher"] >= cfg["min_coherence"]]
        g = gpd.GeoDataFrame(pts[["vel"]], geometry=gpd.GeoSeries.from_wkt(pts["geom"], crs="EPSG:4326")).to_crs(CRS)
        j = gpd.sjoin(g, buffered, how="inner", predicate="within")
        agg = j.groupby("id")["vel"].agg(["median", "count"]).rename(
            columns={"median": f"los_{track}_mm_yr", "count": f"n_ps_{track}"})
        per_track[track] = agg
        print(f"{track}: {len(pts):,} coherent points, {len(agg):,} buildings", flush=True)

    out = metric[["id"]].set_index("id").join(per_track["asc"]).join(per_track["desc"])
    asc = los_unit_vector(incidence_deg=cfg["incidence_deg"], heading_deg=cfg["heading_deg"]["asc"])
    desc = los_unit_vector(incidence_deg=cfg["incidence_deg"], heading_deg=cfg["heading_deg"]["desc"])
    up, east = decompose(out["los_asc_mm_yr"].to_numpy(float), out["los_desc_mm_yr"].to_numpy(float), asc, desc)
    out["vertical_mm_yr"] = np.round(up, 2)
    out["east_mm_yr"] = np.round(east, 2)
    out["data_kind"] = "real"
    out["source"] = "regione_lazio_sentinel1_ps"
    out = out.reset_index()
    args.out.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out / "ground_motion.parquet")
    both = out["vertical_mm_yr"].notna()
    summary = {
        "buildings": len(out),
        "with_asc": int(out["los_asc_mm_yr"].notna().sum()),
        "with_desc": int(out["los_desc_mm_yr"].notna().sum()),
        "with_vertical": int(both.sum()),
        "sinking_over_2mm_yr": int((out["vertical_mm_yr"] < -2).sum()),
        "vertical_p5_p50_p95": [float(v) for v in np.nanpercentile(out["vertical_mm_yr"], [5, 50, 95])] if both.any() else None,
        "seconds": round(time.time() - t0, 1),
    }
    (args.out / "ground_motion.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
