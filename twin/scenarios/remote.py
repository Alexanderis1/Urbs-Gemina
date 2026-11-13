"""Run the heavy scenario kinds out of the API process: a Modal function (scale to zero) or locally.

The API container stays light: SUMO, the terrain hydrology and big rasters run in
the worker defined in deploy/scenarios_worker.py. Only plain JSON crosses the wire,
so a ScenarioData is reduced to its serialisable inputs (live readings, snapshots);
files (terrain, layers, road networks) are read inside the worker from its volumes.
"""
from __future__ import annotations

import os
from typing import Any, Mapping

from twin.scenarios.data import ScenarioData

APP_NAME = "urbs-gemina-scenarios"
FUNCTION_NAME = "run_heavy"
ENV_SWITCH = "URBS_SCENARIO_WORKER"  # "modal" sends isolated kinds to the worker; unset runs them here

#: ScenarioData fields that are plain JSON and can travel to the worker.
PORTABLE = ("loop_counts_veh_per_h", "observed_speeds_m_per_s", "loop_counts_kind", "river_levels",
            "river_discharge", "rain_mm", "snapshots", "baseline_kind")


def to_spec(data: ScenarioData) -> dict[str, Any]:
    spec: dict[str, Any] = {}
    for name in PORTABLE:
        value = getattr(data, name)
        if isinstance(value, Mapping):
            value = {str(k): (list(v) if isinstance(v, tuple) else v) for k, v in value.items()}
        spec[name] = value
    return spec


def from_spec(spec: Mapping[str, Any]) -> ScenarioData:
    fields = {k: spec[k] for k in PORTABLE if k in spec}
    if "river_levels" in fields:
        fields["river_levels"] = {k: (float(v[0]), float(v[1])) for k, v in fields["river_levels"].items()}
    if "river_discharge" in fields:
        fields["river_discharge"] = {k: [(str(d), float(q), float(s)) for d, q, s in v]
                                     for k, v in fields["river_discharge"].items()}
    if "rain_mm" in fields:
        fields["rain_mm"] = {k: [(float(a), float(b), float(c)) for a, b, c in v] for k, v in fields["rain_mm"].items()}
    return ScenarioData(**fields)


def enabled() -> bool:
    return os.environ.get(ENV_SWITCH, "").lower() == "modal"


def call(kind: str, area: Any, change: Mapping[str, Any], data: ScenarioData) -> dict[str, Any]:
    """Run one scenario in the Modal worker and return its envelope."""
    import modal  # type: ignore[import-not-found,import-untyped,unused-ignore]

    function = modal.Function.from_name(APP_NAME, FUNCTION_NAME)
    out: dict[str, Any] = function.remote(kind, area, dict(change), to_spec(data))
    return out
