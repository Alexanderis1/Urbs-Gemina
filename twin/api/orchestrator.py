"""Glue between the tool API and the orchestrator (WS7) / voice webhook (WS9).

The orchestrator runs in the same process as the tools, so its tool calls do not
go back over HTTP: :class:`InProcessGateway` calls the tool handlers directly
with the caller's tier, which the server set from the caller's credentials.
Both WS7 and WS9 modules are optional; without them the endpoints answer 501.
"""
from __future__ import annotations

import importlib
from typing import Any, Callable, Mapping

from pydantic import ValidationError

from twin.api.tools import TOOLS
from twin.tools.envelope import ToolError, make_envelope
from twin.tools.runtime import ToolRuntime


class InProcessGateway:
    """WS7 ``ToolGateway``: ``specs`` and ``call(name, arguments)``, served by the local tool handlers."""

    def __init__(self, runtime: ToolRuntime, role: str, specs: Mapping[str, Any]) -> None:
        self.runtime = runtime
        self.role = role
        self._specs = {name: spec for name, spec in specs.items() if name in TOOLS}

    @property
    def specs(self) -> Mapping[str, Any]:
        return self._specs

    def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        spec = TOOLS.get(name)
        if spec is None:
            return make_envelope(name, dict(arguments), None, {}, status="refused", reason=f"unknown tool '{name}'")
        try:
            request = spec.model.model_validate(dict(arguments))
            return spec.handler(self.runtime, request, self.role)
        except (ValidationError, ToolError) as error:
            return make_envelope(name, dict(arguments), None, {}, status="refused",
                                 reason=f"invalid arguments: {error}")


class TierOrchestrator:
    """WS7 ``Orchestrator``: one ``TwinOrchestrator`` per question, with a gateway for that question's tier."""

    def __init__(self, runtime: Callable[[], ToolRuntime]) -> None:
        self._runtime = runtime
        self._tools = importlib.import_module("agents.tools")
        self._orchestrator = importlib.import_module("agents.orchestrator")

    def ask(self, question: Any) -> Any:
        specs, _ = self._tools.load_tool_specs()
        gateway = self._tools.CompositeGateway(self._tools.LocalWebTools(specs),
                                               InProcessGateway(self._runtime(), str(question.tier), specs))
        return self._orchestrator.TwinOrchestrator(gateway=gateway).ask(question)


def available(module: str) -> bool:
    try:
        importlib.import_module(module)
    except ImportError:
        return False
    return True
