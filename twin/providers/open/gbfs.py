"""Shared e-scooters from GBFS feeds (layer ``micromobility``). Real, open.

Each parked, available vehicle is one observation at its reported position.
Vehicle ids are dropped (GBFS 2.x rotates them anyway), so no trip can be
followed. As an activity proxy this is weak (C=40): scooters gather where trips
end, and their counts change with operator rebalancing.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator

from twin.providers import http
from twin.providers.base import BBox, Observation, ProviderInfo
from twin.providers.geo import in_bbox
from twin.providers.settings import Settings, number

PROVIDER_ID = "bird_gbfs"
DEFAULT_URL = "https://mds.bird.co/gbfs/v2/public/rome/free_bike_status.json"


def parse_free_vehicles(feed: dict[str, Any], source_id: str) -> list[Observation]:
    stamp = datetime.fromtimestamp(int(feed.get("last_updated", 0)), tz=timezone.utc)
    out: list[Observation] = []
    for index, bike in enumerate(feed.get("data", {}).get("bikes", [])):
        if bike.get("is_disabled") or bike.get("is_reserved"):
            continue
        try:
            lon, lat = float(bike["lon"]), float(bike["lat"])
        except (KeyError, TypeError, ValueError):
            continue
        values = {"availableVehicles": 1.0}
        sigma = {"availableVehicles": 0.0}
        if bike.get("current_range_meters") is not None:
            values["rangeKm"] = round(float(bike["current_range_meters"]) / 1000.0, 1)
            sigma["rangeKm"] = 1.0
        out.append(Observation(
            entity_id=f"urn:ngsi-ld:MicromobilityVehicle:{source_id}-{index:05d}",
            entity_type="MicromobilityVehicle",
            lon=round(lon, 5),
            lat=round(lat, 5),
            observed_at=stamp,
            values=values,
            sigma=sigma,
            source_id=source_id,
            synthetic=False,
        ))
    return out


class GbfsProvider:
    def __init__(self, settings: Settings | None = None, fetch_bytes: Callable[[str], bytes] | None = None) -> None:
        settings = settings or Settings.load()
        config = settings.section("open", PROVIDER_ID)
        self._url = str(config.get("free_vehicles_url", DEFAULT_URL))
        timeout = number(config, "timeout_s", 30.0)
        self._max_age_min = number(config, "max_age_minutes", 15.0)
        self._clock_skew_s = number(config, "clock_skew_s", 120.0)
        self._fetch = fetch_bytes or (lambda url: http.get_bytes(url, timeout_s=timeout))

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            id=PROVIDER_ID,
            kind="open",
            layer="micromobility",
            licence="operator terms (Bird GBFS public feed); check before republishing",
            cadence="1 min",
            synthetic=False,
            redistribution=False,
            notes="Available shared e-scooters (Bird). Weak activity proxy (C=40). Vehicle ids dropped.",
        )

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        start = start if start.tzinfo is not None else start.replace(tzinfo=timezone.utc)
        end = end if end.tzinfo is not None else end.replace(tzinfo=timezone.utc)
        # One snapshot of parked vehicles: valid for "now" if no older than max_age, and the
        # operator's clock may run a little ahead of ours.
        start = min(start, end - timedelta(minutes=self._max_age_min))
        end = end + timedelta(seconds=self._clock_skew_s)
        feed = json.loads(self._fetch(self._url).decode("utf-8"))
        for obs in parse_free_vehicles(feed, PROVIDER_ID):
            if start <= obs.observed_at <= end and in_bbox(obs.lon, obs.lat, bbox):
                yield obs
