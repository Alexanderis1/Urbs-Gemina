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
            "river_discharge", "rain_mm", "snapshots", "baseline_kind", "wind", "temperature")


def to_spec(data: ScenarioData) -> dict[str, Any]:
    spec: dict[str, Any] = {}
    for name in PORTABLE:
        value = getattr(data, name)
        if isinstance(value, tuple):
            value = list(value)
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
    if fields.get("wind") is not None:
        fields["wind"] = (float(fields["wind"][0]), float(fields["wind"][1]))
    if "rain_mm" in fields:
        fields["rain_mm"] = {k: [(float(a), float(b), float(c)) for a, b, c in v] for k, v in fields["rain_mm"].items()}
    if "temperature" in fields:
        fields["temperature"] = {k: [tuple(float(x) for x in row) for row in v]
                                 for k, v in fields["temperature"].items()}
    return ScenarioData(**fields)


def enabled() -> bool:
    return os.environ.get(ENV_SWITCH, "").lower() == "modal"


#: Errors raised by the scenario code itself (bad input): retrying cannot help.
INPUT_ERRORS = (ValueError, KeyError, TypeError)
#: One more try after a pause: the first call after idle can fail while the worker starts or is preempted.
RETRY_PAUSE_S = 5.0


def call(kind: str, area: Any, change: Mapping[str, Any], data: ScenarioData,
         attempts: int = 2, sleep: Any = None) -> dict[str, Any]:
    """Run one scenario in the Modal worker and return its envelope (retries a failed start once)."""
    import time

    import modal  # type: ignore[import-not-found,import-untyped,unused-ignore]

    pause = sleep or time.sleep
    spec = to_spec(data)
    for attempt in range(attempts):
        try:
            function = modal.Function.from_name(APP_NAME, FUNCTION_NAME)
            out: dict[str, Any] = function.remote(kind, area, dict(change), spec)
            return out
        except INPUT_ERRORS:
            raise
        except Exception:  # noqa: BLE001 - worker starting, preempted or network blip
            if attempt == attempts - 1:
                raise
            pause(RETRY_PAUSE_S)
    raise AssertionError("unreachable")
