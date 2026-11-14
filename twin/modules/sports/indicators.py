"""Twin-derived indicators for each facility: transit access and residents in reach."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from twin.modules.sports.config import SportsConfig
from twin.modules.sports.deserts import PopulationPoint, reach_radius_m
from twin.modules.sports.geo import GridIndex
from twin.modules.sports.model import Facility


@dataclass(frozen=True)
class TransitStop:
    """A GTFS stop with the routes that serve it (from stop_times + trips)."""
    stop_id: str
    lon: float
    lat: float
    routes: frozenset[str]


def _stop_index(stops: Sequence[TransitStop], cell_m: float) -> GridIndex[TransitStop]:
    index: GridIndex[TransitStop] = GridIndex(cell_m)
    index.extend((s.lon, s.lat, s) for s in stops)
    return index


def _pop_index(points: Sequence[PopulationPoint], cell_m: float) -> GridIndex[PopulationPoint]:
    index: GridIndex[PopulationPoint] = GridIndex(cell_m)
    index.extend((p.lon, p.lat, p) for p in points)
    return index


def transit_access(lon: float, lat: float, stops: Sequence[TransitStop] | GridIndex[TransitStop],
                   radius_m: float) -> dict[str, Any]:
    index = stops if isinstance(stops, GridIndex) else _stop_index(stops, radius_m)
    hits = sorted(index.near(lon, lat, radius_m), key=lambda h: (h[0], h[1].stop_id))
    routes = sorted({r for _, s in hits for r in s.routes})
    return {"radius_m": radius_m, "stops_within": len(hits), "routes_within": routes,
            "nearest_stop_m": round(hits[0][0], 1) if hits else None}


def residents_within(lon: float, lat: float, points: Sequence[PopulationPoint] | GridIndex[PopulationPoint],
                     radius_m: float) -> dict[str, float]:
    index = points if isinstance(points, GridIndex) else _pop_index(points, radius_m)
    residents = children = 0.0
    for _, p in index.near(lon, lat, radius_m):
        residents += p.residents
        children += p.children
    return {"residents": round(residents, 1), "children": round(children, 1)}


def facility_indicators(facilities: Sequence[Facility], stops: Sequence[TransitStop],
                        points: Sequence[PopulationPoint], config: SportsConfig) -> dict[str, dict[str, Any]]:
    """Per facility id. Facilities without coordinates get ``None`` indicators."""
    stop_r = config.transit_stop_radius_m
    reach = reach_radius_m(config)
    stop_idx = _stop_index(stops, stop_r)
    pop_idx = _pop_index(points, reach)
    out: dict[str, dict[str, Any]] = {}
    for f in facilities:
        if f.lon is None or f.lat is None:
            out[f.facility_id] = {"transit": None, "within_reach": None}
            continue
        out[f.facility_id] = {
            "transit": transit_access(f.lon, f.lat, stop_idx, stop_r),
            "within_reach": {"reach_m": round(reach, 1), **residents_within(f.lon, f.lat, pop_idx, reach)},
        }
    return out
