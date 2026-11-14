"""Flash-flood watch: heavy rain now x official flood-hazard zones x road underpasses."""
import json
from datetime import datetime, timezone
from pathlib import Path

from twin.beliefs.config import load_specs
from twin.beliefs.flood import flood_watch, hazard_per_cell, underpasses_per_cell
from twin.beliefs.grid import cell_of, cells_in_bbox
from twin.beliefs.layer import assimilate, prior_layer
from twin.providers.base import Observation

T0 = datetime(2026, 11, 14, 8, 0, tzinfo=timezone.utc)
WINDOW = (12.46, 41.88, 12.50, 41.91)
WET = (12.48, 41.895)
DRY = (12.463, 41.882)


def write(tmp_path: Path, name: str, features: list[dict]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    return path


def square(lon: float, lat: float, d: float = 0.003) -> dict:
    ring = [[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d]]
    return {"type": "Polygon", "coordinates": [ring]}


def fixtures(tmp_path: Path) -> tuple[Path, Path]:
    hazard = write(tmp_path, "hazard.geojson", [
        {"type": "Feature", "properties": {"hazard": "P3"}, "geometry": square(*WET)},
        {"type": "Feature", "properties": {"hazard": "P1"}, "geometry": square(*WET, d=0.008)},
        {"type": "Feature", "properties": {"hazard": "P2"}, "geometry": square(*DRY)},
    ])
    under = write(tmp_path, "underpasses.geojson", [
        {"type": "Feature", "properties": {"name": "x"}, "geometry": {"type": "LineString", "coordinates": [[WET[0] - 0.0002, WET[1]], [WET[0] + 0.0002, WET[1]]]}},
    ])
    return hazard, under


def test_hazard_and_underpasses_per_cell(tmp_path: Path) -> None:
    hazard, under = fixtures(tmp_path)
    cells = cells_in_bbox(WINDOW, 9)
    h = hazard_per_cell(hazard, cells)
    assert h[cell_of(*WET, 9)] == "P3"  # the worst class wins
    assert h[cell_of(*DRY, 9)] == "P2"
    assert underpasses_per_cell(under, cells)[cell_of(*WET, 9)] == 1


def test_heavy_rain_on_a_risky_cell_raises_a_warning(tmp_path: Path) -> None:
    hazard, under = fixtures(tmp_path)
    cells = cells_in_bbox(WINDOW, 9)
    spec = load_specs()["rain"]
    layer = prior_layer(spec, cells, T0)
    radar = [Observation("r1", "WeatherObserved", *WET, T0, {"precipitation": 35.0}, {"precipitation": 2.0}, "dpc_radar", False),
             Observation("r2", "WeatherObserved", *DRY, T0, {"precipitation": 0.0}, {"precipitation": 0.2}, "dpc_radar", False)]
    layer = assimilate(layer, radar)
    out = flood_watch(layer, hazard_per_cell(hazard, cells), underpasses_per_cell(under, cells))
    rows = {r["cell"]: r for r in out["result"]["cells"]}
    wet = rows[cell_of(*WET, 9)]
    assert wet["level"] == "warning"
    assert wet["hazard"] == "P3" and wet["underpasses"] == 1
    assert wet["p_heavy_rain"] > 0.9
    assert cell_of(*DRY, 9) not in rows  # risky ground but no rain: nothing to say
    assert out["result"]["heavy_rain_mm_h"] > 0
    assert any("not a forecast of flooding" in w for w in out["warnings"])
