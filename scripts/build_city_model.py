"""Build the G0 city model (LoD1 blocks) for an area and tile it for the viewer.

Run from the project root:

    python scripts/build_city_model.py                     # whole city
    python scripts/build_city_model.py --bbox 12.46 41.88 12.50 41.91   # a test box

Inputs are cached under data/raw/ and outputs go to data/processed/model/ (both git-ignored):
buildings_lod1.parquet (GeoParquet, all attributes), buildings.pmtiles (viewer),
height_check.md / build.json (validation report, input and output SHA-256 hashes).
Needs the `model` extra:  pip install -e .[model]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twin.model.config import ModelConfig, load_model_config  # noqa: E402
from twin.providers.base import ROME_BBOX, BBox  # noqa: E402

RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "model"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def bbox_key(bbox: BBox) -> str:
    return hashlib.sha256(json.dumps([round(v, 5) for v in bbox]).encode()).hexdigest()[:10]


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def get_footprints(bbox: BBox, cfg: ModelConfig) -> Path:
    import pyarrow.parquet as pq

    from twin.model.sources import fetch_overture_buildings

    path = RAW / "overture" / f"buildings_{cfg.footprints.release}_{bbox_key(bbox)}.parquet"
    if not path.exists():
        log(f"Overture {cfg.footprints.release}: reading buildings from S3")
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(fetch_overture_buildings(bbox, cfg.footprints.release), path)
    return path


def get_gba(bbox: BBox) -> Path:
    from twin.model.sources import GBA_URL, gba_tile_name

    tile = gba_tile_name((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    if tile != gba_tile_name(bbox[0], bbox[1]) or tile != gba_tile_name(bbox[2], bbox[3]):
        raise SystemExit("bbox crosses a GBA 5-degree tile border; not supported yet")
    path = RAW / "gba" / f"{tile}.parquet"
    if not path.exists():
        log(f"GlobalBuildingAtlas: downloading tile {tile}")
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(GBA_URL.format(tile=tile), path)
    return path


def get_raster(kind: str, bbox: BBox) -> Path | None:
    from twin.model.sources import fetch_dem, fetch_urban_atlas_heights

    name = {"dem": "copernicus_dem_glo30", "ua": "urban_atlas_building_height"}[kind]
    path = RAW / name / f"{name}_{bbox_key(bbox)}.tif"
    if path.exists():
        return path
    log(f"{name}: clipping to the area")
    try:
        return (fetch_dem if kind == "dem" else fetch_urban_atlas_heights)(bbox, path)
    except Exception as exc:  # noqa: BLE001 - a missing layer is reported, not fatal (gate A rule)
        log(f"{name}: not available ({exc})")
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"), default=list(ROME_BBOX))
    ap.add_argument("--config", type=Path, default=ROOT / "config" / "model.yaml")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--no-tiles", action="store_true")
    args = ap.parse_args(argv)
    bbox: BBox = (args.bbox[0], args.bbox[1], args.bbox[2], args.bbox[3])
    cfg = load_model_config(args.config)
    t0 = time.time()

    import geopandas as gpd
    import pyarrow.parquet as pq

    from twin.model.lod1 import build_lod1, frame_from_overture
    from twin.model.rasters import sample_ground, sample_polygon_stat
    from twin.model.sources import read_gba
    from twin.model.tiles import write_tiles
    from twin.model.validation import class_agreement, compare_heights, render_report, source_shares

    fp_path = get_footprints(bbox, cfg)
    footprints = frame_from_overture(pq.read_table(fp_path))
    log(f"footprints: {len(footprints):,}")
    inputs: dict[str, Path | None] = {"overture_buildings": fp_path}

    gba = None
    if "gba" in cfg.heights.priority:
        inputs["gba"] = gba_path = get_gba(bbox)
        gba = read_gba(gba_path, bbox)
        log(f"GBA polygons in area: {len(gba):,}")
    ua_path = get_raster("ua", bbox) if "raster" in cfg.heights.priority else None
    dem_path = get_raster("dem", bbox)
    inputs["urban_atlas_building_height"] = ua_path
    inputs["copernicus_dem_glo30"] = dem_path

    hc, tc = cfg.heights, cfg.terrain

    def ua(g: gpd.GeoDataFrame) -> Any:
        assert ua_path is not None
        return sample_polygon_stat(ua_path, g, hc.raster_statistic, min_valid=hc.raster_min_valid)

    def ground(g: gpd.GeoDataFrame) -> Any:
        assert dem_path is not None
        return sample_ground(dem_path, g, ring_m=tc.ring_m, percentile=tc.percentile)

    model = build_lod1(
        footprints, cfg, gba=gba,
        raster_heights=ua if ua_path is not None else None,
        ground=ground if dem_path is not None else None,
    )
    log(f"model: {len(model):,} buildings")

    args.out.mkdir(parents=True, exist_ok=True)
    parquet = args.out / "buildings_lod1.parquet"
    model.to_parquet(parquet, write_covering_bbox=True)
    outputs = {"buildings_lod1.parquet": parquet}
    if not args.no_tiles:
        outputs["buildings.pmtiles"] = write_tiles(model, args.out / "buildings.pmtiles", cfg.tiles)
        log("tiles written")

    within = cfg.validation.within_m
    agreements = []
    for ref in cfg.validation.references:
        for src in ("gba", "raster", "floors"):
            if src == ref:
                continue
            if ref == "raster" and hc.raster_classes:
                agreements.append(class_agreement(
                    list(model[f"h_{src}"]), list(model["raster_low_m"]), list(model["raster_high_m"]), source=src
                ))
            else:
                agreements.append(compare_heights(
                    list(model[f"h_{src}"]), list(model[f"h_{ref}"]), source=src, reference=ref, within_m=within
                ))
    shares = source_shares(model["height_source"])
    notes = [
        "osm_tag = height measured by OpenStreetMap mappers (real). gba = GlobalBuildingAtlas machine-learning "
        "estimate (CC BY-NC 4.0, non-commercial). raster = Copernicus Urban Atlas Building Height 2012 (10 m height classes, midpoint used). "
        "floors = floor count x 3.2 m. default = 9 m placeholder.",
        "raster_class rows: share of buildings whose height falls inside their Urban Atlas class; errors are "
        "distances to the nearest class edge.",
        "GBA was built partly from OpenStreetMap, so where OSM has a height GBA may have learned from it: "
        "the GBA vs osm_tag agreement is probably optimistic (C=60).",
        "The reference heights are not ground truth either: OSM tags can be rough, Urban Atlas dates from 2012 "
        "and covers the core urban area only. The free LiDAR (G2) will be the stronger reference in the centre.",
        "Ground level comes from the Copernicus 30 m surface model (low percentile around each building).",
    ]
    if model.attrs.get("non_commercial"):
        notes.append("LICENCE: building heights include CC BY-NC 4.0 data. Non-commercial use only.")
    report = render_report(len(model), shares, agreements, notes)
    (args.out / "height_check.md").write_text(report, encoding="utf-8")

    build = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bbox": list(bbox),
        "n_buildings": len(model),
        "non_commercial": bool(model.attrs.get("non_commercial")),
        "licences": sorted(set(model["height_licence"])) + ["ODbL (footprints)"],
        "height_sources": shares,
        "agreements": [a.as_dict() for a in agreements],
        "inputs": {k: ({"file": str(p.relative_to(ROOT)), "sha256": sha256(p)} if p else None) for k, p in inputs.items()},
        "outputs": {k: {"sha256": sha256(p), "bytes": p.stat().st_size} for k, p in outputs.items()},
        "seconds": round(time.time() - t0, 1),
    }
    (args.out / "build.json").write_text(json.dumps(build, indent=2), encoding="utf-8")
    log(f"done in {build['seconds']} s -> {args.out}")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
