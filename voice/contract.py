"""What the voice layer sends to the orchestrator and what it expects back.

The voice agent never answers on its own. Every question goes to the same
orchestrator (and verifier) as the chat, owned by the agents stream. This file
is the voice side of that hand-over; the orchestrator side must return a
``TwinAnswer`` (or the JSON shape parsed by ``answer_from_json``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Protocol

Tier = Literal["office", "citizen"]
Language = Literal["it", "en"]
Mode = Literal["question", "briefing"]

TIERS: tuple[Tier, ...] = ("office", "citizen")
LANGUAGES: tuple[Language, ...] = ("it", "en")


@dataclass(frozen=True)
class TwinQuestion:
    question: str
    #: Set by the server from the calling agent's secret, never by the model.
    tier: Tier
    language: Language
    area: str | None = None
    mode: Mode = "question"
    conversation_id: str | None = None
    channel: str = "voice"


@dataclass(frozen=True)
class TwinAnswer:
    #: Answer text written by the orchestrator, already checked by the verifier.
    text: str
    #: True only when the verifier found a run id or source for every figure.
    verified: bool
    run_ids: tuple[str, ...]
    sources: tuple[str, ...]
    #: Layer name -> "real" | "estimated" | "simulated".
    data_kinds: Mapping[str, str]
    synthetic: bool
    #: What is missing when the answer is "insufficient data".
    missing: tuple[str, ...] = ()
    #: Suggested map moves, each {"tool": <client tool name>, "args": {...}}.
    map_actions: tuple[Mapping[str, Any], ...] = field(default=())


class Orchestrator(Protocol):
    def ask(self, question: TwinQuestion) -> TwinAnswer: ...


def _strs(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(v) for v in value)


def answer_from_json(data: Mapping[str, Any]) -> TwinAnswer:
    """Parse the orchestrator's JSON reply. Unknown or missing fields fail safe (unverified)."""
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
