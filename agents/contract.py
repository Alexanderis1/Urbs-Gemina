"""Shared interface 7: what chat (WS8) and voice (WS9) send to the orchestrator and get back.

Same shape as ``voice/contract.py`` on the voice stream's branch; the hub allowed moving it here.
Changes to these dataclasses go through the hub thread.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Protocol

Tier = Literal["office", "citizen"]
Language = Literal["it", "en"]
Mode = Literal["question", "briefing"]


@dataclass(frozen=True)
class TwinQuestion:
    question: str
    #: Set by the server from the caller's credentials, never by the model.
    tier: Tier
    language: Language
    area: str | None = None
    mode: Mode = "question"
    conversation_id: str | None = None
    channel: str = "chat"


@dataclass(frozen=True)
class TwinAnswer:
    text: str
    #: True only when the verifier found a run id or source for every figure.
    verified: bool
    run_ids: tuple[str, ...]
    sources: tuple[str, ...]
    data_kinds: Mapping[str, str]
    synthetic: bool
    missing: tuple[str, ...] = ()
    map_actions: tuple[Mapping[str, Any], ...] = field(default=())
    #: Tool trace of citations: {"line", "kind", "ref", "cite_mode": "explicit" | "auto"} (hub, 13 Nov).
    citations: tuple[Mapping[str, Any], ...] = field(default=())


class Orchestrator(Protocol):
    def ask(self, question: TwinQuestion) -> TwinAnswer: ...
