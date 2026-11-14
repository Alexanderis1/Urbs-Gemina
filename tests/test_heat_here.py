"""Citizen heat service: risk today here, nearest cool indoor place and cooler open-air spots."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from twin.tools import heat_here as heat
from twin.tools.layers import LayerStore
from twin.tools.runtime import ToolRuntime
from twin.tools.settings import Settings

POINT = [12.4823, 41.8960]


def test_apparent_temperature_follows_steadman() -> None:
    # 30 degC, 50 % humidity, calm: e = 21.2 hPa -> 30 + 7.0 - 4.0 = 33.0
    assert heat.apparent_temperature(30.0, 50.0, 0.0) == pytest.approx(33.0, abs=0.1)
    assert heat.apparent_temperature(30.0, 50.0, 4.0) < heat.apparent_temperature(30.0, 50.0, 0.0)


@pytest.fixture()
def rt(tmp_path: Path) -> ToolRuntime:
    store = LayerStore(raw_dir=tmp_path / "raw")
    pt = lambda dx, name, **p: {"type": "Feature", "geometry": {"type": "Point", "coordinates": [POINT[0] + dx, POINT[1]]},
                                 "properties": {"nome": name, **p}}
    store.add("climate_refuges_indoor", {"type": "FeatureCollection", "features": [
        pt(0.002, "Biblioteca vicina", tipo="Biblioteche", indirizzo="Via A 1", orari="Lun-Ven 9-19", chiusura_e="n.d.", aria_cond="SI"),
        pt(0.004, "Centro chiuso", tipo="Centri Anziani (CSAQ)", indirizzo="Via B 2", orari="Temporaneamente chiusa per lavori PNRR",
           chiusura_e="n.d.", aria_cond="SI"),
        pt(0.003, "Museo in pausa", tipo="Musei", indirizzo="Via C 3", orari="Mar-Dom 10-19", chiusura_e="Dal 10 al 22 agosto 2026",
           aria_cond="SI"),
    ]}, sha256="r1")
    return ToolRuntime(settings=Settings.load(), store=store)


def test_indoor_places_check_hours_and_closures(rt: ToolRuntime) -> None:
    monday_noon = datetime(2026, 11, 16, 11, 0, tzinfo=timezone.utc)
    places = heat.indoor_places(rt, POINT, monday_noon)
    by_name = {p["name"]: p for p in places}
    assert by_name["Biblioteca vicina"]["open_at"] is True
    assert by_name["Centro chiuso"]["open_at"] is False
    assert by_name["Museo in pausa"]["open_at"] is False          # Mondays closed
    assert places[0]["name"] == "Biblioteca vicina"               # open first, then nearest
    assert places[0]["walk_min"] > 0
    in_august = heat.indoor_places(rt, POINT, datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc))
    assert {p["name"]: p for p in in_august}["Museo in pausa"]["open_at"] is False   # summer closure


def test_risk_level_uses_config_and_legal_hot_day(rt: ToolRuntime) -> None:
    hot = float(rt.settings.thresholds["heat"]["hot_day_tmax_c"]["value"])
    assert heat.risk_level(rt, hot + 1)["index"] == 4
    assert heat.risk_level(rt, 15.0)["index"] == 1


def test_open_air_spots_rank_cooler_first(rt: ToolRuntime, monkeypatch: pytest.MonkeyPatch) -> None:
    import h3
    from twin.beliefs.config import grid_resolution
    centre = h3.latlng_to_cell(POINT[1], POINT[0], grid_resolution())
    cells = list(h3.grid_disk(centre, 3))
    cool = cells[-1]
    temps = {c: 30.0 for c in cells}
    temps[cool] = 27.0
    rows = {c: {"cell": c, "p50": t, "p5": t - 1, "p95": t + 1} for c, t in temps.items()}
    spots, here = heat.open_air_spots(rt, POINT, rows, humidity=50.0, wind=1.0, micro=lambda cs, at: {})
    assert spots[0]["cell"] == cool
    assert spots[0]["feels_like_c"] < here["feels_like_c"]
    assert spots[0]["cooler_by_c"] > 2.5
