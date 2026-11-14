"""Tools ``crowds`` and ``exposure``: WS5 population views served with the WS4 envelope.

``crowds`` puts the busy-ness signals (Wi-Fi sessions, activity, timetable supply)
next to census residents per cell. ``exposure`` counts residents and children
living where a belief layer is above a legal threshold, with a range. The maths
lives in ``twin.beliefs`` (WS5); here we resolve the area, pick the feeds, read
the threshold from ``config/thresholds.yaml`` and wrap the answer.
"""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from twin.tools.area import Area, resolve_area
from twin.tools.envelope import Source, ToolError
from twin.tools.query_layer import SafeFeed, parse_time
from twin.tools.runtime import ToolRuntime
from twin.tools.settings import value


def _ws5(*names: str) -> list[Any] | None:
    try:
        return [importlib.import_module(f"twin.beliefs.{name}") for name in names]
    except ImportError:
        return None


def _census_path(runtime: ToolRuntime) -> Path:
    return runtime.settings.paths.data / "processed" / "census_sections.geojson"


def _wrap(runtime: ToolRuntime, tool: str, inputs: dict[str, Any], part: Mapping[str, Any], area: Area,
          extra: Mapping[str, Any], feed_warnings: list[str]) -> dict[str, Any]:
    status = str(part.get("status", "ok"))
    result = None if part.get("result") is None else {**dict(part["result"]), "area": area.describe(), **extra}
    sources = [Source(id=str(s["id"]), retrieved_at=str(s.get("retrieved_at") or ""), url=s.get("url"))
               for s in part.get("sources", [])]
    if area.source is not None:
        sources.append(area.source)
    return runtime.envelope(tool, inputs, result, dict(part.get("data_kinds", {})), sources,
                            list(part.get("warnings", [])) + feed_warnings,
                            synthetic=bool(part.get("synthetic")), status=status,
                            reason=part.get("reason") if status != "ok" else None,
                            extra_hashes={f"{tool}:ws5": str(part.get("snapshot_hash", ""))})


