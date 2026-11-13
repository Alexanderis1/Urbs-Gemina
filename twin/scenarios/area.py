"""The ``area`` argument shared by every tool: "city", a named unit, or a GeoJSON polygon."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Union

from twin.scenarios import config
from twin.scenarios.geometry import area_km2, contains

AreaArg = Union[str, Mapping[str, Any]]
#: Turns a named unit ("municipio:1", "zone:6a") into its GeoJSON boundary.
AreaLookup = Callable[[str], Mapping[str, Any]]


class AreaTooLarge(ValueError):
    """A heavy simulation was asked for an area above ``heavy_tools_max_area_km2``."""


class AreaNotAvailable(LookupError):
    """A named area cannot be resolved because its boundary layer is not loaded."""


@dataclass(frozen=True)
class Area:
    id: str
    geometry: Mapping[str, Any]
    area_km2: float

    def contains(self, lon: float, lat: float) -> bool:
        return contains(self.geometry, lon, lat)


def _bbox_polygon(bbox: list[float]) -> dict[str, Any]:
    w, s, e, n = (float(v) for v in bbox)
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


def polygon_area_km2(geometry: Mapping[str, Any]) -> float:
    return area_km2(geometry)


def resolve_area(area: AreaArg, heavy: bool = False, lookup: AreaLookup | None = None) -> Area:
    areas = config.load("areas.yaml")
    if isinstance(area, str):
        if area == "city":
            geometry: Mapping[str, Any] = _bbox_polygon(areas["city"]["bbox"])
            area_id = "city"
        else:
            if lookup is None:
                raise AreaNotAvailable(f"Area '{area}' needs its boundary layer, which is not loaded yet")
            geometry, area_id = lookup(area), area
    else:
        geometry = area["geometry"] if area.get("type") == "Feature" else area
        digest = hashlib.sha256(json.dumps(geometry, sort_keys=True).encode()).hexdigest()[:12]
        area_id = f"polygon:{digest}"
    result = Area(id=area_id, geometry=geometry, area_km2=area_km2(geometry))
    limit = float(areas["heavy_tools_max_area_km2"])
    if heavy and result.area_km2 > limit:
        raise AreaTooLarge(
            f"This simulation runs on at most {limit:g} km2; area '{area_id}' is {result.area_km2:.1f} km2. "
            "Pick a municipio, an urban zone or draw a smaller polygon.")
    return result
