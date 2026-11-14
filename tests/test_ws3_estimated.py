"""WS3: estimated antenna register (real sources fused with a physical model) and real point feeds."""
from __future__ import annotations

import gzip
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pytest

from twin.providers.base import ROME_BBOX, Provider, ProviderNotConfigured
from twin.providers.estimated.register import (
    MODEL_A_FIELDS,
    EstimatedRegisterProvider,
    find_peaks,
    fit_effective_eirp,
)
from twin.providers.estimated.sites import Cell, cluster_sites, read_opencellid_csv, read_osm_masts
from twin.providers.geo import offset
from twin.providers.raster import RasterCell
from twin.providers.settings import Settings

T0 = datetime(2026, 11, 13, 8, 0, tzinfo=timezone.utc)
CENTRE = (12.4823, 41.8960)
SETTINGS = Settings.load()
ROOT_DIR = Path(__file__).resolve().parents[1]


# --- site positions from OpenCelliD / OSM ----------------------------------------

def _cell(net: int, cell: int, east_m: float, radio: str = "LTE") -> Cell:
    lon, lat = offset(*CENTRE, east_m=east_m, north_m=0.0)
    return Cell(radio=radio, mcc=222, net=net, cell=cell, lon=lon, lat=lat, samples=10)


def test_cells_of_one_enodeb_become_one_site() -> None:
    cells = [_cell(1, (12345 << 8) + sector, east_m=30.0 * sector) for sector in range(3)]
    sites = cluster_sites(cells, shift_bits={"LTE": 8}, merge_distance_m=150.0)
    assert len(sites) == 1 and sites[0].net == 1 and sites[0].n_cells == 3


def test_close_sites_merge_but_operators_stay_apart() -> None:
    cells = [
        _cell(1, 100 << 8, east_m=0.0),
        _cell(1, 200 << 8, east_m=80.0),     # same operator, 80 m away -> merged
        _cell(10, 300 << 8, east_m=40.0),    # other operator -> separate
        _cell(1, 400 << 8, east_m=2000.0),   # same operator, far -> separate
    ]
    assert sorted(s.n_cells for s in cluster_sites(cells, {"LTE": 8}, 150.0)) == [1, 1, 2]


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
    assert [c.cell for c in read_opencellid_csv(path, mcc=222, bbox=ROME_BBOX)] == [3160321]


def test_osm_masts_accept_nodes_and_way_centres(tmp_path: Path) -> None:
    path = tmp_path / "masts.json"
    path.write_text(json.dumps({"elements": [
        {"type": "node", "id": 1, "lat": 41.9, "lon": 12.5},
        {"type": "way", "id": 2, "center": {"lat": 41.91, "lon": 12.51}},
        {"type": "node", "id": 3},
    ]}), encoding="utf-8")
    assert read_osm_masts(path) == [(12.5, 41.9), (12.51, 41.91)]


# --- fusion with the Cartoradio grid ----------------------------------------------

def _grid_from_sources(sources: list[tuple[float, float, float]], background: float = 0.3,
                       size: int = 40, cell_m: float = 75.0) -> list[RasterCell]:
    """A field grid computed from known sources with the same free-space model (test data)."""
    cells: list[RasterCell] = []
    for row in range(size):
        for col in range(size):
            lon, lat = offset(*CENTRE, east_m=(col - size / 2) * cell_m, north_m=(size / 2 - row) * cell_m)
            e2 = background**2
            for slon, slat, power in sources:
                dx = (lon - slon) * 111_320.0 * math.cos(math.radians(lat))
                dy = (lat - slat) * 110_540.0
                e2 += 30.0 * power / (dx * dx + dy * dy + 20.0**2)
            cells.append(RasterCell(row, col, lon, lat, math.sqrt(e2)))
    return cells


def test_peaks_are_found_where_the_sources_are_and_plateaus_count_once() -> None:
    a = offset(*CENTRE, east_m=-600.0, north_m=0.0)
    b = offset(*CENTRE, east_m=700.0, north_m=300.0)
    cells = _grid_from_sources([(a[0], a[1], 200.0), (b[0], b[1], 80.0)])
    peaks = find_peaks(cells, min_value=1.0)
    assert len(peaks) == 2
    flat = [RasterCell(r, c, 0.0, 0.0, 15.0 if (r, c) in {(1, 1), (1, 2)} else 1.0) for r in range(4) for c in range(4)]
    assert [(p.row, p.col) for p in find_peaks(flat, min_value=2.0)] == [(1, 1)]


