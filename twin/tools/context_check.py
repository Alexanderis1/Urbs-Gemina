"""Deterministic context check: what lies within a radius of a point.

The language model never computes distances. It calls this tool and reports
its output. Distance is information for the officer, not a prohibition.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

EARTH_RADIUS_M = 6_371_008.8
Geometry = Mapping[str, Any]
FeatureCollection = Mapping[str, Any]
XY = tuple[float, float]


def _to_xy(lon: float, lat: float, lon0: float, lat0: float) -> XY:
    """Metres east/north of (lon0, lat0). Accurate to well under 1 m at city-block scale."""
    x = math.radians(lon - lon0) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * EARTH_RADIUS_M
    return x, y


def _segment_distance(a: XY, b: XY) -> float:
    """Distance from the origin to segment a-b."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0.0:
        return math.hypot(ax, ay)
    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / length_sq))
    return math.hypot(ax + t * dx, ay + t * dy)


def _line_distance(points: Sequence[XY]) -> float:
    if len(points) == 1:
        return math.hypot(*points[0])
    return min(_segment_distance(points[i], points[i + 1]) for i in range(len(points) - 1))


def _ring_contains_origin(ring: Sequence[XY]) -> bool:
    inside = False
    for i in range(len(ring)):
        (x1, y1), (x2, y2) = ring[i], ring[(i + 1) % len(ring)]
        if (y1 > 0.0) != (y2 > 0.0) and 0.0 < x1 + (0.0 - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _polygon_distance(rings: Sequence[Sequence[XY]]) -> float:
    outer, holes = rings[0], rings[1:]
    if _ring_contains_origin(outer) and not any(_ring_contains_origin(hole) for hole in holes):
        return 0.0
    return min(_line_distance(ring) for ring in rings)


def distance_to_geometry_m(lon: float, lat: float, geometry: Geometry) -> float:
    """Shortest distance in metres from a point to a GeoJSON geometry (0 inside a polygon)."""

    def xy(position: Sequence[float]) -> XY:
        return _to_xy(position[0], position[1], lon, lat)

    kind = geometry["type"]
    coords = geometry["coordinates"]
    if kind == "Point":
        return math.hypot(*xy(coords))
    if kind == "MultiPoint":
        return min(math.hypot(*xy(p)) for p in coords)
    if kind == "LineString":
        return _line_distance([xy(p) for p in coords])
    if kind == "MultiLineString":
        return min(_line_distance([xy(p) for p in line]) for line in coords)
    if kind == "Polygon":
        return _polygon_distance([[xy(p) for p in ring] for ring in coords])
    if kind == "MultiPolygon":
        return min(_polygon_distance([[xy(p) for p in ring] for ring in poly]) for poly in coords)
    raise ValueError(f"Unsupported geometry type: {kind}")


def context_check(lon: float, lat: float, layers: Mapping[str, FeatureCollection | None],
                  radius_m: float = 300.0) -> dict[str, Any]:
    """List features of each layer within ``radius_m`` of the point.

    A layer given as ``None`` is reported as "not_available" instead of being
    silently treated as empty.
    """
    result: dict[str, Any] = {"point": {"lon": lon, "lat": lat}, "radius_m": radius_m, "layers": {}}
    for name, collection in layers.items():
        if collection is None:
            result["layers"][name] = {"status": "not_available", "hits": []}
            continue
        found: list[tuple[float, dict[str, Any]]] = []
        for feature in collection.get("features", []):
            geometry = feature.get("geometry")
            if not geometry:
                continue
            distance = distance_to_geometry_m(lon, lat, geometry)
            if distance <= radius_m:
                found.append((distance, feature.get("properties") or {}))
        found.sort(key=lambda item: item[0])
        hits = [{"distance_m": round(distance, 1), "properties": properties} for distance, properties in found]
        result["layers"][name] = {"status": "ok", "count": len(hits), "hits": hits}
    return result
