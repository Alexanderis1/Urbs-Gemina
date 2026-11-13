""""Sport deserts": residents with no facility for a discipline within reach.

Reach is a walking distance turned into a straight-line radius
(config/sports.yaml ``reach``), so results are *estimated*. Population points
are census-section centroids (ISTAT 2021) with residents and children.
The what-if adds facilities (e.g. a school gym opened to the community) and
reports how many more residents are covered.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from twin.modules.sports.config import SportsConfig
from twin.modules.sports.geo import GridIndex
from twin.modules.sports.model import NOT_KNOWN, STANDARD_FIELDS, Facility, FieldStatus, FieldValue, Provenance


@dataclass(frozen=True)
class PopulationPoint:
    point_id: str
    lon: float
    lat: float
    residents: float
    children: float
    #: Urban zone id (one of the 155 zone urbanistiche) used to group results.
    zone: str | None = None
    municipio: str | None = None


def reach_radius_m(config: SportsConfig) -> float:
    r = config.reach
    street_m = r.walk_minutes / 60.0 * r.walk_speed_kmh * 1000.0
    return street_m / r.detour_factor


def _offering(facilities: Iterable[Facility], discipline: str, include_unverified: bool) -> list[Facility]:
    return [f for f in facilities
            if f.lon is not None and f.lat is not None and f.offers(discipline, include_unverified)]


def coverage(points: Sequence[PopulationPoint], facilities: Sequence[Facility], discipline: str,
             radius_m: float, include_unverified: bool = True,
             config: SportsConfig | None = None) -> dict[str, Any]:
    """Who has a facility for ``discipline`` within ``radius_m``, overall and per zone."""
    min_share = config.desert_min_uncovered_share if config else 0.5
    min_res = config.desert_min_residents if config else 1000.0
    offering = _offering(facilities, discipline, include_unverified)
    index: GridIndex[Facility] = GridIndex(radius_m)
    for f in offering:
        assert f.lon is not None and f.lat is not None
        index.add(f.lon, f.lat, f)

    zones: dict[str, dict[str, float]] = {}
    uncovered_ids: list[str] = []
    totals = {"residents": 0.0, "children": 0.0, "res_unc": 0.0, "chi_unc": 0.0}
    for p in points:
        covered = next(iter(index.near(p.lon, p.lat, radius_m)), None) is not None
        z = zones.setdefault(p.zone or "unknown", {"residents": 0.0, "children": 0.0, "res_unc": 0.0, "chi_unc": 0.0})
        for bucket in (z, totals):
            bucket["residents"] += p.residents
            bucket["children"] += p.children
            if not covered:
                bucket["res_unc"] += p.residents
                bucket["chi_unc"] += p.children
        if not covered:
            uncovered_ids.append(p.point_id)

    zone_rows = []
    for zone, z in sorted(zones.items()):
        share = z["res_unc"] / z["residents"] if z["residents"] else 0.0
        zone_rows.append({
            "zone": zone, "residents": round(z["residents"], 1), "children": round(z["children"], 1),
            "residents_uncovered": round(z["res_unc"], 1), "children_uncovered": round(z["chi_unc"], 1),
            "uncovered_share": round(share, 4),
            "desert": share >= min_share and z["residents"] >= min_res,
        })
    return {
        "discipline": discipline,
        "reach_m": round(radius_m, 1),
        "facilities_offering": len(offering),
        "facilities_offering_unverified_only": sum(
            1 for f in offering if f.disciplines[discipline].status == "web_unverified"),
        "residents_total": round(totals["residents"], 1),
        "residents_uncovered": round(totals["res_unc"], 1),
        "children_total": round(totals["children"], 1),
        "children_uncovered": round(totals["chi_unc"], 1),
        "zones": zone_rows,
        "desert_zones": [r["zone"] for r in zone_rows if r["desert"]],
        "uncovered_points": uncovered_ids,
    }


def school_gym_facility(name: str, lon: float, lat: float, config: SportsConfig,
                        disciplines: Iterable[str] | None = None) -> Facility:
    """A simulated facility for the what-if "open this school gym to the community"."""
    ids = sorted(set(disciplines) if disciplines is not None else set(config.school_gym_default_disciplines))
    unknown = [d for d in ids if d not in config.disciplines]
    if unknown:
        raise ValueError(f"unknown disciplines: {unknown}")
    prov = (Provenance("what_if", name),)
    sim: FieldStatus = "simulated"
    fields: dict[str, FieldValue] = {k: NOT_KNOWN for k in STANDARD_FIELDS}
    fields["name"] = FieldValue(name, sim, prov)
    fields["kind"] = FieldValue("school_gym", sim, prov)
    key = f"{name}|{lon:.6f}|{lat:.6f}"
    return Facility(
        facility_id="sim_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12],
        lon=lon, lat=lat, fields=fields,
        disciplines={d: FieldValue(True, sim, prov) for d in ids},
        members=(f"what_if:{name}",), synthetic=True,
    )


def what_if_open(points: Sequence[PopulationPoint], facilities: Sequence[Facility], discipline: str,
                 new_facilities: Sequence[Facility], radius_m: float, include_unverified: bool = True,
                 config: SportsConfig | None = None) -> dict[str, Any]:
    base = coverage(points, facilities, discipline, radius_m, include_unverified, config)
    variant = coverage(points, list(facilities) + list(new_facilities), discipline, radius_m,
                       include_unverified, config)
    base_zone = {z["zone"]: z for z in base["zones"]}
    zone_delta = [
        {"zone": z["zone"],
         "residents_newly_covered": round(base_zone[z["zone"]]["residents_uncovered"] - z["residents_uncovered"], 1),
         "was_desert": base_zone[z["zone"]]["desert"], "is_desert": z["desert"]}
        for z in variant["zones"]
    ]
    return {
        "baseline": base,
        "variant": variant,
        "added": [f.facility_id for f in new_facilities],
        "delta": {
            "residents_newly_covered": round(base["residents_uncovered"] - variant["residents_uncovered"], 1),
            "children_newly_covered": round(base["children_uncovered"] - variant["children_uncovered"], 1),
            "zones": [z for z in zone_delta if z["residents_newly_covered"] or z["was_desert"] != z["is_desert"]],
        },
    }
