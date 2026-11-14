"""Building heights and ground level from the MASE airborne LiDAR (DSM First + DTM, 1 m, 2008-2011).

Two steps, run from the project root:
  python scripts/build_lidar.py fetch [--bbox W S E N]    download the surveyed 1 km tiles
  python scripts/build_lidar.py heights                   per-building roof height and ground level
Downloads go to data/raw/mase_lidar/<layer>/; the output is data/processed/model/lidar_heights.parquet
(one row per building id), joined into the city model by build_city_model.py.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from twin.model.lidar import chunked, footprint_heights, public_download_url, tile_payload  # noqa: E402

OUT = ROOT / "data" / "processed" / "model"
CACHE = ROOT / "data" / "raw" / "mase_lidar"
ROME = (12.23, 41.65, 12.86, 42.10)


def log(msg: str) -> None:
    print(msg, flush=True)


def http(url: str, data: bytes | None = None, *, timeout: int = 120, retries: int = 4) -> bytes:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body: bytes = r.read()
                return body
        except OSError:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** (attempt + 2))
    raise AssertionError("unreachable")


def grid_tiles(cfg: dict[str, Any], bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    geom = json.dumps({"xmin": bbox[0], "ymin": bbox[1], "xmax": bbox[2], "ymax": bbox[3], "spatialReference": {"wkid": 4326}})
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        q = urllib.parse.urlencode({
            "where": "risoluzion=1", "geometry": geom, "geometryType": "esriGeometryEnvelope", "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "outFields": "fid,tavola,regione,contratto,risoluzion,x1,y1",
            "returnGeometry": "false", "resultOffset": offset, "resultRecordCount": 1000, "f": "json",
        })
        d = json.loads(http(f"{cfg['grid']}/query?{q}"))
        feats = [f["attributes"] for f in d.get("features", [])]
        rows += feats
        if not d.get("exceededTransferLimit") or not feats:
            return rows
        offset += len(feats)


def have(layer: str, tavola: str) -> bool:
    return any((CACHE / layer).glob(f"*_{tavola}_*.tif*"))


def fetch_batch(cfg: dict[str, Any], layer: str, tiles: list[dict[str, str]]) -> int:
    payload = {"canale": cfg["canale"], "prodotto": cfg["prodotto"], "layer": layer, "tileList": tiles, "metadataList": []}
    backend = str(cfg["backend"]).rstrip("/")
    resp = json.loads(http(f"{backend}/core/api/esri/api/v1/downloads", json.dumps(payload).encode()))
    sid = resp.get("idSessione")
    if resp.get("reason") != "OK" or not sid:
        raise RuntimeError(f"download request refused: {resp}")
    status: dict[str, Any] = {}
    for _ in range(240):
        status = json.loads(http(f"{backend}/core/api/esri/api/v1/downloads/{sid}"))
        if status.get("status") != "pending":
            break
        time.sleep(10)
    if status.get("status") != "ready":
        raise RuntimeError(f"download not ready: {status}")
    n = 0
    (CACHE / layer).mkdir(parents=True, exist_ok=True)
    for raw in status.get("urls", []):
        data = http(public_download_url(raw, backend), timeout=900)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                if name.lower().endswith((".tif", ".tiff")):
                    (CACHE / layer / Path(name).name).write_bytes(z.read(name))
                    n += 1
    return n


def cmd_fetch(cfg: dict[str, Any], bbox: tuple[float, float, float, float]) -> None:
    tiles = tile_payload(grid_tiles(cfg, bbox))
    log(f"{len(tiles)} surveyed tiles in the area")
    for kind, layer in cfg["layers"].items():
        todo = [t for t in tiles if not have(layer, t["tavola"])]
        log(f"{kind} ({layer}): {len(todo)} to download")
        batches = chunked(todo, int(cfg["max_tiles_per_request"]))
        with ThreadPoolExecutor(max_workers=int(cfg.get("parallel_requests", 1))) as pool:
            futures = {pool.submit(fetch_batch, cfg, layer, b): i for i, b in enumerate(batches)}
            for done, fut in enumerate(as_completed(futures)):
                try:
                    n = fut.result()
                except (OSError, RuntimeError) as exc:
                    log(f"{kind}: batch {futures[fut] + 1} failed ({exc}); rerun fetch to retry")
                    continue
                log(f"{kind}: {done + 1}/{len(batches)} batches, {n} files")


def cmd_heights(cfg: dict[str, Any]) -> None:
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import rasterio
    from rasterio.features import rasterize

    t0 = time.time()
    model = gpd.read_parquet(OUT / "buildings_lod1.parquet", columns=["id", "geometry"])
    model = model.to_crs(4326) if model.crs is not None and model.crs.to_epsg() != 4326 else model
    pts = model.geometry.representative_point()
    dsm_dir, dtm_dir = CACHE / cfg["layers"]["dsm"], CACHE / cfg["layers"]["dtm"]
    rows = []
    dsm_files = sorted(dsm_dir.glob("*.tif*"))
    for k, dsm_path in enumerate(dsm_files):
        tavola = "_".join(dsm_path.stem.split("_")[2:4])
        dtm_match = sorted(dtm_dir.glob(f"*_{tavola}_*.tif*"))
        if not dtm_match:
            continue
        with rasterio.open(dsm_path) as ds, rasterio.open(dtm_match[0]) as dt:
            b = ds.bounds
            inside = (pts.x >= b.left) & (pts.x < b.right) & (pts.y > b.bottom) & (pts.y <= b.top)
            sub = model[inside.to_numpy()]
            if sub.empty:
                continue
            dsm = ds.read(1, masked=True).filled(np.nan).astype("float64")
            dtm = dt.read(1, masked=True, window=dt.window(*b), boundless=True).filled(np.nan).astype("float64")
            if dtm.shape != dsm.shape:
                continue
            for arr, nod in ((dsm, ds.nodata), (dtm, dt.nodata)):
                if nod is not None:
                    arr[arr == nod] = np.nan
            labels = rasterize(
                ((g, i + 1) for i, g in enumerate(sub.geometry)), out_shape=dsm.shape, transform=ds.transform,
                fill=0, dtype="int32",
            )
            h, g, npx = footprint_heights(
                dsm - dtm, dtm, labels, n=len(sub), quantile=float(cfg["quantile"]), min_px=int(cfg["min_px"])
            )
            rows.append(pd.DataFrame({"id": sub["id"].to_numpy(), "h_lidar_raw": h, "ground_lidar_m": g, "n_px_lidar": npx}))
        if (k + 1) % 50 == 0:
            log(f"heights: {k + 1}/{len(dsm_files)} tiles")
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["id", "h_lidar_raw", "ground_lidar_m", "n_px_lidar"])
    out = out.sort_values("n_px_lidar", ascending=False).drop_duplicates("id")
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT / "lidar_heights.parquet", index=False)
    h = out["h_lidar_raw"].to_numpy(dtype="float64")
    summary = {
        "tiles": len(dsm_files), "buildings_measured": int(np.isfinite(h).sum()),
        "height_m_p50": float(np.nanmedian(h)) if np.isfinite(h).any() else None,
        "survey": cfg["survey"], "licence": "CC BY 4.0 (MASE)", "seconds": round(time.time() - t0, 1),
    }
    (OUT / "lidar_heights.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(json.dumps(summary, indent=2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("step", choices=["fetch", "heights"])
    ap.add_argument("--bbox", type=float, nargs=4, default=list(ROME), metavar=("W", "S", "E", "N"))
    args = ap.parse_args(argv)
    cfg = yaml.safe_load(open(ROOT / "config" / "model.yaml", encoding="utf-8"))["lidar"]
    if args.step == "fetch":
        cmd_fetch(cfg, (args.bbox[0], args.bbox[1], args.bbox[2], args.bbox[3]))
    else:
        cmd_heights(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
