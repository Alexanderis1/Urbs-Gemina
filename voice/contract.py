"""Voice side of shared interface 7 (orchestrator hand-over).

The dataclasses live in ``agents/contract.py`` (owned by the agents stream, frozen by
the hub). This module re-exports them and adds the voice-only helpers.
"""
from __future__ import annotations

from typing import Any, Mapping

from agents.contract import Language, Mode, Orchestrator, Tier, TwinAnswer, TwinQuestion

__all__ = ["LANGUAGES", "TIERS", "Language", "Mode", "Orchestrator", "Tier", "TwinAnswer", "TwinQuestion", "answer_from_json"]

TIERS: tuple[Tier, ...] = ("office", "citizen")
LANGUAGES: tuple[Language, ...] = ("it", "en")


def _strs(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(v) for v in value)


def answer_from_json(data: Mapping[str, Any]) -> TwinAnswer:
    """Parse an orchestrator reply sent as JSON. Unknown or missing fields fail safe (unverified)."""
    kinds = data.get("data_kinds")
    actions = data.get("map_actions")
    return TwinAnswer(
        text=str(data.get("text", "")),
        verified=data.get("verified") is True,
        run_ids=_strs(data.get("run_ids")),
        sources=_strs(data.get("sources")),
        data_kinds={str(k): str(v) for k, v in kinds.items()} if isinstance(kinds, Mapping) else {},
        synthetic=data.get("synthetic") is not False,
        missing=_strs(data.get("missing")),
        map_actions=tuple(a for a in actions if isinstance(a, Mapping)) if isinstance(actions, list) else (),
    )
