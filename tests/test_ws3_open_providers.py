"""WS3: live open-data providers and the restricted Cartoradio reader.

The sandbox cannot reach the real endpoints, so each reader is tested on small
files built in the services' published formats, with the HTTP calls replaced.
"""
from __future__ import annotations

import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from twin.providers.base import ROME_BBOX, Provider
from twin.providers.settings import Settings

SETTINGS = Settings.load()
NOW = datetime(2026, 11, 13, 18, 0, tzinfo=timezone.utc)


# --- Roma Mobilita GTFS-RT ------------------------------------------------------

def _gtfs_feed() -> bytes:
    gtfs = pytest.importorskip("google.transit.gtfs_realtime_pb2")
    feed = gtfs.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = int(NOW.timestamp())
    rows = [("bus-1", "64", 12.4823, 41.8960, 5.0, 90.0), ("bus-2", "40", 12.50, 41.90, None, None),
            ("far", "x", 9.19, 45.46, 3.0, 10.0)]
    for vehicle_id, route, lon, lat, speed, bearing in rows:
        entity = feed.entity.add()
        entity.id = vehicle_id
        entity.vehicle.vehicle.id = vehicle_id
        entity.vehicle.trip.trip_id = f"trip-{vehicle_id}"
        entity.vehicle.trip.route_id = route
        entity.vehicle.position.longitude = lon
        entity.vehicle.position.latitude = lat
        if speed is not None:
            entity.vehicle.position.speed = speed
            entity.vehicle.position.bearing = bearing
        entity.vehicle.timestamp = int((NOW - timedelta(seconds=30)).timestamp())
    data: bytes = feed.SerializeToString()
    return data


def _trip_updates() -> bytes:
    gtfs = pytest.importorskip("google.transit.gtfs_realtime_pb2")
    feed = gtfs.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    entity = feed.entity.add()
    entity.id = "1"
    entity.trip_update.trip.trip_id = "trip-bus-1"
    stop = entity.trip_update.stop_time_update.add()
    stop.stop_sequence = 10
    stop.arrival.delay = -280
    stop.arrival.uncertainty = 31
    later = entity.trip_update.stop_time_update.add()
    later.stop_sequence = 11
    later.arrival.delay = 500
    data: bytes = feed.SerializeToString()
    return data


def test_gtfs_rt_vehicle_positions_and_delays_are_parsed_and_filtered() -> None:
    from twin.providers.open.gtfs_rt import DEFAULT_TRIP_UPDATES_URL, RomaGtfsRtProvider

    positions, updates = _gtfs_feed(), _trip_updates()
    provider = RomaGtfsRtProvider(
        SETTINGS, fetch_bytes=lambda url: updates if url == DEFAULT_TRIP_UPDATES_URL else positions)
    assert isinstance(provider, Provider)
    info = provider.describe()
    assert info.kind == "open" and not info.synthetic and info.layer == "transit"
    everything = list(provider.fetch(ROME_BBOX, NOW - timedelta(minutes=5), NOW))
    delays = [obs for obs in everything if obs.entity_type == "PublicTransportDelayObserved"]
    assert len(delays) == 1
    assert delays[0].values == {"delay": -280.0} and delays[0].sigma == {"delay": 31.0}
    assert delays[0].entity_id == "urn:ngsi-ld:PublicTransportDelayObserved:roma-bus-1"
    observations = [obs for obs in everything if obs.entity_type == "Vehicle"]
    assert [obs.entity_id for obs in observations] == ["urn:ngsi-ld:Vehicle:roma-bus-1", "urn:ngsi-ld:Vehicle:roma-bus-2"]
    first = observations[0]
    assert first.values == {"speed_kmh": 18.0, "bearing_deg": 90.0}
    assert set(first.sigma) == set(first.values)
    assert observations[1].values == {}
    assert all(not obs.synthetic and obs.source_id.startswith("roma_gtfs_rt@") for obs in observations)
    # A window that does not contain the snapshot returns nothing.
    assert list(provider.fetch(ROME_BBOX, NOW - timedelta(hours=3), NOW - timedelta(hours=2))) == []


