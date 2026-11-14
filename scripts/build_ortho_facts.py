"""Roof facts and shadow heights per building from the AGEA 2023 aerial photo.

For each 1 km tile: download the photo (WMS, 0.5 m), rasterise the building footprints,
measure roof colour and cover, and measure the free shadow each building casts.
The sun direction and the shadow-to-height factor are calibrated on buildings with a
measured OSM height, so the shadow height is one more calibrated sensor for the fusion.
Run from the project root:  python scripts/build_ortho_facts.py [--bbox W S E N]
Output: data/processed/model/ortho_facts.parquet (one row per building id) and ortho_facts.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

OUT = ROOT / "data" / "processed" / "model"
CACHE = ROOT / "data" / "raw" / "ortho"


def get_tile(cfg: dict[str, Any], x0: float, y0: float, size_m: float, res: float) -> Any:
    import numpy as np
    from PIL import Image

    px = int(round(size_m / res))
    layer_dir = str(cfg["layer"]).split(":")[-1]
    path = CACHE / layer_dir / f"{int(x0)}_{int(y0)}_{res}.png"
    if not path.exists():
        q = urllib.parse.urlencode({
            "service": "WMS", "version": "1.3.0", "request": "GetMap", "layers": cfg["layer"], "styles": "",
            "crs": cfg["crs"], "bbox": f"{x0},{y0},{x0 + size_m},{y0 + size_m}", "width": px, "height": px,
            "format": "image/png",
        })
        for attempt in range(4):
            try:
                with urllib.request.urlopen(f"{cfg['wms']}?{q}", timeout=300) as r:
                    data = r.read()
                if not data.startswith(b"\x89PNG"):
                    raise OSError(data[:200].decode("utf-8", "replace"))
                break
            except OSError:
                if attempt == 3:
                    raise
                time.sleep(2 ** (attempt + 1))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return np.asarray(Image.open(path).convert("RGB"))


def main(argv: list[str] | None = None) -> int:
    cfg = yaml.safe_load(open(ROOT / "config" / "model.yaml", encoding="utf-8"))["ortho"]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bbox", nargs=4, type=float, default=cfg["district_bbox"])
    ap.add_argument("--buildings", type=Path, default=OUT / "buildings_lod1.parquet")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--no-shadows", action="store_true", help="roof facts only (much faster, for the whole city)")
    args = ap.parse_args(argv)

    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import shapely
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    from rasterio.warp import transform_bounds

    from twin.model.ortho import roof_stats, shadow_runs

    t0 = time.time()
    res, size = float(cfg["resolution_m"]), float(cfg["tile_m"])
    b = gpd.read_parquet(args.buildings, columns=["id", "h_osm_tag", "height_m", "geometry"])
    w, s, e, n = args.bbox
    b = b.cx[w:e, s:n].to_crs(cfg["crs"]).reset_index(drop=True)
    x0, y0, x1, y1 = transform_bounds("EPSG:4326", cfg["crs"], w, s, e, n)
    x0, y0 = np.floor(x0 / size) * size, np.floor(y0 / size) * size
    azimuths = [] if args.no_shadows else [float(a) for a in cfg["azimuth_candidates_deg"]]
    sindex = b.sindex
    rows: list[pd.DataFrame] = []
    tiles = [(tx, ty) for tx in np.arange(x0, x1, size) for ty in np.arange(y0, y1, size)]
    for k, (tx, ty) in enumerate(tiles):
        # Buildings whose centroid is in the tile own their stats; a margin keeps neighbours for blocking.
        near_idx = sindex.query(shapely.box(tx - 60, ty - 60, tx + size + 60, ty + size + 60))
        if len(near_idx) == 0:
            continue
        rgb = get_tile(cfg, tx, ty, size, res)
        near = b.iloc[near_idx]
        transform = from_origin(tx, ty + size, res, res)
        labels = rasterize(((g, i + 1) for i, g in enumerate(near.geometry)), out_shape=rgb.shape[:2],
                           transform=transform, fill=0, dtype="int32")
        nb = len(near)
        v = rgb.max(axis=-1) / 255.0
        dark_max = float(np.quantile(v, float(cfg["dark_quantile"])))
        st = roof_stats(rgb, labels, n=nb, thresholds={**cfg["roof_thresholds"], "dark_val_max": dark_max})
        dark = v <= dark_max
        runs = {az: shadow_runs(dark, labels, n=nb, shadow_azimuth_deg=az) for az in azimuths}
        c = near.geometry.centroid
        own = (c.x >= tx) & (c.x < tx + size) & (c.y >= ty) & (c.y < ty + size)
        df = pd.DataFrame({"id": near["id"].to_numpy(), **{key: val for key, val in st.items()}})
        for az, sr in runs.items():
            df[f"shadow_px_{int(az)}"] = sr.length_px
        rows.append(df[own.to_numpy()])
        print(f"tile {k + 1}/{len(tiles)}: {int(own.sum())} buildings", flush=True)

    facts = pd.concat(rows, ignore_index=True)
    facts = facts.merge(b[["id", "h_osm_tag"]], on="id", how="left")

    # Sun direction: the candidate whose shadow lengths correlate best with measured heights.
    best_a, best_r = azimuths[0], -1.0
    for a in azimuths:
        col = facts[f"shadow_px_{int(a)}"] * res
        ok = col.notna() & facts["h_osm_tag"].notna() & (col > 0)
        if ok.sum() >= 50:
            r = float(pd.Series(col[ok]).corr(facts.loc[ok, "h_osm_tag"], method="spearman"))
            if r > best_r:
                best_a, best_r = a, r
    shadow_m = facts[f"shadow_px_{int(best_a)}"] * res if azimuths else pd.Series(np.nan, index=facts.index)
    ok = shadow_m.notna() & facts["h_osm_tag"].notna() & (shadow_m > 0)
    ratio = facts.loc[ok, "h_osm_tag"] / shadow_m[ok]
    k_fac = float(ratio.median()) if ok.any() else float("nan")
    facts["shadow_length_m"] = shadow_m
    facts["h_shadow"] = shadow_m * k_fac
    resid = facts.loc[ok, "h_shadow"] - facts.loc[ok, "h_osm_tag"]
    mad_sd = float(1.4826 * (resid - resid.median()).abs().median()) if ok.any() else float("nan")

    def material(row: Any) -> str:
        if row["n_px"] < 8:
            return "unknown"
        if row["share_green"] >= 0.3:
            return "green_roof"
        if row["share_terracotta"] >= 0.4:
            return "clay_tiles"
        if row["share_light_flat"] >= 0.4:
            return "flat_light"
        if row["share_dark"] >= 0.5:
            return "dark_or_shaded"
        return "mixed"

    facts["roof_material"] = facts.apply(material, axis=1)
    # Solar panels: the colour rule also catches bluish shadows (checked by eye on central tiles),
    # so no solar attribute is published until a texture-aware detector exists (gate failed).
    keep = ["id", "n_px", "share_terracotta", "share_light_flat", "share_green", "share_dark",
            "mean_r", "mean_g", "mean_b", "roof_material", "shadow_length_m", "h_shadow"]
    facts = facts[keep].drop_duplicates("id")
    facts["source"] = "agea_2023_ortho"
    facts["data_kind"] = "estimated"
    args.out.mkdir(parents=True, exist_ok=True)
    facts.to_parquet(args.out / "ortho_facts.parquet")
    summary = {
        "bbox": list(args.bbox), "tiles": len(tiles), "buildings": len(facts),
        "shadow_azimuth_deg": best_a, "spearman_shadow_vs_osm": round(best_r, 3),
        "height_per_shadow_metre": round(k_fac, 3), "sun_elevation_deg": round(float(np.degrees(np.arctan(k_fac))), 1),
        "shadow_height_buildings": int(facts["h_shadow"].notna().sum()), "shadow_vs_osm_n": int(ok.sum()),
        "shadow_vs_osm_bias_m": round(float(resid.median()), 2) if ok.any() else None, "shadow_vs_osm_sd_m": round(mad_sd, 2),
        "roof_material_shares": facts["roof_material"].value_counts(normalize=True).round(3).to_dict(),
        "seconds": round(time.time() - t0, 1),
    }
    (args.out / "ortho_facts.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
