"""Scenario engine core: envelope, run id, area handling, cache, registry."""
import json
import math
from pathlib import Path
from typing import Any

import pytest

from twin.scenarios import engine, layers
from twin.scenarios.area import AreaNotAvailable, AreaTooLarge, check_heavy, polygon_area_km2, resolve_area
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
        check_heavy(resolve_area(square(10_000.0)))  # 100 km2 > 40 km2
    check_heavy(resolve_area(square(2000.0)))


def test_named_area_needs_a_boundary_lookup() -> None:
    with pytest.raises(AreaNotAvailable):
        resolve_area("municipio:1")
    area = resolve_area("municipio:1", lookup=lambda _id: square(1000.0))
    assert area.id == "municipio:1" and area.kind == "municipio"


def test_area_has_the_hub_shape() -> None:
    poly = resolve_area(square(2000.0))
    assert poly.kind == "polygon" and poly.id.startswith("polygon:") and len(poly.id) == len("polygon:") + 12
    w, s, e, n = poly.bbox
    assert w < LON < e and s < LAT < n
    assert resolve_area("zone:6a", lookup=lambda _id: square(500.0)).id == "zone:6A"


@pytest.mark.parametrize("bad", ["town", "municipio:16", "municipio:0", "zone:", 42])
def test_invalid_area_raises_value_error(bad: object) -> None:
    with pytest.raises(ValueError):
        resolve_area(bad)  # type: ignore[arg-type]


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


def test_named_area_without_boundaries_is_not_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(layers, "search_dirs", lambda: [tmp_path / "empty"])
    out = engine.run("antenna", "municipio:1", ADD, cache_dir=tmp_path)
    assert out["status"] == "not_available"
    assert not list(tmp_path.glob("*.json"))


def test_named_areas_come_from_ws1_boundary_layers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    feature = {"type": "Feature", "geometry": square(1000.0), "properties": {"municipio": 1}}
    zone = {"type": "Feature", "geometry": square(500.0), "properties": {"code_zu": "1A"}}
    (tmp_path / "municipi.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}))
    (tmp_path / "urban_zones.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [zone]}))
    monkeypatch.setattr(layers, "search_dirs", lambda: [tmp_path])
    out = engine.run("antenna", "municipio:1", ADD, cache_dir=tmp_path / "c")
    assert out["status"] == "ok"
    assert out["result"]["area"]["area_km2"] == pytest.approx(1.0, rel=0.01)
    assert engine.run("antenna", "zone:1a", ADD, cache_dir=tmp_path / "c")["status"] == "ok"
    with pytest.raises(ValueError):
        engine.run("antenna", "municipio:2", ADD, cache_dir=tmp_path / "c")
