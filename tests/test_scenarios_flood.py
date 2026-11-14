"""River and rain flooding on small synthetic terrains (no network, no shared files)."""
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from twin.scenarios import engine, layers
from twin.scenarios.data import ScenarioData
from twin.scenarios.terrain import Grid

X0, Y0, CELL = 300_000.0, 4_650_000.0, 30.0  # UTM 33N, east of Rome


@pytest.fixture(autouse=True)
def no_shared_layers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(layers, "search_dirs", lambda: [tmp_path / "none"])


def valley() -> Grid:
    """A straight valley running south, 10 m deep sides, river in the middle column."""
    rows, cols = 60, 41
    x = np.abs(np.arange(cols) - 20) * 0.5  # 0.5 m per cell up each bank
    y = np.linspace(20.0, 10.0, rows)[:, None]  # gentle slope to the south
    z = y + x[None, :]
    return Grid(z.astype(np.float64), X0, Y0, CELL, {"id": "test_dtm", "kind": "estimated", "vertical_sigma_m": 0.5})


def river_lines(grid: Grid) -> dict[str, Any]:
    rows = np.arange(grid.shape[0], dtype=np.int64)
    lons, lats = grid.lonlat(rows, np.full(rows.size, 20, dtype=np.int64))
    line = {"type": "LineString", "coordinates": [[lo, la] for lo, la in zip(lons, lats)]}
    return {"type": "FeatureCollection",
            "features": [{"type": "Feature", "geometry": line, "properties": {"name": "Tevere"}}]}


def area(grid: Grid) -> dict[str, Any]:
    lons, lats = grid.lonlat(np.array([0, 0, 59, 59], dtype=np.int64), np.array([0, 40, 40, 0], dtype=np.int64))
    ring = [[lo, la] for lo, la in zip(lons, lats)]
    return {"type": "Polygon", "coordinates": [ring + [ring[0]]]}


def run_river(change: dict[str, Any], tmp_path: Path, **data: Any) -> dict[str, Any]:
    grid = valley()
    return engine.run("river_flood", area(grid), change,
                      data=ScenarioData(dtm=grid, rivers=river_lines(grid), **data), cache_dir=tmp_path)


def test_higher_river_floods_more(tmp_path: Path) -> None:
    low = run_river({"river": "tevere", "rise_m": 1.0}, tmp_path)["result"]["flooded_km2"]
    high = run_river({"river": "tevere", "rise_m": 4.0}, tmp_path)["result"]["flooded_km2"]
    assert high["p50"] > low["p50"] > 0
    for q in (low, high):
        assert q["p5"] <= q["p50"] <= q["p95"]


def test_flood_width_matches_the_banks(tmp_path: Path) -> None:
    # banks rise 0.5 m per cell: a 2 m rise wets 4 cells each side = 8 cells x 60 rows
    out = run_river({"river": "tevere", "rise_m": 2.0}, tmp_path)
    expected_km2 = 8 * 60 * CELL * CELL / 1e6
    assert out["result"]["flooded_km2"]["p50"] == pytest.approx(expected_km2, rel=0.15)
    assert out["data_kinds"]["rivers"] == "real"
    assert out["data_kinds"]["terrain"] == "estimated"
    assert out["synthetic"] is False


def test_discharge_becomes_a_level_with_alert_probabilities(tmp_path: Path) -> None:
    forecast = {"tevere_ripetta": [("2026-11-14", 1733.0, 359.0)]}
    out = run_river({"gauge": "tevere_ripetta", "forecast_day": "peak"}, tmp_path, river_discharge=forecast)
    r = out["result"]
    assert 9.0 < r["gauge_level_m"]["p50"] < 13.0
    assert r["alert_probability"]["attenzione"] > 0.9
    assert 0.0 <= r["alert_probability"]["allarme"] <= r["alert_probability"]["preallarme"]
    assert out["data_kinds"]["river_level"] == "estimated"