def test_fit_recovers_the_power_of_known_sources() -> None:
    a = offset(*CENTRE, east_m=-600.0, north_m=0.0)
    b = offset(*CENTRE, east_m=700.0, north_m=300.0)
    cells = _grid_from_sources([(a[0], a[1], 200.0), (b[0], b[1], 80.0)])
    powers, sigmas, counts, background, error_db = fit_effective_eirp(
        [a, b], cells, radius_m=500.0, height_m=20.0, sigma_db=4.0, cap=15.0)
    assert powers[0] == pytest.approx(200.0, rel=0.1)
    assert powers[1] == pytest.approx(80.0, rel=0.1)
    assert all(s >= 0.0 for s in sigmas) and all(n > 50 for n in counts)
    assert math.sqrt(background) == pytest.approx(0.3, rel=0.3)
    assert error_db < 1.0


class _FakeCartoradio:
    """Stands in for the restricted grid in tests (fixture values, not a layer)."""

    def __init__(self, cells: list[RasterCell]) -> None:
        self._cells = cells

    def fetch(self, bbox: object, start: object, end: object) -> list[object]:
        from twin.providers.base import Observation

        return [Observation(f"urn:ngsi-ld:EMFEstimate:cartoradio-r{c.row}-c{c.col}", "EMFEstimate", c.lon, c.lat,
                            T0, {"electricField": c.value, "at_cap": 0.0}, {"electricField": 0.1, "at_cap": 0.0},
                            "cartoradio_grid", False) for c in self._cells]


def test_register_fuses_seed_positions_peaks_and_fitted_power(tmp_path: Path) -> None:
    near_seed = offset(*CENTRE, east_m=-600.0, north_m=0.0)
    lonely_peak = offset(*CENTRE, east_m=700.0, north_m=300.0)
    cells = _grid_from_sources([(near_seed[0], near_seed[1], 300.0), (lonely_peak[0], lonely_peak[1], 600.0)])
    seed_position = offset(*near_seed, east_m=150.0, north_m=0.0)  # OpenCelliD is off by 150 m
    seed = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "geometry": {"type": "Point", "coordinates": list(seed_position)},
        "properties": {"net": 1, "n_cells": 3, "technologies": ["LTE"]}}]}
    (tmp_path / "sites.geojson").write_text(json.dumps(seed), encoding="utf-8")
    providers = dict(SETTINGS.providers)
    register = SETTINGS.section("estimated", "register")
    providers["estimated"] = {"register": {**register, "refit": {**register["refit"], "enabled": False},
                                           "opencellid_csv": "", "osm_masts_json": "",
                                           "sites_geojson": str(tmp_path / "sites.geojson")}}
    settings = Settings(providers=providers, emf=SETTINGS.emf, root=tmp_path)
    provider = EstimatedRegisterProvider(settings, cartoradio=_FakeCartoradio(cells))  # type: ignore[arg-type]
    assert isinstance(provider, Provider)
    info = provider.describe()
    assert info.synthetic is False and info.redistribution is False and "Cartoradio" in info.notes
    sites = provider.sites()
    by_source = {s.position_source: s for s in sites}
    assert set(by_source) == {"cartoradio_peak", "cartoradio_peak_only"}
    assert by_source["cartoradio_peak"].operator == "TIM"
    assert by_source["cartoradio_peak_only"].operator == "unknown"
    assert by_source["cartoradio_peak"].effective_eirp_w == pytest.approx(300.0, rel=0.25)
    assert by_source["cartoradio_peak_only"].effective_eirp_w == pytest.approx(600.0, rel=0.25)
    record = sites[0].to_model_a()
    assert set(record) == set(MODEL_A_FIELDS)
    assert record["sectors"] is None and record["authorisation_status"] is None
    assert record["data_kind"] == "estimated" and record["calibration"] == "uncalibrated"
    observations = list(provider.fetch(ROME_BBOX, T0, T0))
    assert all(not obs.synthetic and obs.entity_type == "AntennaSite" for obs in observations)
    assert all(set(obs.sigma) == set(obs.values) for obs in observations)


