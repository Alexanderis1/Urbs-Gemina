"""The response envelope shared by every tool (shared interface 3).

``run_id`` is the SHA-256 of the tool name, its inputs, the hashes of the data
snapshots it read and the hashes of the config files that drive the result, so
the same question on the same data and config always gets the same id, and any
change gets a new one. ``status`` is ``ok``, ``not_available`` (an input is
missing) or ``refused`` (a guardrail said no); ``reason`` explains a non-ok
status. ``cached`` says whether the result was served from a cache.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Literal, Mapping

DataKind = Literal["real", "estimated", "simulated", "not_available"]
DATA_KINDS: frozenset[str] = frozenset({"real", "estimated", "simulated", "not_available"})
Status = Literal["ok", "not_available", "refused"]
STATUSES: frozenset[str] = frozenset({"ok", "not_available", "refused"})


class ToolError(ValueError):
    """A request the tool refuses (unknown area, area too large, bad input)."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def compute_run_id(tool: str, inputs: Mapping[str, Any], snapshot_hashes: Mapping[str, str]) -> str:
    payload = canonical_json({"tool": tool, "inputs": inputs, "snapshots": dict(snapshot_hashes)})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Source:
    id: str
    retrieved_at: str
    url: str | None = None
    #: Hash of the snapshot that was read, when there is one. Feeds the run id.
    sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "retrieved_at": self.retrieved_at}
        if self.url:
            out["url"] = self.url
        return out


def make_envelope(
    tool: str,
    inputs: Mapping[str, Any],
    result: Any,
    data_kinds: Mapping[str, str],
    sources: Iterable[Source] = (),
    warnings: Iterable[str] = (),
    synthetic: bool | None = None,
    extra_hashes: Mapping[str, str] | None = None,
    config_hashes: Mapping[str, str] | None = None,
    status: str = "ok",
    reason: str | None = None,
    cached: bool = False,
) -> dict[str, Any]:
    bad = {layer: kind for layer, kind in data_kinds.items() if kind not in DATA_KINDS}
    if bad:
        raise ValueError(f"data kinds must be real, estimated, simulated or not_available: {bad}")
    if status not in STATUSES:
        raise ValueError(f"status must be one of {sorted(STATUSES)}")
    if status != "ok" and not reason:
        raise ValueError("a non-ok status needs a reason")
    source_list = _dedupe(sources)
    hashes = {s.id: s.sha256 for s in source_list if s.sha256}
    hashes.update(extra_hashes or {})
    hashes.update({f"config:{name}": digest for name, digest in (config_hashes or {}).items()})
    is_synthetic = any(kind == "simulated" for kind in data_kinds.values()) if synthetic is None else synthetic
    out: dict[str, Any] = {
        "run_id": compute_run_id(tool, inputs, hashes),
        "tool": tool,
        "status": status,
        "inputs": dict(inputs),
        "result": result,
        "data_kinds": dict(data_kinds),
        "sources": [s.to_dict() for s in source_list],
        "synthetic": is_synthetic,
        "warnings": list(dict.fromkeys(warnings)),
        "cached": cached,
    }
    if reason:
        out["reason"] = reason
    return out


def _dedupe(sources: Iterable[Source]) -> list[Source]:
    seen: dict[str, Source] = {}
    for source in sources:
        seen.setdefault(source.id, source)
    return list(seen.values())
