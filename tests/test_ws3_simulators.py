"""WS3: simulated sensors (antenna register, EMF points, applications, loops)."""
from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from twin.providers.base import ROME_BBOX, Provider
from twin.providers.geo import distance_m, offset
from twin.providers.settings import Settings
from twin.providers.simulated.applications import SimApplicationsProvider
from twin.providers.simulated.emf_points import SimEmfPointsProvider
from twin.providers.simulated.loops import SimLoopsProvider
from twin.providers.simulated.register import (
    MODEL_A_FIELDS,
    Cell,
    SimRegisterProvider,
    cluster_sites,
    read_opencellid_csv,
    read_osm_masts,
)

T0 = datetime(2026, 11, 13, 8, 0, tzinfo=timezone.utc)
CENTRE = (12.4823, 41.8960)
SETTINGS = Settings.load()
ROOT_DIR = Path(__file__).resolve().parents[1]


def _settings_without_seeds(tmp_path: Path) -> Settings:
    """Repository settings, but with a root where no seed file exists."""
    return Settings(providers=SETTINGS.providers, emf=SETTINGS.emf, root=tmp_path)


def _settings_with_seeds(tmp_path: Path, cells_csv: str, masts: dict[str, object]) -> Settings:
    register = SETTINGS.section("simulators", "register")
    (tmp_path / "data/raw/opencellid").mkdir(parents=True)
    (tmp_path / "data/raw/osm").mkdir(parents=True)
    with gzip.open(tmp_path / str(register["opencellid_csv"]), "wt", encoding="utf-8") as handle:
        handle.write(cells_csv)
    (tmp_path / str(register["osm_masts_json"])).write_text(json.dumps(masts), encoding="utf-8")
    return Settings(providers=SETTINGS.providers, emf=SETTINGS.emf, root=tmp_path)


# --- geometry helpers ---------------------------------------------------------

def test_offset_and_distance_agree() -> None:
    lon, lat = offset(*CENTRE, east_m=300.0, north_m=400.0)
    assert abs(distance_m(*CENTRE, lon, lat) - 500.0) < 1.0


# --- antenna register ---------------------------------------------------------

def _cell(net: int, cell: int, east_m: float, radio: str = "LTE", north_m: float = 0.0) -> Cell:
    lon, lat = offset(*CENTRE, east_m=east_m, north_m=north_m)
    return Cell(radio=radio, mcc=222, net=net, cell=cell, lon=lon, lat=lat, samples=10)


def test_cells_of_one_enodeb_become_one_site() -> None:
    enb = 12345
    cells = [_cell(1, (enb << 8) + sector, east_m=30.0 * sector) for sector in range(3)]
    sites = cluster_sites(cells, shift_bits={"LTE": 8}, merge_distance_m=150.0)
    assert len(sites) == 1
    assert sites[0].net == 1 and sites[0].n_cells == 3


def test_close_sites_merge_but_operators_stay_apart() -> None:
    cells = [
        _cell(1, 100 << 8, east_m=0.0),
        _cell(1, 200 << 8, east_m=80.0),     # same operator, 80 m away -> merged
        _cell(10, 300 << 8, east_m=40.0),    # other operator -> separate
        _cell(1, 400 << 8, east_m=2000.0),   # same operator, far -> separate
    ]
    sites = cluster_sites(cells, shift_bits={"LTE": 8}, merge_distance_m=150.0)
    assert sorted(site.n_cells for site in sites) == [1, 1, 2]


def test_opencellid_csv_is_filtered_to_country_and_bbox(tmp_path: Path) -> None:
    lon, lat = CENTRE
    text = (
        "radio,mcc,net,area,cell,unit,lon,lat,range,samples,changeable,created,updated,averageSignal\n"
        f"LTE,222,1,100,3160321,0,{lon},{lat},500,12,1,0,0,0\n"
        f"LTE,208,1,100,3160322,0,{lon},{lat},500,12,1,0,0,0\n"   # France: dropped
        "LTE,222,1,100,3160323,0,9.19,45.46,500,12,1,0,0,0\n"     # Milan: dropped
    )
    path = tmp_path / "cells.csv.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(text)
    cells = read_opencellid_csv(path, mcc=222, bbox=ROME_BBOX)
    assert [cell.cell for cell in cells] == [3160321]


def test_osm_masts_accept_nodes_and_way_centres(tmp_path: Path) -> None:
    path = tmp_path / "masts.json"
    path.write_text(json.dumps({"elements": [
        {"type": "node", "id": 1, "lat": 41.9, "lon": 12.5, "tags": {"man_made": "mast"}},
        {"type": "way", "id": 2, "center": {"lat": 41.91, "lon": 12.51}, "tags": {"man_made": "tower"}},
        {"type": "node", "id": 3, "tags": {}},  # no position: skipped
    ]}), encoding="utf-8")
    assert read_osm_masts(path) == [(12.5, 41.9), (12.51, 41.91)]


