"""Turn config/providers.yaml into live provider objects."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import yaml

from twin.providers.base import Provider, ProviderNotConfigured
from twin.providers.simulated.loops import SimLoopsProvider

Factory = Callable[[], Provider]


def _not_configured(provider_id: str, hint: str) -> Factory:
    def factory() -> Provider:
        raise ProviderNotConfigured(f"Provider '{provider_id}' has no access configured yet. {hint}")

    return factory


#: Every provider id that may appear in providers.yaml.
FACTORIES: dict[str, Factory] = {
    "sim_loops": SimLoopsProvider,
    "pa_datex": _not_configured("pa_datex", "Needs Roma Mobilita DATEX II credentials."),
    "pa_register": _not_configured("pa_register", "Needs the administration's installation register."),
}


def load_config(path: Path) -> dict[str, str]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must map layer names to provider ids")
    return {str(layer): str(provider_id) for layer, provider_id in raw.items()}


def build_providers(config: dict[str, str], skip_unknown: bool = True) -> dict[str, Provider]:
    """Instantiate the active provider of each layer.

    Layers whose provider is not implemented yet are skipped when
    ``skip_unknown`` is True, so the scaffold runs while providers are added.
    """
    active: dict[str, Provider] = {}
    for layer, provider_id in config.items():
        factory = FACTORIES.get(provider_id)
        if factory is None:
            if skip_unknown:
                continue
            known = ", ".join(sorted(FACTORIES))
            raise KeyError(f"Unknown provider '{provider_id}' for layer '{layer}'. Known: {known}")
        active[layer] = factory()
    return active
