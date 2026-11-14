"""Per-cell night-time heat island for the street temperature layer (air_temperature).

    python scripts/build_heat_island.py [--out /mnt/project-files/model/heat_island_night.csv]

Inputs (real, open): Copernicus HRL Imperviousness Density 2018 and Tree Cover Density 2018, 20 m
(imperviousness_2018.tif, tree_cover_2018.tif from scripts/fetch_heat_layers.py). For every H3 cell of
the city grid it takes the cell's own share (100 m around the centre) and its district share (2.2 km,
the forecast's grid spacing), then applies the heatwave scenario's night coefficients
(config/scenarios.yaml, fitted on 17 ASTI stations and checked on the Regione Lazio thermometers).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import numpy.typing as npt
import yaml

from twin.beliefs.grid import cell_center, cells_in_bbox
from twin.beliefs.landuse import night_heat_island

RASTER_DIRS = (Path("data/processed"), Path("/mnt/project-files/data/processed"))


def _find(name: str) -> Path:
    for d in RASTER_DIRS:
        if (d / name).exists():
            return d / name
    raise FileNotFoundError(f"{name} not found in {[str(d) for d in RASTER_DIRS]} (run scripts/fetch_heat_layers.py)")


def _mean_filter(a: npt.NDArray[np.float64], size: int) -> npt.NDArray[np.float64]:
    """Mean over a size x size window, ignoring missing pixels."""
    from scipy.ndimage import uniform_filter  # type: ignore[import-untyped]

    ok = np.isfinite(a)
    total = uniform_filter(np.where(ok, a, 0.0), size=size, mode="nearest")
    count = uniform_filter(ok.astype(np.float64), size=size, mode="nearest")
    out: npt.NDArray[np.float64] = np.where(count > 0, total / np.maximum(count, 1e-12), np.nan)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="/mnt/project-files/model/heat_island_night.csv")
    args = p.parse_args()

    import rasterio  # type: ignore[import-untyped]
    from pyproj import Transformer

    heat = yaml.safe_load(Path("config/scenarios.yaml").read_text(encoding="utf-8"))["heatwave"]
    night = heat["coefficients"]["value"]["night"]
    district_m = float(heat["forecast_scale_m"]["value"])
    cell_m = float(heat["cell_m"]["value"])

    shares: dict[str, tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]] = {}
    transform = crs = None
    for key, name in (("imp", "imperviousness_2018.tif"), ("trees", "tree_cover_2018.tif")):
        with rasterio.open(_find(name)) as src:
            raw = src.read(1).astype(np.float64)
            raw[(raw == src.nodata) | (raw > 100)] = np.nan
            share = raw / 100.0
            px = abs(src.res[0])
            transform, crs = src.transform, src.crs
        shares[key] = (_mean_filter(share, max(1, round(cell_m / px))), _mean_filter(share, max(1, round(district_m / px))))

    areas = yaml.safe_load(Path("config/areas.yaml").read_text(encoding="utf-8"))
    cells = cells_in_bbox(tuple(areas["city"]["bbox"]), int(areas["grid"]["city_resolution"]))
    centres = [cell_center(c) for c in cells]
    to_raster = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    xs, ys = to_raster.transform([c[0] for c in centres], [c[1] for c in centres])
    rows, cols = rasterio.transform.rowcol(transform, xs, ys)
    rows, cols = np.asarray(rows), np.asarray(cols)
    imp, imp_nb = shares["imp"]
    trees, trees_nb = shares["trees"]
    inside = (rows >= 0) & (rows < imp.shape[0]) & (cols >= 0) & (cols < imp.shape[1])
    r, c = np.where(inside, rows, 0), np.where(inside, cols, 0)
    uhi = night_heat_island(imp[r, c], imp_nb[r, c], trees[r, c], trees_nb[r, c],
                            city=float(night["impervious_city"][0]), local=float(night["impervious"][0]),
                            tree=float(night["trees"][0]))
    uhi = np.where(inside & np.isfinite(uhi), uhi, np.nan)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    with out.open("w", encoding="utf-8") as f:
        f.write("cell,value\n")
        for cell, v in zip(cells, uhi):
            if np.isfinite(v):
                f.write(f"{cell},{v:.2f}\n")
                kept += 1
    vals = uhi[np.isfinite(uhi)]
    print(f"{kept} of {len(cells)} cells -> {out}; heat island at night: median {np.median(vals):.2f}, "
          f"P5 {np.percentile(vals, 5):.2f}, P95 {np.percentile(vals, 95):.2f}, max {vals.max():.2f} degC")


if __name__ == "__main__":
    main()
