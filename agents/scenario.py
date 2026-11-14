"""Scenario agent: asks for what is missing, then runs ``run_scenario`` and explains the delta."""
from __future__ import annotations

from typing import Any, Mapping

from agents.config import AgentConfig
from agents.llm import LLM
from agents.orchestrator import Answer, answer
from agents.tools import ToolGateway, ToolSpec, error_envelope

REQUIRED_SLOTS = ("kind", "area", "change")


def missing_slots(spec: Mapping[str, Any]) -> list[str]:
    return [s for s in REQUIRED_SLOTS if not spec.get(s)]


class SlotCheckingGateway:
    """Refuses ``run_scenario`` until kind, area and change are all given (no guessed parameters)."""

    def __init__(self, inner: ToolGateway) -> None:
        self.inner = inner

    @property
    def specs(self) -> Mapping[str, ToolSpec]:
        return self.inner.specs

    def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if name == "run_scenario":
            missing = missing_slots(arguments)
            if missing:
                return error_envelope(name, arguments, "ask the officer for: " + ", ".join(missing))
        return self.inner.call(name, arguments)


def scenario_turn(message: str, *, llm: LLM, gateway: ToolGateway, language: str = "it",
                  first_message: bool = False, config: AgentConfig | None = None) -> Answer:
    return answer(message, llm=llm, gateway=SlotCheckingGateway(gateway),
                  tool_names=["resolve_place", "run_scenario", "query_layer", "estimate_field"],
                  first_message=first_message, language=language, agent="scenario", config=config)
