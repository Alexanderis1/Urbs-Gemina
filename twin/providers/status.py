"""``data_status()``: what the honesty panel shows for every layer.

For each layer in config/providers.yaml: the active provider, whether it can
run, whether its data is real, estimated or simulated, licence, cadence,
whether it may be redistributed, and notes (credits, caveats). The tool API
(WS4) wraps this list in the standard response envelope.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from twin.providers.base import ProviderInfo, ProviderNotConfigured
from twin.providers.registry import DATA_KIND, FACTORIES, load_config
from twin.providers.settings import CONFIG_DIR, Settings

#: Sources that are not Provider classes but still appear in providers.yaml.
STATIC_INFO: dict[str, ProviderInfo] = {
    "roma_wfs": ProviderInfo(
        id="roma_wfs", kind="open", layer="context_layers",
        licence="not stated; credit Roma Capitale - GeoPortale (CC BY assumed, C=60)",
        cadence="static download (scripts/fetch_static_layers.py)", synthetic=False,
        notes="Official context layers; personal contact fields dropped at ingest."),
}


def data_status(config_path: Path | None = None, settings: Settings | None = None) -> list[dict[str, Any]]:
    settings = settings or Settings.load()
    config = load_config(config_path or CONFIG_DIR / "providers.yaml")
    rows: list[dict[str, Any]] = []
    for layer, provider_id in config.items():
        row: dict[str, Any] = {
            "layer": layer,
            "provider": provider_id,
            "data_kind": DATA_KIND.get(provider_id, "unknown"),
            "state": "active",
            "reason": "",
        }
        info: ProviderInfo | None = STATIC_INFO.get(provider_id)
        if info is None:
            factory = FACTORIES.get(provider_id)
            if factory is None:
                row.update(state="not_implemented", reason=f"No provider called '{provider_id}' exists yet.")
            else:
                try:
                    info = factory(settings).describe()
                except ProviderNotConfigured as error:
                    row.update(state="needs_access", reason=str(error))
        if info is not None:
            row.update(
                kind=info.kind,
                synthetic=info.synthetic,
                licence=info.licence,
                cadence=info.cadence,
                redistribution=info.redistribution,
                notes=info.notes,
            )
        else:
            row.update(synthetic=row["data_kind"] == "simulated", redistribution=None)
        rows.append(row)
    return rows
