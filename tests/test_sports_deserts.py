from __future__ import annotations

import pytest

from tests.sports_fixtures import at, geoserver_sports, osm_elements
from twin.modules.sports.config import load_config
from twin.modules.sports.deserts import PopulationPoint, coverage, reach_radius_m, school_gym_facility, what_if_open
from twin.modules.sports.indicators import TransitStop, facility_indicators, residents_within, transit_access
from twin.modules.sports.matching import build_facilities
from twin.modules.sports.sources import from_geoserver_sports, from_osm
from twin.modules.sports.tools import sport_deserts, sports_facilities

CFG = load_config()


def facilities():  # type: ignore[no-untyped-def]
    cands = from_geoserver_sports(geoserver_sports(), CFG, "2026-11-13") + from_osm(osm_elements(), CFG, "2026-11-13")
    return build_facilities(cands, CFG)[0]


def pop(pid: str, east: float, north: float, residents: float, children: float, zone: str = "Z1") -> PopulationPoint:
    lon, lat = at(east, north)
    return PopulationPoint(point_id=pid, lon=lon, lat=lat, residents=residents, children=children, zone=zone, municipio="VII")


POINTS = [
    pop("p1", 100, 0, 1000, 100),          # next to the football centre
    pop("p2", 0, 3000, 2000, 300, "Z2"),   # 3 km north: no football in reach
    pop("p3", 2100, 0, 500, 50),           # next to the pool
]


def test_reach_radius_follows_config() -> None:
    # 15 min at 4.8 km/h = 1200 m of street / 1.3 detour
    assert reach_radius_m(CFG) == pytest.approx(923.1, abs=0.1)


def test_transit_access_and_residents_within() -> None:
    lon, lat = at(0, 0)
    stops = [TransitStop("s1", *at(100, 0), frozenset({"105", "558"})), TransitStop("s2", *at(0, 350), frozenset({"105"})),
             TransitStop("s3", *at(900, 0), frozenset({"MA"}))]
    access = transit_access(lon, lat, stops, 400.0)
    assert access["stops_within"] == 2
    assert access["routes_within"] == ["105", "558"]
    assert access["nearest_stop_m"] == pytest.approx(100.0, abs=1.0)
    assert residents_within(lon, lat, POINTS, 500.0) == {"residents": 1000.0, "children": 100.0}
    ind = facility_indicators(facilities(), stops, POINTS, CFG)
    assert all("transit" in v and "within_reach" in v for v in ind.values())


def test_coverage_finds_the_desert_zone() -> None:
    result = coverage(POINTS, facilities(), "football", reach_radius_m(CFG))
    assert result["residents_total"] == 3500
    assert result["residents_uncovered"] == 2500  # p2, and p3 (pool, no football)
    zones = {z["zone"]: z for z in result["zones"]}
    assert zones["Z2"]["uncovered_share"] == 1.0
    assert zones["Z2"]["desert"] is True
    assert zones["Z2"]["centroid"] == [round(c, 6) for c in at(0, 3000)]
    assert zones["Z1"]["desert"] is False


def test_what_if_opening_a_school_gym_closes_the_gap() -> None:
    gym = school_gym_facility("Scuola Media Esempio", *at(0, 2900), CFG, disciplines={"football"})
    out = what_if_open(POINTS, facilities(), "football", [gym], reach_radius_m(CFG))
    assert out["baseline"]["residents_uncovered"] == 2500
    assert out["variant"]["residents_uncovered"] == 500
    assert out["delta"]["residents_newly_covered"] == 2000
    assert out["delta"]["children_newly_covered"] == 300
    assert gym.fields["name"].status == "simulated"


def test_school_gym_default_disciplines_come_from_config() -> None:
    gym = school_gym_facility("Scuola", *at(0, 0), CFG)
    assert set(gym.disciplines) == set(CFG.school_gym_default_disciplines)


def test_tool_envelopes_follow_the_contract() -> None:
    env = sport_deserts(area="municipio:7", discipline="football", facilities=facilities(), population=POINTS, config=CFG,
                        snapshot_hashes={"roma_sports_municipal": "abc"})
    for key in ("run_id", "tool", "inputs", "result", "data_kinds", "sources", "synthetic", "warnings", "status",
                "cached"):
        assert key in env
    assert env["status"] == "ok" and env["cached"] is False
    assert env["tool"] == "sport_deserts"
    assert len(env["run_id"]) == 64
    assert env["data_kinds"]["reach"] == "estimated"
    again = sport_deserts(area="municipio:7", discipline="football", facilities=facilities(), population=POINTS, config=CFG,
                          snapshot_hashes={"roma_sports_municipal": "abc"})
    assert again["run_id"] == env["run_id"]

    gym = school_gym_facility("Scuola", *at(0, 2900), CFG, disciplines={"football"})
    sim = sport_deserts(area="city", discipline="football", facilities=facilities(), population=POINTS, config=CFG,
                        open_facilities=[gym])
    assert sim["synthetic"] is True
    assert sim["result"]["delta"]["residents_newly_covered"] == 2000


