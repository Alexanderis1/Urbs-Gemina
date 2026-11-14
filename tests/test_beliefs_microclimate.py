"""Street-level heat: tree cover cools, sealed ground warms, on top of the forecast."""
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from twin.beliefs.config import load_specs
from twin.beliefs.grid import cell_of, cells_in_bbox
from twin.beliefs.layer import prior_layer
from twin.beliefs.microclimate import apply_microclimate, raster_mean_per_cell

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin  # noqa: E402

T0 = datetime(2026, 7, 14, 13, 0, tzinfo=timezone.utc)
WINDOW = (12.46, 41.88, 12.50, 41.91)
WEST = (12.465, 41.895)
EAST = (12.495, 41.895)


def tif(tmp_path: Path, name: str, west_value: int, east_value: int) -> Path:
    data = np.full((40, 50), west_value, dtype=np.uint8)
    data[:, 25:] = east_value
    data[0, 0] = 255  # one no-data pixel
    path = tmp_path / name
    with rasterio.open(path, "w", driver="GTiff", width=50, height=40, count=1, dtype="uint8", crs="EPSG:4326",
                       transform=from_origin(12.455, 41.915, 0.001, 0.001), nodata=255) as dst:
        dst.write(data, 1)
    return path


def test_raster_mean_per_cell(tmp_path: Path) -> None:
    cells = cells_in_bbox(WINDOW, 9)
    cover = raster_mean_per_cell(tif(tmp_path, "trees.tif", 60, 5), cells)
    assert cover[cell_of(*WEST, 9)] == pytest.approx(60, abs=1)
    assert cover[cell_of(*EAST, 9)] == pytest.approx(5, abs=1)


def test_leafy_cells_cooler_sealed_cells_warmer_with_wider_margin(tmp_path: Path) -> None:
    cells = cells_in_bbox(WINDOW, 9)
    trees = raster_mean_per_cell(tif(tmp_path, "trees.tif", 60, 5), cells)
    sealed = raster_mean_per_cell(tif(tmp_path, "imperv.tif", 10, 90), cells)
    layer = prior_layer(load_specs()["temperature"], cells, T0)
    adjusted = apply_microclimate(layer, trees, sealed)
    west, east = adjusted.belief(cell_of(*WEST, 9)), adjusted.belief(cell_of(*EAST, 9))
    base = layer.belief(cell_of(*WEST, 9))
    assert west.mean < base.mean < east.mean
    assert 1.0 < east.mean - west.mean < 6.0
    assert west.variance > base.variance
    assert any("tree cover" in c for c in adjusted.spec.caveats)
