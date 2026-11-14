"""Emergency access: residents reached within the target time, before and after closures."""
import math
from pathlib import Path
from typing import Any

import pytest

from twin.scenarios import engine
from twin.scenarios.data import ScenarioData
from twin.scenarios.traffic import sumo_binary

LAT0, LON0 = 41.900, 12.480
STEP_M = 400.0
DLON = STEP_M / (111_195.0 * math.cos(math.radians(LAT0)))
DLAT_NORTH = 1000.0 / 111_195.0  # the detour road runs 1 km north
N = 6  # junctions along the south road, 400 m apart
AREA = {"type": "Polygon", "coordinates": [[[12.47, 41.89], [12.52, 41.89], [12.52, 41.92], [12.47, 41.92], [12.47, 41.89]]]}

needs_sumo = pytest.mark.skipif(sumo_binary("netconvert") is None, reason="SUMO not installed")


def _lon(i: int) -> float:
    return LON0 + i * DLON


def _way(wid: int, refs: list[int], name: str) -> str:
    return (f'<way id="{wid}" version="1">' + "".join(f'<nd ref="{r}"/>' for r in refs)
            + f'<tag k="highway" v="secondary"/><tag k="name" v="{name}"/></way>')


def _osm(path: Path) -> None:
    """A ladder: south road (sections), north detour road, two links at the ends."""
    xml = ['<?xml version="1.0"?><osm version="0.6">']
    xml += [f'<node id="{i + 1}" lat="{LAT0}" lon="{_lon(i):.7f}" version="1"/>' for i in range(N)]
    xml += [f'<node id="{i + 101}" lat="{LAT0 + DLAT_NORTH:.7f}" lon="{_lon(i):.7f}" version="1"/>' for i in (0, N - 1)]
    # short dead-end lanes keep every south node a real junction (netconvert merges plain bends)
    xml += [f'<node id="{i + 201}" lat="{LAT0 - 0.0015}" lon="{_lon(i):.7f}" version="1"/>' for i in range(N)]
    xml.append(_way(10, [1, 2, 3], "Via Sud Ovest"))
    xml.append(_way(11, list(range(3, N + 1)), "Via Sud Est"))
    xml.append(_way(12, [1, 101, 100 + N, N], "Via Nord"))
    xml += [_way(20 + i, [i + 1, i + 201], f"Vicolo {i}") for i in range(N)]
    xml.append("</osm>")
    path.write_text("".join(xml), encoding="utf-8")


def _section(i: int, residents: int) -> dict[str, Any]:
    d = 0.0005
    lon = _lon(i)
    ring = [[lon - d, LAT0 - d], [lon + d, LAT0 - d], [lon + d, LAT0 + d], [lon - d, LAT0 + d], [lon - d, LAT0 - d]]
    return {"type": "Feature", "properties": {"sez_id": f"S{i}", "residents": residents},
            "geometry": {"type": "Polygon", "coordinates": [ring]}}


CENSUS = {"type": "FeatureCollection", "features": [_section(i, 100) for i in range(N)]}
STATION = [(LON0, LAT0, "Stazione Ovest")]