def test_register_v2_estimates_sector_directions_and_heights(tmp_path: Path) -> None:
    site = offset(*CENTRE, east_m=0.0, north_m=0.0)
    cells = _grid_from_sources([(site[0], site[1], 400.0)])
    seed = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "geometry": {"type": "Point", "coordinates": list(site)},
        "properties": {"net": 1, "n_cells": 3, "technologies": ["LTE"]}}]}
    (tmp_path / "sites.geojson").write_text(json.dumps(seed), encoding="utf-8")
    providers = dict(SETTINGS.providers)
    register = SETTINGS.section("estimated", "register")
    providers["estimated"] = {"register": {**register, "refit": {**register["refit"], "enabled": True},
                                           "opencellid_csv": "", "osm_masts_json": "",
                                           "sites_geojson": str(tmp_path / "sites.geojson")}}
    settings = Settings(providers=providers, emf=SETTINGS.emf, root=tmp_path)
    provider = EstimatedRegisterProvider(settings, cartoradio=_FakeCartoradio(cells))  # type: ignore[arg-type]
    record = provider.sites()[0].to_model_a()
    assert set(record) == set(MODEL_A_FIELDS)
    assert record["antenna_height_agl_m"] is not None and record["antenna_height_agl_m"] > 0
    assert len(record["sectors"]) == 3
    azimuths = sorted(s["azimuth_deg"] for s in record["sectors"])
    assert azimuths[1] - azimuths[0] == pytest.approx(120.0)
    assert all(s["status"] == "estimated" for s in record["sectors"])
    assert record["data_kind"] == "estimated" and record["calibration"] == "uncalibrated"


# --- real point feeds ------------------------------------------------------------

def test_arpa_points_need_a_table_and_never_invent_values() -> None:
    from twin.providers.open.arpa_points import ArpaPointsProvider

    with pytest.raises(ProviderNotConfigured, match="table_path"):
        ArpaPointsProvider(SETTINGS)


def test_arpa_points_read_the_table_and_refuse_personal_columns(tmp_path: Path) -> None:
    from twin.providers.open.arpa_points import ArpaPointsProvider, parse_measurements

    table = tmp_path / "arpa.csv"
    table.write_text("lon,lat,measured_on,e_v_m,location\n12.49,41.91,2016-05-04,1.8,Via X\n"
                     "12.50,41.92,2017-02-01,0.9,\n", encoding="utf-8")
    providers = dict(SETTINGS.providers)
    providers["open"] = {**SETTINGS.section("open"), "arpa_points": {"table_path": str(table), "relative_sigma": 0.26}}
    provider = ArpaPointsProvider(Settings(providers=providers, emf=SETTINGS.emf, root=tmp_path))
    observations = list(provider.fetch(ROME_BBOX, T0, T0))
    assert [obs.values["electricField"] for obs in observations] == [1.8, 0.9]
    assert observations[0].sigma["electricField"] == pytest.approx(0.468)
    assert observations[0].entity_type == "ElectromagneticFieldObserved" and not observations[0].synthetic
    with pytest.raises(ValueError, match="personal"):
        parse_measurements("lon,lat,measured_on,e_v_m,nome_esponente\n", 0.26, "x")


def test_gbfs_keeps_available_vehicles_without_ids() -> None:
    from twin.providers.open.gbfs import GbfsProvider

    feed = {"last_updated": int(T0.timestamp()), "ttl": 60, "data": {"bikes": [
        {"bike_id": "secret-1", "lat": 41.9, "lon": 12.5, "is_disabled": False, "is_reserved": False,
         "current_range_meters": 35520.0},
        {"bike_id": "secret-2", "lat": 41.9, "lon": 12.5, "is_disabled": False, "is_reserved": True},
        {"bike_id": "secret-3", "lat": 41.9, "lon": 12.5, "is_disabled": True, "is_reserved": False},
    ]}}
    provider = GbfsProvider(SETTINGS, fetch_bytes=lambda url: json.dumps(feed).encode())
    observations = list(provider.fetch(ROME_BBOX, T0, T0))
    assert len(observations) == 1
    assert observations[0].values == {"availableVehicles": 1.0, "rangeKm": 35.5}
    assert "secret" not in observations[0].entity_id
    assert provider.describe().synthetic is False


def test_sensor_community_pm_gets_a_wider_sigma_in_humid_air() -> None:
    from twin.providers.open.sensor_community import SensorCommunityProvider

    stamp = T0.strftime("%Y-%m-%d %H:%M:%S")
    records = [
        {"location": {"id": 1, "longitude": "12.50", "latitude": "41.90", "indoor": 0}, "sensor": {"id": 10},
         "timestamp": stamp, "sensordatavalues": [{"value_type": "P1", "value": "20.0"}, {"value_type": "P2", "value": "10.0"}]},
        {"location": {"id": 2, "longitude": "12.51", "latitude": "41.91", "indoor": 0}, "sensor": {"id": 11},
         "timestamp": stamp, "sensordatavalues": [{"value_type": "P1", "value": "20.0"}, {"value_type": "P2", "value": "999.9"}]},
        {"location": {"id": 2, "longitude": "12.51", "latitude": "41.91", "indoor": 0}, "sensor": {"id": 12},
         "timestamp": stamp, "sensordatavalues": [{"value_type": "humidity", "value": "95"}]},
        {"location": {"id": 3, "longitude": "12.52", "latitude": "41.92", "indoor": 1}, "sensor": {"id": 13},
         "timestamp": stamp, "sensordatavalues": [{"value_type": "P1", "value": "50.0"}]},
    ]
    provider = SensorCommunityProvider(SETTINGS, fetch_bytes=lambda url: json.dumps(records).encode())
    observations = list(provider.fetch(ROME_BBOX, T0, T0))
    assert [obs.values for obs in observations] == [{"pm10": 20.0, "pm25": 10.0}, {"pm10": 20.0}]
    assert observations[0].sigma["pm10"] == pytest.approx(8.0)       # dry: 40 %
    assert observations[1].sigma["pm10"] == pytest.approx(16.0)      # humid: doubled
    assert all(obs.entity_type == "AirQualityObserved" and not obs.synthetic for obs in observations)


