"""WS3: weather forecasts and river discharge for the flood and environment scenarios (WS6).

Fixtures in tests/fixtures/ws3/ follow the Open-Meteo answer format, so these tests run offline.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from twin.providers.base import ROME_BBOX
from twin.providers.open.open_meteo_weather import (
    FloodDischargeProvider,
    OpenMeteoForecastProvider,
)
from twin.providers.registry import DATA_KIND, build_providers
from twin.providers.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures" / "ws3"
ROOT = Path(__file__).resolve().parents[1]
SETTINGS = Settings.load()
NIGHT = datetime(2026, 11, 14, 0, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 11, 14, 5, 0, tzinfo=timezone.utc)


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_rain_forecast_gives_hourly_mm_per_hour_with_a_sigma() -> None:
    urls: list[str] = []

    def fetch(url: str) -> bytes:
        urls.append(url)
        return _fixture("open_meteo_forecast.json")

    provider = OpenMeteoForecastProvider(SETTINGS, "om_rain_forecast", fetch_bytes=fetch)
    info = provider.describe()
    assert info.layer == "rain_forecast" and info.kind == "open" and info.synthetic is False
    obs = list(provider.fetch(ROME_BBOX, NIGHT, LATER))
    assert "precipitation" in urls[0] and "models=" in urls[0]
    assert {o.entity_type for o in obs} == {"WeatherForecast"}
    first_point = [o for o in obs if o.lon == 12.45]
    assert [o.values.get("precipitation") for o in first_point] == [0.0, 0.4, 2.6, 7.9, 1.0]  # the None hour is skipped
    assert all(o.sigma["precipitation"] > 0 for o in obs)
    assert all(set(o.values) == {"precipitation"} for o in obs)


def test_weather_forecast_gives_wind_and_temperature() -> None:
    provider = OpenMeteoForecastProvider(SETTINGS, "om_weather_forecast",
                                         fetch_bytes=lambda url: _fixture("open_meteo_forecast.json"))
    assert provider.describe().layer == "weather_forecast"
    obs = list(provider.fetch(ROME_BBOX, NIGHT, NIGHT))
    assert len(obs) == 2
    assert obs[0].values == {"wind_speed_ms": 3.1, "wind_direction_deg": 200.0, "temperature_c": 12.1}
    assert set(obs[0].sigma) == set(obs[0].values)


def test_forecast_falls_back_to_the_next_model_when_one_has_no_data() -> None:
    answers = iter([_fixture("open_meteo_no_data.json"), _fixture("open_meteo_forecast.json")])
    urls: list[str] = []

    def fetch(url: str) -> bytes:
        urls.append(url)
        return next(answers)

    provider = OpenMeteoForecastProvider(SETTINGS, "om_rain_forecast", fetch_bytes=fetch)
    obs = list(provider.fetch(ROME_BBOX, NIGHT, LATER))
    assert len(urls) == 2 and urls[0] != urls[1]
    assert obs and provider.last_model == SETTINGS.section("open", "om_rain_forecast")["models"][1]
    assert provider.last_model in obs[0].source_id


def test_flood_api_gives_tiber_discharge_with_an_ensemble_sigma() -> None:
    provider = FloodDischargeProvider(SETTINGS, fetch_bytes=lambda url: _fixture("open_meteo_flood.json"))
    info = provider.describe()
    assert info.layer == "river_discharge" and info.synthetic is False
    obs = list(provider.fetch(ROME_BBOX, datetime(2026, 11, 13, tzinfo=timezone.utc),
                              datetime(2026, 11, 16, tzinfo=timezone.utc)))
    gauges = SETTINGS.section("open", "glofas_flood")["points"]
    assert len(obs) == 2 * len(gauges)  # the empty day is skipped, one series per configured point
    first = obs[0]
    assert first.entity_type == "RiverDischargeForecast" and first.values == {"discharge_m3s": 212.4}
    assert first.sigma["discharge_m3s"] == pytest.approx((235.0 - 190.0) / 1.349, rel=1e-3)


def test_new_layers_are_registered_and_labelled() -> None:
    config = yaml.safe_load((ROOT / "config" / "providers.yaml").read_text(encoding="utf-8"))
    assert config["rain_forecast"] == "om_rain_forecast"
    assert config["weather_forecast"] == "om_weather_forecast"
    assert config["river_discharge"] == "glofas_flood"
    assert DATA_KIND["glofas_flood"] == "estimated" and DATA_KIND["om_rain_forecast"] == "estimated"
    built = build_providers({k: config[k] for k in ("rain_forecast", "weather_forecast", "river_discharge")},
                            settings=SETTINGS)
    assert {p.describe().layer for p in built.values()} == {"rain_forecast", "weather_forecast", "river_discharge"}


def test_river_alert_thresholds_are_official_and_ordered() -> None:
    thresholds = yaml.safe_load((ROOT / "config" / "thresholds.yaml").read_text(encoding="utf-8"))
    gauges = thresholds["river_gauges"]
    assert "G11149" in gauges["source"]
    ripetta = gauges["stations"]["tevere_ripetta"]
    assert (ripetta["attenzione_m"], ripetta["preallarme_m"], ripetta["allarme_m"]) == (7.0, 11.0, 13.0)
    for station in gauges["stations"].values():
        assert station["attenzione_m"] < station["preallarme_m"] <= station["allarme_m"]
