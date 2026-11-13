"""Tool response envelope (shared interface 3 of the workstream plan).

Kept local to the sports module until the tool API stream publishes a shared
helper; the shape is the frozen contract, so swapping is a one-line import.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence


def run_id(tool: str, inputs: Mapping[str, Any], snapshot_hashes: Mapping[str, str]) -> str:
    """SHA-256 of tool name + inputs + data snapshot hashes (canonical JSON)."""
    payload = json.dumps({"tool": tool, "inputs": inputs, "snapshots": dict(sorted(snapshot_hashes.items()))},
                         sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_envelope(tool: str, inputs: Mapping[str, Any], result: Any, data_kinds: Mapping[str, str],
                  sources: Sequence[Mapping[str, Any]], synthetic: bool, warnings: Sequence[str],
                  snapshot_hashes: Mapping[str, str] | None = None) -> dict[str, Any]:
    bad = {k: v for k, v in data_kinds.items() if v not in ("real", "estimated", "simulated")}
    if bad:
        raise ValueError(f"data kinds must be real|estimated|simulated: {bad}")
    return {
        "run_id": run_id(tool, inputs, snapshot_hashes or {}),
        "tool": tool,
        "inputs": dict(inputs),
        "result": result,
        "data_kinds": dict(data_kinds),
        "sources": [dict(s) for s in sources],
        "synthetic": synthetic,
        "warnings": list(warnings),
    }