def test_cams_model_background_is_labelled_as_a_forecast() -> None:
    from twin.providers.open.open_meteo import CamsOpenMeteoProvider, lattice

    points = lattice((12.40, 41.80, 12.60, 41.90), 0.1)
    assert len(points) == 2
    answers = [{"latitude": p[1], "longitude": p[0], "hourly": {
        "time": ["2026-11-13T08:00"], "nitrogen_dioxide": [30.0], "pm10": [20.0], "pm2_5": [None]}} for p in points]
    provider = CamsOpenMeteoProvider(SETTINGS, fetch_bytes=lambda url: json.dumps(answers).encode())
    observations = list(provider.fetch((12.40, 41.80, 12.60, 41.90), T0, T0))
    assert len(observations) == 2
    assert observations[0].entity_type == "AirQualityForecast"
    assert observations[0].values == {"no2": 30.0, "pm10": 20.0}
    assert observations[0].sigma == {"no2": 15.0, "pm10": 10.0}


def test_cams_answers_a_small_area_and_a_now_window() -> None:
    from twin.providers.open.open_meteo import CamsOpenMeteoProvider, lattice

    small = (12.47, 41.89, 12.49, 41.90)  # smaller than one 0.1 degree model cell
    assert lattice(small, 0.1) == [(12.48, 41.895)]
    answers = [{"latitude": 41.895, "longitude": 12.48, "hourly": {
        "time": ["2026-11-13T07:00", "2026-11-13T08:00", "2026-11-13T09:00"],
        "nitrogen_dioxide": [28.0, 30.0, 33.0], "pm10": [20.0, 20.0, 21.0], "pm2_5": [9.0, 10.0, 11.0]}}]
    provider = CamsOpenMeteoProvider(SETTINGS, fetch_bytes=lambda url: json.dumps(answers).encode())
    now = datetime(2026, 11, 13, 8, 43, tzinfo=timezone.utc)
    observations = list(provider.fetch(small, now, now))
    assert [obs.observed_at.hour for obs in observations] == [8]
    assert observations[0].values["no2"] == 30.0


def test_osm_masts_also_read_from_geojson(tmp_path: Path) -> None:
    path = tmp_path / "masts.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [12.4088, 41.8276]},
         "properties": {"osm_id": "node/1", "man_made": "tower"}},
        {"type": "Feature", "geometry": None, "properties": {}},
    ]}), encoding="utf-8")
    assert read_osm_masts(path) == [(12.4088, 41.8276)]


def test_committed_osm_mast_seed_is_configured() -> None:
    masts_path = SETTINGS.path(str(SETTINGS.section("estimated", "register")["osm_masts_json"]))
    assert masts_path is not None and masts_path.exists()
    assert len(read_osm_masts(masts_path)) > 300


def test_gbfs_snapshot_answers_a_now_window_despite_clock_skew() -> None:
    from datetime import timedelta

    from twin.providers.open.gbfs import GbfsProvider

    feed = {"last_updated": int((T0 + timedelta(seconds=30)).timestamp()), "data": {"bikes": [
        {"lat": 41.9, "lon": 12.5, "is_disabled": False, "is_reserved": False}]}}
    provider = GbfsProvider(SETTINGS, fetch_bytes=lambda url: json.dumps(feed).encode())
    assert len(list(provider.fetch(ROME_BBOX, T0, T0))) == 1  # feed clock 30 s ahead of ours
    assert len(list(provider.fetch(ROME_BBOX, T0 + timedelta(minutes=5), T0 + timedelta(minutes=5)))) == 1
    assert list(provider.fetch(ROME_BBOX, T0 + timedelta(hours=2), T0 + timedelta(hours=2))) == []
