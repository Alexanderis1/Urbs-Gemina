"""Heatwave: local day and night temperatures from the forecast, sealed ground and tree cover."""
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from twin.scenarios import engine, layers
from twin.scenarios.data import ScenarioData
from twin.scenarios.terrain import to_utm, to_wgs84

LON0, LAT0 = 12.48, 41.90
X0, Y0 = (v[0] for v in to_utm([LON0], [LAT0]))
HALF = 3000.0  # rasters cover 6 km x 6 km around the centre


def _box(x_min: float, x_max: float, y_min: float, y_max: float) -> dict[str, Any]:
    lons, lats = to_wgs84([X0 + x_min, X0 + x_max, X0 + x_max, X0 + x_min, X0 + x_min],
                          [Y0 + y_min, Y0 + y_min, Y0 + y_max, Y0 + y_max, Y0 + y_min])
    return {"type": "Polygon", "coordinates": [[[a, b] for a, b in zip(lons, lats)]]}


AREA = _box(-2000, 2000, -1000, 1000)
WEST = _box(-600, -100, -250, 250)  # sealed side of the divide, no trees
EAST = _box(100, 600, -250, 250)    # green side: no sealing, full tree cover


def _section(sez: str, geom: dict[str, Any], residents: int, elderly: int) -> dict[str, Any]:
    return {"type": "Feature", "geometry": geom,
            "properties": {"sez_id": sez, "residents": residents, "children_0_14": 10, "elderly_65_plus": elderly}}


CENSUS = {"type": "FeatureCollection", "features": [_section("W", WEST, 400, 100), _section("E", EAST, 300, 80)]}


def _raster(path: Path, west_value: int, east_value: int) -> None:
    import rasterio
    from rasterio.transform import from_origin

    n = int(2 * HALF / 20)
    band = np.full((n, n), east_value, dtype="uint8")
    band[:, : n // 2] = west_value
    with rasterio.open(path, "w", driver="GTiff", width=n, height=n, count=1, dtype="uint8", nodata=255,
                       crs="EPSG:32633", transform=from_origin(X0 - HALF, Y0 + HALF, 20, 20)) as dst:
        dst.write(band, 1)


@pytest.fixture(autouse=True)
def heat_layers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _raster(tmp_path / "imperviousness_2018.tif", 100, 0)
    _raster(tmp_path / "tree_cover_2018.tif", 0, 100)
    monkeypatch.setattr(layers, "search_dirs", lambda: [tmp_path])
    return tmp_path


def run(change: dict[str, Any], data: ScenarioData | None = None) -> dict[str, Any]:
    return engine.run("heatwave", AREA, change, data=data or ScenarioData(census=CENSUS), use_cache=False)


def test_sealed_ground_is_hotter_than_trees() -> None:
    out = run({"tmax_c": 34.0, "tmin_c": 19.0})
    assert out["status"] == "ok"
    r = out["result"]
    hot = r["hot_day"]
    assert hot["threshold_c"] == 35
    assert hot["residents"]["p50"] == 400
    assert hot["elderly_65_plus"]["p50"] == 100
    assert hot["residents"]["p5"] <= hot["residents"]["p50"] <= hot["residents"]["p95"]
    night = r["tropical_night"]
    assert night["residents"]["p50"] == 400
    sections = {s["sez_id"]: s for s in r["sections"]}
    assert sections["W"]["tmax_c"]["p50"] > 35 > 33 > sections["E"]["tmax_c"]["p50"]
    assert out["data_kinds"]["temperature"] == "hypothetical"
    assert out["data_kinds"]["tree_cover"] == "real"
    assert out["synthetic"] is False
    assert r["hot_map_p50"]["type"] == "MultiPolygon" and r["hot_map_p50"]["coordinates"]


def test_planting_trees_cools_the_sealed_side() -> None:
    out = run({"tmax_c": 34.0, "tmin_c": 15.0, "plant_trees": {"where": WEST, "cover_added_pct": 80}})
    r = out["result"]
    assert r["hot_day"]["residents"]["p50"] == 400  # baseline
    what_if = r["what_if"]
    assert what_if["hot_day_residents"]["p50"] == 0
    assert what_if["cooling_day_c"]["p50"] > 2
    assert what_if["trees_added"] > 1000
    assert what_if["residents_no_longer_hot"]["p50"] == 400


def test_forecast_temperature_picks_the_hottest_day() -> None:
    data = ScenarioData(census=CENSUS, temperature={
        "2026-07-20": [(LON0, LAT0, 30.0, 18.0, 1.0)],
        "2026-07-21": [(LON0, LAT0, 33.5, 21.0, 1.0)]})
    out = run({"temperature": "forecast"}, data)
    assert out["result"]["day"] == "2026-07-21"
    assert out["data_kinds"]["temperature"] == "estimated"
    assert out["result"]["hot_day"]["residents"]["p50"] == 400


def test_no_forecast_is_not_available() -> None:
    out = run({"temperature": "forecast"})
    assert out["status"] == "not_available"


def test_elderly_counts_are_joined_from_the_ages_file(heat_layers: Path) -> None:
    (heat_layers / "census_ages.csv").write_text("sez_id,elderly_65_plus,elderly_75_plus\nW,123,50\nE,7,2\n")
    census = {"type": "FeatureCollection",
              "features": [_section("W", WEST, 400, 0), _section("E", EAST, 300, 0)]}
    for f in census["features"]:
        del f["properties"]["elderly_65_plus"]
    out = run({"tmax_c": 34.0, "tmin_c": 15.0}, ScenarioData(census=census))
    assert out["result"]["hot_day"]["elderly_65_plus"]["p50"] == 123
