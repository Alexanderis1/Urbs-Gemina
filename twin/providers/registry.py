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
from twin.providers.open.dpc_radar import DpcRadarProvider
from twin.providers.open.eea import EeaHourlyProvider
from twin.providers.open.gtfs_rt import RomaGtfsRtProvider
from twin.providers.pa.register_file import PaRegisterFileProvider
from twin.providers.restricted.cartoradio import CartoradioGridProvider
from twin.providers.settings import Settings
from twin.providers.simulated.applications import SimApplicationsProvider
from twin.providers.simulated.emf_points import SimEmfPointsProvider
from twin.providers.simulated.loops import SimLoopsProvider
from twin.providers.simulated.register import SimRegisterProvider

Factory = Callable[[Settings], Provider]
DataKind = Literal["real", "estimated", "simulated"]


def _not_configured(provider_id: str, hint: str) -> Factory:
    def factory(settings: Settings) -> Provider:
        raise ProviderNotConfigured(f"Provider '{provider_id}' has no access configured yet. {hint}")

    return factory


#: Every provider id that may appear in providers.yaml.
FACTORIES: dict[str, Factory] = {
    # simulated (fill the three gaps the administration confirmed, plus the demo inbox)
    "sim_loops": SimLoopsProvider.from_settings,
    "sim_register": SimRegisterProvider,
    "sim_emf_points": SimEmfPointsProvider,
    "sim_applications": SimApplicationsProvider,
    # open, real
    "roma_gtfs_rt": RomaGtfsRtProvider,
    "eea_hourly": EeaHourlyProvider,
    "dpc_radar": DpcRadarProvider,
    # restricted: runtime read only
    "cartoradio_grid": CartoradioGridProvider,
    # the administration's own data
    "pa_register_file": PaRegisterFileProvider,
    "pa_datex": _not_configured("pa_datex", "Needs Roma Mobilita DATEX II credentials."),
    "pa_register": _not_configured("pa_register", "Needs the administration's installation register."),
    "arpa_points": _not_configured("arpa_points", "Needs ARPA Lazio measurement-point access."),
}

#: real | estimated | simulated label of each provider's data (shown in the honesty panel).
DATA_KIND: dict[str, DataKind] = {
    "sim_loops": "simulated",
    "sim_register": "simulated",
    "sim_emf_points": "simulated",
    "sim_applications": "simulated",
    "roma_gtfs_rt": "real",
    "eea_hourly": "real",
    "dpc_radar": "real",
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
                    settings: Settings | None = None) -> dict[str, Provider]:
    """Instantiate the active provider of each layer.

    Layers whose provider is not a ``Provider`` (e.g. ``roma_wfs``, a static
    reader used at ingest) are skipped when ``skip_unknown`` is True.
    """
    settings = settings or Settings.load()
    active: dict[str, Provider] = {}
    for layer, provider_id in config.items():
        if provider_id not in FACTORIES:
            if skip_unknown:
                continue
            known = ", ".join(sorted(FACTORIES))
            raise KeyError(f"Unknown provider '{provider_id}' for layer '{layer}'. Known: {known}")
        active[layer] = FACTORIES[provider_id](settings)
    return active
