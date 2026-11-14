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


def test_nights_follow_sealing_and_days_follow_the_forecast_and_the_canopy() -> None:
    out = run({"tmax_c": 35.5, "tmin_c": 19.0})
    assert out["status"] == "ok"
    r = out["result"]
    hot = r["hot_day"]
    assert hot["threshold_c"] == 35
    # by day sealing barely matters (Rome stations); street-level shade does: the fully wooded side drops below 35 C
    assert hot["residents"]["p50"] == 400
    assert hot["elderly_65_plus"]["p50"] == 100
    assert hot["residents"]["p5"] <= hot["residents"]["p50"] <= hot["residents"]["p95"]
    night = r["tropical_night"]
    assert night["residents"]["p50"] == 400  # only the sealed side stays above 20 C at night
    sections = {s["sez_id"]: s for s in r["sections"]}
    assert sections["W"]["tmin_c"]["p50"] > 20 > sections["E"]["tmin_c"]["p50"]
    assert out["data_kinds"]["temperature"] == "hypothetical"
    assert out["data_kinds"]["tree_cover"] == "real"
    assert out["synthetic"] is False
    assert r["hot_map_p50"]["type"] == "MultiPolygon" and r["hot_map_p50"]["coordinates"]


def test_contrast_matches_rome_stations() -> None:
    """Rome summer stations: nights warm with the sealing of the whole district, days barely differ."""
    r = run({"tmax_c": 30.0, "tmin_c": 18.0})["result"]
    sections = {s["sez_id"]: s for s in r["sections"]}
    # half-sealed district (the 2.2 km forecast cell straddles the divide): even the green side is warmer
    assert 0.0 < sections["E"]["tmin_c"]["p50"] - 18.0 < 2.5
    assert 0.5 < sections["W"]["tmin_c"]["p50"] - sections["E"]["tmin_c"]["p50"] < 3.0
    day = sections["W"]["tmax_c"]["p50"] - sections["E"]["tmax_c"]["p50"]
    assert 1.0 < day < 2.5  # canopy, not sealing: about 1.8 C from bare to full canopy (Ziter 2019)
    assert abs(sections["E"]["tmax_c"]["p50"] - 30.0) < 1.2  # no district term by day
    assert r["calibration"].startswith("stations")


def test_sealed_district_is_warmer_at_night_than_open_country(heat_layers: Path) -> None:
    raster = _raster  # uniform rasters: the whole district sealed, then open country
    raster(heat_layers / "imperviousness_2018.tif", 100, 100)
    raster(heat_layers / "tree_cover_2018.tif", 0, 0)
    sealed = run({"tmax_c": 30.0, "tmin_c": 18.0})["result"]["sections"][0]["tmin_c"]["p50"]
    raster(heat_layers / "imperviousness_2018.tif", 0, 0)
    open_country = run({"tmax_c": 30.0, "tmin_c": 18.0})["result"]["sections"][0]["tmin_c"]["p50"]
    assert 2.0 < sealed - open_country < 4.0  # Rome: about 2.9 C per 100 % district sealing


def test_planting_trees_cools_the_day_more_than_the_night() -> None:
    out = run({"tmax_c": 35.5, "tmin_c": 18.0, "plant_trees": {"where": WEST, "cover_added_pct": 80}})
    r = out["result"]
    assert r["hot_day"]["residents"]["p50"] == 400  # baseline: the wooded side is below 35 C by day
    assert r["tropical_night"]["residents"]["p50"] == 400
    what_if = r["what_if"]
    # street-level studies: canopy cools the day more than the night (Ziter 2019: >1.5 C for 0-100 % at block scale)
    assert 0.5 < what_if["cooling_night_c"]["p50"] < what_if["cooling_day_c"]["p50"] < 2.0
    assert 0.5 < what_if["cooling_night_c"]["p50"] < 1.5
    assert what_if["trees_added"] > 1000
    assert what_if["tropical_night_residents"]["p50"] <= 400
    assert what_if["residents_no_longer_tropical"]["p95"] == 400


def test_ten_points_more_canopy_cools_the_day_by_tenths_of_a_degree() -> None:
    out = run({"tmax_c": 38.0, "tmin_c": 25.0, "plant_trees": {"where": WEST, "cover_added_pct": 10}})
    day = out["result"]["what_if"]["cooling_day_c"]
    assert 0.1 <= day["p50"] <= 0.3  # "a few tenths" per +10 % canopy (Ziter 2019; Locke 2024)
    assert day["p5"] > 0


def test_forecast_temperature_picks_the_hottest_day() -> None:
    data = ScenarioData(census=CENSUS, temperature={
        "2026-07-20": [(LON0, LAT0, 30.0, 18.0, 1.0)],
        "2026-07-21": [(LON0, LAT0, 35.5, 21.0, 1.0)]})
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
    out = run({"tmax_c": 35.5, "tmin_c": 15.0}, ScenarioData(census=census))
    assert out["result"]["hot_day"]["elderly_65_plus"]["p50"] == 123  # only the bare side is above 35 C by day
