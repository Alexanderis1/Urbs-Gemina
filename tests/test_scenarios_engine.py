"""Scenario engine core: envelope, run id, area handling, cache, registry."""
import json
import math
from pathlib import Path
from typing import Any

import pytest

from twin.scenarios import engine
from twin.scenarios.area import AreaTooLarge, AreaNotAvailable, polygon_area_km2, resolve_area
from twin.scenarios.data import ScenarioData

LON, LAT = 12.4823, 41.8960  # Piazza Venezia
M_PER_DEG_LAT = 111_195.0
M_PER_DEG_LON = M_PER_DEG_LAT * math.cos(math.radians(LAT))


def square(side_m: float) -> dict[str, Any]:
    dx, dy = side_m / 2 / M_PER_DEG_LON, side_m / 2 / M_PER_DEG_LAT
    ring = [[LON - dx, LAT - dy], [LON + dx, LAT - dy], [LON + dx, LAT + dy], [LON - dx, LAT + dy], [LON - dx, LAT - dy]]
    return {"type": "Polygon", "coordinates": [ring]}


ADD = {"action": "add", "site": {"lon": LON, "lat": LAT, "height_m": 25.0}, "eirp_w": 2000.0}


def test_polygon_area_is_close_to_true_area() -> None:
    assert polygon_area_km2(square(2000.0)) == pytest.approx(4.0, rel=0.01)


def test_city_area_resolves_from_config() -> None:
    area = resolve_area("city")
    assert area.id == "city"
    assert 1000 < area.area_km2 < 3000  # bounding box of Rome, larger than the 1,287 km2 municipality


def test_heavy_runs_refuse_large_areas() -> None:
    with pytest.raises(AreaTooLarge):
        resolve_area(square(10_000.0), heavy=True)  # 100 km2 > 40 km2
    assert resolve_area(square(2000.0), heavy=True).area_km2 == pytest.approx(4.0, rel=0.01)


def test_named_area_needs_a_boundary_lookup() -> None:
    with pytest.raises(AreaNotAvailable):
        resolve_area("municipio:1")
    area = resolve_area("municipio:1", lookup=lambda _id: square(1000.0))
    assert area.id == "municipio:1"


def test_run_returns_the_shared_envelope(tmp_path: Path) -> None:
    out = engine.run("antenna", "city", ADD, cache_dir=tmp_path)
    assert out["status"] == "ok" and "reason" not in out
    assert set(out) >= {"run_id", "tool", "inputs", "result", "data_kinds", "sources", "synthetic", "warnings"}
    assert out["tool"] == "run_scenario"
    assert out["inputs"] == {"kind": "antenna", "area": "city", "change": ADD}
    assert len(out["run_id"]) == 64
    json.dumps(out)  # must be plain JSON


def test_run_id_depends_on_inputs_and_data_snapshots(tmp_path: Path) -> None:
    a = engine.run("antenna", "city", ADD, cache_dir=tmp_path)["run_id"]
    b = engine.run("antenna", "city", ADD, cache_dir=tmp_path)["run_id"]
    c = engine.run("antenna", "city", {**ADD, "eirp_w": 1000.0}, cache_dir=tmp_path)["run_id"]
    d = engine.run("antenna", "city", ADD, data=ScenarioData(snapshots={"cartoradio": "abc"}), cache_dir=tmp_path)["run_id"]
    assert a == b and a != c and a != d


def test_second_run_is_served_from_cache(tmp_path: Path) -> None:
    first = engine.run("antenna", "city", ADD, cache_dir=tmp_path)
    assert first["cached"] is False
    second = engine.run("antenna", "city", ADD, cache_dir=tmp_path)
    assert second["cached"] is True
    assert second["result"] == first["result"]
    assert (tmp_path / f"{first['run_id']}.json").exists()


def test_unknown_kind_lists_the_known_ones() -> None:
    with pytest.raises(KeyError, match="antenna"):
        engine.run("flood", "city", {})


def test_kinds_are_listed() -> None:
    assert {"antenna", "population_exposure"} <= set(engine.kinds())


def test_named_area_without_boundaries_is_not_available(tmp_path: Path) -> None:
    out = engine.run("antenna", "municipio:1", ADD, cache_dir=tmp_path)
    assert out["status"] == "not_available"
    assert not list(tmp_path.glob("*.json"))