def _not_wired(runtime: ToolRuntime, tool: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return runtime.envelope(tool, inputs, None, {}, [], [], status="not_available",
                            reason="Population views (WS5 twin.beliefs crowds/exposure) are not installed in this build.")


def _window(runtime: ToolRuntime, time: str | None) -> tuple[datetime, datetime]:
    at = parse_time(time)
    return at - timedelta(hours=float(runtime.settings.tool("query_layer", "belief_history_hours"))), at


def crowds_view(runtime: ToolRuntime, area: Any = "city", time: str | None = None) -> dict[str, Any]:
    inputs = {"area": area, "time": time}
    mods = _ws5("crowds", "grid", "config")
    if mods is None:
        return _not_wired(runtime, "crowds", inputs)
    crowds, grid, bconfig = mods
    resolved = resolve_area(area, runtime.store, runtime.settings)
    start, at = _window(runtime, time)
    cells = grid.cells_in_polygon(resolved.geometry, bconfig.grid_resolution())
    feed_warnings: list[str] = []
    safe = {name: SafeFeed(name, p, feed_warnings) for name, p in runtime.providers.items()}
    census = _census_path(runtime)
    part = crowds.crowds(cells, start, at, safe, census if census.exists() else None)
    return _wrap(runtime, "crowds", inputs, part, resolved, {}, feed_warnings)


def threshold_for(runtime: ToolRuntime, layer: str, name: str) -> dict[str, Any]:
    table: dict[str, dict[str, list[str]]] = runtime.settings.tools.get("exposure", {}).get("thresholds", {})
    if layer not in table:
        raise ToolError(f"exposure works on {sorted(table)}, not '{layer}'")
    if name not in table[layer]:
        raise ToolError(f"threshold for '{layer}' must be one of {sorted(table[layer])}")
    section, key = table[layer][name]
    entry = runtime.settings.thresholds[section][key]
    return {"name": name, "value": float(value(entry)), "source": str(entry.get("source", "")),
            "averaging": str(entry.get("averaging", ""))}


def _belief(runtime: ToolRuntime, layer: str, area: Area, time: str | None, feed_warnings: list[str]
            ) -> tuple[Any, datetime, list[str]] | str:
    """Build a WS5 belief layer on the area's cells from the feeds named in beliefs.yaml, or a reason why not."""
    api, grid, bconfig = [importlib.import_module(f"twin.beliefs.{n}") for n in ("api", "grid", "config")]
    if layer not in api.layer_names():
        raise ToolError(f"unknown belief layer '{layer}'. Known: {', '.join(sorted(api.layer_names()))}")
    start, at = _window(runtime, time)
    spec = bconfig.load_specs()[layer]
    cells = grid.cells_in_polygon(area.geometry, bconfig.grid_resolution())
    safe = {name: SafeFeed(name, p, feed_warnings) for name, p in runtime.providers.items()}
    pairs = [(safe[s.layer], s) for s in spec.sources if s.layer in safe]
    prior_field = getattr(spec, "prior_field", None)
    prior = safe.get(prior_field.source) if prior_field is not None else None
    if not pairs and prior is None:
        return f"No source connected for layer '{layer}'."
    belief = api.build_layer(layer, cells, [p for p, _ in pairs], start, at, spec=spec, prior_provider=prior,
                             sources=[s for _, s in pairs])
    return belief, at, list(cells)


def _averaging_warning(limit: Mapping[str, Any], at: datetime) -> str:
    return (f"The estimate is for {at:%Y-%m-%d %H:%M} UTC; the legal value applies to a "
            f"{limit['averaging'] or 'longer'} average, so this is an indication, not a legal exceedance.")


def exposure_count(runtime: ToolRuntime, layer: str, area: Any = "city", threshold: str = "",
                   time: str | None = None) -> dict[str, Any]:
    inputs = {"layer": layer, "area": area, "threshold": threshold, "time": time}
    limit = threshold_for(runtime, layer, threshold)
    mods = _ws5("api", "grid", "config", "crowds", "exposure")
    if mods is None:
        return _not_wired(runtime, "exposure", inputs)
    crowds, exposure = mods[3], mods[4]
    resolved = resolve_area(area, runtime.store, runtime.settings)
    census_path = _census_path(runtime)
    if not census_path.exists():
        return runtime.envelope("exposure", inputs, None, {"residents": "not_available"}, [], [],
                                status="not_available", reason="Census sections (WS1) not built yet.")
    feed_warnings: list[str] = []
    built = _belief(runtime, layer, resolved, time, feed_warnings)
    if isinstance(built, str):
        return runtime.envelope("exposure", inputs, None, {layer: "not_available"}, [], feed_warnings,
                                status="not_available", reason=built)
    belief, at, cells = built
    part = exposure.exposure(belief, crowds.census_per_cell(census_path, cells), limit["value"])
    return _wrap(runtime, "exposure", inputs, part, resolved, {"threshold": limit},
                 feed_warnings + [_averaging_warning(limit, at)])


def site_values_at(runtime: ToolRuntime, layer: str, area: Any = "city", threshold: str | None = None,
                   categories: list[str] | None = None, limit: int = 50, time: str | None = None) -> dict[str, Any]:
    """The layer at each sensitive site (schools, hospitals...) in the area, riskiest first."""
    inputs = {"layer": layer, "area": area, "threshold": threshold, "categories": categories, "limit": limit,
              "time": time}
    named = threshold_for(runtime, layer, threshold) if threshold else None
    mods = _ws5("api", "grid", "config", "sites")
    if mods is None:
        return _not_wired(runtime, "site_values", inputs)
    sites = mods[3]
    path = runtime.settings.paths.data / "processed" / "sensitive_sites.geojson"
    if not path.exists():
        return runtime.envelope("site_values", inputs, None, {"sensitive_sites": "not_available"}, [], [],
                                status="not_available", reason="Sensitive sites layer (WS1) not built yet.")
    resolved = resolve_area(area, runtime.store, runtime.settings)
    feed_warnings: list[str] = []
    built = _belief(runtime, layer, resolved, time, feed_warnings)
    if isinstance(built, str):
        return runtime.envelope("site_values", inputs, None, {layer: "not_available"}, [], feed_warnings,
                                status="not_available", reason=built)
    belief, at, _ = built
    part = dict(sites.site_values(belief, path, named["value"] if named else None, categories))
    result = dict(part.get("result") or {})
    rows = list(result.get("sites", []))
    result.update(sites=rows[:limit], count=len(rows), truncated=len(rows) > limit)
    part["result"] = result
    extra: dict[str, Any] = {"threshold": named} if named else {}
    warnings = feed_warnings + ([_averaging_warning(named, at)] if named else [])
    return _wrap(runtime, "site_values", inputs, part, resolved, extra, warnings)


def check_sensors_tool(runtime: ToolRuntime, layer: str, area: Any = "city", time: str | None = None
                       ) -> dict[str, Any]:
    """Stations of a layer that keep disagreeing with their neighbours (WS5 sensor health)."""
    inputs = {"layer": layer, "area": area, "time": time}
    mods = _ws5("api", "config")
    if mods is None or not hasattr(mods[0], "check_sensors"):
        return _not_wired(runtime, "check_sensors", inputs)
    api, bconfig = mods
    if layer not in api.layer_names():
        raise ToolError(f"unknown belief layer '{layer}'. Known: {', '.join(sorted(api.layer_names()))}")
    resolved = resolve_area(area, runtime.store, runtime.settings)
    start, at = _window(runtime, time)
    spec = bconfig.load_specs()[layer]
    feed_warnings: list[str] = []
    readings: list[Any] = []
    used: list[str] = []
    for source in spec.sources:
        provider = runtime.providers.get(source.layer)
        if provider is None:
            continue
        feed = SafeFeed(source.layer, provider, feed_warnings)
        readings += list(api.adapt(feed.fetch(resolved.bbox, start, at), source, spec))
        used.append(source.layer)
    if not used:
        return runtime.envelope("check_sensors", inputs, None, {layer: "not_available"}, [], feed_warnings,
                                status="not_available", reason=f"No source connected for layer '{layer}'.")
    stations = list(api.check_sensors(layer, readings))
    result = {"layer": layer, "area": resolved.describe(), "from": start.isoformat(), "to": at.isoformat(),
              "readings": len(readings), "stations": stations,
              "flagged": [s for s in stations if s.get("flag")],
              "meaning": "A flagged station disagrees with its neighbours again and again: check it before trusting it."}
    sources = [Source(id=name, retrieved_at=at.isoformat()) for name in used]
    return runtime.envelope("check_sensors", inputs, result, {name: "real" for name in used}, sources,
                            feed_warnings)
