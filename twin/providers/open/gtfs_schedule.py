"""Scheduled bus, tram and metro positions from Rome's static GTFS (layer ``transit_schedule``).

Estimated, open. Each running trip's position is interpolated in time between
its scheduled stops (straight line between stops, so the error is the street
detour plus any delay). This is what the timetable says, not what the vehicles
do. It is the fallback for the ``transit`` layer when the live GTFS-RT feed is
stale, and the baseline that live positions are compared with (delay).

The zip (about 47 MB) is downloaded once per ``cache_hours`` and the day's index
is built in memory (pyarrow CSV reader, a few seconds); nothing is written to disk.
"""
from __future__ import annotations

import io
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo

import numpy as np

from twin.providers import http
from twin.providers.base import BBox, Observation, ProviderInfo
from twin.providers.geo import in_bbox
from twin.providers.settings import Settings, number, text

PROVIDER_ID = "roma_gtfs_schedule"
DEFAULT_URL = "https://romamobilita.it/wp-content/uploads/shared/rome_static_gtfs.zip"
ROME = ZoneInfo("Europe/Rome")


@dataclass(frozen=True)
class ScheduledPosition:
    trip: str
    route: str
    route_type: int
    lon: float
    lat: float


def _stop_times(archive: zipfile.ZipFile) -> tuple[np.ndarray, list[str], np.ndarray, np.ndarray, list[str], np.ndarray]:
    """stop_times.txt as compact arrays (about 5 million rows for Rome), without Python string lists.

    Returns trip codes, trip ids, departure seconds after the service day's start (hours may
    pass 24), stop codes, stop ids and stop sequence.
    """
    import pyarrow as pa  # type: ignore[import-untyped]
    import pyarrow.compute as pc  # type: ignore[import-untyped]
    import pyarrow.csv as pcsv  # type: ignore[import-untyped]

    columns = ["trip_id", "departure_time", "stop_id", "stop_sequence"]
    with archive.open("stop_times.txt") as handle:
        table = pcsv.read_csv(handle, convert_options=pcsv.ConvertOptions(
            include_columns=columns, column_types={c: pa.string() for c in columns}))
    trips = pc.dictionary_encode(table.column("trip_id")).combine_chunks()
    stops = pc.dictionary_encode(table.column("stop_id")).combine_chunks()
    parts = pc.split_pattern(table.column("departure_time"), ":")
    hours = pc.cast(pc.list_element(parts, 0), pa.int32()).to_numpy()
    minutes = pc.cast(pc.list_element(parts, 1), pa.int32()).to_numpy()
    seconds = pc.cast(pc.list_element(parts, 2), pa.int32()).to_numpy()
    secs = hours.astype(np.int32) * 3600 + minutes * 60 + seconds
    seq = pc.cast(table.column("stop_sequence"), pa.int32()).to_numpy()
    return (trips.indices.to_numpy().astype(np.int32), [str(t) for t in trips.dictionary.to_pylist()], secs,
            stops.indices.to_numpy().astype(np.int32), [str(t) for t in stops.dictionary.to_pylist()], seq)


def _read(archive: zipfile.ZipFile, name: str, columns: list[str]) -> dict[str, list[str]]:
    import pyarrow.csv as pcsv

    with archive.open(name) as handle:
        table = pcsv.read_csv(
            handle,
            convert_options=pcsv.ConvertOptions(include_columns=columns,
                                                column_types={c: "string" for c in columns}),
        )
    return {c: table.column(c).to_pylist() for c in columns}


