"""Roma Mobilita GTFS-Realtime (layer ``transit``). Real, open (CC BY-SA).

Two feeds are read: vehicle positions (one ``Vehicle`` observation per bus or
tram) and trip updates. They share ``trip_id``, so each vehicle's delay at its
next stop becomes a ``PublicTransportDelayObserved`` observation (``delay`` in
seconds, negative = early) at the vehicle's position.

``parse_vehicle_positions`` and ``parse_trip_delays`` are pure functions so the
ingest stream's snapshot pullers can reuse them on stored bytes. The provider reads either the live URL or
a local snapshot file. Each observation's ``source_id`` carries the SHA-256 of
the bytes it came from, so every value traces to one snapshot.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from twin.providers import http
from twin.providers.base import BBox, Observation, ProviderInfo
from twin.providers.geo import in_bbox
from twin.providers.settings import Settings, number

PROVIDER_ID = "roma_gtfs_rt"
DEFAULT_URL = "https://romamobilita.it/sites/default/files/rome_rtgtfs_vehicle_positions_feed.pb"
DEFAULT_TRIP_UPDATES_URL = "https://romamobilita.it/sites/default/files/rome_rtgtfs_trip_updates_feed.pb"
BEARING_SIGMA_DEG = 10.0


def snapshot_id(data: bytes) -> str:
    return f"{PROVIDER_ID}@{hashlib.sha256(data).hexdigest()[:16]}"


def _feed(data: bytes) -> Any:
    from google.transit import gtfs_realtime_pb2

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(data)
    return feed


def parse_trip_delays(data: bytes) -> dict[str, tuple[float, float | None]]:
    """trip_id -> (delay in s at the next stop, uncertainty in s or None) from a trip-updates feed."""
    delays: dict[str, tuple[float, float | None]] = {}
    for entity in _feed(data).entity:
        if not entity.HasField("trip_update"):
            continue
        update = entity.trip_update
        trip_id = update.trip.trip_id
        if not trip_id:
            continue
        for stop in update.stop_time_update:
            event = stop.arrival if stop.HasField("arrival") else stop.departure
            if event.HasField("delay"):
                uncertainty = float(event.uncertainty) if event.HasField("uncertainty") else None
                delays[trip_id] = (float(event.delay), uncertainty)
                break
        else:
            if update.HasField("delay"):
                delays[trip_id] = (float(update.delay), None)
    return delays


def parse_vehicle_positions(data: bytes, speed_sigma_kmh: float = 3.0) -> list[Observation]:
    """Decode a GTFS-RT FeedMessage into one observation per vehicle with a position."""
    return [obs for obs, _trip in _vehicles(data, speed_sigma_kmh)]


def _vehicles(data: bytes, speed_sigma_kmh: float) -> list[tuple[Observation, str]]:
    feed = _feed(data)
    header_time = int(feed.header.timestamp) if feed.header.HasField("timestamp") else 0
    source = snapshot_id(data)
    observations: list[tuple[Observation, str]] = []
    for entity in feed.entity:
        if not entity.HasField("vehicle") or not entity.vehicle.HasField("position"):
            continue
        vehicle = entity.vehicle
        position = vehicle.position
        vehicle_id = vehicle.vehicle.id if vehicle.vehicle.id else entity.id
        stamp = int(vehicle.timestamp) if vehicle.HasField("timestamp") else header_time
        values: dict[str, float] = {}
        sigma: dict[str, float] = {}
        if position.HasField("speed"):
            values["speed_kmh"] = round(float(position.speed) * 3.6, 1)
            sigma["speed_kmh"] = speed_sigma_kmh
        if position.HasField("bearing"):
            values["bearing_deg"] = round(float(position.bearing), 1)
            sigma["bearing_deg"] = BEARING_SIGMA_DEG
        observations.append((Observation(
            entity_id=f"urn:ngsi-ld:Vehicle:roma-{vehicle_id}",
            entity_type="Vehicle",
            lon=round(float(position.longitude), 6),
            lat=round(float(position.latitude), 6),
            observed_at=datetime.fromtimestamp(stamp, tz=timezone.utc),
            values=values,
            sigma=sigma,
            source_id=source,
            synthetic=False,
        ), vehicle.trip.trip_id))
    return observations


def join_delays(vehicles: list[tuple[Observation, str]], delays: dict[str, tuple[float, float | None]],
                default_sigma_s: float, trip_updates_source: str) -> list[Observation]:
    """One PublicTransportDelayObserved per vehicle whose trip has a delay."""
    out: list[Observation] = []
    for vehicle, trip_id in vehicles:
        if trip_id not in delays:
            continue
        delay, uncertainty = delays[trip_id]
        out.append(Observation(
            entity_id=vehicle.entity_id.replace(":Vehicle:", ":PublicTransportDelayObserved:"),
            entity_type="PublicTransportDelayObserved",
            lon=vehicle.lon,
            lat=vehicle.lat,
            observed_at=vehicle.observed_at,
            values={"delay": delay},
            sigma={"delay": uncertainty if uncertainty is not None else default_sigma_s},
            source_id=f"{vehicle.source_id}+{trip_updates_source}",
            synthetic=False,
        ))
    return out


class RomaGtfsRtProvider:
    """Live bus and tram positions. ``source`` is a URL or a local snapshot path."""

    def __init__(self, settings: Settings | None = None, source: str | None = None,
                 fetch_bytes: Callable[[str], bytes] | None = None,
                 trip_updates_source: str | None = None) -> None:
        settings = settings or Settings.load()
        config = settings.section("open", PROVIDER_ID)
        self._source = source or str(config.get("vehicle_positions_url", DEFAULT_URL))
        if trip_updates_source is None and source is None:
            trip_updates_source = str(config.get("trip_updates_url", DEFAULT_TRIP_UPDATES_URL))
        #: None = positions only (e.g. a single local snapshot file).
        self._trip_updates_source = trip_updates_source or None
        self._speed_sigma = number(config, "speed_sigma_kmh", 3.0)
        self._delay_sigma = number(config, "delay_sigma_s", 60.0)
        self._max_age_min = number(config, "max_age_minutes", 15.0)
        self._clock_skew_s = number(config, "clock_skew_s", 120.0)
        #: Header time of the last positions feed read (None before the first fetch).
        self.last_feed_time: datetime | None = None
        timeout = number(config, "timeout_s", 30.0)
        self._fetch_bytes = fetch_bytes or (lambda url: http.get_bytes(url, timeout_s=timeout))

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            id=PROVIDER_ID,
            kind="open",
            layer="transit",
            licence="CC BY-SA (Roma Mobilita)",
            cadence="about 30 s",
            synthetic=False,
            notes="Vehicle positions and delay at the next stop (trip updates). Credit: Roma Mobilita.",
        )

    def read(self, source: str | None = None) -> bytes:
        source = source or self._source
        if source.startswith(("http://", "https://")):
            return self._fetch_bytes(source)
        return Path(source).read_bytes()

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        start, end = _aware(start), _aware(end)
        # A "now" window still gets the latest positions, which are seconds to minutes old;
        # a feed older than max_age is not passed off as live (see last_feed_time).
        start = min(start, end - timedelta(minutes=self._max_age_min))
        end = end + timedelta(seconds=self._clock_skew_s)
        positions = self.read()
        self.last_feed_time = feed_time(positions)
        vehicles = [
            (obs, trip) for obs, trip in _vehicles(positions, self._speed_sigma)
            if start <= obs.observed_at <= end and in_bbox(obs.lon, obs.lat, bbox)
        ]
        yield from (obs for obs, _trip in vehicles)
        if self._trip_updates_source is not None and vehicles:
            updates = self.read(self._trip_updates_source)
            yield from join_delays(vehicles, parse_trip_delays(updates), self._delay_sigma, snapshot_id(updates))


def feed_time(data: bytes) -> datetime | None:
    """The feed header time: when the operator last refreshed the snapshot."""
    feed = _feed(data)
    if not feed.header.HasField("timestamp") or feed.header.timestamp == 0:
        return None
    return datetime.fromtimestamp(int(feed.header.timestamp), tz=timezone.utc)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)