def test_gtfs_rt_reads_a_local_snapshot(tmp_path: Path) -> None:
    from twin.providers.open.gtfs_rt import RomaGtfsRtProvider

    path = tmp_path / "positions.pb"
    path.write_bytes(_gtfs_feed())
    provider = RomaGtfsRtProvider(SETTINGS, source=str(path))
    assert len(list(provider.fetch(ROME_BBOX, NOW - timedelta(minutes=5), NOW))) == 2


# --- EEA hourly air quality ----------------------------------------------------

def _eea_parquet() -> bytes:
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    # Local time is UTC+1, so the hour ending 18:00 local is stamped 17:00 UTC.
    table = pa.table({
        "Samplingpoint": ["IT/SPO.IT0953A_8_chemi_2000", "IT/SPO.IT0953A_8_chemi_2000", "IT/SPO.IT0953A_8_chemi_2000"],
        "Pollutant": [8, 8, 8],
        "Start": [datetime(2026, 11, 13, 17), datetime(2026, 11, 13, 18), datetime(2026, 11, 13, 19)],
        "End": [datetime(2026, 11, 13, 18), datetime(2026, 11, 13, 19), datetime(2026, 11, 13, 20)],
        "Value": [41.0, -999.0, 38.0],
        "Unit": ["ug.m-3"] * 3,
        "AggType": ["hour"] * 3,
        "Validity": [1, -1, 1],
        "Verification": [3, 3, 3],
    })
    buffer = io.BytesIO()
    pq.write_table(table, buffer)
    return buffer.getvalue()


METADATA = (
    "Countrycode\tAirQualityStationEoICode\tSamplingPoint\tAirPollutantCode\tLongitude\tLatitude\n"
    "IT\tIT0953A\tSPO.IT0953A_8_chemi_2000\thttp://dd.eionet.europa.eu/vocabulary/aq/pollutant/8\t12.5069\t41.9327\n"
)


def test_eea_hourly_values_get_coordinates_and_utc_times() -> None:
    from twin.providers.open.eea import EeaHourlyProvider

    parquet = _eea_parquet()
    calls: list[dict[str, Any]] = []

    def post(url: str, body: dict[str, Any]) -> str:
        calls.append(body)
        return "ParquetFileUrl\nhttps://example.test/IT/SPO.IT0953A.parquet\n"

    def get(url: str) -> bytes:
        return METADATA.encode() if url.endswith(".csv") else parquet

    provider = EeaHourlyProvider(SETTINGS, http_post=post, http_get=get)
    assert provider.describe().kind == "open" and not provider.describe().synthetic
    observations = list(provider.fetch(ROME_BBOX, datetime(2026, 11, 13, 16, tzinfo=timezone.utc), NOW + timedelta(hours=2)))
    assert calls[0]["countries"] == ["IT"] and calls[0]["pollutants"] == ["NO2", "PM10", "PM2.5", "O3"]
    assert [obs.observed_at for obs in observations] == [
        datetime(2026, 11, 13, 17, tzinfo=timezone.utc), datetime(2026, 11, 13, 19, tzinfo=timezone.utc)]
    assert all(type(obs.observed_at) is datetime for obs in observations)
    first = observations[0]
    assert first.entity_type == "AirQualityObserved" and first.values == {"no2": 41.0}
    assert first.sigma == {"no2": pytest.approx(6.15)}
    assert (first.lon, first.lat) == (12.5069, 41.9327)


# --- Civil Protection rain radar ------------------------------------------------

def _geotiff(crs: str, transform: Any, array: Any, nodata: float) -> bytes:
    rasterio = pytest.importorskip("rasterio")
    buffer = io.BytesIO()
    with rasterio.MemoryFile() as memory:
        with memory.open(driver="GTiff", width=array.shape[1], height=array.shape[0], count=1,
                         dtype="float32", crs=crs, transform=transform, nodata=nodata,
                         tiled=True, blockxsize=16, blockysize=16) as dst:
            dst.write(array, 1)
        buffer.write(memory.read())
    return buffer.getvalue()