class ScheduleIndex:
    """Stop events of every trip, sorted by trip and time, as flat numpy arrays."""

    def __init__(self, archive_bytes: bytes) -> None:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
        routes = _read(archive, "routes.txt", ["route_id", "route_short_name", "route_type"])
        self._route_name = dict(zip(routes["route_id"], routes["route_short_name"]))
        self._route_type = {r: int(t or 3) for r, t in zip(routes["route_id"], routes["route_type"])}
        trips = _read(archive, "trips.txt", ["route_id", "service_id", "trip_id"])
        self._trip_route = dict(zip(trips["trip_id"], trips["route_id"]))
        self._trip_service = dict(zip(trips["trip_id"], trips["service_id"]))
        dates = _read(archive, "calendar_dates.txt", ["service_id", "date", "exception_type"])
        self._services: dict[str, set[str]] = {}
        for service, day, kind in zip(dates["service_id"], dates["date"], dates["exception_type"]):
            if kind == "1":
                self._services.setdefault(day, set()).add(service)
        stops = _read(archive, "stops.txt", ["stop_id", "stop_lat", "stop_lon"])
        stop_pos = {s: (float(lo), float(la)) for s, la, lo in zip(stops["stop_id"], stops["stop_lat"], stops["stop_lon"])}
        trip, trip_ids, secs, stop_codes, stop_names, seq = _stop_times(archive)
        lookup_lon = np.array([stop_pos.get(str(s), (np.nan, np.nan))[0] for s in stop_names])
        lookup_lat = np.array([stop_pos.get(str(s), (np.nan, np.nan))[1] for s in stop_names])
        lon, lat = lookup_lon[stop_codes], lookup_lat[stop_codes]
        order = np.lexsort((seq, trip))
        self._trip_ids = trip_ids
        self._trip, self._secs, self._lon, self._lat = trip[order], secs[order], lon[order], lat[order]

    @classmethod
    def build(cls, archive_bytes: bytes) -> "ScheduleIndex":
        return cls(archive_bytes)

    def _running(self, service_day: date, seconds: int) -> list[ScheduledPosition]:
        active = self._services.get(service_day.strftime("%Y%m%d"), set())
        if not active:
            return []
        same = self._trip[:-1] == self._trip[1:]
        between = (self._secs[:-1] <= seconds) & (self._secs[1:] > seconds) & same
        out: list[ScheduledPosition] = []
        for i in np.flatnonzero(between):
            trip_id = self._trip_ids[int(self._trip[i])]
            if self._trip_service.get(trip_id) not in active:
                continue
            span = float(self._secs[i + 1] - self._secs[i])
            f = (seconds - float(self._secs[i])) / span if span > 0 else 0.0
            lon = float(self._lon[i] + f * (self._lon[i + 1] - self._lon[i]))
            lat = float(self._lat[i] + f * (self._lat[i + 1] - self._lat[i]))
            if np.isnan(lon) or np.isnan(lat):
                continue
            route = self._trip_route.get(trip_id, "")
            out.append(ScheduledPosition(trip=trip_id, route=self._route_name.get(route, route) or route,
                                         route_type=self._route_type.get(route, 3), lon=lon, lat=lat))
        return out

    def positions_at(self, moment: datetime) -> list[ScheduledPosition]:
        """Trips running at ``moment``: today's service, plus yesterday's trips that run past midnight."""
        local = moment.astimezone(ROME)
        seconds = local.hour * 3600 + local.minute * 60 + local.second
        today = local.date()
        return self._running(today, seconds) + self._running(today - timedelta(days=1), seconds + 86400)


_ZIP_CACHE: dict[str, tuple[float, ScheduleIndex]] = {}


class RomaGtfsScheduleProvider:
    def __init__(self, settings: Settings | None = None, fetch_bytes: Callable[[str], bytes] | None = None) -> None:
        settings = settings or Settings.load()
        self._config = settings.section("open", PROVIDER_ID)
        self._url = text(self._config, "static_gtfs_url", DEFAULT_URL)
        self._shared = fetch_bytes is None
        timeout = number(self._config, "timeout_s", 180.0)
        self._fetch = fetch_bytes or (lambda url: http.get_bytes(url, timeout_s=timeout))
        self._index: ScheduleIndex | None = None

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            id=PROVIDER_ID,
            kind="open",
            layer="transit_schedule",
            licence="CC BY 4.0, Roma Servizi per la Mobilità (static GTFS)",
            cadence="timetable updated almost daily; positions computed for any time",
            synthetic=False,
            notes="Where buses, trams and metros should be according to the timetable, interpolated "
                  "between stops. Estimated, not measured: use when the live feed is stale.",
        )

    def index(self) -> ScheduleIndex:
        if self._index is None:
            ttl = number(self._config, "cache_hours", 12.0) * 3600.0
            hit = _ZIP_CACHE.get(self._url) if self._shared else None
            if hit is None or time.monotonic() - hit[0] > ttl:
                hit = (time.monotonic(), ScheduleIndex.build(self._fetch(self._url)))
                if self._shared:
                    _ZIP_CACHE[self._url] = hit
            self._index = hit[1]
        return self._index

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        """Scheduled positions at the end of the window (one snapshot)."""
        end = end if end.tzinfo is not None else end.replace(tzinfo=timezone.utc)
        for n, pos in enumerate(self.index().positions_at(end)):
            if not in_bbox(pos.lon, pos.lat, bbox):
                continue
            yield Observation(
                entity_id=f"urn:ngsi-ld:ScheduledVehicle:{PROVIDER_ID}-{pos.route}-{n:05d}",
                entity_type="ScheduledVehicle",
                lon=round(pos.lon, 6),
                lat=round(pos.lat, 6),
                observed_at=end,
                values={"scheduledVehicles": 1.0, "routeType": float(pos.route_type)},
                sigma={"scheduledVehicles": 0.0, "routeType": 0.0},
                source_id=PROVIDER_ID,
                synthetic=False,
            )
