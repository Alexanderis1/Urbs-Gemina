"""CAMS air-quality model via Open-Meteo (layer ``air_quality_model``). Estimated, open.

The CAMS European ensemble is a chemistry-transport model (about 10 km cells),
not a measurement. It is the background the belief layer starts from, which
station and citizen readings then correct. Values come at a lattice of points
over the area, spaced like the model grid, one ``AirQualityForecast`` per
point and hour, with a large relative sigma.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from twin.providers import http
from twin.providers.base import BBox, Observation, ProviderInfo
from twin.providers.settings import Settings, number

PROVIDER_ID = "cams_open_meteo"
VARIABLES = {"nitrogen_dioxide": "no2", "pm10": "pm10", "pm2_5": "pm25"}


def lattice(bbox: BBox, step_deg: float) -> list[tuple[float, float]]:
    min_lon, min_lat, max_lon, max_lat = bbox
    points: list[tuple[float, float]] = []
    lat = min_lat + step_deg / 2
    while lat < max_lat:
        lon = min_lon + step_deg / 2
        while lon < max_lon:
            points.append((round(lon, 4), round(lat, 4)))
            lon += step_deg
        lat += step_deg
    return points


def parse_forecast(answers: list[dict[str, Any]], relative_sigma: float, source_id: str) -> list[Observation]:
    out: list[Observation] = []
    for index, answer in enumerate(answers):
        hourly = answer.get("hourly") or {}
        times = hourly.get("time") or []
        for t, stamp in enumerate(times):
            values: dict[str, float] = {}
            for variable, key in VARIABLES.items():
                series = hourly.get(variable) or []
                if t < len(series) and series[t] is not None:
                    values[key] = float(series[t])
            if not values:
                continue
            out.append(Observation(
                entity_id=f"urn:ngsi-ld:AirQualityForecast:cams-{index:03d}",
                entity_type="AirQualityForecast",
                lon=float(answer["longitude"]),
                lat=float(answer["latitude"]),
                observed_at=datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc),
                values=values,
                sigma={k: round(max(1.0, v * relative_sigma), 2) for k, v in values.items()},
                source_id=source_id,
                synthetic=False,
            ))
    return out


class CamsOpenMeteoProvider:
    def __init__(self, settings: Settings | None = None, fetch_bytes: Callable[[str], bytes] | None = None) -> None:
        settings = settings or Settings.load()
        self._config = settings.section("open", PROVIDER_ID)
        timeout = number(self._config, "timeout_s", 60.0)
        self._fetch = fetch_bytes or (lambda url: http.get_bytes(url, timeout_s=timeout))

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            id=PROVIDER_ID,
            kind="open",
            layer="air_quality_model",
            licence="CC BY 4.0 (Open-Meteo; CAMS, Copernicus Atmosphere Monitoring Service)",
            cadence="hourly",
            synthetic=False,
            notes="Model background (CAMS Europe, about 10 km), not a measurement. Credit: Open-Meteo, CAMS.",
        )

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        start = start if start.tzinfo is not None else start.replace(tzinfo=timezone.utc)
        end = end if end.tzinfo is not None else end.replace(tzinfo=timezone.utc)
        points = lattice(bbox, number(self._config, "step_deg", 0.1))
        if not points:
            return
        url = (f"{self._config.get('api_url')}?latitude={','.join(str(p[1]) for p in points)}"
               f"&longitude={','.join(str(p[0]) for p in points)}&hourly={','.join(VARIABLES)}"
               f"&start_date={start.date().isoformat()}&end_date={end.date().isoformat()}&timezone=UTC")
        answer = json.loads(self._fetch(url).decode("utf-8"))
        answers = answer if isinstance(answer, list) else [answer]
        for obs in parse_forecast(answers, number(self._config, "relative_sigma", 0.5), PROVIDER_ID):
            if start <= obs.observed_at <= end:
                yield obs
