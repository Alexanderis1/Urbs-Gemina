"""Road closure with SUMO on one district: baseline vs variant over several demand seeds."""
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from twin.scenarios import engine
from twin.scenarios.area import AreaTooLarge
from twin.scenarios.data import ScenarioData
from twin.scenarios.traffic import sumo_binary

LON, LAT = 12.4823, 41.8960
M_PER_DEG_LAT = 111_195.0
M_PER_DEG_LON = M_PER_DEG_LAT * math.cos(math.radians(LAT))


def square(side_m: float) -> dict[str, Any]:
    dx, dy = side_m / 2 / M_PER_DEG_LON, side_m / 2 / M_PER_DEG_LAT
    ring = [[LON - dx, LAT - dy], [LON + dx, LAT - dy], [LON + dx, LAT + dy], [LON - dx, LAT + dy], [LON - dx, LAT - dy]]
    return {"type": "Polygon", "coordinates": [ring]}


DISTRICT = square(2000.0)
CLOSE = {"close": {"edges": ["B2C2", "C2B2"]}}


def test_closure_refuses_the_whole_city() -> None:
    with pytest.raises(AreaTooLarge):
        engine.run("road_closure", "city", CLOSE, data=ScenarioData(road_network=Path("x.net.xml")), use_cache=False)


def test_missing_network_is_not_available_and_not_cached(tmp_path: Path) -> None:
    out = engine.run("road_closure", DISTRICT, CLOSE, data=ScenarioData(), cache_dir=tmp_path)
    assert out["result"]["status"] == "not_available"
    assert "network" in out["result"]["reason"]
    assert not list(tmp_path.glob("*.json"))


def test_closure_needs_edges_or_a_street() -> None:
    with pytest.raises(ValueError):
        engine.run("road_closure", DISTRICT, {"close": {}}, data=ScenarioData(road_network=Path("x")), use_cache=False)


needs_sumo = pytest.mark.skipif(sumo_binary("sumo") is None, reason="SUMO not installed (pip install eclipse-sumo)")


@pytest.fixture(scope="module")
def grid_net(tmp_path_factory: pytest.TempPathFactory) -> Path:
    netgenerate = sumo_binary("netgenerate")
    assert netgenerate is not None
    out = tmp_path_factory.mktemp("net") / "grid.net.xml"
    subprocess.run([netgenerate, "--grid", "--grid.number", "5", "--grid.length", "200",
                    "--default.lanenumber", "1", "-o", str(out)], check=True, capture_output=True)
    return out


@needs_sumo
def test_closing_a_central_road_adds_delay(grid_net: Path, tmp_path: Path) -> None:
    data = ScenarioData(road_network=grid_net, road_network_kind="simulated")
    out = engine.run("road_closure", DISTRICT, CLOSE, data=data, cache_dir=tmp_path)
    result = out["result"]
    assert result["status"] == "ok"
    assert result["closed_edges"] == ["B2C2", "C2B2"]
    base, variant = result["baseline"], result["variant"]
    for side in (base, variant):
        for key in ("mean_travel_time_s", "mean_time_loss_s", "vehicle_hours_lost"):
            assert side[key]["p5"] <= side[key]["p50"] <= side[key]["p95"]
    assert variant["mean_travel_time_s"]["p50"] > base["mean_travel_time_s"]["p50"]
    assert result["difference"]["mean_travel_time_s"]["p50"] > 0
    assert result["replicates"] == 5
    assert out["synthetic"] is True
    assert out["data_kinds"]["traffic_demand"] == "simulated"
    assert any("synthetic demand" in w.lower() for w in out["warnings"])
    assert len(result["changed_roads"]) > 0


@needs_sumo
def test_same_inputs_give_the_same_numbers(grid_net: Path, tmp_path: Path) -> None:
    data = ScenarioData(road_network=grid_net)
    a = engine.run("road_closure", DISTRICT, CLOSE, data=data, use_cache=False)
    b = engine.run("road_closure", DISTRICT, CLOSE, data=data, use_cache=False)
    assert a["result"]["variant"] == b["result"]["variant"]


@needs_sumo
def test_unknown_road_is_rejected(grid_net: Path) -> None:
    with pytest.raises(ValueError, match="Z9Z9"):
        engine.run("road_closure", DISTRICT, {"close": {"edges": ["Z9Z9"]}},
                   data=ScenarioData(road_network=grid_net), use_cache=False)


def _tiny_osm(path: Path) -> None:
    nodes = [(1, 41.900, 12.480), (2, 41.900, 12.483), (3, 41.900, 12.486), (4, 41.903, 12.483)]
    xml = ['<?xml version="1.0"?><osm version="0.6">']
    xml += [f'<node id="{i}" lat="{lat}" lon="{lon}" version="1"/>' for i, lat, lon in nodes]
    xml.append('<way id="10" version="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/>'
               '<tag k="highway" v="secondary"/><tag k="name" v="Via di Prova"/></way>')
    xml.append('<way id="11" version="1"><nd ref="2"/><nd ref="4"/>'
               '<tag k="highway" v="residential"/><tag k="name" v="Vicolo Corto"/></way>')
    xml.append("</osm>")
    path.write_text("".join(xml), encoding="utf-8")


@needs_sumo
def test_network_is_built_from_osm_with_street_names(tmp_path: Path) -> None:
    from twin.scenarios.traffic import build_network, street_names

    osm = tmp_path / "district.osm"
    _tiny_osm(osm)
    net = build_network(osm, tmp_path / "district.net.xml")
    assert {"Via di Prova", "Vicolo Corto"} <= street_names(net)
