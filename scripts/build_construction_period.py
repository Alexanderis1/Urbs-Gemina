"""Construction period per building from the 1998-2023 photo series (Regione Lazio WMS).

Run from the project root:  python scripts/build_construction_period.py [--bbox W S E N]
Output: data/processed/model/construction_period.parquet and .json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import yaml  # noqa: E402

from build_ortho_facts import get_tile  # noqa: E402

OUT = ROOT / "data" / "processed" / "model"


def main(argv: list[str] | None = None) -> int:
    full = yaml.safe_load(open(ROOT / "config" / "model.yaml", encoding="utf-8"))
    ortho, hist = full["ortho"], full["history"]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bbox", nargs=4, type=float, default=ortho["district_bbox"])
    ap.add_argument("--buildings", type=Path, default=OUT / "buildings_lod1.parquet")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)

    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import shapely
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    from rasterio.warp import transform_bounds
    from scipy import ndimage

    from twin.model.change import align_shift, appearance_period, ncc_per_label

    t0 = time.time()
    res, size = float(hist["resolution_m"]), float(ortho["tile_m"])
    years = sorted(int(y) for y in hist["layers"])
    b = gpd.read_parquet(args.buildings, columns=["id", "geometry"])
    w, s, e, n = args.bbox
    b = b.cx[w:e, s:n].to_crs(ortho["crs"]).reset_index(drop=True)
    b = b[b.area >= float(hist["min_footprint_m2"])].reset_index(drop=True)
    x0, y0, x1, y1 = transform_bounds("EPSG:4326", ortho["crs"], w, s, e, n)
    x0, y0 = np.floor(x0 / size) * size, np.floor(y0 / size) * size
    tiles = [(tx, ty) for tx in np.arange(x0, x1, size) for ty in np.arange(y0, y1, size)]
    parts = []

    def gray(layer: str, tx: float, ty: float) -> Any:
        rgb = get_tile({**ortho, "layer": layer}, tx, ty, size, res)
        g = rgb.astype("float64").mean(axis=-1)
        return ndimage.gaussian_filter(g, 1.0)  # soften misregistration of a metre or two

    for k, (tx, ty) in enumerate(tiles):
        c = b.geometry.centroid
        own = b[(c.x >= tx) & (c.x < tx + size) & (c.y >= ty) & (c.y < ty + size)]
        if own.empty:
            continue
        labels = rasterize(((g, i + 1) for i, g in enumerate(own.geometry)), out_shape=(int(size / res),) * 2,
                           transform=from_origin(tx, ty + size, res, res), fill=0, dtype="int32")
        labels = np.where(ndimage.grey_erosion(labels, size=3) == labels, labels, 0)  # drop edges
        today = gray(ortho["layer"], tx, ty)
        ncc = {}
        for y in years:
            img = gray(hist["layers"][y], tx, ty)
            # Old photos are shifted by metres: align each to today's before comparing roofs.
            dy, dx = align_shift(img, today, max_shift=int(hist.get("max_shift_m", 10) / res))
            img = np.roll(img, (-dy, -dx), axis=(0, 1))
            valid = img > 0
            r = ncc_per_label(img, today, np.where(valid, labels, 0), n=len(own))
            ncc[y] = r
        first, label = appearance_period(ncc, years, latest_year=2023, threshold=float(hist["ncc_threshold"]))
        df = pd.DataFrame({"id": own["id"].to_numpy(), "built_from_year": first, "construction_period": label})
        for y in years:
            df[f"ncc_{y}"] = np.round(ncc[y], 3)
        parts.append(df)
        print(f"tile {k + 1}/{len(tiles)}: {len(own)} buildings", flush=True)

    out = pd.concat(parts, ignore_index=True)
    out["data_kind"] = "estimated"
    out["calibration"] = "uncalibrated"
    out["source"] = "regione_lazio_ortho_1998_2023"
    args.out.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out / "construction_period.parquet")
    summary = {"bbox": list(args.bbox), "buildings": len(out),
               "periods": out["construction_period"].value_counts().to_dict(), "seconds": round(time.time() - t0, 1)}
    (args.out / "construction_period.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
