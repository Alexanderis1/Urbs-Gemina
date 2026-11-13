"""Tool ``data_status``: the honesty panel. Real, estimated or simulated, per layer."""
from __future__ import annotations

import json
from typing import Any

from twin.providers.base import ProviderNotConfigured
from twin.providers.registry import FACTORIES
from twin.tools.runtime import ToolRuntime

TOOL = "data_status"


def data_status(runtime: ToolRuntime) -> dict[str, Any]:
    settings = runtime.settings
    manifest: dict[str, Any] = {}
    if settings.paths.manifest.exists():
        manifest = json.loads(settings.paths.manifest.read_text(encoding="utf-8"))
    catalogue: dict[str, Any] = manifest.get("sources", {})
    kind_map: dict[str, Any] = settings.tools.get("data_kind_by_provider_kind", {})

    layers: list[dict[str, Any]] = []
    kinds: dict[str, str] = {}
    synthetic_any = False
    allowed_sim = set(settings.tools.get("allowed_simulated_layers", []))
    violations: list[str] = []
    for layer, provider_id in settings.providers.items():
        entry: dict[str, Any] = {"layer": layer, "provider": provider_id}
        provider = runtime.providers.get(layer)
        meta = catalogue.get(provider_id, {})
        if provider is not None:
            try:
                info = provider.describe()
                entry.update(status="active", provider_kind=info.kind, synthetic=info.synthetic,
                             licence=info.licence, cadence=info.cadence, redistribution=info.redistribution,
                             notes=info.notes)
                data_kind = str(kind_map.get(info.kind, "real"))
            except ProviderNotConfigured as error:
                entry.update(status="not_configured", reason=str(error))
                data_kind = _manifest_kind(meta)
        else:
            entry["status"] = "planned" if provider_id not in FACTORIES else "not_configured"
            data_kind = _manifest_kind(meta)
            entry.update(synthetic=data_kind == "simulated", licence=meta.get("licence"),
                         redistribution=meta.get("redistribution"))
        entry["data_kind"] = data_kind
        if data_kind == "simulated" and layer not in allowed_sim:
            entry["violation"] = "only traffic loops may be simulated: switch this layer to a real or estimated provider"
            violations.append(layer)
        synthetic_any = synthetic_any or bool(entry.get("synthetic"))
        kinds[layer] = data_kind
        layers.append(entry)

    snapshots = [
        {"key": key, "status": snap.get("status"), "features": snap.get("features"),
         "sha256": snap.get("sha256"), "fetched_at": snap.get("fetched_at"), "source": snap.get("source")}
        for key, snap in sorted(manifest.get("snapshots", {}).items())
    ]
    context = settings.context_layers.get("layers", {})
    context_rows = [{"layer": key, "label": meta.get("label", key), "group": meta.get("group"),
                     "downloaded": runtime.store.get(key) is not None} for key, meta in context.items()]
    result = {
        "layers": layers,
        "static_snapshots": snapshots,
        "context_layers": context_rows,
        "counts": {kind: sum(1 for k in kinds.values() if k == kind) for kind in ("real", "estimated", "simulated")},
        "thresholds_as_of": settings.thresholds.get("as_of"),
        "allowed_simulated_layers": sorted(allowed_sim),
        "simulation_violations": violations,
    }
    warnings = [f"Layer '{v}' is configured with a simulated provider; only traffic loops may be simulated."
                for v in violations]
    return runtime.envelope(TOOL, {}, result, kinds, warnings=warnings, synthetic=synthetic_any)


def _manifest_kind(meta: dict[str, Any]) -> str:
    kind = str(meta.get("kind", "real"))
    return {"restricted": "estimated"}.get(kind, kind if kind in ("real", "estimated", "simulated") else "real")