def test_sports_facilities_tool_filters_by_area_and_discipline() -> None:
    env = sports_facilities(area="municipio:7", discipline="swimming", facilities=facilities(), config=CFG)
    feats = env["result"]["features"]
    assert len(feats) == 1
    assert feats[0]["properties"]["name"] == "Piscina Comunale Quadraro"
    lon, lat = at(-100, -100)
    lon2, lat2 = at(100, 100)
    square = {"type": "Polygon", "coordinates": [[[lon, lat], [lon2, lat], [lon2, lat2], [lon, lat2], [lon, lat]]]}
    env = sports_facilities(area=square, discipline=None, facilities=facilities(), config=CFG)
    names = sorted(f["properties"]["name"] for f in env["result"]["features"])
    assert names == ["Campo Bocce Cinecitta", "Centro Sportivo Fulvio Bernardini"]
    with pytest.raises(ValueError):
        sports_facilities(area="municipio:7", discipline="quidditch", facilities=facilities(), config=CFG)


def test_area_ids_follow_the_shared_contract() -> None:
    from twin.modules.sports.tools import parse_area

    assert parse_area("city") == ("city", None)
    assert parse_area("municipio:7") == ("municipio", "VII")
    assert parse_area("zone:6A") == ("zone", "6A")
    for bad in ("VII", "municipio:16", "zone:6a", {"type": "Point", "coordinates": [0, 0]}):
        with pytest.raises(ValueError):
            parse_area(bad)  # type: ignore[arg-type]
    zone = sport_deserts(area="zone:Z2", discipline="football", facilities=facilities(), population=POINTS, config=CFG)
    assert zone["result"]["residents_total"] == 2000
    env = sports_facilities(area="zone:Z2", discipline=None, facilities=facilities(), config=CFG)
    assert env["status"] == "not_available" and env["reason"]
    empty = sport_deserts(area="city", discipline="football", facilities=facilities(), population=[], config=CFG)
    assert empty["status"] == "not_available" and empty["data_kinds"]["population"] == "not_available"


def test_type_and_accessible_filters_and_max_minutes() -> None:
    from twin.modules.sports.tools import sport_coverage

    env = sports_facilities(area="city", discipline=None, facilities=facilities(), config=CFG, type="private")
    assert [f["properties"]["name"] for f in env["result"]["features"]] == ["Gym Private Club"]
    env = sports_facilities(area="city", discipline=None, facilities=facilities(), config=CFG, type="public")
    assert env["result"]["count"] == 3
    # Known only from OSM with no operator:type: never guessed as private.
    env = sports_facilities(area="city", discipline=None, facilities=facilities(), config=CFG, type="unclassified")
    assert [f["properties"]["name"] for f in env["result"]["features"]] == ["Campo Parrocchia"]
    env = sports_facilities(area="city", discipline=None, facilities=facilities(), config=CFG, accessible=True)
    assert env["result"]["count"] == 0  # nothing states accessibility in the fixtures
    with pytest.raises(ValueError):
        sports_facilities(area="city", discipline=None, facilities=facilities(), config=CFG, type="castle")
    # 2 min = 123 m straight line: only p1 (100 m from the football centre) is covered.
    short = sport_coverage(area="city", discipline="football", facilities=facilities(), population=POINTS,
                           config=CFG, max_minutes=2)
    assert short["tool"] == "sport_coverage" and short["inputs"]["max_minutes"] == 2
    assert short["result"]["residents_uncovered"] == 2500
    long = sport_coverage(area="city", discipline="football", facilities=facilities(), population=POINTS,
                          config=CFG, max_minutes=40)  # 40 min = 2462 m straight line: p3 at 2.1 km is covered
    assert long["result"]["residents_uncovered"] == 2000


def test_population_from_census_sections() -> None:
    from twin.modules.sports.deserts import population_from_census

    lon0, lat0 = at(0, 0)
    lon1, lat1 = at(200, 100)
    square = [[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [square]},
         "properties": {"sez_id": "058091000123", "residents": 420, "children_0_14": 55, "municipio": 7, "zone": "10A"}},
        {"type": "Feature", "geometry": None, "properties": {"sez_id": "x", "residents": 1}},
    ]}
    (p,) = population_from_census(fc)
    assert (p.point_id, p.residents, p.children, p.municipio, p.zone) == ("058091000123", 420.0, 55.0, "VII", "10A")
    assert (p.lon, p.lat) == pytest.approx(at(100, 50), abs=1e-9)


def test_closed_facilities_do_not_cover_anyone() -> None:
    from twin.modules.sports.model import FieldValue

    closed = []
    for f in facilities():
        if "football" in f.disciplines:
            f = f.with_changes(extra={**f.extra, "appears_closed": FieldValue(True, "web_unverified")})
        closed.append(f)
    result = coverage(POINTS, closed, "football", reach_radius_m(CFG))
    assert result["residents_uncovered"] == 3500
    assert result["facilities_offering"] == 0
