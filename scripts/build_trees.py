"""Build the trees layer: every tree >= 3 m in Roma Capitale with height and crown radius.

Source: Meta / WRI global canopy height model, 1 m (CC BY 4.0), read window by window.
Run from the project root:  python scripts/build_trees.py [--bbox W S E N]
Outputs in data/processed/model/: trees.parquet (points) and trees.pmtiles (crown polygons for 3D).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twin.providers.base import ROME_BBOX, BBox  # noqa: E402

OUT = ROOT / "data" / "processed" / "model"
CRS = "EPSG:32633"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bbox", nargs=4, type=float, default=list(ROME_BBOX))
    ap.add_argument("--chunk-m", type=float, default=4000.0)
    ap.add_argument("--min-height-m", type=float, default=3.0)
    ap.add_argument("--window-m", type=float, default=5.0)
    ap.add_argument("--buildings", type=Path, default=OUT / "buildings_lod1.parquet")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    bbox: BBox = (args.bbox[0], args.bbox[1], args.bbox[2], args.bbox[3])

    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import rasterio
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    from rasterio.vrt import WarpedVRT
    from rasterio.warp import Resampling, transform_bounds
    from shapely.geometry import Point
    from shapely.geometry import box as shapely_box

    from twin.model.sources import CANOPY_URL, quadkeys_for_bbox
    from twin.model.tiles import write_tiles
    from twin.model.config import TileConfig
    from twin.model.trees import detect_trees

    t0 = time.time()
    buildings = gpd.read_parquet(args.buildings, columns=["geometry"]).to_crs(CRS) if args.buildings.exists() else None
    x0, y0, x1, y1 = transform_bounds("EPSG:4326", CRS, *bbox)
    pad = 20.0
    frames = []
    env = rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MULTIRANGE="YES",
                       GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES", GDAL_CACHEMAX=1024)
    with env:
        sources = [rasterio.open(f"/vsicurl/{CANOPY_URL.format(quadkey=q)}") for q in quadkeys_for_bbox(bbox)]
        xs = np.arange(x0, x1, args.chunk_m)
        ys = np.arange(y0, y1, args.chunk_m)
        for i, cx in enumerate(xs):
            for cy in ys:
                bx0, by0, bx1, by1 = cx - pad, cy - pad, min(cx + args.chunk_m, x1) + pad, min(cy + args.chunk_m, y1) + pad
                w, h = int(bx1 - bx0), int(by1 - by0)
                transform = from_origin(bx0, by1, 1.0, 1.0)
                chm = np.zeros((h, w), dtype="float32")
                for src in sources:
                    with WarpedVRT(src, crs=CRS, transform=transform, width=w, height=h,
                                   resampling=Resampling.bilinear, src_nodata=None, nodata=0) as v:
                        chm = np.maximum(chm, v.read(1).astype("float32"))
                if chm.max() < args.min_height_m:
                    continue
                mask = None
                if buildings is not None:
                    near = buildings.iloc[buildings.sindex.query(shapely_box(bx0, by0, bx1, by1))]
                    if len(near):
                        mask = rasterize(((g, 1) for g in near.geometry), out_shape=(h, w), transform=transform,
                                         fill=0, dtype="uint8").astype(bool)
                trees = detect_trees(chm, pixel_m=1.0, min_height_m=args.min_height_m, window_m=args.window_m,
                                     origin=(bx0, by1), exclude=mask)
                core = (trees.x >= cx) & (trees.x < cx + args.chunk_m) & (trees.y >= cy) & (trees.y < cy + args.chunk_m)
                if core.any():
                    frames.append(pd.DataFrame({
                        "x": trees.x[core], "y": trees.y[core],
                        "height_m": np.round(trees.height_m[core], 1),
                        "crown_radius_m": np.round(trees.crown_radius_m[core], 1),
                    }))
            print(f"column {i + 1}/{len(xs)}: {sum(len(f) for f in frames):,} trees", flush=True)
        for src in sources:
            src.close()

    df = pd.concat(frames, ignore_index=True)
    pts = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.x, df.y), crs=CRS).drop(columns=["x", "y"])
    pts["source"] = "meta_wri_chm_1m"
    pts["data_kind"] = "estimated"
    pts["synthetic"] = False
    args.out.mkdir(parents=True, exist_ok=True)
    pts.to_crs("EPSG:4326").to_parquet(args.out / "trees.parquet", write_covering_bbox=True)

    # Crowns as octagons for 3D extrusion: the crown starts at a third of the height (trunk below).
    crowns = pts.copy()
    crowns["geometry"] = [Point(p.x, p.y).buffer(r, quad_segs=2) for p, r in zip(pts.geometry, pts.crown_radius_m)]
    crowns["base_m"] = np.round(crowns["height_m"] / 3.0, 1)
    tiles = write_tiles(crowns.to_crs("EPSG:4326"), args.out / "trees.pmtiles", TileConfig("trees", 14, 16),
                        columns=("height_m", "base_m", "crown_radius_m"))
    summary = {
        "n_trees": len(pts), "height_m_p50": float(pts.height_m.median()),
        "crown_radius_m_p50": float(pts.crown_radius_m.median()), "seconds": round(time.time() - t0, 1),
        "tiles_bytes": tiles.stat().st_size, "licence": "CC BY 4.0 (Meta / World Resources Institute)",
    }
    (args.out / "trees.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
