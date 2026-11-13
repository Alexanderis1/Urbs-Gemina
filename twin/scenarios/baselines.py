"""Live inputs for scenarios: the Cartoradio grid (WS3 provider) as the EMF baseline.

The grid is read at runtime for the window a scenario needs and kept in memory
only (Cartoradio: ``redistribution: false``).
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Protocol

from twin.providers.base import BBox, Observation
from twin.scenarios import config, layers
from twin.scenarios.area import AreaArg, resolve_area
from twin.scenarios.data import FieldFn, FieldSample, ScenarioData

R_MERCATOR = 6_378_137.0
_CELL_ID = re.compile(r"-r(\d+)-c(\d+)$")


class _Fetcher(Protocol):
    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterable[Observation]: ...


def _mercator(lon: float, lat: float) -> tuple[float, float]:
    return (R_MERCATOR * math.radians(lon),
            R_MERCATOR * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def grid_field(cells: Iterable[Observation]) -> FieldFn:
    """Nearest-cell lookup on a regular Web Mercator grid (cell ids carry row and column)."""
    table: dict[tuple[int, int], FieldSample] = {}
    anchors: list[tuple[int, int, float, float]] = []
    for obs in cells:
        m = _CELL_ID.search(obs.entity_id)
        if m is None:
            continue
        row, col = int(m.group(1)), int(m.group(2))
        value = float(obs.values["electricField"])
        sigma = float(obs.sigma.get("electricField", 0.0))
        sigma_db = 20.0 * math.log10(1.0 + sigma / value) if value > 0 else 0.0
        table[(row, col)] = FieldSample(value, sigma_db)
        if len(anchors) < 2 or (col != anchors[0][1] and len(anchors) < 3):
            anchors.append((row, col, *_mercator(obs.lon, obs.lat)))
    if not table:
        return lambda lon, lat: None
    r0, c0, x0, y0 = anchors[0]
    size = 100.0
    for r1, c1, x1, y1 in anchors[1:]:
        if c1 != c0:
            size = (x1 - x0) / (c1 - c0)
            break
        if r1 != r0:
            size = (y0 - y1) / (r1 - r0)
            break
    origin_x, origin_y = x0 - (c0 + 0.5) * size, y0 + (r0 + 0.5) * size

    def field(lon: float, lat: float) -> FieldSample | None:
        x, y = _mercator(lon, lat)
        return table.get((math.floor((origin_y - y) / size), math.floor((x - origin_x) / size)))

    return field


def antenna_bbox(change: Mapping[str, Any]) -> BBox:
    """Window around the changed site(s): the scenario radius plus one grid cell."""
    radius = float(config.value(config.load("scenarios.yaml")["antenna"], "radius_m")) + 150.0
    sites = [change["site"]] + ([change["from"]] if change.get("from") else [])
    lons, lats = [float(s["lon"]) for s in sites], [float(s["lat"]) for s in sites]
    dlat = math.degrees(radius / 6_371_008.8)
    dlon = dlat / math.cos(math.radians(sum(lats) / len(lats)))
    return (min(lons) - dlon, min(lats) - dlat, max(lons) + dlon, max(lats) + dlat)


def live_data(kind: str, area: AreaArg, change: Mapping[str, Any], provider: _Fetcher | None = None,
              **overrides: Any) -> ScenarioData:
    """ScenarioData with the real Cartoradio baseline for the window this run needs."""
    if kind not in ("antenna", "population_exposure"):
        return ScenarioData(**overrides)
    if provider is None:
        from twin.providers.restricted.cartoradio import CartoradioGridProvider
        provider = CartoradioGridProvider()
    if kind == "antenna":
        bbox = antenna_bbox(change)
    else:
        bbox = resolve_area(area, lookup=overrides.get("area_lookup") or layers.default_area_lookup).bbox
    now = datetime.now(timezone.utc)
    settings = config.load("provider_settings.yaml").get("restricted", {}).get("cartoradio_grid", {})
    source = {"id": "cartoradio_grid", "url": str(settings.get("url", "")),
              "retrieved_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "credit": str(settings.get("credit", "Fonte: Cartoradio - MIMIT/FUB")),
              "data_date": str(settings.get("data_date", "")),
              "note": "Official estimate, not a measurement; values at 15 V/m mean '15 or more'."}
    field = grid_field(provider.fetch(bbox, now, now))
    snapshots = {"emf_baseline": f"cartoradio_grid@{source['data_date']}", **overrides.pop("snapshots", {})}
    return ScenarioData(baseline_field=field, baseline_kind="estimated", baseline_source=source,
                        snapshots=snapshots, **overrides)
