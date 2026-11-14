"""Tool ``query_layer``: what a layer holds inside an area at a time.

Three kinds of layer, tried in this order:

1. belief layers (WS5), through ``twin.beliefs.api`` when that package is installed;
2. provider layers from ``config/providers.yaml`` (live or simulated observations);
3. static context layers downloaded by WS1 (``data/raw/<key>.geojson``).

Citizens get counts on a coarse grid for layers listed as office-only detail.
"""
from __future__ import annotations

import importlib
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from twin.providers.base import ProviderNotConfigured
from twin.providers.registry import data_kind_of
from twin.tools.area import Area, resolve_area
from twin.tools.context_check import distance_to_geometry_m
from twin.tools.envelope import Source, ToolError, utc_now
from twin.tools.layers import iter_positions
from twin.tools.runtime import ToolRuntime

TOOL = "query_layer"
Role = str


def parse_time(time: str | None) -> datetime:
    if not time:
        return datetime.now(timezone.utc).replace(microsecond=0)
    try:
        parsed = datetime.fromisoformat(time.replace("Z", "+00:00"))
    except ValueError as error:
        raise ToolError(f"time must be ISO 8601, got '{time}'") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class SafeFeed:
    """A provider whose failures become a warning and no readings, so one feed down does not fail the layer."""

    def __init__(self, name: str, provider: Any, warnings: list[str]) -> None:
        self._name, self._provider, self._warnings = name, provider, warnings

    def __getattr__(self, attribute: str) -> Any:
        return getattr(self._provider, attribute)

    def fetch(self, bbox: Any, start: datetime, end: datetime) -> list[Any]:
        try:
            return list(self._provider.fetch(bbox, start, end))
        except ProviderNotConfigured as error:
            self._warnings.append(f"Feed '{self._name}' not configured, so not used: {error}")
        except Exception as error:  # noqa: BLE001 - upstream server down or bad payload
            self._warnings.append(f"Feed '{self._name}' failed, so not used ({type(error).__name__}: {error}).")
        return []


def _belief_layer(runtime: ToolRuntime, layer: str, area: Area, at: datetime, limit: int,
                  inputs: dict[str, Any], sources: list[Source]) -> dict[str, Any] | None:
    """Belief layer from WS5 (``twin.beliefs``), or ``None`` when the layer is not a belief layer."""
    try:
        api = importlib.import_module("twin.beliefs.api")
        grid = importlib.import_module("twin.beliefs.grid")
        bconfig = importlib.import_module("twin.beliefs.config")
    except ImportError:
        return None
    if layer not in api.layer_names():
        return None
    spec = bconfig.load_specs()[layer]
    geometry = area.geometry
    cells = grid.cells_in_polygon(geometry, bconfig.grid_resolution())
    start = at - timedelta(hours=float(runtime.settings.tool("query_layer", "belief_history_hours")))
    feed_warnings: list[str] = []
    payload_fn = getattr(api, "layer_payload", None)
    payload: dict[str, Any]
    if payload_fn is not None:
        # WS5 picks only the feeds named in config/beliefs.yaml (faster, and applies source conversions).
        safe = {name: SafeFeed(name, provider, feed_warnings) for name, provider in runtime.providers.items()}
        payload = dict(payload_fn(layer, cells, start, at, safe))
    else:
        readings = []
        for provider in runtime.providers.values():
            try:
                readings += [o for o in provider.fetch(area.bbox, start, at) if o.entity_type in spec.entity_types]
            except ProviderNotConfigured:
                continue
        payload = api.query(api.build_layer(layer, cells, None, start, at, observations=readings, spec=spec))
    payload["warnings"] = list(payload.get("warnings", [])) + feed_warnings
    result = dict(payload.get("result") or {})
    all_cells = result.pop("cells", [])
    result.update(type="belief", area=area.describe(), cells=all_cells[:limit], count=len(all_cells),
                  truncated=len(all_cells) > limit)
    sources += [Source(id=str(s["id"]), retrieved_at=str(s.get("retrieved_at", utc_now())), url=s.get("url"))
                for s in payload.get("sources", [])]
    status = str(payload.get("status", "ok"))
    return runtime.envelope(TOOL, inputs, result, payload["data_kinds"], sources, payload.get("warnings", []),
                            synthetic=bool(payload.get("synthetic")), status=status,
                            reason=payload.get("reason") if status != "ok" else None,
                            extra_hashes={f"belief:{layer}": str(payload.get("snapshot_hash", ""))})


