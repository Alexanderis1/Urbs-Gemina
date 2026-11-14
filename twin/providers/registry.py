"""Turn config/providers.yaml into live provider objects.

One active provider per layer. Switching a layer to another provider id in the
YAML changes the data with no code change (Gate C). Every factory takes the
loaded ``Settings`` so its parameters come from config, not code.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Literal

import yaml

from twin.providers.base import Provider, ProviderNotConfigured
from twin.providers.estimated.register import EstimatedRegisterProvider
from twin.providers.open.dpc_radar import DpcRadarProvider
from twin.providers.open.arpa_points import ArpaPointsProvider
from twin.providers.open.eea import EeaHourlyProvider
from twin.providers.open.gbfs import GbfsProvider
from twin.providers.open.gtfs_rt import RomaGtfsRtProvider
from twin.providers.open.gtfs_schedule import RomaGtfsScheduleProvider
from twin.providers.open.ingv import IngvEarthquakeProvider
from twin.providers.open.open_meteo import CamsOpenMeteoProvider
from twin.providers.open.open_meteo_weather import FloodDischargeProvider, OpenMeteoForecastProvider
from twin.providers.open.roma_wifi import RomaWifiProvider
from twin.providers.open.sensor_community import SensorCommunityProvider
from twin.providers.pa.register_file import PaRegisterFileProvider
from twin.providers.restricted.cartoradio import CartoradioGridProvider
from twin.providers.settings import Settings
from twin.providers.simulated.loops import SimLoopsProvider

Factory = Callable[[Settings], Provider]
DataKind = Literal["real", "estimated", "simulated"]


def _not_configured(provider_id: str, hint: str) -> Factory:
    def factory(settings: Settings) -> Provider:
        raise ProviderNotConfigured(f"Provider '{provider_id}' has no access configured yet. {hint}")

    return factory


#: Every provider id that may appear in providers.yaml.
FACTORIES: dict[str, Factory] = {
    # simulated: only the road loops, which have no open real equivalent
    "sim_loops": SimLoopsProvider.from_settings,
    # estimated: real sources fused with a physical model
    "est_register": EstimatedRegisterProvider,
    # open, real
    "roma_gtfs_rt": RomaGtfsRtProvider,
    "roma_gtfs_schedule": RomaGtfsScheduleProvider,
    "ingv_earthquakes": IngvEarthquakeProvider,
    "eea_hourly": EeaHourlyProvider,
    "dpc_radar": DpcRadarProvider,
    "arpa_points": ArpaPointsProvider,
    "bird_gbfs": GbfsProvider,
    "sensor_community": SensorCommunityProvider,
    "roma_wifi": RomaWifiProvider,
    # estimated: weather and hydrological model forecasts (flood and environment scenarios)
    "om_rain_forecast": lambda settings: OpenMeteoForecastProvider(settings, "om_rain_forecast"),
    "om_weather_forecast": lambda settings: OpenMeteoForecastProvider(settings, "om_weather_forecast"),
    "glofas_flood": FloodDischargeProvider,
    "cams_open_meteo": CamsOpenMeteoProvider,
    # restricted: runtime read only
    "cartoradio_grid": CartoradioGridProvider,
    # the administration's own data
    "pa_register_file": PaRegisterFileProvider,
    "pa_datex": _not_configured("pa_datex", "Needs Roma Mobilita DATEX II credentials."),
    "pa_register": _not_configured("pa_register", "Needs the administration's installation register."),
}

#: real | estimated | simulated label of each provider's data (shown in the honesty panel).
DATA_KIND: dict[str, DataKind] = {
    "sim_loops": "simulated",
    "est_register": "estimated",
    "roma_gtfs_rt": "real",
    "roma_gtfs_schedule": "estimated",
    "ingv_earthquakes": "real",
    "eea_hourly": "real",
    "dpc_radar": "real",
    "bird_gbfs": "real",
    "sensor_community": "real",
    "roma_wifi": "real",
    "om_rain_forecast": "estimated",
    "om_weather_forecast": "estimated",
    "glofas_flood": "estimated",
    "cams_open_meteo": "estimated",
    "cartoradio_grid": "estimated",
    "roma_wfs": "real",
    "pa_register_file": "real",
    "pa_datex": "real",
    "pa_register": "real",
    "arpa_points": "real",
}


def load_config(path: Path) -> dict[str, str]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must map layer names to provider ids")
    return {str(layer): str(provider_id) for layer, provider_id in raw.items()}


def build_provider(provider_id: str, settings: Settings | None = None) -> Provider:
    factory = FACTORIES.get(provider_id)
    if factory is None:
        known = ", ".join(sorted(FACTORIES))
        raise KeyError(f"Unknown provider '{provider_id}'. Known: {known}")
    return factory(settings or Settings.load())


def build_providers(config: dict[str, str], skip_unknown: bool = True,
                    settings: Settings | None = None, skip_unavailable: bool = False) -> dict[str, Provider]:
    """Instantiate the active provider of each layer.

    Layers whose provider is not a ``Provider`` (e.g. ``roma_wfs``, a static
    reader used at ingest) are skipped when ``skip_unknown`` is True. Layers
    whose provider has no access yet raise ``ProviderNotConfigured``, or are
    left out when ``skip_unavailable`` is True (``data_status`` explains why).
    """
    settings = settings or Settings.load()
    active: dict[str, Provider] = {}
    for layer, provider_id in config.items():
        if provider_id not in FACTORIES:
            if skip_unknown:
                continue
            known = ", ".join(sorted(FACTORIES))
            raise KeyError(f"Unknown provider '{provider_id}' for layer '{layer}'. Known: {known}")
        try:
            active[layer] = FACTORIES[provider_id](settings)
        except ProviderNotConfigured:
            if not skip_unavailable:
                raise
    return active
