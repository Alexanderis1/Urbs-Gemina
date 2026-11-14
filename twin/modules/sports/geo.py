"""Small geometry helpers: distances in metres and a grid index for near-by search."""
from __future__ import annotations

import math
from typing import Generic, Iterable, Iterator, TypeVar

EARTH_RADIUS_M = 6_371_008.8
T = TypeVar("T")


def distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance (haversine) in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


class GridIndex(Generic[T]):
    """Buckets points in square cells so a radius query only checks nearby cells."""

    def __init__(self, cell_m: float, ref_lat: float = 41.9) -> None:
        if cell_m <= 0:
            raise ValueError("cell_m must be positive")
        self._dlat = cell_m / 111_195.0
        self._dlon = self._dlat / math.cos(math.radians(ref_lat))
        self._cells: dict[tuple[int, int], list[tuple[float, float, T]]] = {}
        self._cell_m = cell_m

    def _cell(self, lon: float, lat: float) -> tuple[int, int]:
        return math.floor(lon / self._dlon), math.floor(lat / self._dlat)

    def add(self, lon: float, lat: float, item: T) -> None:
        self._cells.setdefault(self._cell(lon, lat), []).append((lon, lat, item))

    def extend(self, items: Iterable[tuple[float, float, T]]) -> None:
        for lon, lat, item in items:
            self.add(lon, lat, item)

    def near(self, lon: float, lat: float, radius_m: float) -> Iterator[tuple[float, T]]:
        """Yield (distance_m, item) for every item within ``radius_m``."""
        span = max(1, math.ceil(radius_m / self._cell_m) + 1)
        cx, cy = self._cell(lon, lat)
        for ix in range(cx - span, cx + span + 1):
            for iy in range(cy - span, cy + span + 1):
                for plon, plat, item in self._cells.get((ix, iy), ()):
                    d = distance_m(lon, lat, plon, plat)
                    if d <= radius_m:
                        yield d, item
