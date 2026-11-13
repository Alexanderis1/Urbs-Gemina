"""Small planar geometry helpers in a local metric frame (good to well under 1 m at city scale)."""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

EARTH_RADIUS_M = 6_371_008.8
Geometry = Mapping[str, Any]
Ring = Sequence[Sequence[float]]


def to_xy(lon: float, lat: float, lon0: float, lat0: float) -> tuple[float, float]:
    """Metres east/north of (lon0, lat0)."""
    x = math.radians(lon - lon0) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * EARTH_RADIUS_M
    return x, y


def from_xy(x: float, y: float, lon0: float, lat0: float) -> tuple[float, float]:
    lon = lon0 + math.degrees(x / (EARTH_RADIUS_M * math.cos(math.radians(lat0))))
    lat = lat0 + math.degrees(y / EARTH_RADIUS_M)
    return lon, lat


def polygons(geometry: Geometry) -> list[Sequence[Ring]]:
    """Polygon or MultiPolygon as a list of polygons (each a list of rings)."""
    kind = geometry.get("type")
    if kind == "Polygon":
        return [geometry["coordinates"]]
    if kind == "MultiPolygon":
        return list(geometry["coordinates"])
    raise ValueError(f"An area must be a Polygon or MultiPolygon, got {kind!r}")


def _ring_area_m2(ring: Ring, lon0: float, lat0: float) -> float:
    pts = [to_xy(p[0], p[1], lon0, lat0) for p in ring]
    return 0.5 * abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                         for i in range(len(pts))))


def area_km2(geometry: Geometry) -> float:
    polys = polygons(geometry)
    first = polys[0][0][0]
    lon0, lat0 = float(first[0]), float(first[1])
    total = 0.0
    for rings in polys:
        total += _ring_area_m2(rings[0], lon0, lat0) - sum(_ring_area_m2(h, lon0, lat0) for h in rings[1:])
    return total / 1e6


def _in_ring(lon: float, lat: float, ring: Ring) -> bool:
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def contains(geometry: Geometry, lon: float, lat: float) -> bool:
    for rings in polygons(geometry):
        if _in_ring(lon, lat, rings[0]) and not any(_in_ring(lon, lat, hole) for hole in rings[1:]):
            return True
    return False


def centroid(geometry: Geometry) -> tuple[float, float]:
    """Mean of the outer-ring vertices of the largest polygon (enough for small census sections)."""
    rings = max(polygons(geometry), key=lambda r: len(r[0]))
    outer = list(rings[0])
    if len(outer) > 1 and list(outer[0]) == list(outer[-1]):
        outer = outer[:-1]
    return (sum(p[0] for p in outer) / len(outer), sum(p[1] for p in outer) / len(outer))
