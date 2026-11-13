"""Tool entry points of the sports module. Each returns the shared response envelope.

The tool API stream wires these to ``POST /tools/<name>``; agents call them and
report the run id, never their own numbers.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from twin.modules.sports.config import SportsConfig
from twin.modules.sports.deserts import PopulationPoint, coverage, reach_radius_m, what_if_open
from twin.modules.sports.envelope import make_envelope
from twin.modules.sports.model import Facility
from twin.modules.sports.sources import municipio_id
from twin.tools.context_check import distance_to_geometry_m

Area = str | Mapping[str, Any]

def parse_area(area: Area) -> tuple[str, Any]:
    """Shared area ids (hub contract): "city", "municipio:<1-15>", "zone:<CODE>", or a GeoJSON polygon.

    Local parser until WS4 publishes twin/tools/area.py; then this delegates to it.
    """
    if isinstance(area, Mapping):
        if area.get("type") not in ("Polygon", "MultiPolygon"):
            raise ValueError("area polygon must be a GeoJSON Polygon or MultiPolygon")
        return "polygon", area
    if area == "city":
        return "city", None
    kind, _, value = area.partition(":")
    if kind == "municipio" and value.isdigit() and 1 <= int(value) <= 15:
        return "municipio", municipio_id(value)
    if kind == "zone" and value and value == value.upper():
        return "zone", value
    raise ValueError(f"unknown area {area!r}: use 'city', 'municipio:<1-15>', 'zone:<CODE>' or a GeoJSON polygon")


def _in_area(lon: float | None, lat: float | None, municipio: str | None, zone: str | None,
             parsed: tuple[str, Any]) -> bool:
    kind, value = parsed
    if kind == "polygon":
        return lon is not None and lat is not None and distance_to_geometry_m(lon, lat, value) == 0.0
    if kind == "city":
        return True
    if kind == "municipio":
        return bool(municipio == value)
    return bool(zone == value)


def _area_input(area: Area) -> Any:
    return dict(area) if isinstance(area, Mapping) else area


def _check_discipline(discipline: str | None, config: SportsConfig) -> None:
    if discipline is not None and discipline not in config.disciplines:
        raise ValueError(f"unknown discipline {discipline!r}; known: {sorted(config.disciplines)}")


def _sources_for(facilities: Sequence[Facility], retrieved: Mapping[str, str] | None) -> list[dict[str, Any]]:
    used = {m.split(":", 1)[0] for f in facilities for m in f.members}
    out: list[dict[str, Any]] = [{"id": s, "retrieved_at": (retrieved or {}).get(s, "unknown")} for s in sorted(used)]
    return out


def _kinds(facilities: Sequence[Facility]) -> dict[str, str]:
    kinds = {"facilities": "real"}
    if any(v.status == "web_unverified" for f in facilities for v in (*f.disciplines.values(), *f.fields.values())):
        kinds["web_fields"] = "estimated"
    if any(f.synthetic for f in facilities):
        kinds["what_if_facilities"] = "simulated"
    return kinds


def sports_facilities(area: Area, discipline: str | None, facilities: Sequence[Facility], config: SportsConfig,
                      include_unverified: bool = True, snapshot_hashes: Mapping[str, str] | None = None,
                      retrieved: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Merged facility map, filtered by area and discipline, as a GeoJSON FeatureCollection."""
    _check_discipline(discipline, config)
    parsed = parse_area(area)
    inputs = {"area": _area_input(area), "discipline": discipline, "include_unverified": include_unverified}
    if parsed[0] == "zone":
        return make_envelope("sports_facilities", inputs, None, {"facilities": "not_available"}, [], synthetic=False,
                             warnings=[], snapshot_hashes=snapshot_hashes, status="not_available",
                             reason="filtering facilities by urban zone needs the zone polygons; pass the polygon")
    selected = [
        f for f in facilities
        if _in_area(f.lon, f.lat, f.fields["municipio"].value, None, parsed)
        and (discipline is None or f.offers(discipline, include_unverified))
    ]
    warnings = []
    unlocated = sum(1 for f in selected if f.lon is None)
    if unlocated:
        warnings.append(f"{unlocated} facilities have no coordinates yet and are not drawn on the map")
    if any(f.fields["accessibility"].status == "not_known" for f in selected):
        warnings.append("accessibility is 'not known' unless a source states it")
    result = {"type": "FeatureCollection", "count": len(selected), "features": [f.to_feature() for f in selected]}
    return make_envelope("sports_facilities", inputs, result, _kinds(selected), _sources_for(selected, retrieved),
                         synthetic=any(f.synthetic for f in selected), warnings=warnings,
                         snapshot_hashes=snapshot_hashes)


def sport_deserts(area: Area, discipline: str, facilities: Sequence[Facility], population: Sequence[PopulationPoint],
                  config: SportsConfig, open_facilities: Sequence[Facility] = (), include_unverified: bool = True,
                  snapshot_hashes: Mapping[str, str] | None = None,
                  retrieved: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Coverage of ``discipline`` in ``area``; with ``open_facilities`` it is the what-if.

    Facilities outside the area still count: people cross borders to play.
    """
    _check_discipline(discipline, config)
    parsed = parse_area(area)
    points = [p for p in population if _in_area(p.lon, p.lat, p.municipio, p.zone, parsed)]
    radius = reach_radius_m(config)
    if open_facilities:
        result: dict[str, Any] = what_if_open(points, facilities, discipline, open_facilities, radius,
                                              include_unverified, config)
    else:
        result = coverage(points, facilities, discipline, radius, include_unverified, config)
    warnings = ["reach is a straight-line estimate of a "
                f"{config.reach.walk_minutes:g}-minute walk (detour factor {config.reach.detour_factor:g})"]
    if not population:
        return make_envelope("sport_deserts", {"area": _area_input(area), "discipline": discipline},
                             None, {"population": "not_available"}, [], synthetic=False, warnings=warnings,
                             snapshot_hashes=snapshot_hashes, status="not_available",
                             reason="census population points are not loaded")
    if not points:
        warnings.append("no population points in this area")
    kinds = {**_kinds(list(facilities) + list(open_facilities)), "population": "real", "reach": "estimated"}
    inputs = {"area": _area_input(area), "discipline": discipline, "include_unverified": include_unverified,
              "open_facilities": [f.to_feature() for f in open_facilities]}
    sources = _sources_for(facilities, retrieved) + [{"id": "istat_census_2021", "retrieved_at": "unknown"}]
    return make_envelope("sport_deserts", inputs, result, kinds, sources,
                         synthetic=bool(open_facilities), warnings=warnings, snapshot_hashes=snapshot_hashes)
