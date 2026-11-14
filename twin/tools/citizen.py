"""Citizen services: air and radio-frequency field "here", city heat maps.

Every number comes from the belief layers (twin/beliefs) through ``query_layer``; every level and
reference value comes from config/thresholds.yaml (legal values, EEA air index) or config/tools.yaml
``citizen`` (assumptions with a basis note). One city build per layer and 10-minute slot is cached,
so a point answer and a heat map share the same numbers and cost one build.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
import time as clock
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Sequence

import h3  # type: ignore[import-untyped]

from twin.tools.area import resolve_area
from twin.tools.envelope import Source, ToolError, utc_now
from twin.tools.query_layer import _belief_layer, parse_time
from twin.tools.runtime import ToolRuntime
from twin.tools.settings import value

HEATMAP_LAYERS = ("air_no2", "air_pm10", "air_pm25", "air_o3", "emf", "road_speed")
#: (layer, slot iso) -> (monotonic time, envelope, rows by cell)
_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any], dict[str, dict[str, Any]]]] = {}
_LOCK = threading.Lock()


def _cfg(rt: ToolRuntime) -> Mapping[str, Any]:
    return dict(rt.settings.tools.get("citizen", {}))


def _slot(rt: ToolRuntime, time: str | None) -> datetime:
    """The request time floored to the cache slot, so callers in the same slot share one build."""
    minutes = int(value(_cfg(rt).get("cache_minutes", 10)))
    at = parse_time(time)
    floored = at.replace(minute=(at.minute // minutes) * minutes, second=0, microsecond=0)
    return floored


def _build_city(rt: ToolRuntime, layer: str, at: datetime) -> dict[str, Any]:
    """The whole-city belief layer, every cell (no thinning)."""
    area = resolve_area("city", rt.store, rt.settings)
    inputs: dict[str, Any] = {"layer": layer, "area": "city", "time": at.isoformat()}
    sources: list[Source] = [area.source] if area.source else []
    envelope = _belief_layer(rt, layer, area, at, 10**7, inputs, sources)
    if envelope is None:
        raise ToolError(f"'{layer}' is not a belief layer")
    return envelope


def city_layer(rt: ToolRuntime, layer: str, at: datetime,
               build: Callable[[ToolRuntime, str, datetime], dict[str, Any]] | None = None
               ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """(envelope, rows by H3 cell) of a city belief layer at ``at``; cached per slot."""
    key = (layer, at.isoformat())
    ttl = float(value(_cfg(rt).get("cache_minutes", 10))) * 60.0
    with _LOCK:
        hit = _CACHE.get(key)
        if hit is not None and clock.monotonic() - hit[0] < ttl:
            return hit[1], hit[2]
    envelope = (build or _build_city)(rt, layer, at)
    rows = {str(r["cell"]): r for r in ((envelope.get("result") or {}).get("cells") or [])}
    with _LOCK:
        for stale in [k for k, v in _CACHE.items() if clock.monotonic() - v[0] >= ttl]:
            _CACHE.pop(stale, None)
        _CACHE[key] = (clock.monotonic(), envelope, rows)
    return envelope, rows


def band(value_: float, uppers: Sequence[float]) -> int:
    """1-based band: 1 when value <= uppers[0], len(uppers) + 1 above the last upper limit."""
    for i, upper in enumerate(uppers):
        if value_ <= upper:
            return i + 1
    return len(uppers) + 1


def _air_index(rt: ToolRuntime) -> Mapping[str, Any]:
    return dict(rt.settings.thresholds["air_quality_index"])


def air_level(rt: ToolRuntime, pollutant: str, concentration: float) -> dict[str, Any]:
    idx = _air_index(rt)
    i = band(concentration, [float(x) for x in idx["upper_ug_m3"][pollutant]])
    return {"index": i, "label_it": idx["labels_it"][i - 1], "label_en": idx["labels_en"][i - 1],
            "scale": "EEA European Air Quality Index (2024 bands)", "source": idx["source"]}


def _references(rt: ToolRuntime, layer: str) -> list[dict[str, Any]]:
    """Legal values for a layer, read through tools.yaml exposure.thresholds -> thresholds.yaml."""
    out = []
    for name, path in (rt.settings.tools.get("exposure", {}).get("thresholds", {}).get(layer) or {}).items():
        node: Any = rt.settings.thresholds
        for key in path:
            node = node[key]
        out.append({"name": name, "value": float(node["value"]), "averaging": node.get("averaging"),
                    "applies_to": node.get("applies_to"), "source": node.get("source")})
    return out


def _emf_bands(rt: ToolRuntime) -> list[float]:
    low = [float(x) for x in value(_cfg(rt)["emf_low_bands_v_per_m"])]
    emf = rt.settings.thresholds["emf"]
    return low + [float(emf["attention_value_v_per_m"]["value"]), float(emf["exposure_limit_v_per_m"]["value"])]


def emf_level(rt: ToolRuntime, field: float) -> dict[str, Any]:
    i = band(field, _emf_bands(rt))
    return {"index": i, "label_it": _cfg(rt)["emf_labels_it"][i - 1]}


def _free_flow(rt: ToolRuntime) -> tuple[dict[str, float] | None, float]:
    congestion = _cfg(rt)["congestion"]
    try:
        from twin.beliefs.landuse import load_cell_covariate
        per_cell = load_cell_covariate("road_free_flow_kmh.csv")
    except ImportError:
        per_cell = None
    return per_cell, float(value(congestion["free_flow_kmh"]))


def congestion_level(rt: ToolRuntime, speed: float, free_flow: float) -> dict[str, Any]:
    congestion = _cfg(rt)["congestion"]
    ratio = speed / free_flow if free_flow > 0 else 1.0
    i = band(ratio, [float(x) for x in value(congestion["ratio_bands"])])
    # band 1 = slowest; labels are ordered from blocked to free flowing
    return {"index": i, "label_it": congestion["labels_it"][i - 1], "speed_ratio": round(ratio, 2)}


def _point_cell(point: Sequence[float]) -> str:
    from twin.beliefs.config import grid_resolution
    return str(h3.latlng_to_cell(float(point[1]), float(point[0]), grid_resolution()))


def _merge(envelopes: Sequence[Mapping[str, Any]]) -> tuple[dict[str, str], list[Source], list[str], bool]:
    kinds: dict[str, str] = {}
    sources: dict[str, Source] = {}
    warnings: list[str] = []
    synthetic = False
    for env in envelopes:
        kinds.update({str(k): str(v) for k, v in (env.get("data_kinds") or {}).items()})
        for s in env.get("sources") or []:
            if isinstance(s, Mapping) and s.get("id"):
                sources[str(s["id"])] = Source(id=str(s["id"]), retrieved_at=str(s.get("retrieved_at") or utc_now()),
                                               url=s.get("url"))
        warnings += [w for w in env.get("warnings") or [] if w not in warnings and not str(w).startswith("Large area")]
        synthetic = synthetic or bool(env.get("synthetic"))
    return kinds, list(sources.values()), warnings, synthetic


def _row_value(row: Mapping[str, Any]) -> tuple[float, float, float]:
    return float(row.get("p50", row.get("mean", 0.0))), float(row.get("p5", 0.0)), float(row.get("p95", 0.0))


def air_here(rt: ToolRuntime, point: Sequence[float], time: str | None = None,
             build: Callable[[ToolRuntime, str, datetime], dict[str, Any]] | None = None) -> dict[str, Any]:
    cfg = _cfg(rt)
    at = _slot(rt, time)
    cell = _point_cell(point)
    inputs = {"point": list(point), "time": at.isoformat()}
    pollutants: list[dict[str, Any]] = []
    envelopes = []
    layers = dict(cfg["air_layers"])
    with ThreadPoolExecutor(max_workers=len(layers)) as pool:  # the four city builds wait on different feeds
        built = dict(zip(layers, pool.map(lambda name: city_layer(rt, name, at, build), layers.values())))
    for pollutant, layer in layers.items():
        env, rows = built[pollutant]
        envelopes.append(env)
        row = rows.get(cell)
        entry: dict[str, Any] = {"id": pollutant, "layer": layer, "label": cfg["air_labels_it"][pollutant],
                                 "unit": "µg/m³", "kind": (env.get("data_kinds") or {}).get(layer, "estimated")}
        if env.get("status") != "ok" or row is None:
            entry.update(status="not_available", reason=env.get("reason") or "no value for this cell")
        else:
            mid, low, high = _row_value(row)
            entry.update(status="ok", value=round(mid, 1), low=round(low, 1), high=round(high, 1),
                         level=air_level(rt, pollutant, mid), references=_references(rt, layer))
        pollutants.append(entry)
    ok = [p for p in pollutants if p["status"] == "ok"]
    kinds, sources, warnings, synthetic = _merge(envelopes)
    if not ok:
        return rt.envelope("air_here", inputs, None, kinds or {"air": "not_available"}, sources, warnings,
                           status="not_available", reason="no air layer could be built")
    worst = max(ok, key=lambda p: p["level"]["index"])
    summary = (f"Qualità dell'aria stimata qui: {worst['level']['label_it'].lower()} "
               f"(indice europeo EEA; inquinante che pesa di più: {worst['label']}, "
               f"circa {worst['value']:g} µg/m³, tra {worst['low']:g} e {worst['high']:g}).")
    result = {"cell": cell, "pollutants": pollutants, "overall": worst["level"], "worst": worst["id"],
              "summary_it": summary,
              "note_it": "Stima oraria da stazioni ufficiali e modello CAMS. I limiti di legge valgono su medie "
                         "più lunghe (ora, giorno, anno): il confronto è orientativo."}
    warnings.append("Air values are hourly estimates; legal limits apply to longer averages, so the comparison is indicative.")
    return rt.envelope("air_here", inputs, result, kinds, sources, warnings, synthetic=synthetic)


def emf_here(rt: ToolRuntime, point: Sequence[float], time: str | None = None,
             build: Callable[[ToolRuntime, str, datetime], dict[str, Any]] | None = None) -> dict[str, Any]:
    at = _slot(rt, time)
    cell = _point_cell(point)
    inputs = {"point": list(point), "time": at.isoformat()}
    env, rows = city_layer(rt, "emf", at, build)
    kinds, sources, warnings, synthetic = _merge([env])
    row = rows.get(cell)
    if env.get("status") != "ok" or row is None:
        return rt.envelope("emf_here", inputs, None, kinds or {"emf": "not_available"}, sources, warnings,
                           status="not_available", reason=env.get("reason") or "no value for this cell")
    mid, low, high = _row_value(row)
    level = emf_level(rt, high)  # judged on the upper end of the range: the cautious reading
    refs = _references(rt, "emf")
    attention = next((r["value"] for r in refs if r["name"] == "attention_value"), None)
    summary = (f"Campo elettrico stimato qui: circa {mid:.2g} V/m (tra {low:.2g} e {high:.2g}), livello "
               f"{level['label_it'].lower()}" + (f"; il valore di attenzione di legge è {attention:g} V/m." if attention else "."))
    result = {"cell": cell, "value": round(mid, 3), "low": round(low, 3), "high": round(high, 3), "unit": "V/m",
              "kind": (env.get("data_kinds") or {}).get("emf", "estimated"), "level": level, "references": refs,
              "summary_it": summary,
              "note_it": "Stima da modello sulle antenne note, non una misura. Per una misura rivolgersi ad ARPA Lazio."}
    return rt.envelope("emf_here", inputs, result, kinds, sources, warnings, synthetic=synthetic)


def _legend(rt: ToolRuntime, layer: str) -> list[dict[str, Any]]:
    if layer.startswith("air_"):
        pollutant = layer[4:]
        idx = _air_index(rt)
        uppers = [float(x) for x in idx["upper_ug_m3"][pollutant]]
        labels = idx["labels_it"]
        unit = "µg/m³"
    elif layer == "emf":
        uppers, labels, unit = _emf_bands(rt), _cfg(rt)["emf_labels_it"], "V/m"
    else:
        congestion = _cfg(rt)["congestion"]
        uppers, labels, unit = [float(x) for x in value(congestion["ratio_bands"])], congestion["labels_it"], "velocità / velocità libera"
    edges: list[float | None] = [0.0, *uppers, None]
    return [{"index": i + 1, "label_it": labels[i], "from": edges[i], "to": edges[i + 1], "unit": unit}
            for i in range(len(labels))]


def city_heatmap(rt: ToolRuntime, layer: str, time: str | None = None, resolution: int | None = None,
                 build: Callable[[ToolRuntime, str, datetime], dict[str, Any]] | None = None) -> dict[str, Any]:
    if layer not in HEATMAP_LAYERS:
        raise ToolError(f"layer must be one of {', '.join(HEATMAP_LAYERS)}")
    res = int(resolution or value(_cfg(rt)["heatmap_resolution"]))
    at = _slot(rt, time)
    inputs = {"layer": layer, "time": at.isoformat(), "resolution": res}
    env, rows = city_layer(rt, layer, at, build)
    kinds, sources, warnings, synthetic = _merge([env])
    if env.get("status") != "ok" or not rows:
        return rt.envelope("city_heatmap", inputs, None, kinds or {layer: "not_available"}, sources, warnings,
                           status="not_available", reason=env.get("reason") or "layer is empty")
    per_cell, default_free = _free_flow(rt) if layer == "road_speed" else (None, 0.0)
    groups: dict[str, list[tuple[float, float, float, float]]] = {}
    for cell, row in rows.items():
        mid, low, high = _row_value(row)
        free = (per_cell or {}).get(cell, default_free)
        parent = str(h3.cell_to_parent(cell, res)) if h3.get_resolution(cell) > res else cell
        groups.setdefault(parent, []).append((mid, low, high, free))
    cells = []
    for parent, vals in groups.items():
        n = len(vals)
        mid, low, high, free = (sum(v[k] for v in vals) / n for k in range(4))
        lat, lon = h3.cell_to_latlng(parent)
        entry: dict[str, Any] = {"cell": parent, "lon": round(lon, 5), "lat": round(lat, 5),
                                 "value": round(mid, 3), "low": round(low, 3), "high": round(high, 3)}
        if layer.startswith("air_"):
            entry["level"] = air_level(rt, layer[4:], mid)["index"]
        elif layer == "emf":
            entry["level"] = emf_level(rt, high)["index"]
        else:
            entry["level"] = congestion_level(rt, mid, free)["index"]
        cells.append(entry)
    cells.sort(key=lambda c: c["cell"])
    result = {"layer": layer, "resolution": res, "count": len(cells), "cells": cells, "legend": _legend(rt, layer),
              "time": at.isoformat(), "kind": kinds.get(layer)}
    if layer == "road_speed" and at > datetime.now(timezone.utc) + timedelta(minutes=10):
        result["predicted"] = True
        warnings.append("Future time: congestion is the expected pattern for that hour (road classes x city profile), "
                        "not a forecast of today's incidents.")
    return rt.envelope("city_heatmap", inputs, result, kinds, sources, warnings, synthetic=synthetic)


def prewarm(rt: ToolRuntime) -> dict[str, str]:
    """Build the citizen layers for the current slot, so the first person does not wait (API start-up)."""
    at = _slot(rt, None)
    names = [str(n) for n in _cfg(rt).get("prewarm_layers", [])]
    done: dict[str, str] = {}

    def one(name: str) -> None:
        try:
            env, _ = city_layer(rt, name, at)
            done[name] = str(env.get("status"))
        except Exception as error:  # noqa: BLE001 - best effort
            done[name] = f"failed: {type(error).__name__}"

    with ThreadPoolExecutor(max_workers=max(1, len(names))) as pool:
        list(pool.map(one, names))
    return done
