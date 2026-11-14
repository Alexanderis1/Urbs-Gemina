"""EEA hourly air quality for Rome (layer ``air_quality``). Real, open.

Flow: POST the EEA download API for the list of parquet files (one per sampling
point, whole series), read each file, keep valid hourly values in the window,
and place them with the EEA station metadata. The metadata and parquet files
name sampling points differently, so the join is on the station EoI code
(e.g. ``IT0953A``) that both contain.

Parquet ``Start``/``End`` times are station local time; Italy reports in UTC+1
(offset in config). ``observed_at`` is the end of the hour in UTC, when the
hourly mean is complete. Values are in micrograms per cubic metre.
"""
from __future__ import annotations

import csv
import io
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Iterator, Mapping

from twin.providers import http
from twin.providers.base import BBox, Observation, ProviderInfo
from twin.providers.geo import expand_bbox, in_bbox
from twin.providers.settings import Settings, integer, number
from twin.providers.settings import value as setting_value

PROVIDER_ID = "eea_hourly"
STATION_CODE = re.compile(r"SPO[.\-]([A-Z]{2}\d{4}[A-Z])")


def station_code(sampling_point: str) -> str | None:
    match = STATION_CODE.search(sampling_point)
    return match.group(1) if match else None


def read_station_metadata(text: str) -> dict[str, tuple[float, float]]:
    """EoI station code -> (lon, lat) from the tab-separated PanEuropean metadata file."""
    stations: dict[str, tuple[float, float]] = {}
    for row in csv.DictReader(io.StringIO(text.lstrip("﻿")), delimiter="\t"):
        code = (row.get("AirQualityStationEoICode") or "").strip()
        try:
            lon, lat = float(row["Longitude"]), float(row["Latitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if code and code not in stations:
            stations[code] = (lon, lat)
    return stations


def read_parquet_rows(data: bytes) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq  # type: ignore[import-untyped]

    table = pq.read_table(io.BytesIO(data))
    rows: list[dict[str, Any]] = table.to_pylist()
    return rows


def parse_rows(rows: Iterable[Mapping[str, Any]], stations: Mapping[str, tuple[float, float]],
               pollutant_names: Mapping[int, str], utc_offset_hours: float,
               relative_sigma: float, source_id: str,
               sigma_floor: Mapping[str, float] | None = None) -> Iterator[Observation]:
    """Turn EEA parquet rows into observations; drops invalid and unlocated values.

    A reading's error is ``relative_sigma`` x value, combined with an absolute ``sigma_floor`` per
    pollutant (the instrument's uncertainty near zero), so low readings are not trusted too much."""
    floors = sigma_floor or {}
    offset = timedelta(hours=utc_offset_hours)
    for row in rows:
        value = row.get("Value")
        validity = row.get("Validity")
        if value is None or validity is None or int(validity) < 1 or float(value) < 0:
            continue
        code = station_code(str(row.get("Samplingpoint", "")))
        name = pollutant_names.get(int(row.get("Pollutant") or -1))
        if code is None or code not in stations or name is None:
            continue
        end_local = row.get("End")
        if not isinstance(end_local, datetime):
            continue
        # Rebuild a plain datetime (parquet readers may return pandas Timestamps).
        observed = datetime(end_local.year, end_local.month, end_local.day, end_local.hour,
                            end_local.minute, tzinfo=timezone.utc) - offset
        lon, lat = stations[code]
        key = name.lower().replace(".", "")
        yield Observation(
            entity_id=f"urn:ngsi-ld:AirQualityObserved:eea-{code}",
            entity_type="AirQualityObserved",
            lon=lon,
            lat=lat,
            observed_at=observed,
            values={key: float(value)},
            sigma={key: round(math.hypot(relative_sigma * float(value), floors.get(key, 0.0)), 3)},
            source_id=source_id,
            synthetic=False,
        )


class EeaHourlyProvider:
    def __init__(self, settings: Settings | None = None,
                 http_post: Callable[[str, dict[str, Any]], str] | None = None,
                 http_get: Callable[[str], bytes] | None = None) -> None:
        settings = settings or Settings.load()
        self._config = settings.section("open", PROVIDER_ID)
        timeout = number(self._config, "timeout_s", 60.0)
        self._post = http_post or (lambda url, body: http.post_json(url, body, timeout_s=timeout).decode("utf-8-sig"))
        self._default_get: Callable[[str], bytes] = lambda url: http.get_bytes(url, timeout_s=timeout)
        self._get = http_get or self._default_get
        codes = self._config.get("pollutant_codes", {}) or {}
        self._pollutant_names = {int(code): str(name) for name, code in codes.items()}
        self._stations: dict[str, tuple[float, float]] | None = None

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            id=PROVIDER_ID,
            kind="open",
            layer="air_quality",
            licence="EEA open data (credit: European Environment Agency)",
            cadence="hourly (unverified up-to-date data)",
            synthetic=False,
            notes="Rome stations from the EEA download service; values unverified until the yearly validation.",
        )

    def parquet_urls(self) -> list[str]:
        body = {
            "countries": [str(self._config.get("country", "IT"))],
            "cities": [str(self._config.get("city", "Roma"))],
            "pollutants": [str(p) for p in self._config.get("pollutants", ["NO2"])],
            "dataset": integer(self._config, "dataset", 1),
            "source": "API",
        }
        text = self._post(str(self._config.get("api_url")), body)
        return [line.strip() for line in text.splitlines()[1:] if line.strip().startswith("http")]

    def stations(self) -> dict[str, tuple[float, float]]:
        if self._stations is None:
            url = str(self._config.get("metadata_url"))
            if url not in _STATION_CACHE or self._get is not self._default_get:
                raw = self._get(url)
                stations = read_station_metadata(raw.decode("utf-8", errors="replace"))
                if self._get is not self._default_get:
                    self._stations = stations
                    return stations
                _STATION_CACHE[url] = stations
            self._stations = _STATION_CACHE[url]
        return self._stations

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        start, end = _aware(start), _aware(end)
        # Up-to-date (E2a) values arrive a few hours late: a "now" window looks back far enough
        # to hold the latest hours. observed_at always says when each value was measured.
        start = min(start, end - timedelta(hours=number(self._config, "lookback_hours", 6.0)))
        # A district may hold no station: nearby stations still describe it (their real
        # positions are kept, so the belief layer weighs them by distance).
        search = expand_bbox(bbox, number(self._config, "search_buffer_km", 5.0) * 1000.0)
        stations = {code: pos for code, pos in self.stations().items() if in_bbox(pos[0], pos[1], search)}
        offset = number(self._config, "utc_offset_hours", 1.0)
        rel_sigma = number(self._config, "relative_sigma", 0.15)
        floors = {str(k): float(setting_value(v, 0.0)) for k, v in (self._config.get("sigma_floor") or {}).items()}
        wanted = [url for url in self.parquet_urls()
                  if (code := station_code(url)) is None or code in stations]
        workers = max(1, integer(self._config, "download_workers", 8))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            files = list(pool.map(self._get_cached, wanted))
        for url, data in zip(wanted, files):
            source = f"{PROVIDER_ID}@{url.rsplit('/', 1)[-1]}"
            for obs in parse_rows(read_parquet_rows(data), stations, self._pollutant_names, offset, rel_sigma, source,
                                  sigma_floor=floors):
                if start <= obs.observed_at <= end:
                    yield obs

    def _get_cached(self, url: str) -> bytes:
        """Station files change once an hour: keep each for ``cache_minutes`` (per process)."""
        if self._get is not self._default_get:  # injected (tests): no shared cache
            return self._get(url)
        ttl = number(self._config, "cache_minutes", 10.0) * 60.0
        now = time.monotonic()
        hit = _FILE_CACHE.get(url)
        if hit is not None and now - hit[0] < ttl:
            return hit[1]
        data = self._get(url)
        _FILE_CACHE[url] = (now, data)
        return data


#: url -> (monotonic time, bytes) of recently downloaded station files.
_FILE_CACHE: dict[str, tuple[float, bytes]] = {}
#: metadata url -> station positions (the station list changes rarely; one read per process).
_STATION_CACHE: dict[str, dict[str, tuple[float, float]]] = {}


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)
