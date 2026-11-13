"""``run(kind, area, change) -> envelope``: the single entry point behind ``run_scenario``."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from twin.scenarios import cache, config
from twin.scenarios.antenna import run_antenna
from twin.scenarios.area import Area, AreaArg, resolve_area
from twin.scenarios.data import ScenarioData
from twin.scenarios.envelope import envelope, run_id
from twin.scenarios.exposure import run_population_exposure
from twin.scenarios.traffic import run_road_closure

TOOL = "run_scenario"
Runner = Callable[[Area, Mapping[str, Any], ScenarioData], dict[str, Any]]


@dataclass(frozen=True)
class Kind:
    runner: Runner
    heavy: bool
    description: str


KINDS: dict[str, Kind] = {
    "antenna": Kind(run_antenna, False,
                    "Add or move an antenna: field P5/P50/P95 and exceedance probability, baseline vs variant"),
    "population_exposure": Kind(run_population_exposure, False,
                                "Residents in census sections above the EMF thresholds, baseline vs variant"),
    "road_closure": Kind(run_road_closure, True,
                         "Close roads on one district: SUMO travel time and delay, baseline vs variant (synthetic demand)"),
}


def kinds() -> dict[str, str]:
    return {name: k.description for name, k in KINDS.items()}


def default_cache_dir() -> Path:
    return config.ROOT / str(config.load("scenarios.yaml")["cache"]["dir"])


def run(kind: str, area: AreaArg, change: Mapping[str, Any], data: ScenarioData | None = None,
        cache_dir: Path | None = None, use_cache: bool = True) -> dict[str, Any]:
    if kind not in KINDS:
        raise KeyError(f"Unknown scenario kind '{kind}'. Known: {', '.join(sorted(KINDS))}")
    data = data or ScenarioData()
    spec = KINDS[kind]
    inputs = {"kind": kind, "area": area, "change": dict(change)}
    snapshots = {**config.config_hashes(), **data.fingerprint()}
    rid = run_id(TOOL, inputs, snapshots)
    directory = cache_dir if cache_dir is not None else default_cache_dir()
    if use_cache:
        hit = cache.get(directory, rid)
        if hit is not None:
            return {**hit, "cached": True}

    resolved = resolve_area(area, heavy=spec.heavy, lookup=data.area_lookup)
    part = spec.runner(resolved, change, data)
    status = part["result"].get("status", "ok")
    out = envelope(TOOL, inputs, snapshots, {"status": status, **part["result"], "area": {"id": resolved.id,
                                                                        "area_km2": round(resolved.area_km2, 3)}},
                   part["data_kinds"], part["sources"], bool(part["synthetic"]), part["warnings"])
    if use_cache and status == "ok":
        cache.put(directory, rid, out)
    return {**out, "cached": False}
