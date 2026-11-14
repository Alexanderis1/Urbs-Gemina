"""The shared tool response envelope (workstreams.md, shared interface 3).

Every tool, local or remote, returns this shape. ``run_id`` is the SHA-256 of the tool name,
its inputs and the data snapshot hashes, so the same question on the same data gives the same id.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def sha256_of(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def compute_run_id(tool: str, inputs: Mapping[str, Any], snapshot_hashes: Sequence[str]) -> str:
    return sha256_of({"tool": tool, "inputs": dict(inputs), "snapshots": sorted(snapshot_hashes)})


def make_envelope(
    *,
    tool: str,
    inputs: Mapping[str, Any],
    result: Mapping[str, Any],
    data_kinds: Mapping[str, str],
    sources: Sequence[Mapping[str, Any]],
    synthetic: bool = False,
    warnings: Sequence[str] = (),
    snapshot_hashes: Sequence[str] | None = None,
    status: str = "ok",
    reason: str | None = None,
    cached: bool = False,
) -> dict[str, Any]:
    """Build an envelope. Without explicit snapshot hashes, the result itself is hashed."""
    snaps = list(snapshot_hashes) if snapshot_hashes is not None else [sha256_of(result)]
    env: dict[str, Any] = {
        "run_id": compute_run_id(tool, inputs, snaps),
        "tool": tool,
        "inputs": dict(inputs),
        "result": dict(result),
        "data_kinds": dict(data_kinds),
        "sources": [dict(s) for s in sources],
        "synthetic": synthetic,
        "warnings": list(warnings),
        "status": status,
        "cached": cached if status == "ok" else False,
    }
    if status != "ok":
        env["reason"] = reason or status
    return env


REQUIRED_KEYS = ("run_id", "tool", "inputs", "result", "data_kinds", "sources", "synthetic", "warnings")
STATUSES = ("ok", "not_available", "refused")
DATA_KINDS = ("real", "estimated", "simulated", "not_available")


def is_ok(env: Mapping[str, Any]) -> bool:
    """Envelopes without a status (older tools) count as ok; anything else must say "ok"."""
    return env.get("status", "ok") == "ok" and "error" not in dict(env.get("result", {}))


def check_envelope(env: Mapping[str, Any]) -> list[str]:
    """Return the problems with an envelope received from a tool (empty list if fine)."""
    problems = [f"missing key '{k}'" for k in REQUIRED_KEYS if k not in env]
    for layer, kind in dict(env.get("data_kinds", {})).items():
        if kind not in DATA_KINDS:
            problems.append(f"layer '{layer}' has data kind '{kind}'")
    if env.get("status", "ok") not in STATUSES:
        problems.append(f"status '{env.get('status')}' is not one of {STATUSES}")
    if env.get("status", "ok") != "ok" and not env.get("reason"):
        problems.append("a result that is not ok must give a reason")
    if "simulated" in dict(env.get("data_kinds", {})).values() and env.get("synthetic") is not True:
        problems.append("simulated layer but synthetic is not true")
    return problems


def flatten_runs(envs: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index runs by id, including runs nested in a composite tool's ``result.tool_runs`` (e.g. permit_report)."""
    out: dict[str, dict[str, Any]] = {}
    stack = list(envs)
    while stack:
        env = stack.pop()
        if isinstance(env, Mapping) and "run_id" in env:
            out[str(env["run_id"])] = dict(env)
            inner = dict(env.get("result", {}) or {}).get("tool_runs")
            if isinstance(inner, list):
                stack.extend(i for i in inner if isinstance(i, Mapping))
    return out


_GEOMETRY_TYPES = frozenset({"Polygon", "MultiPolygon", "LineString", "MultiLineString", "MultiPoint", "GeometryCollection"})


def compact_for_model(value: Any, max_items: int = 25) -> Any:
    """Copy of a tool output small enough for the model (``config/agents.yaml`` model_view).

    Polygons and lines become a short placeholder (the map gets them from the run, the model only
    needs the facts); lists longer than ``max_items`` keep their first items (tools list the most
    important first) and say how many were left out. Counts and totals are kept, so the model never
    has to count. The stored run, which the verifier and the map read, is not changed.
    """
    if isinstance(value, Mapping):
        if value.get("type") in _GEOMETRY_TYPES and ("coordinates" in value or "geometries" in value):
            return {"type": value["type"], "omitted": "geometry (shown on the map)"}
        return {k: compact_for_model(v, max_items) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        items = [compact_for_model(v, max_items) for v in value[:max_items]]
        if len(value) > max_items:
            items.append(f"... {len(value) - max_items} more items omitted (the full list is in run output)")
        return items
    return value
