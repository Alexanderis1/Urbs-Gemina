"""Sewers: capacity from Rome's design rules, routing with surcharge, outfalls blocked by a high river."""
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from twin.scenarios import engine, layers, sewer
from twin.scenarios.data import ScenarioData
from twin.scenarios.terrain import Grid

X0, Y0, CELL = 300_000.0, 4_650_000.0, 30.0


def test_design_rain_follows_the_rome_curve() -> None:
    small, one, two = sewer.design_intensity_mm_h(np.array([0.001, 1.0, 2.0]))
    # 15 minutes minimum concentration time: H = 111.6 * 0.25**0.73 mm in a quarter of an hour
    assert small == pytest.approx(111.6 * 0.25 ** 0.73 / 0.25, rel=0.02)
    assert small > one > two > 60


def test_routing_surcharges_where_the_pipe_is_too_small() -> None:
    # chain 0 -> 1 -> 2 -> 3 (3 is the outfall)
    receiver = np.array([1, 2, 3, 3])
    order = np.array([3, 2, 1, 0])  # outlets first, like priority-flood
    sink = np.array([False, False, False, True])
    captured = np.array([[3.0, 3.0, 3.0, 0.0]])
    capacity = np.array([[10.0, 10.0, 4.0, 0.0]])
    surcharge, discharged = sewer.route(receiver, order, sink, captured, capacity)
    assert surcharge.tolist() == [[0.0, 0.0, 5.0, 0.0]]
    assert discharged.tolist() == [[4.0]]


def test_outfalls_file_is_converted_to_wgs84_points() -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from fetch_sewer_layers import outfalls_geojson

    raw = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point",
           "coordinates": [290267.3, 4654678.9]}, "properties": {"IDGIS": "A2", "DENOM": "SFIO.VIA LONATO",
           "LOCALITA": "Roma", "X_GEO": 12.46698, "Y_GEO": 42.016198, "D_CORPO_RI": "F. Tevere",
           "FUNZIONE": "Intermedio da Sito Fognario"}}]}
    out = outfalls_geojson(raw)
    f = out["features"][0]
    assert f["geometry"]["coordinates"] == [12.46698, 42.016198]
    assert f["properties"] == {"id": "A2", "name": "SFIO.VIA LONATO", "comune": "Roma", "receiving": "F. Tevere",
                               "function": "Intermedio da Sito Fognario"}


def bowl() -> Grid:
    rows, cols = 40, 40
    yy, xx = np.mgrid[0:rows, 0:cols]
    z = 30.0 + 0.02 * yy + 0.02 * xx
    hollow = (yy - 20) ** 2 + (xx - 20) ** 2 <= 9
    z = np.where(hollow, z - 1.0, z)
    return Grid(z.astype(np.float64), X0, Y0, CELL, {"id": "test_dtm", "kind": "estimated", "vertical_sigma_m": 0.5})


def _outfall_layer(directory: Path, grid: Grid) -> None:
    lons, lats = grid.lonlat(np.array([0], dtype=np.int64), np.array([0], dtype=np.int64))
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "sewer_outfalls.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lons[0], lats[0]]},
         "properties": {"id": "O1", "name": "Scarico prova", "receiving": "F. Tevere", "function": "x"}}]}))


def run_rain(change: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    grid = bowl()
    lons, lats = grid.lonlat(np.array([0, 0, 39, 39], dtype=np.int64), np.array([0, 39, 39, 0], dtype=np.int64))
    ring = [[lo, la] for lo, la in zip(lons, lats)]
    return engine.run("rain_flood", {"type": "Polygon", "coordinates": [ring + [ring[0]]]}, change,
                      data=ScenarioData(dtm=grid), use_cache=False)


@pytest.fixture(autouse=True)
def outfalls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outfall_layer(tmp_path / "layers", bowl())
    monkeypatch.setattr(layers, "search_dirs", lambda: [tmp_path / "layers"])


def test_rain_flood_reports_the_sewer_model(tmp_path: Path) -> None:
    out = run_rain({"rain_mm": 60, "duration_h": 1}, tmp_path)
    s = out["result"]["sewer"]
    assert s["model"] == "rome_design_rules"
    assert s["outfalls_considered"] == 1
    assert s["outfalls_blocked"]["p95"] == 0
    assert out["data_kinds"]["outfalls"] == "real"


def test_a_high_river_blocks_the_outfall_and_floods_more(tmp_path: Path) -> None:
    dry = run_rain({"rain_mm": 60, "duration_h": 1}, tmp_path)["result"]
    wet = run_rain({"rain_mm": 60, "duration_h": 1, "river": {"rise_m": 8.0}}, tmp_path)
    r = wet["result"]
    assert r["sewer"]["outfalls_blocked"]["p50"] == 1
    assert r["sewer"]["blocked"][0]["name"] == "Scarico prova"
    assert r["sewer"]["surcharge_m3"]["p50"] > dry["sewer"]["surcharge_m3"]["p50"]
    assert r["hotspots"][0]["max_depth_m"]["p50"] > dry["hotspots"][0]["max_depth_m"]["p50"]
    assert wet["data_kinds"]["river_level"] == "hypothetical"
