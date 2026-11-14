"""Maintenance mission planner: send road and sewer crews to the problems citizens reported.

Deterministic. Steps:
1. Keep the events a crew should visit: potholes, sewer/flood problems and unannounced worksites whose
   confidence is at least ``min_confidence`` (or that an officer confirmed). Priority = severity x confidence.
2. Crews start and end at a depot. Depots get crews in order of how many problems are nearest to them.
3. Most urgent first: each problem is inserted in the crew route and position that add the least time,
   as long as the crew still gets back within its shift. What does not fit is left for the next shift.
4. Each route is then shortened with 2-opt (same stops, shorter order).
5. The plan is compared with one crew trip per citizen report from the nearest depot (no merging, no routing).

Distances are straight-line times a detour factor (no road graph yet): an estimate, labelled as such.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from twin.tools.signals import distance_m

Point = tuple[float, float]


def _km(a: Point, b: Point, detour: float) -> float:
    return distance_m(a[0], a[1], b[0], b[1]) / 1000.0 * detour


class _Model:
    def __init__(self, cfg: Mapping[str, Any], shift_hours: float | None) -> None:
        m = cfg["maintenance"]
        self.kinds: dict[str, dict[str, Any]] = {k: dict(v) for k, v in m["kinds"].items()}
        self.detour = float(m["detour_factor"])
        self.speed = float(m["speed_kmh"])
        self.shift_min = 60.0 * float(shift_hours if shift_hours is not None else m["shift_hours"])
        self.rate_h = float(m["cost_per_crew_hour_eur"])
        self.rate_km = float(m["cost_per_km_eur"])
        self.min_conf = float(m["min_confidence"])
        self.depots = [dict(d) for d in m["depots"]]

    def km(self, a: Point, b: Point) -> float:
        return _km(a, b, self.detour)

    def minutes(self, a: Point, b: Point) -> float:
        return self.km(a, b) / self.speed * 60.0

    def cost(self, minutes: float, km: float) -> float:
        return minutes / 60.0 * self.rate_h + km * self.rate_km


def _route_stats(model: _Model, depot: Point, stops: Sequence[Mapping[str, Any]]) -> tuple[float, float]:
    """Total minutes (driving + service) and km for depot -> stops -> depot."""
    km = 0.0
    service = 0.0
    here = depot
    for s in stops:
        km += model.km(here, (s["lon"], s["lat"]))
        service += float(s["service_min"])
        here = (s["lon"], s["lat"])
    km += model.km(here, depot)
    return km / model.speed * 60.0 + service, km


def _two_opt(model: _Model, depot: Point, stops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best = stops
    best_km = _route_stats(model, depot, best)[1]
    improved = True
    while improved:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                cand = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                km = _route_stats(model, depot, cand)[1]
                if km < best_km - 1e-9:
                    best, best_km, improved = cand, km, True
    return best


def plan_maintenance(events: Iterable[Mapping[str, Any]], cfg: Mapping[str, Any], crews: Mapping[str, int],
                     shift_hours: float | None = None) -> dict[str, Any]:
    model = _Model(cfg, shift_hours)
    items: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for e in sorted(events, key=lambda x: str(x.get("id"))):
        kind = str(e.get("category"))
        spec = model.kinds.get(kind)
        conf = e.get("confidence")
        confirmed = bool(e.get("confirmed"))
        if spec is None or not e.get("scored", True):
            skipped.append({"id": e.get("id"), "reason": "not a crew job"})
            continue
        if not confirmed and (conf is None or float(conf) < model.min_conf):
            skipped.append({"id": e.get("id"), "reason": f"confidence below {model.min_conf:.0%} and not confirmed"})
            continue
        weight = 1.0 if confirmed or conf is None else float(conf)
        items.append({"id": str(e["id"]), "kind": kind, "label": e.get("category_label", kind),
                      "lon": float(e["lon"]), "lat": float(e["lat"]), "crew_type": str(spec["crew"]),
                      "service_min": float(spec["service_min"]),
                      "priority": round(float(spec["severity"]) * weight, 4),
                      "n_reports": max(1, int(e.get("n_reports") or 1))})

    routes: list[dict[str, Any]] = []
    unserved: list[dict[str, Any]] = []
    depot_pts: dict[str, Point] = {str(d["id"]): (float(d["lon"]), float(d["lat"])) for d in model.depots}

    def nearest_depot(p: Point) -> str:
        return str(min(depot_pts, key=lambda d: (model.km(depot_pts[d], p), d)))

    raw_min = 0.0
    for crew_type in sorted({i["crew_type"] for i in items} | set(crews)):
        jobs = [i for i in items if i["crew_type"] == crew_type]
        n = max(0, int(crews.get(crew_type, 0)))
        if not jobs:
            continue
        if n == 0:
            unserved += [{"id": j["id"], "reason": "no crew of this type"} for j in jobs]
            continue
        # Depots ordered by how many problems are nearest to them; crews go round-robin over that order.
        load: dict[str, int] = {d: 0 for d in depot_pts}
        for j in jobs:
            load[nearest_depot((j["lon"], j["lat"]))] += 1
        order = sorted(depot_pts, key=lambda d: (-load[d], d))
        order = [d for d in order if load[d] > 0] or order
        crew_routes: list[dict[str, Any]] = [{"crew": f"{crew_type}-{k + 1}", "crew_type": crew_type, "depot": order[k % len(order)],
                        "stops": []} for k in range(n)]
        for job in sorted(jobs, key=lambda j: (-j["priority"], j["id"])):
            best: tuple[float, int, int] | None = None
            for ci, route in enumerate(crew_routes):
                depot = depot_pts[route["depot"]]
                stops: list[dict[str, Any]] = route["stops"]
                before = _route_stats(model, depot, stops)[0] if stops else 0.0
                for pos in range(len(stops) + 1):
                    cand = stops[:pos] + [job] + stops[pos:]
                    after = _route_stats(model, depot, cand)[0]
                    if after > model.shift_min + 1e-9:
                        continue
                    key = (after - before, ci, pos)
                    if best is None or key < best:
                        best = key
            if best is None:
                unserved.append({"id": job["id"], "reason": "does not fit in this shift"})
            else:
                crew_routes[best[1]]["stops"].insert(best[2], job)
        for route in crew_routes:
            if not route["stops"]:
                continue
            depot = depot_pts[route["depot"]]
            stops = _two_opt(model, depot, list(route["stops"]))
            minutes, km = _route_stats(model, depot, stops)
            clock = 0.0
            here = depot
            out_stops = []
            for s in stops:
                clock += model.minutes(here, (s["lon"], s["lat"]))
                out_stops.append({"id": s["id"], "kind": s["kind"], "label": s["label"], "lon": s["lon"], "lat": s["lat"],
                                  "priority": s["priority"], "arrive_min": round(clock)})
                clock += s["service_min"]
                here = (s["lon"], s["lat"])
            raw_min += minutes
            routes.append({"crew": route["crew"], "crew_type": crew_type, "depot": route["depot"],
                           "depot_lon": depot[0], "depot_lat": depot[1], "stops": out_stops,
                           "km": round(km, 1), "hours": round(minutes / 60.0, 2),
                           "cost_eur": round(model.cost(minutes, km))})

    planned = [s for r in routes for s in r["stops"]]
    served_ids = {s["id"] for s in planned}
    base_min = base_km = 0.0
    for item in items:
        if item["id"] not in served_ids:
            continue
        p = (item["lon"], item["lat"])
        d = depot_pts[nearest_depot(p)]
        trips = item["n_reports"]  # without merging, every citizen report sends its own crew
        base_km += trips * 2 * model.km(d, p)
        base_min += trips * (2 * model.minutes(d, p) + item["service_min"])
    tot_min = raw_min
    tot_km = sum(r["km"] for r in routes)
    plan_cost = sum(r["cost_eur"] for r in routes)
    base_cost = model.cost(base_min, base_km)

    def pct(new: float, old: float) -> float:
        return max(0.0, round(100.0 * (old - new) / old, 1)) if old > 0 else 0.0

    return {
        "routes": routes,
        "unserved": sorted(unserved, key=lambda u: str(u["id"])),
        "skipped": skipped,
        "total": {"stops": len(planned), "km": round(tot_km, 1), "hours": round(tot_min / 60.0, 2), "cost_eur": plan_cost},
        "baseline": {"km": round(base_km, 1), "hours": round(base_min / 60.0, 2), "cost_eur": round(base_cost),
                     "what": "one crew trip per citizen report, from the nearest depot (no merging, no routing)"},
        "savings": {"km_pct": pct(tot_km, base_km), "hours_pct": pct(tot_min, base_min), "cost_pct": pct(plan_cost, base_cost)},
        "depots": [{"id": d["id"], "name": d.get("name", d["id"]), "lon": d["lon"], "lat": d["lat"]} for d in model.depots],
        "assumptions": {k: cfg["maintenance"][k] for k in ("speed_kmh", "detour_factor", "cost_per_crew_hour_eur",
                                                           "cost_per_km_eur", "basis", "depots_basis")}
                       | {"shift_hours": model.shift_min / 60.0},
    }


__all__ = ["plan_maintenance"]
