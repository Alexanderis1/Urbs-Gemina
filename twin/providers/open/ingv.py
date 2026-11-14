"""Earthquakes recorded by INGV around Rome (layer ``earthquakes``). Real, open (CC BY 4.0).

INGV's FDSN event service gives every located event in Italy within minutes.
Events are rare, so a "now" window looks back ``lookback_days``, and the search
covers the area plus a buffer (shaking is felt well beyond the epicentre).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Iterator

from twin.providers import http
from twin.providers.base import BBox, Observation, ProviderInfo
from twin.providers.geo import expand_bbox
from twin.providers.settings import Settings, number, text

PROVIDER_ID = "ingv_earthquakes"
DEFAULT_URL = "https://webservices.ingv.it/fdsnws/event/1/query"


def parse_events(text_answer: str, magnitude_sigma: float, depth_sigma_km: float) -> list[Observation]:
    """Events from an FDSN ``format=text`` answer (pipe-separated, one header line)."""
    out: list[Observation] = []
    for line in text_answer.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split("|")
        try:
            stamp = datetime.fromisoformat(cols[1]).replace(tzinfo=timezone.utc)
            lat, lon, depth, magnitude = float(cols[2]), float(cols[3]), float(cols[4]), float(cols[10])
        except (IndexError, ValueError):
            continue
        out.append(Observation(
            entity_id=f"urn:ngsi-ld:EarthquakeObserved:ingv-{cols[0]}",
            entity_type="EarthquakeObserved",
            lon=lon,
            lat=lat,
            observed_at=stamp,
            values={"magnitude": magnitude, "depth_km": depth},
            sigma={"magnitude": magnitude_sigma, "depth_km": depth_sigma_km},
            source_id=f"{PROVIDER_ID}@{cols[9] or 'M'}",
            synthetic=False,
        ))
    return out


class IngvEarthquakeProvider:
    def __init__(self, settings: Settings | None = None, fetch_bytes: Callable[[str], bytes] | None = None) -> None:
        settings = settings or Settings.load()
        self._config = settings.section("open", PROVIDER_ID)
        timeout = number(self._config, "timeout_s", 30.0)
        self._fetch = fetch_bytes or (lambda url: http.get_bytes(url, timeout_s=timeout))

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            id=PROVIDER_ID,
            kind="open",
            layer="earthquakes",
            licence="CC BY 4.0, INGV (Istituto Nazionale di Geofisica e Vulcanologia)",
            cadence="minutes after each event",
            synthetic=False,
            notes="Located earthquakes around Rome (INGV FDSN service): magnitude and depth.",
        )

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        start = start if start.tzinfo is not None else start.replace(tzinfo=timezone.utc)
        end = end if end.tzinfo is not None else end.replace(tzinfo=timezone.utc)
        start = min(start, end - timedelta(days=number(self._config, "lookback_days", 30.0)))
        west, south, east, north = expand_bbox(bbox, number(self._config, "search_buffer_km", 60.0) * 1000.0)
        url = (f"{text(self._config, 'api_url', DEFAULT_URL)}?starttime={start.date().isoformat()}"
               f"&endtime={(end + timedelta(days=1)).date().isoformat()}"
               f"&minlatitude={south:.3f}&maxlatitude={north:.3f}&minlongitude={west:.3f}&maxlongitude={east:.3f}"
               f"&minmagnitude={number(self._config, 'min_magnitude', 0.0)}&format=text&orderby=time")
        answer = self._fetch(url).decode("utf-8", errors="replace")
        for event in parse_events(answer, number(self._config, "magnitude_sigma", 0.2),
                                  number(self._config, "depth_sigma_km", 2.0)):
            if start <= event.observed_at <= end + timedelta(minutes=5):
                yield event