def test_return_period_is_a_labelled_scenario_with_the_official_discharge(tmp_path: Path) -> None:
    out = run_river({"gauge": "tevere_ripetta", "return_period_years": 200}, tmp_path)
    r = out["result"]
    assert r["return_period_years"] == 200
    assert r["discharge_m3s"] == pytest.approx(3360)  # Calenda et al. 2017, T200 at Ripetta
    assert 16.5 < r["gauge_level_m"]["p50"] < 18.5  # just below the 18.45 m walls
    assert r["scenario"].startswith("200-year flood")
    assert out["data_kinds"]["river_level"] == "hypothetical"
    assert any("scenario" in w.lower() and "not a forecast" in w for w in out["warnings"])
    assert r["flooded_km2"]["p50"] > 0
    # a rarer flood is bigger; the gauge defaults to the Tiber at Ripetta
    rarer = run_river({"return_period_years": 500}, tmp_path)["result"]
    assert rarer["gauge"] == "tevere_ripetta" and rarer["discharge_m3s"] > r["discharge_m3s"]
    with pytest.raises(ValueError):
        run_river({"gauge": "tevere_ripetta", "return_period_years": 75}, tmp_path)


def test_missing_live_gauge_is_not_available(tmp_path: Path) -> None:
    out = run_river({"gauge": "tevere_ripetta", "live": True}, tmp_path)
    assert out["status"] == "not_available"
    assert "login" in out["reason"]


def test_bad_river_change_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        run_river({"river": "tevere"}, tmp_path)


def bowl() -> Grid:
    """A tilted plane with one 1 m deep hollow in the middle."""
    rows, cols = 40, 40
    yy, xx = np.mgrid[0:rows, 0:cols]
    z = 30.0 + 0.02 * yy + 0.02 * xx
    hollow = (yy - 20) ** 2 + (xx - 20) ** 2 <= 9
    z = np.where(hollow, z - 1.0, z)
    return Grid(z.astype(np.float64), X0, Y0, CELL, {"id": "test_dtm", "kind": "estimated", "vertical_sigma_m": 0.5})


def run_rain(change: dict[str, Any], tmp_path: Path, **data: Any) -> dict[str, Any]:
    grid = bowl()
    lons, lats = grid.lonlat(np.array([0, 0, 39, 39], dtype=np.int64), np.array([0, 39, 39, 0], dtype=np.int64))
    ring = [[lo, la] for lo, la in zip(lons, lats)]
    return engine.run("rain_flood", {"type": "Polygon", "coordinates": [ring + [ring[0]]]}, change,
                      data=ScenarioData(dtm=grid, **data), cache_dir=tmp_path)


def test_heavy_rain_fills_the_hollow(tmp_path: Path) -> None:
    out = run_rain({"rain_mm": 120, "duration_h": 1}, tmp_path)
    r = out["result"]
    assert out["status"] == "ok"
    assert r["hotspots_count"] == 1
    depth = r["hotspots"][0]["max_depth_m"]
    assert 0.0 < depth["p5"] <= depth["p50"] <= depth["p95"] <= 1.0 + 1e-9
    assert out["data_kinds"]["drainage"] == "estimated"


def test_light_rain_drains_away(tmp_path: Path) -> None:
    out = run_rain({"rain_mm": 2, "duration_h": 1}, tmp_path)
    assert out["result"]["hotspots_count"] == 0


def test_more_rain_more_water(tmp_path: Path) -> None:
    a = run_rain({"rain_mm": 40, "duration_h": 1}, tmp_path)["result"]["hotspots"][0]["max_depth_m"]["p50"]
    b = run_rain({"rain_mm": 80, "duration_h": 1}, tmp_path)["result"]["hotspots"][0]["max_depth_m"]["p50"]
    assert b > a


def test_radar_rain_without_data_is_not_available(tmp_path: Path) -> None:
    out = run_rain({"source": "radar", "duration_h": 1}, tmp_path)
    assert out["status"] == "not_available"


def test_rain_result_lists_trouble_spots_ranked_by_low_ground_and_history(tmp_path: Path) -> None:
    out = run_rain({"rain_mm": 120, "duration_h": 1}, tmp_path)
    ts = out["result"]["trouble_spots"]
    assert ts["spots"] and "AUC" in ts["method"]
    assert ts["spots"][0]["low_ground_m"] < 0  # the hollow comes first
    assert out["data_kinds"]["call_out_history"] in ("real", "not_available")
    hot = out["result"]["hotspots"][0]
    assert "low_ground_m" in hot and "past_call_outs" in hot
