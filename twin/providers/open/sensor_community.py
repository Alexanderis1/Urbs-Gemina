"""Sensor.Community citizen PM sensors (layer ``air_quality_citizen``). Real, open (ODbL).

Low-cost optical sensors (mostly SDS011) run by residents. They are real
measurements but noisier than the official stations. Each reading is divided by
the sensor's dry scale (learned against the EEA stations in Rome by
``scripts/calibrate_citizen_pm.py``: the sensors read about half the official
daily mean) and carries the relative error learned there, doubled when the
co-located humidity reading is high. Indoor sensors are dropped.
Sensor.Community already blurs positions (about 100 m); no owner data is kept.

``P1`` is PM10 and ``P2`` is PM2.5, in micrograms per cubic metre.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from twin.providers import http
from twin.providers.base import BBox, Observation, ProviderInfo
from twin.providers.geo import in_bbox
from twin.providers.settings import Settings, number
from twin.providers.settings import value as setting_value

PROVIDER_ID = "sensor_community"
KEYS = {"P1": "pm10", "P2": "pm25"}


def parse_readings(records: list[dict[str, Any]], relative_sigma: float | dict[str, float], humid_threshold: float,
                   humid_factor: float, source_id: str, dry_scale: dict[str, float] | None = None) -> list[Observation]:
    """Readings as observations; ``dry_scale`` and ``relative_sigma`` may be given per pollutant key."""
    def rel(key: str) -> float:
        return relative_sigma.get(key, 0.4) if isinstance(relative_sigma, dict) else relative_sigma

    scale = dry_scale or {}
    humidity: dict[Any, float] = {}
    for record in records:
        for item in record.get("sensordatavalues", []):
            if item.get("value_type") == "humidity":
                try:
                    humidity[record["location"]["id"]] = float(item["value"])
                except (KeyError, TypeError, ValueError):
                    pass
    out: list[Observation] = []
    for record in records:
        location = record.get("location") or {}
        if str(location.get("indoor", "0")) == "1":
            continue
        values: dict[str, float] = {}
        for item in record.get("sensordatavalues", []):
            key = KEYS.get(str(item.get("value_type")))
            if key is None:
                continue
            try:
                value = float(item["value"])
            except (TypeError, ValueError):
                continue
            if 0.0 <= value < 999.0:  # 999.9 is the SDS011 saturation code
                values[key] = round(value / scale.get(key, 1.0), 2)
        if not values:
            continue
        try:
            lon, lat = float(location["longitude"]), float(location["latitude"])
            stamp = datetime.strptime(str(record["timestamp"]), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        factor = humid_factor if humidity.get(location.get("id"), 0.0) >= humid_threshold else 1.0
        out.append(Observation(
            entity_id=f"urn:ngsi-ld:AirQualityObserved:sc-{record.get('sensor', {}).get('id', 'x')}",
            entity_type="AirQualityObserved",
            lon=lon,
            lat=lat,
            observed_at=stamp,
            values=values,
            sigma={k: round(max(1.0, v * rel(k) * factor), 2) for k, v in values.items()},
            source_id=source_id,
            synthetic=False,
        ))
    return out


class SensorCommunityProvider:
    def __init__(self, settings: Settings | None = None, fetch_bytes: Callable[[str], bytes] | None = None) -> None:
        settings = settings or Settings.load()
        self._config = settings.section("open", PROVIDER_ID)
        timeout = number(self._config, "timeout_s", 90.0)
        self._fetch = fetch_bytes or (lambda url: http.get_bytes(url, timeout_s=timeout))

    def _per_key(self, name: str, key: str, default: float) -> float:
        raw = self._config.get(name)
        if isinstance(raw, dict) and key in raw:
            return float(setting_value(raw[key]))
        return number(self._config, name, default) if not isinstance(raw, dict) or "value" in raw else default

    def dry_scale(self, key: str) -> float:
        """Sensor reading / official reading in dry air (1.0 when not calibrated)."""
        return self._per_key("dry_scale", key, 1.0)

    def relative_sigma(self, key: str) -> float:
        return self._per_key("relative_sigma", key, 0.4)

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            id=PROVIDER_ID,
            kind="open",
            layer="air_quality_citizen",
            licence="ODbL (Sensor.Community)",
            cadence="5 min",
            synthetic=False,
            notes="Citizen low-cost PM sensors: real but noisy; rescaled to the official stations, larger sigma, doubled in humid air. Credit: Sensor.Community.",
        )

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        start = start if start.tzinfo is not None else start.replace(tzinfo=timezone.utc)
        end = end if end.tzinfo is not None else end.replace(tzinfo=timezone.utc)
        min_lon, min_lat, max_lon, max_lat = bbox
        url = f"{str(self._config.get('api_url')).rstrip('/')}/box={max_lat},{min_lon},{min_lat},{max_lon}"
        records = json.loads(self._fetch(url).decode("utf-8"))
        keys = KEYS.values()
        readings = parse_readings(records, {k: self.relative_sigma(k) for k in keys},
                                  number(self._config, "humid_threshold_pct", 80.0),
                                  number(self._config, "humid_sigma_factor", 2.0), PROVIDER_ID,
                                  dry_scale={k: self.dry_scale(k) for k in keys})
        for obs in readings:
            if start <= obs.observed_at <= end and in_bbox(obs.lon, obs.lat, bbox):
                yield obs