def _aggregate(points: list[tuple[float, float]], cell_m: float) -> list[dict[str, Any]]:
    """Counts per square cell of ``cell_m`` metres, reported at the cell centre."""
    if not points:
        return []
    lat0 = sum(lat for _, lat in points) / len(points)
    d_lat = cell_m / 111_195.0
    d_lon = d_lat / math.cos(math.radians(lat0))
    counts = Counter((math.floor(lon / d_lon), math.floor(lat / d_lat)) for lon, lat in points)
    return [{"lon": round((i + 0.5) * d_lon, 6), "lat": round((j + 0.5) * d_lat, 6), "count": n}
            for (i, j), n in sorted(counts.items())]


def query_layer(runtime: ToolRuntime, layer: str, area: Any = "city", time: str | None = None,
                limit: int | None = None, role: Role = "office", group_by: str | None = None) -> dict[str, Any]:
    cfg = runtime.settings.tools.get("query_layer", {})
    max_limit = int(cfg.get("max_limit", 5000))
    limit = min(int(limit or cfg.get("default_limit", 500)), max_limit)
    at = parse_time(time)
    resolved = resolve_area(area, runtime.store, runtime.settings)
    inputs = {"layer": layer, "area": area, "time": at.isoformat(), "limit": limit, "role": role}
    if group_by:
        inputs["group_by"] = group_by
    office_only = set(runtime.settings.tools.get("api", {}).get("office_only_detail_layers", []))
    aggregate = role != "office" and layer in office_only
    sources: list[Source] = [resolved.source] if resolved.source else []

    belief = _belief_layer(runtime, layer, resolved, at, limit, inputs, sources)
    if belief is not None:
        return belief

    if layer in runtime.settings.providers:
        return _provider_layer(runtime, layer, resolved, at, limit, aggregate, inputs, sources)

    snapshot = runtime.store.get(layer)
    if snapshot is None:
        known = sorted(set(runtime.settings.providers) | set(runtime.settings.context_layers.get("layers", {})))
        reason = f"Layer '{layer}' is not available. Known layer names: {', '.join(known)}"
        return runtime.envelope(TOOL, inputs, {"type": "unknown"}, {layer: "not_available"}, sources,
                                status="not_available", reason=reason)
    index = _AreaIndex(resolved)
    features = [f for f in snapshot.near(resolved.bbox) if _touches_area(f["geometry"], resolved, index)]
    kind = str(runtime.settings.context_layers.get("layers", {}).get(layer, {}).get("data_kind", "real"))
    result = {"type": "features", "area": resolved.describe(), "count": len(features),
              "features": {"type": "FeatureCollection", "features": features[:limit]},
              "truncated": len(features) > limit}
    if group_by:
        # Counted over every feature in the area, not only the listed ones (static layers only).
        tally = Counter(str((f.get("properties") or {}).get(group_by)) for f in features)
        result["counts_by"] = {group_by: dict(tally.most_common())}
    return runtime.envelope(TOOL, inputs, result, {layer: kind}, [*sources, snapshot.source()],
                         ["Features are included when one of their vertices lies inside the area, or when a "
                          "polygon contains the area's first vertex (an area inside a large zone)."])


class _AreaIndex:
    """Point-in-area test with the area's edges bucketed in latitude bands (even-odd rule, holes included).

    Area.contains walks every edge for every point; a municipio has up to about 1,800 edges and a hazard layer
    can bring 400,000 vertices, so a city-scale query took minutes. Here a point only meets the edges of its band.
    """

    BANDS = 512

    def __init__(self, area: Area) -> None:
        self.area = area
        self.w, self.s, self.e, self.n = area.bbox
        self.step = max((self.n - self.s) / self.BANDS, 1e-12)
        self.bands: list[list[tuple[float, float, float, float]]] = [[] for _ in range(self.BANDS)]
        if area.kind == "city":
            return
        geometry = area.geometry
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        for rings in polygons:
            for ring in rings:
                for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
                    if y1 == y2:
                        continue
                    for band in range(self._band(min(y1, y2)), self._band(max(y1, y2)) + 1):
                        self.bands[band].append((float(x1), float(y1), float(x2), float(y2)))

    def _band(self, lat: float) -> int:
        return min(self.BANDS - 1, max(0, int((lat - self.s) / self.step)))

    def contains(self, lon: float, lat: float) -> bool:
        if not (self.w <= lon <= self.e and self.s <= lat <= self.n):
            return False
        if self.area.kind == "city":
            return True
        inside = False
        for x1, y1, x2, y2 in self.bands[self._band(lat)]:
            if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
        return inside


