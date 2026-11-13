"""Small geometry helpers for providers (WGS84, distances in metres)."""
from __future__ import annotations

import math

from twin.providers.base import BBox

EARTH_RADIUS_M = 6_371_008.8


def distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in metres (haversine)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def offset(lon: float, lat: float, east_m: float, north_m: float) -> tuple[float, float]:
    """Point moved by the given metres east and north (local flat-earth approximation)."""
    dlat = math.degrees(north_m / EARTH_RADIUS_M)
    dlon = math.degrees(east_m / (EARTH_RADIUS_M * math.cos(math.radians(lat))))
    return lon + dlon, lat + dlat


def in_bbox(lon: float, lat: float, bbox: BBox) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat
