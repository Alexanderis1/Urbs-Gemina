"""Bare-earth terrain (DTM) for Roma Capitale from Copernicus DEM GLO-30, as a Cloud-Optimised GeoTIFF.

GLO-30 is a surface model (roofs and trees included). A low-percentile filter
over a window wider than a city block removes most buildings; the result is
labelled ``estimated``. Output: data/processed/dtm_glo30_ground.tif
(EPSG:4326, heights in metres above the EGM2008 geoid, about 30 m pixels).

Usage: python scripts/build_dtm.py [--out PATH]
Source: s3://copernicus-dem-30m (public, no sign-in). Copernicus DEM (c) DLR / Airbus, ESA licence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

BBOX = (12.234, 41.655, 12.856, 42.141)  # Roma Capitale, same as the city model
TILES = ("N41_00_E012_00", "N42_00_E012_00")
URL = "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{t}_DEM/Copernicus_DSM_COG_10_{t}_DEM.tif"
WINDOW_PX = 5        # 5 x 30 m = 150 m, wider than a Roman block
PERCENTILE = 10.0


def ground_filter(dsm: np.ndarray[Any, Any], window: int = WINDOW_PX,
                  percentile: float = PERCENTILE) -> np.ndarray[Any, Any]:
    """Low percentile in a moving window, then a mean of the same size to smooth the steps."""
    from scipy import ndimage  # type: ignore[import-untyped]

    low = ndimage.percentile_filter(dsm, percentile, size=window, mode="nearest")
    out: np.ndarray[Any, Any] = ndimage.uniform_filter(low, size=window, mode="nearest")
    return np.asarray(np.minimum(out, dsm))


def main() -> None:
    import rasterio  # type: ignore[import-untyped]
    from rasterio.merge import merge  # type: ignore[import-untyped]

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/processed/dtm_glo30_ground.tif")
    args = parser.parse_args()
    sources = [rasterio.open(URL.format(t=t)) for t in TILES]
    mosaic, transform = merge(sources, bounds=BBOX)
    dsm = mosaic[0].astype("float32")
    dtm = ground_filter(dsm).astype("float32")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    profile = {"driver": "COG", "dtype": "float32", "count": 1, "height": dtm.shape[0], "width": dtm.shape[1],
               "crs": "EPSG:4326", "transform": transform, "compress": "deflate", "nodata": -9999.0}
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(dtm, 1)
        dst.update_tags(data_kind="estimated", source="Copernicus DEM GLO-30 (DSM)",
                        method=f"{PERCENTILE:g}th percentile over {WINDOW_PX}x{WINDOW_PX} px, then mean filter",
                        vertical_datum="EGM2008", licence="Copernicus DEM licence (free, attribution)")
    meta = {"file": out.name, "crs": "EPSG:4326", "vertical_datum": "EGM2008", "pixel_deg": abs(transform.a),
            "shape": list(dtm.shape), "data_kind": "estimated",
            "vertical_accuracy": "GLO-30 absolute LE90 < 4 m in open ground (Copernicus DEM validation report); "
                                 "worse in dense built-up areas after building removal",
            "min_m": float(np.nanmin(dtm)), "max_m": float(np.nanmax(dtm))}
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
