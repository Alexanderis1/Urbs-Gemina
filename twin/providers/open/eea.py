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
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Iterator, Mapping

from twin.providers import http
from twin.providers.base import BBox, Observation, ProviderInfo
from twin.providers.geo import in_bbox
from twin.providers.settings import Settings, integer, number

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
               relative_sigma: float, source_id: str) -> Iterator[Observation]:
    """Turn EEA parquet rows into observations; drops invalid and unlocated values."""
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
            sigma={key: round(relative_sigma * float(value), 3)},
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
        self._get = http_get or (lambda url: http.get_bytes(url, timeout_s=timeout))
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
            raw = self._get(str(self._config.get("metadata_url")))
            self._stations = read_station_metadata(raw.decode("utf-8", errors="replace"))
        return self._stations

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        start, end = _aware(start), _aware(end)
        stations = {code: pos for code, pos in self.stations().items() if in_bbox(pos[0], pos[1], bbox)}
        offset = number(self._config, "utc_offset_hours", 1.0)
        rel_sigma = number(self._config, "relative_sigma", 0.15)
        for url in self.parquet_urls():
            code = station_code(url)
            if code is not None and code not in stations:
                continue
            data = self._get(url)
            source = f"{PROVIDER_ID}@{url.rsplit('/', 1)[-1]}"
            for obs in parse_rows(read_parquet_rows(data), stations, self._pollutant_names, offset, rel_sigma, source):
                if start <= obs.observed_at <= end:
                    yield obs


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)
