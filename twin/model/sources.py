"""Download / read the inputs of the city model for a bounding box.

Network access: Overture and Copernicus DEM on AWS S3, GBA on Source Cooperative,
Urban Atlas Building Height on the EEA ImageServer.
"""
from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Any

from twin.providers.base import BBox

OVERTURE_BUCKET = "overturemaps-us-west-2"
GBA_URL = "https://data.source.coop/tge-labs/globalbuildingatlas-lod1/{tile}.parquet"
DEM_URL = (
    "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{lat}_00_{lon}_00_DEM/"
    "Copernicus_DSM_COG_10_{lat}_00_{lon}_00_DEM.tif"
)
#: EEA ImageServer for Urban Atlas Building Height 2012 (public, no login; serves height classes).
UA_SERVICE = (
    "https://copernicus.discomap.eea.europa.eu/arcgis/rest/services/UrbanAtlas/UA_BuildingHeights_2012_10m/ImageServer"
)
OVERTURE_COLUMNS = ["id", "height", "num_floors", "is_underground", "class", "subtype", "geometry", "bbox"]


def _bbox_filter(bbox: BBox) -> Any:
    import pyarrow.compute as pc

    def f(k: str) -> Any:
        return pc.field(("bbox", k))

    xmin, ymin, xmax, ymax = bbox
    return (f("xmin") < xmax) & (f("xmax") > xmin) & (f("ymin") < ymax) & (f("ymax") > ymin)


def fetch_overture_buildings(bbox: BBox, release: str) -> Any:
    """Overture buildings intersecting ``bbox`` as an Arrow table (anonymous S3 read)."""
    import pyarrow.dataset as ds
    import pyarrow.fs as pafs

    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    kwargs: dict[str, Any] = {"anonymous": True, "region": "us-west-2"}
    if proxy:
        kwargs["proxy_options"] = proxy
    fs = pafs.S3FileSystem(**kwargs)
    path = f"{OVERTURE_BUCKET}/release/{release}/theme=buildings/type=building/"
    dataset = ds.dataset(path, filesystem=fs, format="parquet")
    return dataset.to_table(columns=OVERTURE_COLUMNS, filter=_bbox_filter(bbox)).drop_columns(["bbox"])


def gba_tile_name(lon: float, lat: float) -> str:
    """GBA 5-degree tile containing a point, e.g. (12.5, 41.9) -> e010_n45_e015_n40."""
    x0 = int(math.floor(lon / 5.0) * 5)
    y1 = int(math.floor(lat / 5.0) * 5 + 5)

    def ew(v: int) -> str:
        return f"{'e' if v >= 0 else 'w'}{abs(v):03d}"

    def ns(v: int) -> str:
        return f"{'n' if v >= 0 else 's'}{abs(v):02d}"

    return f"{ew(x0)}_{ns(y1)}_{ew(x0 + 5)}_{ns(y1 - 5)}"


def read_gba(path: Path, bbox: BBox) -> Any:
    """GBA LoD1 polygons with height and variance inside ``bbox`` (GeoDataFrame, WGS84)."""
    import geopandas as gpd
    import numpy as np
    import pyarrow.dataset as ds
    import shapely

    table = ds.dataset(str(path), format="parquet").to_table(
        columns=["height", "var", "geometry"], filter=_bbox_filter(bbox)
    )
    geoms = shapely.from_wkb(np.asarray(table.column("geometry").to_pylist(), dtype=object))
    df = table.drop_columns(["geometry"]).to_pandas()
    for col in ("height", "var"):
        df.loc[df[col] <= -999.0, col] = np.nan
    return gpd.GeoDataFrame(df, geometry=geoms, crs="EPSG:4326")


