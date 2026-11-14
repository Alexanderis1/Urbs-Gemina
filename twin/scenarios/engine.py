"""``run(kind, area, change) -> envelope``: the single entry point behind ``run_scenario``."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from twin.scenarios import cache, config, layers, remote
from twin.scenarios.antenna import run_antenna
from twin.scenarios.area import Area, AreaArg, AreaNotAvailable, AreaTooLarge, check_heavy, resolve_area
from twin.scenarios.data import ScenarioData
from twin.scenarios.envelope import envelope, run_id
from twin.scenarios.exposure import run_population_exposure
from twin.scenarios.flood import run_rain_flood, run_river_flood
from twin.scenarios.heat import run_heatwave
from twin.scenarios.access import run_emergency_access
from twin.scenarios.plume import run_chemical_plume
from twin.scenarios.traffic import run_road_closure, run_traffic_event

TOOL = "run_scenario"
Runner = Callable[[Area, Mapping[str, Any], ScenarioData], dict[str, Any]]


@dataclass(frozen=True)
class Kind:
    runner: Runner
    heavy: bool
    description: str
    #: WS1 layer files the kind reads; their hashes enter the run id.
    reads: tuple[str, ...] = ()
    #: Run in the scenario worker (Modal) when URBS_SCENARIO_WORKER=modal.
    isolate: bool = False


KINDS: dict[str, Kind] = {
    "antenna": Kind(run_antenna, False,
                    "Add or move an antenna: field P5/P50/P95 and exceedance probability, baseline vs variant"),
    "population_exposure": Kind(run_population_exposure, False,
                                "Residents in census sections above the EMF thresholds, baseline vs variant",
                                ("census_sections.geojson",)),
    "river_flood": Kind(run_river_flood, False,
                        "Tiber / Aniene rises by X m, or the T-year flood (return_period_years): flooded area, residents and sensitive sites (P5/P50/P95), "
                        "beside the official PGRA hazard areas",
                        ("dtm_glo30_ground.tif", "rivers_osm.geojson", "flood_hazard_pgra.geojson",
                         "census_sections.geojson", "sensitive_sites.geojson"), True),
    "rain_flood": Kind(run_rain_flood, False,
                       "Heavy rain: where water collects (hotspots with P5/P50/P95 depth), residents and sensitive "
                       "sites affected",
                       ("dtm_glo30_ground.tif", "imperviousness_2018.tif", "ptpr_b_aree_urbanizzate.geojson",
                        "road_underpasses_osm.geojson", "census_sections.geojson", "sensitive_sites.geojson"), True),
    "chemical_plume": Kind(run_chemical_plume, False,
                           "Toxic release at a high-risk (Seveso) plant: where each health threshold is likely or "
                           "possibly exceeded, residents and sensitive sites, beside the official damage zones",
                           ("seveso_perimeters.geojson", "hazardous_sites.geojson", "seveso_damage_zones.geojson",
                            "census_sections.geojson", "sensitive_sites.geojson")),
    "heatwave": Kind(run_heatwave, False,
                     "Day and night temperatures street by street from the forecast, sealed ground and tree cover; "
                     "residents, children and over-65s above heat thresholds; what-if: plant trees or remove paving",
                     ("imperviousness_2018.tif", "tree_cover_2018.tif", "census_ages.csv", "census_sections.geojson")),
    "emergency_access": Kind(run_emergency_access, True,
                             "Residents that fire, police or ambulances reach within their target time, before and "
                             "after road closures, a closed area or a flood footprint",
                             ("police_fire.geojson", "emergency_hospitals.geojson", "census_sections.geojson"), True),
    "traffic_event": Kind(run_traffic_event, True,
                          "Roadworks, closures and big events on one district: SUMO travel time, delay and congestion "
                          "points, baseline vs variant (synthetic demand anchored to loop counts)", (), True),
    "road_closure": Kind(run_road_closure, True,
                         "Close roads on one district: SUMO travel time and delay, baseline vs variant (synthetic demand)",
                         (), True),
}


def kinds() -> dict[str, str]:
    return {name: k.description for name, k in KINDS.items()}


def default_cache_dir() -> Path:
    return config.ROOT / str(config.load("scenarios.yaml")["cache"]["dir"])


#: kinds that share another kind's config section
AREA_SECTION = {"traffic_event": "road_closure"}


def _area_limit(kind: str) -> float | None:
    """Per-kind area limit (``max_area_km2`` in config/scenarios.yaml), when tighter than the heavy-tool one."""
    section = config.load("scenarios.yaml").get(AREA_SECTION.get(kind, kind)) or {}
    return float(config.value(section, "max_area_km2")) if "max_area_km2" in section else None


def run(kind: str, area: AreaArg, change: Mapping[str, Any], data: ScenarioData | None = None,
        cache_dir: Path | None = None, use_cache: bool = True, isolate: bool = True) -> dict[str, Any]:
    if kind not in KINDS:
        raise KeyError(f"Unknown scenario kind '{kind}'. Known: {', '.join(sorted(KINDS))}")
    data = data or ScenarioData()
    spec = KINDS[kind]
    inputs = {"kind": kind, "area": area, "change": dict(change)}
    snapshots = {**config.config_hashes(), **data.fingerprint()}
    if isinstance(area, str) and area != "city" and data.area_lookup is None:
        boundary = "municipi.geojson" if area.startswith("municipio:") else "urban_zones.geojson"
        snapshots.update(layers.snapshots([boundary]))
    if data.census is None:
        snapshots.update(layers.snapshots(list(spec.reads)))
    rid = run_id(TOOL, inputs, snapshots)
    directory = cache_dir if cache_dir is not None else default_cache_dir()
    if use_cache:
        hit = cache.get(directory, rid)
        if hit is not None:
            return {**hit, "cached": True}

    if spec.heavy:  # refuse oversize areas here, before a worker is woken up for nothing
        try:
            check_heavy(resolve_area(area, lookup=data.area_lookup or layers.default_area_lookup), _area_limit(kind))
        except AreaTooLarge as exc:
            return _not_ok(inputs, snapshots, "refused", str(exc))
        except AreaNotAvailable:
            pass  # the worker may have the boundary layer; it answers for itself

    if isolate and spec.isolate and remote.enabled():
        try:
            out = remote.call(kind, area, change, data)
        except Exception as exc:  # noqa: BLE001 - worker down or not deployed: say so, never hang the API
            return _not_ok(inputs, snapshots, "not_available", f"Scenario worker unavailable: {exc}")
        if use_cache and out.get("status") == "ok":
            cache.put(directory, rid, out)
        return out
    try:
        resolved = resolve_area(area, lookup=data.area_lookup or layers.default_area_lookup)
        if spec.heavy:
            check_heavy(resolved, _area_limit(kind))
    except AreaTooLarge as exc:
        return _not_ok(inputs, snapshots, "refused", str(exc))
    except AreaNotAvailable as exc:
        return _not_ok(inputs, snapshots, "not_available", str(exc))
    part = spec.runner(resolved, change, data)
    result = dict(part["result"])
    status = str(result.pop("status", "ok"))
    reason = result.pop("reason", None)
    out = envelope(TOOL, inputs, snapshots, {**result, "area": {"id": resolved.id,
                                                                "area_km2": round(resolved.area_km2, 3)}},
                   part["data_kinds"], part["sources"], bool(part["synthetic"]), part["warnings"])
    out = {"status": status, **({"reason": reason} if reason else {}), **out}
    if use_cache and status == "ok":
        cache.put(directory, rid, out)
    return {**out, "cached": False}


def _not_ok(inputs: Mapping[str, Any], snapshots: Mapping[str, str], status: str, reason: str) -> dict[str, Any]:
    """Envelope for a run that did not happen: never cached."""
    out = envelope(TOOL, inputs, snapshots, {}, {}, [], False, [reason])
    return {"status": status, "reason": reason, **out, "cached": False}
