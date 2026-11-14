"""Tool response envelope shared by every tool (see the shared interfaces in the plan)."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence


def run_id(tool: str, inputs: Mapping[str, Any], snapshots: Mapping[str, str]) -> str:
    """SHA-256 of tool name + inputs + data snapshot hashes."""
    payload = json.dumps({"tool": tool, "inputs": inputs, "snapshots": snapshots}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def envelope(tool: str, inputs: Mapping[str, Any], snapshots: Mapping[str, str], result: Mapping[str, Any],
             data_kinds: Mapping[str, str], sources: Sequence[Mapping[str, Any]], synthetic: bool,
             warnings: Sequence[str]) -> dict[str, Any]:
    return {
        "run_id": run_id(tool, inputs, snapshots),
        "tool": tool,
        "inputs": dict(inputs),
        "result": dict(result),
        "data_kinds": dict(data_kinds),
        "sources": [dict(s) for s in sources],
        "synthetic": synthetic,
        "warnings": list(warnings),
    }