def test_register_without_seeds_is_generated_reproducible_and_synthetic(tmp_path: Path) -> None:
    settings = _settings_without_seeds(tmp_path)
    first = SimRegisterProvider(settings)
    second = SimRegisterProvider(settings)
    assert isinstance(first, Provider)
    info = first.describe()
    assert info.kind == "simulated" and info.synthetic and info.layer == "antenna_register"
    assert first.sites() == second.sites()
    assert len(first.sites()) == 1500
    observations = list(first.fetch(ROME_BBOX, T0, T0))
    assert observations and all(obs.synthetic for obs in observations)
    assert all(obs.source_id == "sim_register:generated" for obs in observations)
    assert all(obs.entity_type == "AntennaSite" for obs in observations)
    assert all(set(obs.sigma) == set(obs.values) for obs in observations)


def test_register_records_use_model_a_field_names(tmp_path: Path) -> None:
    record = SimRegisterProvider(_settings_without_seeds(tmp_path)).sites()[0].to_model_a()
    assert set(record) == set(MODEL_A_FIELDS)
    assert record["synthetic"] is True
    assert record["operator"] in {"TIM", "Vodafone", "Iliad", "WINDTRE"}
    for sector in record["sectors"]:
        assert 0.0 <= sector["azimuth_deg"] < 360.0
        assert sector["eirp_w"] > 0.0


def test_register_is_seeded_from_opencellid_and_snapped_to_osm_masts(tmp_path: Path) -> None:
    lon, lat = CENTRE
    mast_lon, mast_lat = offset(lon, lat, east_m=120.0, north_m=0.0)
    far_lon, far_lat = offset(lon, lat, east_m=5000.0, north_m=0.0)
    header = "radio,mcc,net,area,cell,unit,lon,lat,range,samples,changeable,created,updated,averageSignal\n"
    rows = [
        f"LTE,222,1,100,{(500 << 8) + s},0,{lon},{lat},500,12,1,0,0,0" for s in range(3)
    ] + [f"LTE,222,10,100,{(900 << 8)},0,{far_lon},{far_lat},500,12,1,0,0,0"]
    masts = {"elements": [{"type": "node", "id": 7, "lat": mast_lat, "lon": mast_lon, "tags": {}}]}
    provider = SimRegisterProvider(_settings_with_seeds(tmp_path, header + "\n".join(rows) + "\n", masts))
    sites = provider.sites()
    assert len(sites) == 2
    snapped = [site for site in sites if site.position_source == "osm_mast"]
    assert len(snapped) == 1 and snapped[0].operator == "TIM"
    assert distance_m(snapped[0].lon, snapped[0].lat, mast_lon, mast_lat) < 1.0
    assert {obs.source_id for obs in provider.fetch(ROME_BBOX, T0, T0)} == {"sim_register:opencellid"}


# --- EMF monitoring points ----------------------------------------------------

def test_emf_points_are_hourly_reproducible_and_synthetic(tmp_path: Path) -> None:
    settings = _settings_without_seeds(tmp_path)
    provider = SimEmfPointsProvider(settings)
    assert provider.describe().layer == "emf_measurements" and provider.describe().synthetic
    window = list(provider.fetch(ROME_BBOX, T0, T0 + timedelta(hours=2)))
    assert len(window) == 40 * 3
    again = list(SimEmfPointsProvider(settings).fetch(ROME_BBOX, T0, T0))
    assert again == [obs for obs in window if obs.observed_at == T0]
    for obs in window:
        assert obs.synthetic and obs.entity_type == "ElectromagneticFieldObserved"
        assert 0.0 < obs.values["electricField"] < 61.0
        assert obs.sigma["electricField"] > 0.0


def test_emf_points_follow_network_load(tmp_path: Path) -> None:
    provider = SimEmfPointsProvider(_settings_without_seeds(tmp_path))
    night = T0.replace(hour=3)
    evening = T0.replace(hour=19)

    def total(moment: datetime) -> float:
        return sum(obs.values["electricField"] for obs in provider.fetch(ROME_BBOX, moment, moment))

    assert total(evening) > total(night)


# --- application inbox --------------------------------------------------------

def test_applications_are_synthetic_and_dated() -> None:
    provider = SimApplicationsProvider(SETTINGS)
    info = provider.describe()
    assert info.synthetic and info.layer == "antenna_applications"
    records = provider.applications()
    assert len(records) == 5 and all(record["synthetic"] for record in records)
    assert all(record["status"] == "submitted" for record in records)
    before = list(provider.fetch(ROME_BBOX, T0, datetime(2026, 10, 10, tzinfo=timezone.utc)))
    assert {obs.entity_id.rsplit(":", 1)[-1] for obs in before} == {"sim-app-001", "sim-app-002"}


