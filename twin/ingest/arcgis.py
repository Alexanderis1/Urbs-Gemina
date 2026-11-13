"""ArcGIS REST sources.

* ``arcgis_features``: a MapServer whose sub-layers are queried with the city bbox,
  page by page, as GeoJSON in EPSG:4326. Each sub-layer can stand for one class
  (e.g. ISPRA flood scenarios P3, P2, P1), written to a field named in the config.
* ``arcgis_image``: an ImageServer exported over the city bbox in a projected CRS at a
  fixed pixel size and written as a Cloud Optimized GeoTIFF.
"""
from __future__ import annotations

import io
import json
import math
import urllib.parse
from pathlib import Path
from typing import Any

from twin.ingest.catalog import BBox, LayerSpec
from twin.ingest.http import Fetch, HttpRequest

PAGE = 1000
MAX_PAGES = 200


def _query_url(base: str, sublayer: int, bbox: BBox, offset: int) -> str:
    params = {
        "where": "1=1",
        "geometry": ",".join(str(v) for v in bbox),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "outSR": "4326",
        "returnGeometry": "true",
        "resultOffset": str(offset),
        "resultRecordCount": str(PAGE),
        "orderByFields": "objectid",
        "f": "geojson",
    }
    return f"{base.rstrip('/')}/{sublayer}/query?" + urllib.parse.urlencode(params)


def query_features(layer: LayerSpec, base: str, bbox: BBox, fetch: Fetch) -> tuple[list[dict[str, Any]], list[str]]:
    """All features of every configured sub-layer inside bbox. Returns (features, URLs used)."""
    options = layer.options
    sublayers: dict[str, int] = {str(k): int(v) for k, v in (options.get("sublayers") or {}).items()}
    class_field = str(options.get("class_field", "class"))
    constants: dict[str, Any] = dict(options.get("constants") or {})
    features: list[dict[str, Any]] = []
    urls: list[str] = []
    for label, sublayer in sublayers.items():
        for page in range(MAX_PAGES):
            url = _query_url(base, sublayer, bbox, page * PAGE)
            urls.append(url)
            payload = json.loads(fetch(HttpRequest(url, timeout_s=300.0)))
            if "error" in payload:
                raise ValueError(f"ArcGIS error on sub-layer {sublayer}: {payload['error']}")
            batch = payload.get("features") or []
            for feature in batch:
                properties = {**(feature.get("properties") or {}), class_field: label, **constants}
                features.append({**feature, "properties": properties})
            more = bool((payload.get("properties") or {}).get("exceededTransferLimit")) \
                or bool(payload.get("exceededTransferLimit"))
            if not batch or (len(batch) < PAGE and not more):
                break
        else:
            raise ValueError(f"sub-layer {sublayer} has more than {MAX_PAGES * PAGE} features")
    return features, urls


def _projected_bounds(bbox: BBox, epsg: int, pixel: float) -> tuple[float, float, float, float]:
    from pyproj import Transformer  # type: ignore[import-untyped,import-not-found,unused-ignore]

    west, south, east, north = bbox
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    xs, ys = [], []
    for lon in (west, east):
        for lat in (south, (south + north) / 2, north):
            x, y = transformer.transform(lon, lat)
            xs.append(x)
            ys.append(y)
    # Snap outwards to the pixel grid so repeated runs give the same grid.
    return (math.floor(min(xs) / pixel) * pixel, math.floor(min(ys) / pixel) * pixel,
            math.ceil(max(xs) / pixel) * pixel, math.ceil(max(ys) / pixel) * pixel)


def export_image(layer: LayerSpec, base: str, bbox: BBox, fetch: Fetch, out_path: Path) -> dict[str, Any]:
    """Export the image over bbox and write it as a COG. Returns details for the manifest."""
    import numpy as np  # type: ignore[import-untyped,import-not-found,unused-ignore]
    import rasterio  # type: ignore[import-untyped,import-not-found,unused-ignore]

    options = layer.options
    epsg = int(options.get("epsg", 3035))
    pixel = float(options.get("pixel_m", 20))
    nodata = int(options.get("nodata", 255))
    west, south, east, north = _projected_bounds(bbox, epsg, pixel)
    width, height = int(round((east - west) / pixel)), int(round((north - south) / pixel))
    params = {
        "bbox": f"{west},{south},{east},{north}",
        "bboxSR": str(epsg),
        "imageSR": str(epsg),
        "size": f"{width},{height}",
        "format": "tiff",
        "pixelType": str(options.get("pixel_type", "U8")),
        "noData": str(nodata),
        "interpolation": "RSP_NearestNeighbor",
        "f": "image",
    }
    url = f"{base.rstrip('/')}/exportImage?" + urllib.parse.urlencode(params)
    raw = fetch(HttpRequest(url, timeout_s=600.0))
    with rasterio.open(io.BytesIO(raw)) as source:
        data = source.read(1)
        if source.width != width or source.height != height:
            raise ValueError(f"server returned {source.width}x{source.height}, asked for {width}x{height}")
    low, high = (int(v) for v in options.get("value_range", [0, 255]))
    data = np.where((data >= low) & (data <= high), data, nodata).astype("uint8")
    transform = rasterio.transform.from_bounds(west, south, east, north, width, height)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", driver="COG", width=width, height=height, count=1, dtype="uint8",
                       crs=f"EPSG:{epsg}", transform=transform, nodata=nodata, compress="deflate",
                       overview_resampling="average") as out:
        out.write(data, 1)
    return {"request_url": url, "raw": raw, "width": width, "height": height,
            "bounds": [west, south, east, north], "crs": f"EPSG:{epsg}", "pixel_m": pixel}
