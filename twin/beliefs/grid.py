"""The belief grid: H3 hexagons (resolution from config/areas.yaml).

Thin typed wrappers around the ``h3`` library, so the rest of the code never
touches its untyped API. Coordinates are always (lon, lat) in this module,
matching GeoJSON and ``twin.providers.base.BBox``.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import h3  # type: ignore[import-untyped]

from twin.providers.base import BBox

KM_PER_DEG_LAT = 111.32
#: Reference latitude for the local flat projection (centre of Rome).
REF_LAT = 41.9


def cell_of(lon: float, lat: float, resolution: int) -> str:
    return str(h3.latlng_to_cell(lat, lon, resolution))


def cell_center(cell: str) -> tuple[float, float]:
    lat, lon = h3.cell_to_latlng(cell)
    return float(lon), float(lat)


def cell_boundary(cell: str) -> list[tuple[float, float]]:
    """Closed ring of (lon, lat) vertices, ready for a GeoJSON polygon."""
    ring = [(float(lon), float(lat)) for lat, lon in h3.cell_to_boundary(cell)]
    ring.append(ring[0])
    return ring


def cells_in_polygon(geojson: Mapping[str, Any], resolution: int) -> list[str]:
    """Sorted cells whose centre lies inside a GeoJSON Polygon or MultiPolygon."""
    return sorted(str(c) for c in h3.geo_to_cells(dict(geojson), resolution))


def cells_in_bbox(bbox: BBox, resolution: int) -> list[str]:
    min_lon, min_lat, max_lon, max_lat = bbox
    ring = [[min_lon, min_lat], [max_lon, min_lat], [max_lon, max_lat], [min_lon, max_lat], [min_lon, min_lat]]
    return cells_in_polygon({"type": "Polygon", "coordinates": [ring]}, resolution)


def bbox_of_cells(cells: Sequence[str]) -> BBox:
    pts = [p for c in cells for p in cell_boundary(c)]
    lons = [p[0] for p in pts]
    lats = [p[1] for p in pts]
    return (min(lons), min(lats), max(lons), max(lats))


def local_xy_km(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    """Flat (x, y) in km around Rome. Error well under 1% over the city extent."""
    k = KM_PER_DEG_LAT * math.cos(math.radians(REF_LAT))
    return [(lon * k, lat * KM_PER_DEG_LAT) for lon, lat in points]
