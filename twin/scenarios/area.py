"""The ``area`` argument shared by every tool: "city", "municipio:<1-15>", "zone:<CODE>" or a GeoJSON polygon.

Same shape as the hub-fixed ``twin.tools.area.resolve_area`` (WS4). Replace this
module with an import of that one once it lands on main.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping, Union

from twin.providers.base import BBox
from twin.scenarios import config
from twin.scenarios.geometry import area_km2, contains, polygons

AreaArg = Union[str, Mapping[str, Any]]
AreaKind = Literal["city", "municipio", "zone", "polygon"]
#: Turns a named unit ("municipio:1", "zone:6A") into its GeoJSON boundary.
AreaLookup = Callable[[str], Mapping[str, Any]]

_MUNICIPIO = re.compile(r"^municipio:(\d{1,2})$")
_ZONE = re.compile(r"^zone:([A-Za-z0-9]+)$")


class AreaTooLarge(ValueError):
    """A heavy simulation was asked for an area above ``heavy_tools_max_area_km2``."""


class AreaNotAvailable(LookupError):
    """A named area cannot be resolved because its boundary layer is not loaded."""


@dataclass(frozen=True)
class Area:
    id: str
    kind: AreaKind
    geometry: dict[str, Any]
    bbox: BBox
    area_km2: float

    def contains(self, lon: float, lat: float) -> bool:
        return contains(self.geometry, lon, lat)


def _bbox_polygon(bbox: list[float]) -> dict[str, Any]:
    w, s, e, n = (float(v) for v in bbox)
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


def _bbox(geometry: Mapping[str, Any]) -> BBox:
    pts = [p for rings in polygons(geometry) for ring in rings for p in ring]
    lons, lats = [float(p[0]) for p in pts], [float(p[1]) for p in pts]
    return (min(lons), min(lats), max(lons), max(lats))


def polygon_area_km2(geometry: Mapping[str, Any]) -> float:
    return area_km2(geometry)


def _canonical_name(area: str) -> tuple[str, AreaKind]:
    if area == "city":
        return "city", "city"
    m = _MUNICIPIO.match(area)
    if m:
        number = int(m.group(1))
        if not 1 <= number <= 15:
            raise ValueError(f"Roma Capitale has municipi 1 to 15, not {number}")
        return f"municipio:{number}", "municipio"
    z = _ZONE.match(area)
    if z:
        return f"zone:{z.group(1).upper()}", "zone"
    raise ValueError(f"Unknown area {area!r}: use 'city', 'municipio:<1-15>', 'zone:<CODE>' or a GeoJSON polygon")


def resolve_area(area: AreaArg, *, lookup: AreaLookup | None = None) -> Area:
    """Resolve the shared ``area`` argument. Invalid input raises ValueError."""
    if isinstance(area, str):
        area_id, kind = _canonical_name(area)
        if kind == "city":
            geometry: dict[str, Any] = _bbox_polygon(config.load("areas.yaml")["city"]["bbox"])
        else:
            if lookup is None:
                raise AreaNotAvailable(f"Area '{area_id}' needs its boundary layer, which is not loaded yet")
            geometry = dict(lookup(area_id))
    elif isinstance(area, Mapping):
        geometry = dict(area["geometry"] if area.get("type") == "Feature" else area)
        digest = hashlib.sha256(json.dumps(geometry, sort_keys=True).encode()).hexdigest()[:12]
        area_id, kind = f"polygon:{digest}", "polygon"
    else:
        raise ValueError("area must be a string id or a GeoJSON polygon")
    try:
        km2 = area_km2(geometry)
        bbox = _bbox(geometry)
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Invalid GeoJSON geometry for area {area_id!r}") from exc
    return Area(id=area_id, kind=kind, geometry=geometry, bbox=bbox, area_km2=km2)


def check_heavy(area: Area) -> None:
    """Heavy simulations refuse areas above ``heavy_tools_max_area_km2``."""
    limit = float(config.load("areas.yaml")["heavy_tools_max_area_km2"])
    if area.area_km2 > limit:
        raise AreaTooLarge(
            f"This simulation runs on at most {limit:g} km2; area '{area.id}' is {area.area_km2:.1f} km2. "
            "Pick a municipio, an urban zone or draw a smaller polygon.")