@pytest.fixture(scope="module")
def chain_net(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from twin.scenarios.traffic import build_network

    work = tmp_path_factory.mktemp("access")
    _osm(work / "chain.osm")
    return build_network(work / "chain.osm", work / "chain.net.xml")


def _data(net: Path) -> ScenarioData:
    return ScenarioData(road_network=net, census=CENSUS, facilities=STATION)


def test_change_must_say_what_is_closed() -> None:
    with pytest.raises(ValueError):
        engine.run("emergency_access", AREA, {"service": "fire"}, data=ScenarioData(road_network=Path("x")),
                   use_cache=False)


def test_no_facilities_is_not_available(tmp_path: Path) -> None:
    out = engine.run("emergency_access", AREA, {"service": "fire", "close": {"street": "Via Est"}},
                     data=ScenarioData(road_network=Path("x"), census=CENSUS, facilities=[]), cache_dir=tmp_path)
    assert out["status"] == "not_available"
    assert not list(tmp_path.glob("*.json"))


@needs_sumo
def test_closing_a_street_cuts_off_the_sections_on_it(chain_net: Path, tmp_path: Path) -> None:
    out = engine.run("emergency_access", AREA, {"service": "fire", "close": {"street": "Via Sud Est"}},
                     data=_data(chain_net), cache_dir=tmp_path)
    assert out["status"] == "ok"
    r = out["result"]
    assert r["facilities"] == 1
    assert r["target_min"] == 20
    assert r["closed_roads"] >= 2
    assert r["residents_total"] == 600
    assert r["residents_beyond_target"]["baseline"]["p95"] == 0
    assert r["residents_cut_off"] == 200
    assert r["residents_beyond_target"]["variant"]["p50"] == 200
    assert {s["sez_id"] for s in r["sections"]} == {"S3", "S4"}
    assert all(s["minutes_after"] is None for s in r["sections"])
    travel = r["travel_min_baseline"]  # resident-weighted, median speed: what the model says before any closure
    assert 0 < travel["median_resident"] <= travel["p75_resident"] < 20
    assert out["data_kinds"]["speeds"] == "estimated"
    assert out["synthetic"] is False


@needs_sumo
def test_a_closed_block_forces_a_detour_beyond_the_target(chain_net: Path) -> None:
    d = 0.0008
    lon = (_lon(3) + _lon(4)) / 2
    block = {"type": "Polygon", "coordinates": [[[lon - d, LAT0 - d], [lon + d, LAT0 - d], [lon + d, LAT0 + d],
                                                 [lon - d, LAT0 + d], [lon - d, LAT0 - d]]]}
    out = engine.run("emergency_access", AREA, {"service": "ambulance", "closed_area": block, "target_min": 5,
                                               "count_from": "departure"},
                     data=_data(chain_net), use_cache=False)
    r = out["result"]
    assert r["closed_roads"] >= 1
    assert r["residents_cut_off"] == 0
    base, var = r["residents_beyond_target"]["baseline"], r["residents_beyond_target"]["variant"]
    assert var["p5"] <= var["p50"] <= var["p95"]
    assert var["p50"] > base["p50"]
    lost = {s["sez_id"]: s for s in r["sections"]}
    assert "S4" in lost and "S5" in lost
    assert lost["S4"]["minutes_after"] > 5 >= lost["S4"]["minutes_before"]
    assert any("hospitals" in w for w in out["warnings"])
    assert any("75th percentile" in w for w in out["warnings"])  # the real 118 benchmark is always shown


@needs_sumo
def test_a_station_off_the_network_pays_its_approach_distance(chain_net: Path) -> None:
    change = {"service": "fire", "close": {"street": "Via Sud Est"}, "target_min": 2, "count_from": "departure"}
    near = engine.run("emergency_access", AREA, change, data=_data(chain_net), use_cache=False)["result"]
    far_station = [(LON0 - 5 * DLON, LAT0, "Stazione lontana")]  # 2 km west of the district network
    far = engine.run("emergency_access", AREA, change, use_cache=False,
                     data=ScenarioData(road_network=chain_net, census=CENSUS, facilities=far_station))["result"]
    assert near["residents_beyond_target"]["baseline"]["p50"] < 600
    assert far["residents_beyond_target"]["baseline"]["p50"] == 600


@needs_sumo
def test_targets_count_from_the_call_including_call_handling_and_dispatch(chain_net: Path) -> None:
    """Legal 118 targets run from the call: the model adds call handling, dispatch and crew departure."""
    change = {"service": "ambulance", "close": {"street": "Via Sud Est"}, "target_min": 5}
    call = engine.run("emergency_access", AREA, change, data=_data(chain_net), use_cache=False)["result"]
    road = engine.run("emergency_access", AREA, {**change, "count_from": "departure"}, data=_data(chain_net),
                      use_cache=False)["result"]
    assert call["count_from"] == "call" and road["count_from"] == "departure"
    assert call["residents_beyond_target"]["baseline"]["p50"] > road["residents_beyond_target"]["baseline"]["p50"]
    pre = call["pre_travel_min"]
    assert 3 <= pre["p50"] <= 6 and pre["p5"] < pre["p50"] < pre["p95"]
    travel, response = call["travel_min_baseline"], call["response_min_baseline"]
    assert response["p75_resident"] == pytest.approx(travel["p75_resident"] + pre["p50"], abs=0.2)


def test_ambulances_start_from_the_118_posts_when_the_layer_exists(monkeypatch: pytest.MonkeyPatch,
                                                                     tmp_path: Path) -> None:
    import json

    from twin.scenarios import access, layers

    posts = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [12.5, 41.9]}, "properties": {"name": "Post A"}}]}
    (tmp_path / "ares118_posts.geojson").write_text(json.dumps(posts), encoding="utf-8")
    real_find = layers.find
    monkeypatch.setattr(layers, "find", lambda name, dirs=None: (tmp_path / name) if name == "ares118_posts.geojson"
                        else real_find(name, dirs))
    assert access.facilities("ambulance", ScenarioData()) == [(12.5, 41.9, "Post A")]
    monkeypatch.setattr(layers, "find", lambda name, dirs=None: None if name == "ares118_posts.geojson"
                        else real_find(name, dirs))
    fallback = access.facilities("ambulance", ScenarioData())
    assert all(name != "Post A" for _, _, name in fallback)  # emergency hospitals instead (or none in a bare checkout)