# --- loops: settings-driven and versioned -------------------------------------

def test_loops_read_station_positions_from_a_geojson_file(tmp_path: Path) -> None:
    stations = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [12.49, 41.90]},
         "properties": {"road_class": "primary"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [12.52, 41.88]}, "properties": {}},
    ]}
    path = tmp_path / "stations.geojson"
    path.write_text(json.dumps(stations), encoding="utf-8")
    provider = SimLoopsProvider(seed=5, stations_path=path)
    observations = list(provider.fetch(ROME_BBOX, T0, T0))
    assert [(obs.lon, obs.lat) for obs in observations] == [(12.49, 41.90), (12.52, 41.88)]


def test_loops_from_settings_carry_the_simulator_version() -> None:
    provider = SimLoopsProvider.from_settings(SETTINGS)
    assert SETTINGS.simulator_version in provider.describe().notes
    assert len(list(provider.fetch(ROME_BBOX, T0, T0))) == 93


def test_committed_loop_seed_sits_on_major_roads_at_controlled_signals() -> None:
    seed = ROOT_DIR / "twin/providers/simulated/seed_data/loop_stations.geojson"
    data = json.loads(seed.read_text(encoding="utf-8"))
    features = data["features"]
    assert len(features) == 93
    for feature in features:
        props = feature["properties"]
        assert props["road_class"] in {"motorway", "trunk", "primary", "secondary"}
        assert props["control_system"] and props["road_name"]
    points = [tuple(f["geometry"]["coordinates"]) for f in features]
    closest = min(distance_m(*a, *b) for i, a in enumerate(points) for b in points[i + 1:])
    assert closest >= 600.0
    provider = SimLoopsProvider.from_settings(SETTINGS)
    assert "signalised junctions" in provider.describe().notes
    assert {(obs.lon, obs.lat) for obs in provider.fetch(ROME_BBOX, T0, T0)} == set(points)


def test_loop_selection_keeps_controlled_vehicle_signals_near_major_roads() -> None:
    from twin.providers.simulated.build_seeds import select_loop_stations

    road = {"type": "Feature", "properties": {"code": 5113, "name": "Via Nomentana"},
            "geometry": {"type": "LineString", "coordinates": [[12.50, 41.91], [12.52, 41.91]]}}
    track = {"type": "Feature", "properties": {"code": 5141, "name": "Vicolo"},
             "geometry": {"type": "LineString", "coordinates": [[12.50, 41.95], [12.52, 41.95]]}}

    def signal(lon: float, lat: float, kind: str = "V", system: str | None = "Omnia") -> dict[str, object]:
        return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {"TIPO": kind, "SISTEMA_1": system, "COD_IMP": "1"}}

    signals = {"features": [
        signal(12.505, 41.9101),                # on the primary road: kept
        signal(12.5052, 41.9101),               # 17 m from the first: dropped by spacing
        signal(12.515, 41.9101, kind="P"),      # pedestrian signal: dropped
        signal(12.516, 41.9101, system=None),   # not centrally controlled: dropped
        signal(12.51, 41.9501),                 # next to a minor road only: dropped
    ]}
    result = select_loop_stations(signals, {"features": [road, track]}, n_stations=10, snap_m=40.0,
                                  spacing_m=600.0, seed=1)
    assert [f["properties"]["road_name"] for f in result["features"]] == ["Via Nomentana"]


def test_point_in_polygon_respects_holes() -> None:
    from twin.providers.simulated.build_seeds import in_polygons

    square = [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)],
              [(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0), (4.0, 4.0)]]
    assert in_polygons(1.0, 1.0, [square])
    assert not in_polygons(5.0, 5.0, [square])
    assert not in_polygons(11.0, 5.0, [square])


def test_committed_antenna_seed_gives_estimated_positions_inside_rome() -> None:
    provider = SimRegisterProvider(SETTINGS)
    sites = provider.sites()
    assert len(sites) > 500
    assert {site.position_source for site in sites} <= {"opencellid", "osm_mast"}
    assert {site.operator for site in sites} <= {"TIM", "Vodafone", "Iliad", "WINDTRE"}
    assert all(ROME_BBOX[0] <= s.lon <= ROME_BBOX[2] and ROME_BBOX[1] <= s.lat <= ROME_BBOX[3] for s in sites)
    assert {obs.source_id for obs in provider.fetch(ROME_BBOX, T0, T0)} == {"sim_register:opencellid"}
    assert "OpenCelliD" in provider.describe().notes
