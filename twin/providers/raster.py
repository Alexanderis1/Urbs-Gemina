"""Read the cells of a GeoTIFF that fall inside a WGS84 bounding box.

Uses rasterio (GDAL). A source may be bytes (opened in memory), a local path,
or a ``/vsicurl/`` URL, in which case GDAL reads only the byte ranges of the
tiles it needs (cloud-optimised GeoTIFF) and keeps them in memory, not on disk.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from twin.providers.base import BBox
from twin.providers.geo import in_bbox

#: GDAL settings for remote range reads: no directory listing, no disk cache.
REMOTE_GDAL_ENV: dict[str, str] = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff",
    "GDAL_HTTP_MULTIRANGE": "YES",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
}


@dataclass(frozen=True)
class RasterCell:
    #: Row and column in the full raster, so ids stay stable whatever window is read.
    row: int
    col: int
    lon: float
    lat: float
    value: float


def read_cells(source: str | bytes, bbox: BBox, band: int = 1) -> list[RasterCell]:
    """Valid cells (not nodata, not NaN) whose centre lies inside ``bbox``."""
    import rasterio  # type: ignore[import-untyped]
    from rasterio.io import MemoryFile  # type: ignore[import-untyped]

    with rasterio.Env(**REMOTE_GDAL_ENV):
        if isinstance(source, bytes):
            with MemoryFile(source) as memory, memory.open() as dataset:
                return _cells(dataset, bbox, band)
        with rasterio.open(source) as dataset:
            return _cells(dataset, bbox, band)


def _cells(dataset: Any, bbox: BBox, band: int) -> list[RasterCell]:
    from rasterio.warp import transform, transform_bounds  # type: ignore[import-untyped]
    from rasterio.windows import Window, from_bounds  # type: ignore[import-untyped]

    left, bottom, right, top = transform_bounds("EPSG:4326", dataset.crs, *bbox, densify_pts=21)
    window = from_bounds(left, bottom, right, top, transform=dataset.transform)
    col_off = max(0, math.floor(window.col_off))
    row_off = max(0, math.floor(window.row_off))
    col_end = min(dataset.width, math.ceil(window.col_off + window.width))
    row_end = min(dataset.height, math.ceil(window.row_off + window.height))
    if col_end <= col_off or row_end <= row_off:
        return []
    window = Window(col_off, row_off, col_end - col_off, row_end - row_off)
    import numpy as np

    data = np.asarray(dataset.read(band, window=window), dtype="float64")
    valid = ~np.isnan(data)
    if dataset.nodata is not None:
        valid &= data != float(dataset.nodata)
    local_rows, local_cols = np.nonzero(valid)
    if local_rows.size == 0:
        return []
    rows = local_rows + row_off
    cols = local_cols + col_off
    values = data[local_rows, local_cols]
    t = dataset.transform
    xs = t.c + (cols + 0.5) * t.a + (rows + 0.5) * t.b
    ys = t.f + (cols + 0.5) * t.d + (rows + 0.5) * t.e
    lons, lats = transform(dataset.crs, "EPSG:4326", xs.tolist(), ys.tolist())
    return [
        RasterCell(int(row), int(col), round(lon, 6), round(lat, 6), float(v))
        for row, col, lon, lat, v in zip(rows.tolist(), cols.tolist(), lons, lats, values.tolist())
        if in_bbox(lon, lat, bbox)
    ]
