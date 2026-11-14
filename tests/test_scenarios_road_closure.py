"""Road closure with SUMO on one district: baseline vs variant over several demand seeds."""
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from twin.scenarios import engine
from twin.scenarios.data import ScenarioData
from twin.scenarios.traffic import sumo_binary

LON, LAT = 12.4823, 41.8960
M_PER_DEG_LAT = 111_195.0
M_PER_DEG_LON = M_PER_DEG_LAT * math.cos(math.radians(LAT))


def square(side_m: float) -> dict[str, Any]:
    dx, dy = side_m / 2 / M_PER_DEG_LON, side_m / 2 / M_PER_DEG_LAT
    ring = [[LON - dx, LAT - dy], [LON + dx, LAT - dy], [LON + dx, LAT + dy], [LON - dx, LAT + dy], [LON - dx, LAT - dy]]
    return {"type": "Polygon", "coordinates": [ring]}


DISTRICT = square(1700.0)  # under the 3 km2 SUMO limit
CLOSE = {"close": {"edges": ["B2C2", "C2B2"]}}


def test_closure_refuses_the_whole_city(tmp_path: Path) -> None:
    out = engine.run("road_closure", "city", CLOSE, data=ScenarioData(road_network=Path("x.net.xml")),
                     cache_dir=tmp_path)
    assert out["status"] == "refused"
    assert "km2" in out["reason"]
    assert not list(tmp_path.glob("*.json"))


