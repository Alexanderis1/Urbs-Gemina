"""ArcGIS REST sources: feature layers queried by bbox (ISPRA flood hazard) and image
services exported as a Cloud Optimized GeoTIFF (Copernicus imperviousness)."""
import io
import json
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import pytest

gpd = pytest.importorskip("geopandas")
np = pytest.importorskip("numpy")
rasterio = pytest.importorskip("rasterio")

from twin.ingest.catalog import load_catalog  # noqa: E402
from twin.ingest.http import HttpRequest  # noqa: E402
from twin.ingest.static import ingest_layer  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CATALOG = load_catalog(ROOT / "config" / "ingest.yaml")
NOW = datetime(2026, 11, 13, 23, 30, tzinfo=timezone.utc)


def square(x: float, y: float, d: float = 0.01) -> dict[str, object]:
    return {"type": "Polygon", "coordinates": [[[x, y], [x + d, y], [x + d, y + d], [x, y + d], [x, y]]]}


def test_flood_hazard_merges_scenarios_and_pages(tmp_path: Path) -> None:
    calls: list[dict[str, list[str]]] = []

    def fetch(request: HttpRequest) -> bytes:
        url = urllib.parse.urlparse(request.url)
        query = urllib.parse.parse_qs(url.query)
        calls.append(query)
        layer = url.path.split("/")[-2]
        offset = int(query["resultOffset"][0])
        assert query["outSR"] == ["4326"] and query["f"] == ["geojson"]
        if layer == "0" and offset == 0:  # P3: a full page, so the next page is asked for
            features = [{"type": "Feature", "id": i, "geometry": square(12.4, 41.8),
                         "properties": {"objectid": i, "scenario": "P3"}} for i in range(2)]
            return json.dumps({"type": "FeatureCollection", "features": features,
                               "properties": {"exceededTransferLimit": True}}).encode()
        if layer == "1" and offset == 0:
            return json.dumps({"type": "FeatureCollection", "features": [
                {"type": "Feature", "id": 9, "geometry": square(12.5, 41.9), "properties": {"objectid": 9}}]}).encode()
        return json.dumps({"type": "FeatureCollection", "features": []}).encode()

    entry = ingest_layer(CATALOG.layers["flood_hazard_pgra"], CATALOG, fetch, tmp_path, NOW)
    assert entry["status"] == "ok", entry.get("error")
    frame = gpd.read_parquet(tmp_path / "flood_hazard_pgra.parquet")
    assert sorted(frame["hazard"]) == ["P2", "P3", "P3"]
    assert set(frame["source"]) == {"ISPRA mosaic v5.0 (2020)"}
    assert set(frame["data_kind"]) == {"real"}
    assert {"hazard", "source", "data_kind", "geometry"} <= set(frame.columns)
    assert sum(1 for q in calls if q["resultOffset"] == ["1000"]) == 1  # only P3 needed a second page


def test_imperviousness_is_written_as_a_clipped_cog(tmp_path: Path) -> None:
    def fetch(request: HttpRequest) -> bytes:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(request.url).query)
        width, height = (int(v) for v in query["size"][0].split(","))
        west, south, east, north = (float(v) for v in query["bbox"][0].split(","))
        data = np.full((1, height, width), 40, dtype="uint8")
        data[0, 0, 0] = 255  # outside Europe / no data
        buffer = io.BytesIO()
        transform = rasterio.transform.from_bounds(west, south, east, north, width, height)
        with rasterio.open(buffer, "w", driver="GTiff", width=width, height=height, count=1, dtype="uint8",
                           crs=f"EPSG:{query['imageSR'][0]}", transform=transform) as out:
            out.write(data)
        return buffer.getvalue()

    entry = ingest_layer(CATALOG.layers["imperviousness_2018"], CATALOG, fetch, tmp_path, NOW)
    assert entry["status"] == "ok", entry.get("error")
    path = tmp_path / "imperviousness_2018.tif"
    assert entry["files"]["cog"]["path"].endswith("imperviousness_2018.tif")
    with rasterio.open(path) as raster:
        assert raster.crs.to_epsg() == 3035
        assert raster.res == (20.0, 20.0)
        assert raster.nodata == 255
        values = raster.read(1)
        assert set(np.unique(values)) <= {40, 255}
        assert raster.overviews(1)  # cloud optimised: has overviews
    assert entry["value_range"] == [0, 100] and entry["units"] == "percent sealed"
