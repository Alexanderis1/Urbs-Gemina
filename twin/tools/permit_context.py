"""Tool ``context_check``: everything of Challenge 02 within the radius of a point.

Wraps :func:`twin.tools.context_check.context_check` over the layer list in
``config/context_layers.yaml``. Distance is context for the officer, not a ban;
the wording comes from ``config/thresholds.yaml``.
"""
from __future__ import annotations

import math
from typing import Any

from twin.tools.context_check import context_check
from twin.tools.envelope import Source, ToolError, utc_now
from twin.tools.layers import first_property
from twin.tools.prg import prg_around
from twin.tools.runtime import ToolRuntime

TOOL = "context_check"
MAX_RADIUS_M = 2000.0


def default_radius_m(runtime: ToolRuntime) -> float:
    return float(runtime.settings.thresholds["antenna_context"]["radius_m"])


def run_context_check(runtime: ToolRuntime, lon: float, lat: float, radius_m: float | None = None,
                      include_properties: bool = True) -> dict[str, Any]:
    radius = default_radius_m(runtime) if radius_m is None else float(radius_m)
    if not 0.0 < radius <= MAX_RADIUS_M:
        raise ToolError(f"radius_m must be between 0 and {MAX_RADIUS_M:g}")
    inputs = {"point": {"lon": lon, "lat": lat}, "radius_m": radius}
    catalogue: dict[str, Any] = runtime.settings.context_layers.get("layers", {})
    name_fields = list(runtime.settings.context_layers.get("name_fields", []))
    groups: dict[str, str] = runtime.settings.context_layers.get("groups", {})

    d_lat = radius / 111_195.0
    d_lon = d_lat / math.cos(math.radians(lat))
    window = (lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat)

    collections: dict[str, dict[str, Any] | None] = {}
    sources: list[Source] = []
    kinds: dict[str, str] = {}
    live: dict[str, list[dict[str, Any]]] = {}
    live_warnings: list[str] = []
    for key, meta in catalogue.items():
        if meta.get("live") == "wms_point":
            try:
                live[key] = prg_around(lon, lat, radius, meta, runtime.prg_fetcher)
                kinds[key] = str(meta.get("data_kind", "real"))
                sources.append(Source(id=f"live:{key}", retrieved_at=utc_now(), url=str(meta.get("url"))))
                live_warnings.append(f"{meta.get('label', key)}: sampled at the centre and on rings, not exhaustive.")
            except Exception as error:  # noqa: BLE001 - city server down: report, do not fail the check
                kinds[key] = "not_available"
                live_warnings.append(f"{meta.get('label', key)}: live query failed ({type(error).__name__}).")
            collections[key] = None
            continue
        snapshot = runtime.store.get(key)
        if snapshot is None:
            collections[key] = None
            kinds[key] = "not_available"
            continue
        collections[key] = {"type": "FeatureCollection", "features": snapshot.near(window)}
        sources.append(snapshot.source())
        kinds[key] = str(meta.get("data_kind", "real"))
    raw = context_check(lon, lat, collections, radius_m=radius)
    for key, hits in live.items():
        raw["layers"][key] = {"status": "ok", "count": len(hits), "hits": hits}

    by_group: dict[str, list[dict[str, Any]]] = {group: [] for group in groups}
    missing: list[str] = []
    for key, meta in catalogue.items():
        layer = raw["layers"][key]
        entry: dict[str, Any] = {"layer": key, "label": meta.get("label", key), "status": layer["status"]}
        if layer["status"] == "ok":
            entry["count"] = layer["count"]
            entry["hits"] = [
                {"distance_m": hit["distance_m"],
                 "name": hit.get("name") or first_property(hit["properties"], name_fields),
                 **({"properties": hit["properties"]} if include_properties else {})}
                for hit in layer["hits"]
            ]
        else:
            missing.append(str(meta.get("label", key)))
        by_group.setdefault(str(meta.get("group", "other")), []).append(entry)

    meaning = str(runtime.settings.thresholds["antenna_context"].get("meaning", ""))
    result = {
        "point": raw["point"],
        "radius_m": radius,
        "meaning": meaning,
        "groups": {group: {"label": groups.get(group, group), "layers": layers} for group, layers in by_group.items()},
        "summary": {
            group: sum(layer.get("count", 0) for layer in layers) for group, layers in by_group.items()
        },
        "not_available": missing,
    }
    warnings = [f"Layer not available, so not checked: {label}." for label in missing] + live_warnings
    return runtime.envelope(TOOL, inputs, result, kinds, sources, warnings)