def test_dpc_radar_reads_the_latest_frames_in_the_window() -> None:
    np = pytest.importorskip("numpy")
    rasterio = pytest.importorskip("rasterio")
    from twin.providers.open.dpc_radar import DpcRadarProvider

    array = np.zeros((32, 32), dtype="float32")
    array[10, 10] = 4.5
    array[0, 0] = -9999.0
    tiff = _geotiff("EPSG:4326", rasterio.transform.from_origin(12.3, 42.1, 0.0133, 0.0091), array, -9999.0)
    latest = int(NOW.timestamp() * 1000)
    asked: list[int] = []

    def get_json(url: str) -> Any:
        return {"total": 1, "lastProducts": [{"productType": "SRI", "time": latest, "period": "PT5M"}]}

    def post(url: str, body: dict[str, Any]) -> bytes:
        asked.append(int(body["productDate"]))
        return json.dumps({"url": "https://example.test/x.tif"}).encode()

    provider = DpcRadarProvider(SETTINGS, http_get_json=get_json, http_post=post, http_get=lambda url: tiff)
    info = provider.describe()
    assert info.layer == "rain" and info.kind == "open"
    observations = list(provider.fetch(ROME_BBOX, NOW - timedelta(minutes=10), NOW + timedelta(hours=1)))
    assert sorted(asked) == [latest - 600_000, latest - 300_000, latest]
    one_frame = [obs for obs in observations if obs.observed_at == NOW]
    assert one_frame and all(obs.values["precipitation"] >= 0.0 for obs in one_frame)
    assert max(obs.values["precipitation"] for obs in one_frame) == pytest.approx(4.5)


# --- Cartoradio (restricted) ---------------------------------------------------

def _cartoradio_fixture(tmp_path: Path) -> Path:
    np = pytest.importorskip("numpy")
    rasterio = pytest.importorskip("rasterio")
    # 100 m cells in Web Mercator around Piazza Venezia (x 1389500, y 5145000).
    array = np.full((40, 40), 0.6, dtype="float32")
    array[20, 20] = 15.0
    array[0, :] = -9999.0
    transform = rasterio.transform.from_origin(1387500.0, 5147000.0, 100.0, 100.0)
    path = tmp_path / "fixture" / "carto.tif"
    path.parent.mkdir()
    path.write_bytes(_geotiff("EPSG:3857", transform, array, -9999.0))
    return path


def test_cartoradio_window_is_read_with_range_and_cap_flag(tmp_path: Path) -> None:
    from twin.providers.restricted.cartoradio import CartoradioGridProvider

    provider = CartoradioGridProvider(SETTINGS, source=str(_cartoradio_fixture(tmp_path)))
    info = provider.describe()
    assert info.kind == "restricted" and info.redistribution is False and not info.synthetic
    assert "Cartoradio" in info.notes
    bbox = (12.46, 41.88, 12.50, 41.91)
    observations = list(provider.fetch(bbox, NOW, NOW))
    assert observations and all(obs.entity_type == "EMFEstimate" for obs in observations)
    capped = [obs for obs in observations if obs.values["at_cap"] == 1.0]
    assert len(capped) == 1 and capped[0].values["electricField"] == 15.0
    normal = next(obs for obs in observations if obs.values["at_cap"] == 0.0)
    assert normal.values["electricField"] == pytest.approx(0.6)
    # 4 dB one-sigma spread: factor 10^(4/20) - 1 = 0.585
    assert normal.sigma["electricField"] == pytest.approx(0.6 * 0.585, rel=0.01)
    assert all(-9999.0 not in obs.values.values() for obs in observations)
    assert observations[0].observed_at == datetime(2026, 9, 8, tzinfo=timezone.utc)