def dem_tile_urls(bbox: BBox) -> list[str]:
    """Copernicus GLO-30 1-degree tiles covering ``bbox``."""
    urls = []
    for lat in range(math.floor(bbox[1]), math.floor(bbox[3]) + 1):
        for lon in range(math.floor(bbox[0]), math.floor(bbox[2]) + 1):
            la = f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}"
            lo = f"{'E' if lon >= 0 else 'W'}{abs(lon):03d}"
            urls.append(DEM_URL.format(lat=la, lon=lo))
    return urls


def _clip_to_file(sources: list[str], bbox: BBox, dst: Path, *, nodata: float | None) -> Path:
    import rasterio
    from rasterio.merge import merge
    from rasterio.warp import transform_bounds

    dst.parent.mkdir(parents=True, exist_ok=True)
    handles = [rasterio.open(s) for s in sources]
    try:
        bounds = transform_bounds("EPSG:4326", handles[0].crs, *bbox)
        data, transform = merge(handles, bounds=bounds, nodata=nodata)
        profile = handles[0].profile
        profile.update(
            driver="GTiff", height=data.shape[1], width=data.shape[2], transform=transform,
            compress="deflate", tiled=True, blockxsize=256, blockysize=256, nodata=nodata, count=1,
        )
        with rasterio.open(dst, "w", **profile) as out:
            out.write(data[0], 1)
    finally:
        for h in handles:
            h.close()
    return dst


def fetch_dem(bbox: BBox, dst: Path) -> Path:
    """Clip the Copernicus GLO-30 surface model to ``bbox`` (EPSG:4326 grid, metres)."""
    import rasterio

    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        return _clip_to_file([f"/vsicurl/{u}" for u in dem_tile_urls(bbox)], bbox, dst, nodata=-9999.0)


def fetch_urban_atlas_heights(bbox: BBox, dst: Path, *, chunk_px: int = 2000, retries: int = 4) -> Path:
    """Urban Atlas Building Height 2012 height classes (10 m, EPSG:3035) for ``bbox`` as one GeoTIFF.

    Read from the EEA ImageServer in chunks (the server caps one image at 15000 x 4100 px).
    Cell values are class codes 1-10 (see config/model.yaml); 0 = no building.
    """
    import urllib.request

    import numpy as np
    import rasterio
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin
    from rasterio.warp import transform_bounds

    x0, y0, x1, y1 = transform_bounds("EPSG:4326", "EPSG:3035", *bbox)
    res = 10.0
    x0, y1 = math.floor(x0 / res) * res, math.ceil(y1 / res) * res
    width, height = int(math.ceil((x1 - x0) / res)), int(math.ceil((y1 - y0) / res))
    mosaic = np.zeros((height, width), dtype="uint16")
    for r in range(0, height, chunk_px):
        for c in range(0, width, chunk_px):
            w, h = min(chunk_px, width - c), min(chunk_px, height - r)
            cx0, cy1 = x0 + c * res, y1 - r * res
            url = (
                f"{UA_SERVICE}/exportImage?bbox={cx0},{cy1 - h * res},{cx0 + w * res},{cy1}"
                f"&bboxSR=3035&imageSR=3035&size={w},{h}&format=tiff&pixelType=U16"
                "&interpolation=RSP_NearestNeighbor&f=image"
            )
            payload = b""
            for attempt in range(retries):
                try:
                    with urllib.request.urlopen(url, timeout=300) as resp:
                        payload = resp.read()
                    break
                except OSError:
                    if attempt == retries - 1:
                        raise
                    time.sleep(2 ** (attempt + 1))
            with MemoryFile(payload) as mem, mem.open() as src:
                block = src.read(1)
            block[block == 65535] = 0
            mosaic[r : r + h, c : c + w] = block[:h, :w]
    dst.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        dst, "w", driver="GTiff", height=height, width=width, count=1, dtype="uint16", crs="EPSG:3035",
        transform=from_origin(x0, y1, res, res), nodata=0, compress="deflate", tiled=True,
        blockxsize=256, blockysize=256,
    ) as out:
        out.write(mosaic, 1)
    return dst