def test_sumo_kinds_refuse_a_whole_municipio_before_calling_the_worker(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A synchronous SUMO run over about 3 km2 outlasts the API's time limit: refuse it with a clear reason."""
    from twin.scenarios import remote

    called: list[str] = []
    monkeypatch.setattr(remote, "enabled", lambda: True)
    monkeypatch.setattr(remote, "call", lambda kind, *a, **k: called.append(kind) or {"status": "ok"})
    for kind, change in (("road_closure", CLOSE), ("traffic_event", {"event": {"edges": ["B2C2"], "attendees": 100}})):
        out = engine.run(kind, square(2500.0), change, data=ScenarioData(road_network=Path("x.net.xml")),
                         cache_dir=tmp_path)
        assert out["status"] == "refused", kind
        assert "3 km2" in out["reason"] and "smaller" in out["reason"]
    assert called == []


def test_missing_network_is_not_available_and_not_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from twin.scenarios import traffic

    def offline(area: object) -> Path:
        raise OSError("offline")

    monkeypatch.setattr(traffic, "network_for_area", offline)
    out = engine.run("road_closure", DISTRICT, CLOSE, data=ScenarioData(), cache_dir=tmp_path)
    assert out["status"] == "not_available"
    assert "network" in out["reason"]
    assert "status" not in out["result"]
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
    assert out["status"] == "ok"
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


@needs_sumo
def test_demand_is_scaled_to_real_loop_counts(grid_net: Path, tmp_path: Path) -> None:
    plain = engine.run("road_closure", DISTRICT, CLOSE, data=ScenarioData(road_network=grid_net), use_cache=False)
    assert plain["result"]["demand_anchor"]["loop_stations"] == 0
    assert plain["result"]["demand_anchor"]["scale"] == 1.0
    busy = {"A1B1": 2000.0, "B1C1": 2000.0, "C1D1": 2000.0}
    out = engine.run("road_closure", DISTRICT, CLOSE, use_cache=False,
                     data=ScenarioData(road_network=grid_net, loop_counts_veh_per_h=busy, loop_counts_kind="real"))
    anchor = out["result"]["demand_anchor"]
    assert anchor["loop_stations"] == 3
    assert anchor["scale"] > 1.0
    assert out["data_kinds"]["loop_counts"] == "real"
    assert out["synthetic"] is True
    assert any("synthetic demand" in w.lower() for w in out["warnings"])


@needs_sumo
def test_bus_speeds_are_checked_against_the_baseline(grid_net: Path) -> None:
    speeds = {"A1B1": 8.0, "B1C1": 8.0}
    out = engine.run("road_closure", DISTRICT, CLOSE, use_cache=False,
                     data=ScenarioData(road_network=grid_net, observed_speeds_m_per_s=speeds))
    check = out["result"]["speed_check"]
    assert check["edges"] == 2
    assert check["mean_abs_error_m_per_s"] >= 0.0
    assert out["data_kinds"]["bus_speeds"] == "real"


@pytest.fixture(scope="module")
def two_lane_net(tmp_path_factory: pytest.TempPathFactory) -> Path:
    netgenerate = sumo_binary("netgenerate")
    assert netgenerate is not None
    out = tmp_path_factory.mktemp("net2") / "grid2.net.xml"
    subprocess.run([netgenerate, "--grid", "--grid.number", "5", "--grid.length", "200",
                    "--default.lanenumber", "2", "-o", str(out)], check=True, capture_output=True)
    return out


@needs_sumo
def test_roadworks_cut_lanes_and_add_delay(two_lane_net: Path) -> None:
    works = {"roadworks": [{"edges": ["B2C2", "C2B2", "C2D2", "D2C2"], "lanes_closed": 1, "speed_kmh": 20}]}
    out = engine.run("traffic_event", DISTRICT, works, data=ScenarioData(road_network=two_lane_net), use_cache=False)
    r = out["result"]
    assert out["status"] == "ok"
    assert {w["edge"] for w in r["roadworks"]} == {"B2C2", "C2B2", "C2D2", "D2C2"}
    assert r["roadworks"][0]["lanes"] == [2, 1]
    assert r["difference"]["mean_time_loss_s"]["p50"] > 0


@needs_sumo
def test_big_event_adds_traffic_and_congestion_points(grid_net: Path) -> None:
    change = {"event": {"edges": ["C2C3", "C3C2"], "attendees": 3000, "arrive_from_s": 0, "arrive_to_s": 1800}}
    out = engine.run("traffic_event", DISTRICT, change, data=ScenarioData(road_network=grid_net), use_cache=False)
    r = out["result"]
    assert r["event"]["vehicles"] == round(3000 * 0.35 / 1.8)
    assert r["variant"]["completed"]["p50"] > r["baseline"]["completed"]["p50"]
    assert r["congestion_points"] and r["congestion_points"][0]["extra_vehicle_hours_lost"] > 0
    assert any("event traffic" in w.lower() for w in out["warnings"])


def test_traffic_change_needs_something_to_do() -> None:
    with pytest.raises(ValueError):
        engine.run("traffic_event", DISTRICT, {"event": {"attendees": 0}},
                   data=ScenarioData(road_network=Path("x")), use_cache=False)


def test_isolated_kinds_go_to_the_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from twin.scenarios import remote

    calls: list[tuple[str, dict[str, object]]] = []

    def fake_call(kind: str, area: object, change: dict[str, object], data: ScenarioData) -> dict[str, object]:
        calls.append((kind, remote.to_spec(data)))
        return {"status": "ok", "run_id": "x", "result": {}, "cached": False}

    monkeypatch.setenv(remote.ENV_SWITCH, "modal")
    monkeypatch.setattr(remote, "call", fake_call)
    data = ScenarioData(loop_counts_veh_per_h={"A1B1": 100.0}, river_discharge={"g": [("2026-11-14", 1.0, 0.1)]})
    out = engine.run("traffic_event", DISTRICT, CLOSE, data=data, cache_dir=tmp_path)
    assert out["status"] == "ok" and calls[0][0] == "traffic_event"
    back = remote.from_spec(calls[0][1])
    assert back.loop_counts_veh_per_h == {"A1B1": 100.0}
    assert back.river_discharge == {"g": [("2026-11-14", 1.0, 0.1)]}
    # light kinds stay in the API process
    assert engine.run("antenna", "city", {"action": "add", "site": {"lon": 12.48, "lat": 41.9, "height_m": 20},
                                          "eirp_w": 100.0}, data=ScenarioData(), cache_dir=tmp_path)["status"] == "ok"
    assert len(calls) == 1


def test_worker_down_is_not_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from twin.scenarios import remote

    def broken(*args: object) -> dict[str, object]:
        raise ConnectionError("no worker")

    monkeypatch.setenv(remote.ENV_SWITCH, "modal")
    monkeypatch.setattr(remote, "call", broken)
    out = engine.run("road_closure", DISTRICT, CLOSE, data=ScenarioData(), cache_dir=tmp_path)
    assert out["status"] == "not_available" and "worker" in out["reason"]


def test_random_trips_says_when_the_router_wrote_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """In a container without SUMO's system libraries duarouter dies silently; say so instead of a bare file error."""
    from twin.scenarios import traffic

    monkeypatch.setattr(traffic, "_run", lambda *a, **k: None)  # randomTrips "ran" but produced nothing
    cfg = {"duration_s": 600, "min_trip_distance_m": 300, "fringe_factor": 5}
    with pytest.raises(RuntimeError, match="duarouter"):
        traffic._random_trips(tmp_path, tmp_path / "x.net.xml", tmp_path / "out.trips.xml", 1, 10.0, cfg, {}, tmp_path)