def _touches_area(geometry: Mapping[str, Any], area: Area, index: _AreaIndex) -> bool:
    """A feature vertex inside the area, or (polygons) the area's first vertex inside the feature.

    The second test catches an area that lies wholly inside a large zone (a flood or Seveso zone around a
    hospital), which has no zone vertex inside it.
    """
    if any(index.contains(float(p[0]), float(p[1])) for p in iter_positions(geometry["coordinates"])):
        return True
    if geometry.get("type") not in ("Polygon", "MultiPolygon") or area.kind == "city":
        return False
    first = next(iter_positions(area.geometry["coordinates"]))  # inside the zone => the whole area is (or edges cross)
    return distance_to_geometry_m(float(first[0]), float(first[1]), geometry) == 0.0

def _provider_layer(runtime: ToolRuntime, layer: str, area: Area, at: datetime, limit: int,
                    aggregate: bool, inputs: dict[str, Any], sources: list[Source]) -> dict[str, Any]:
    provider = runtime.providers.get(layer)
    provider_id = runtime.settings.providers[layer]
    if provider is None:
        return runtime.envelope(TOOL, inputs, {"type": "observations", "provider": provider_id},
                                {layer: "not_available"}, sources, status="not_available",
                                reason=f"Provider '{provider_id}' for layer '{layer}' is not implemented or configured yet.")
    if not runtime.simulation_allowed(layer, provider):
        return runtime.envelope(TOOL, inputs, None, {layer: "simulated"}, sources, status="refused",
                                reason=f"Layer '{layer}' may not be served from simulated data "
                                       f"(provider '{provider_id}'); only {runtime.settings.tools.get('allowed_simulated_layers', [])} may.")
    try:
        info = provider.describe()
        window = int(runtime.settings.tool("query_layer", "window_minutes"))
        observations = [o for o in provider.fetch(area.bbox, at - timedelta(minutes=window), at)
                        if area.contains(o.lon, o.lat)]
    except ProviderNotConfigured as error:
        return runtime.envelope(TOOL, inputs, {"type": "observations", "provider": provider_id},
                                {layer: "not_available"}, sources, status="not_available", reason=str(error))
    except Exception as error:  # noqa: BLE001 - upstream server down or bad payload: say so, do not crash
        return runtime.envelope(TOOL, inputs, {"type": "observations", "provider": provider_id},
                                {layer: "not_available"}, sources, status="not_available",
                                reason=f"Provider '{provider_id}' failed: {type(error).__name__}: {error}")
    kind = data_kind_of(provider_id, info.kind, runtime.settings.tools["data_kind_by_provider_kind"])
    latest: dict[str, Any] = {}
    for obs in observations:
        if obs.entity_id not in latest or obs.observed_at > latest[obs.entity_id].observed_at:
            latest[obs.entity_id] = obs
    rows = sorted(latest.values(), key=lambda o: o.entity_id)
    sources.append(Source(id=info.id, retrieved_at=utc_now()))
    if aggregate:
        cell = float(runtime.settings.tool("query_layer", "aggregate_cell_m"))
        result: dict[str, Any] = {"type": "aggregate", "area": area.describe(), "provider": info.id,
                                  "cell_m": cell, "total": len(rows),
                                  "cells": _aggregate([(o.lon, o.lat) for o in rows], cell)}
        warnings = ["Citizen view: single records are aggregated."]
    else:
        result = {"type": "observations", "area": area.describe(), "provider": info.id, "count": len(rows),
                  "truncated": len(rows) > limit,
                  "observations": [{"id": o.entity_id, "entity_type": o.entity_type, "lon": round(o.lon, 6),
                                    "lat": round(o.lat, 6), "observed_at": o.observed_at.isoformat(),
                                    "values": o.values, "sigma": o.sigma, "synthetic": o.synthetic}
                                   for o in rows[:limit]]}
        warnings = []
    if info.synthetic:
        warnings.append("SIMULATED data: generated values, not measurements.")
    feed_time = getattr(provider, "last_feed_time", None)  # set by snapshot feeds (GTFS-RT, GBFS)
    if isinstance(feed_time, datetime):
        feed_time = feed_time if feed_time.tzinfo else feed_time.replace(tzinfo=timezone.utc)
        result["feed_updated_at"] = feed_time.isoformat()
        stale_after = float(runtime.settings.tool("query_layer", "stale_feed_minutes"))
        if at - feed_time > timedelta(minutes=stale_after):
            warnings.append(f"{info.id}: the source feed has not updated since {feed_time:%Y-%m-%d %H:%M} UTC, "
                            "so there are no live readings.")
    return runtime.envelope(TOOL, inputs, result, {layer: kind}, sources, warnings,
                         synthetic=info.synthetic or kind == "simulated")