def test_cartoradio_never_writes_anything_to_disk(tmp_path: Path) -> None:
    from twin.providers.restricted.cartoradio import CartoradioGridProvider

    source = _cartoradio_fixture(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    before = set(Path(tmp_path).rglob("*"))
    cwd = os.getcwd()
    try:
        os.chdir(work)
        list(CartoradioGridProvider(SETTINGS, source=str(source)).fetch(ROME_BBOX, NOW, NOW))
    finally:
        os.chdir(cwd)
    assert set(Path(tmp_path).rglob("*")) == before


def test_cartoradio_default_source_is_a_remote_range_read() -> None:
    from twin.providers.restricted.cartoradio import CartoradioGridProvider

    assert CartoradioGridProvider(SETTINGS).source.startswith("/vsicurl/https://")


def test_eea_station_error_has_a_floor_for_low_readings() -> None:
    """A reference instrument is never better than its between-sampler uncertainty, even near zero."""
    from twin.providers.open.eea import parse_rows

    row = {"Samplingpoint": "IT/SPO.IT0953A_5_BETA", "Pollutant": 5, "Value": 8.0, "Validity": 1,
           "End": datetime(2026, 11, 13, 1, 0)}
    stations = {"IT0953A": (12.5069, 41.9327)}
    plain = next(parse_rows([row], stations, {5: "PM10"}, 1.0, 0.15, "eea"))
    floored = next(parse_rows([row], stations, {5: "PM10"}, 1.0, 0.15, "eea", sigma_floor={"pm10": 2.0}))
    assert plain.sigma["pm10"] == pytest.approx(1.2)
    assert floored.sigma["pm10"] == pytest.approx((1.2**2 + 2.0**2) ** 0.5, abs=1e-3)


def test_eea_hourly_answers_a_now_window_with_the_latest_hours_and_nearby_stations() -> None:
    """EEA up-to-date data lags a few hours, and a district may hold no station: look back and around."""
    from twin.providers.open.eea import EeaHourlyProvider

    parquet = _eea_parquet()
    provider = EeaHourlyProvider(
        SETTINGS, http_post=lambda url, body: "ParquetFileUrl\nhttps://example.test/IT/SPO.IT0953A.parquet\n",
        http_get=lambda url: METADATA.encode() if url.endswith(".csv") else parquet)
    now = datetime(2026, 11, 13, 21, 43, tzinfo=timezone.utc)
    # A small box 2 km south of the station (12.5069, 41.9327), asked for "now" only.
    small = (12.495, 41.905, 12.515, 41.915)
    observations = list(provider.fetch(small, now, now))
    assert [obs.observed_at.hour for obs in observations] == [17, 19]
    assert (observations[0].lon, observations[0].lat) == (12.5069, 41.9327)


def test_http_get_retries_a_reset_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    from twin.providers import http

    attempts: list[int] = []

    class _Answer:
        def __enter__(self) -> "_Answer":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"ok"

    def flaky(request: object, timeout: float) -> _Answer:
        attempts.append(1)
        if len(attempts) < 2:
            raise urllib.error.URLError(ConnectionResetError(104, "reset"))
        return _Answer()

    monkeypatch.setattr(http.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(http, "RETRY_PAUSE_S", 0.0)
    assert http.get_bytes("https://example.test/x") == b"ok" and len(attempts) == 2


def test_gtfs_rt_answers_a_now_window_and_reports_the_feed_time() -> None:
    from twin.providers.open.gtfs_rt import RomaGtfsRtProvider

    provider = RomaGtfsRtProvider(SETTINGS, source="https://example.test/positions.pb",
                                  fetch_bytes=lambda url: _gtfs_feed())
    later = NOW + timedelta(minutes=3)  # positions are a few minutes old when asked about "now"
    assert len(list(provider.fetch(ROME_BBOX, later, later))) == 2
    assert provider.last_feed_time is not None and provider.last_feed_time <= later
    # A feed hours old is not passed off as live.
    assert list(provider.fetch(ROME_BBOX, NOW + timedelta(hours=3), NOW + timedelta(hours=3))) == []
