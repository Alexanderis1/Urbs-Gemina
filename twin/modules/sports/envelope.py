"""Tool response envelope (shared interface 3 of the workstream plan).

Kept local to the sports module until the tool API stream publishes a shared
helper; the shape is the frozen contract, so swapping is a one-line import.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

Status = Literal["ok", "not_available", "refused"]
SPORTS_CONFIG = Path(__file__).resolve().parents[3] / "config" / "sports.yaml"


def config_hashes() -> dict[str, str]:
    """Hashes of the config files that drive sports results (part of the run id, per the contract)."""
    return {"config/sports.yaml": hashlib.sha256(SPORTS_CONFIG.read_bytes()).hexdigest()}


def run_id(tool: str, inputs: Mapping[str, Any], snapshot_hashes: Mapping[str, str]) -> str:
    """SHA-256 of tool name + inputs + data snapshot hashes (canonical JSON)."""
    payload = json.dumps({"tool": tool, "inputs": inputs, "snapshots": dict(sorted(snapshot_hashes.items())),
                          "config": config_hashes()},
                         sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_envelope(tool: str, inputs: Mapping[str, Any], result: Any, data_kinds: Mapping[str, str],
                  sources: Sequence[Mapping[str, Any]], synthetic: bool, warnings: Sequence[str],
                  snapshot_hashes: Mapping[str, str] | None = None, status: Status = "ok",
                  reason: str | None = None, cached: bool = False) -> dict[str, Any]:
    if status != "ok" and not reason:
        raise ValueError("a status other than 'ok' needs a reason")
    bad = {k: v for k, v in data_kinds.items() if v not in ("real", "estimated", "simulated", "not_available")}
    if bad:
        raise ValueError(f"data kinds must be real|estimated|simulated|not_available: {bad}")
    envelope: dict[str, Any] = {
        "run_id": run_id(tool, inputs, snapshot_hashes or {}),
        "tool": tool,
        "inputs": dict(inputs),
        "result": result,
        "data_kinds": dict(data_kinds),
        "sources": [dict(s) for s in sources],
        "synthetic": synthetic,
        "warnings": list(warnings),
        "status": status,
        "cached": cached,
    }
    if reason:
        envelope["reason"] = reason
    return envelope
