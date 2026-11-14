"""Weather forecasts and river discharge from Open-Meteo, for the flood and environment scenarios.

- ``om_rain_forecast`` (layer ``rain_forecast``): hourly precipitation (mm in the
  hour, i.e. mm/h) for the next 48 h, so the scenario engine can extend the
  ``dpc_radar`` nowcast.
- ``om_weather_forecast`` (layer ``weather_forecast``): hourly wind at 10 m
  (speed in m/s, direction it blows from in degrees) and air temperature at 2 m
  (the standard height; models give no 10 m temperature), for plume and heat
  scenarios.
- ``glofas_flood`` (layer ``river_discharge``): daily river discharge from the
  GloFAS hydrological model (about 5 km) at configured points on the Tiber and
  Aniene, with the ensemble spread as sigma.

All are model output, so their data kind is "estimated". Models are tried in
the configured order (ARPAE ICON-2I covers Italy at 2.2 km; ICON-D2 does not
reach Rome), and the first one with data is used and named in ``source_id``.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator, Mapping

from twin.providers import http
from twin.providers.base import BBox, Observation, ProviderInfo
from twin.providers.geo import in_bbox
from twin.providers.open.open_meteo import lattice
from twin.providers.settings import Settings, number

#: provider id -> (layer, Open-Meteo hourly variable -> our value key)
PROFILES: dict[str, tuple[str, dict[str, str]]] = {
    "om_rain_forecast": ("rain_forecast", {"precipitation": "precipitation"}),
    "om_weather_forecast": ("weather_forecast", {
        "wind_speed_10m": "wind_speed_ms",
        "wind_direction_10m": "wind_direction_deg",
        "temperature_2m": "temperature_c",
        "relative_humidity_2m": "humidity_pct",
    }),
}


def _sigma(key: str, value: float, config: Mapping[str, Any]) -> float:
    """One-sigma error of a forecast value, from the ``sigma`` block in config."""
    spec = (config.get("sigma") or {}).get(key) or {}
    absolute = number(spec, "absolute", 0.0)
    relative = number(spec, "relative", 0.0)
    return round(max(absolute, abs(value) * relative), 3) or 0.1


def parse_hourly(answers: list[dict[str, Any]], variables: Mapping[str, str], config: Mapping[str, Any],
                 source_id: str, prefix: str) -> list[Observation]:
    out: list[Observation] = []
    for index, answer in enumerate(answers):
        hourly = answer.get("hourly") or {}
        for t, stamp in enumerate(hourly.get("time") or []):
            values: dict[str, float] = {}
            for variable, key in variables.items():
                series = hourly.get(variable) or []
                if t < len(series) and series[t] is not None:
                    values[key] = float(series[t])
            if not values:
                continue
            out.append(Observation(
                entity_id=f"urn:ngsi-ld:WeatherForecast:{prefix}-{index:03d}",
                entity_type="WeatherForecast",
                lon=float(answer["longitude"]),
                lat=float(answer["latitude"]),
                observed_at=datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc),
                values=values,
                sigma={k: _sigma(k, v, config) for k, v in values.items()},
                source_id=source_id,
                synthetic=False,
            ))
    return out


def _has_data(answers: list[dict[str, Any]], variables: Mapping[str, str]) -> bool:
    for answer in answers:
        if answer.get("error"):
            return False
        hourly = answer.get("hourly") or {}
        if any(v is not None for variable in variables for v in (hourly.get(variable) or [])):
            return True
    return False


class OpenMeteoForecastProvider:
    def __init__(self, settings: Settings | None, provider_id: str,
                 fetch_bytes: Callable[[str], bytes] | None = None) -> None:
        settings = settings or Settings.load()
        self._id = provider_id
        self._layer, self._variables = PROFILES[provider_id]
        self._config = settings.section("open", provider_id)
        timeout = number(self._config, "timeout_s", 60.0)
        self._fetch = fetch_bytes or http.CachedFetcher(  # shared across requests: the free API rate-limits
            lambda url: http.get_bytes(url, timeout_s=timeout), ttl_s=number(self._config, "cache_ttl_s", 1800.0))
        #: The model that answered the last fetch (None before the first).
        self.last_model: str | None = None

    def describe(self) -> ProviderInfo:
        what = "Hourly rain forecast (mm/h)" if self._layer == "rain_forecast" else \
            "Hourly wind at 10 m and temperature at 2 m"
        return ProviderInfo(
            id=self._id,
            kind="open",
            layer=self._layer,
            licence="CC BY 4.0 (Open-Meteo; model data from ARPAE/ItaliaMeteo, DWD)",
            cadence="hourly values, model runs every 3-6 h",
            synthetic=False,
            notes=f"{what}. Model forecast, not a measurement. Credit: Open-Meteo.",
        )

    def _url(self, points: list[tuple[float, float]], model: str, start: datetime, end: datetime) -> str:
        return (f"{self._config.get('api_url')}?latitude={','.join(str(p[1]) for p in points)}"
                f"&longitude={','.join(str(p[0]) for p in points)}&hourly={','.join(self._variables)}"
                f"&models={model}&wind_speed_unit=ms&timezone=UTC"
                f"&start_date={start.date().isoformat()}&end_date={end.date().isoformat()}")

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        start = start if start.tzinfo is not None else start.replace(tzinfo=timezone.utc)
        end = end if end.tzinfo is not None else end.replace(tzinfo=timezone.utc)
        start = start.replace(minute=0, second=0, microsecond=0)  # hourly values: "now" gets this hour
        points = lattice(bbox, number(self._config, "step_deg", 0.1))
        for model in [str(m) for m in self._config.get("models", ["best_match"])]:
            answer = json.loads(self._fetch(self._url(points, model, start, end)).decode("utf-8"))
            answers = answer if isinstance(answer, list) else [answer]
            if not _has_data(answers, self._variables):
                continue
            self.last_model = model
            source = f"{self._id}@{model}"
            for obs in parse_hourly(answers, self._variables, self._config, source, self._id):
                if start <= obs.observed_at <= end:
                    yield obs
            return


class FloodDischargeProvider:
    """GloFAS river discharge at configured river points (Open-Meteo flood API)."""

    PROVIDER_ID = "glofas_flood"

    def __init__(self, settings: Settings | None = None, fetch_bytes: Callable[[str], bytes] | None = None) -> None:
        settings = settings or Settings.load()
        self._config = settings.section("open", self.PROVIDER_ID)
        timeout = number(self._config, "timeout_s", 60.0)
        self._fetch = fetch_bytes or http.CachedFetcher(  # shared across requests: the free API rate-limits
            lambda url: http.get_bytes(url, timeout_s=timeout), ttl_s=number(self._config, "cache_ttl_s", 1800.0))

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.PROVIDER_ID,
            kind="open",
            layer="river_discharge",
            licence="CC BY 4.0 (Open-Meteo; GloFAS, Copernicus Emergency Management Service)",
            cadence="daily values, forecast up to 7 days",
            synthetic=False,
            notes="Modelled daily river discharge (GloFAS, about 5 km), not a gauge reading. "
                  "Sigma from the ensemble spread. Credit: Open-Meteo, Copernicus CEMS.",
        )

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        start = start if start.tzinfo is not None else start.replace(tzinfo=timezone.utc)
        end = end if end.tzinfo is not None else end.replace(tzinfo=timezone.utc)
        day_start = start.replace(hour=0, minute=0, second=0, microsecond=0)  # daily values
        relative = number(self._config, "relative_sigma", 0.3)
        for name, point in (self._config.get("points") or {}).items():
            lon, lat = float(point["lon"]), float(point["lat"])
            if not in_bbox(lon, lat, bbox):
                continue
            url = (f"{self._config.get('api_url')}?latitude={lat}&longitude={lon}"
                   f"&daily=river_discharge,river_discharge_p25,river_discharge_p75"
                   f"&start_date={day_start.date().isoformat()}&end_date={(end + timedelta(days=0)).date().isoformat()}")
            daily = json.loads(self._fetch(url).decode("utf-8")).get("daily") or {}
            series = daily.get("river_discharge") or []
            p25 = daily.get("river_discharge_p25") or []
            p75 = daily.get("river_discharge_p75") or []
            for t, stamp in enumerate(daily.get("time") or []):
                if t >= len(series) or series[t] is None:
                    continue
                value = float(series[t])
                if t < len(p25) and t < len(p75) and p25[t] is not None and p75[t] is not None:
                    sigma = max(1.0, (float(p75[t]) - float(p25[t])) / 1.349)  # IQR of a normal = 1.349 sigma
                else:
                    sigma = max(1.0, value * relative)
                observed_at = datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
                if not (day_start <= observed_at <= end):
                    continue
                yield Observation(
                    entity_id=f"urn:ngsi-ld:RiverDischargeForecast:glofas-{name}",
                    entity_type="RiverDischargeForecast",
                    lon=lon,
                    lat=lat,
                    observed_at=observed_at,
                    values={"discharge_m3s": value},
                    sigma={"discharge_m3s": round(sigma, 2)},
                    source_id=f"{self.PROVIDER_ID}@{name}",
                    synthetic=False,
                )
