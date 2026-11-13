"""The agent loop: model -> tools -> model, with the turn guard.

Turn guard (guardrail 9): once a tool has returned web content in this turn, no state-changing
tool may run until the turn ends. Web text reaches the model only inside the quote fence.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from agents.envelope import check_envelope
from agents.llm import LLM
from agents.tools import ToolError, ToolGateway, error_envelope
from agents.web import quote_untrusted


@dataclass
class LoopResult:
    text: str
    runs: list[dict[str, Any]]
    messages: list[dict[str, Any]]
    blocked_calls: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stopped_reason: str = "end_turn"
    web_content_seen: bool = False


def render_for_model(env: dict[str, Any], untrusted: bool) -> str:
    """Envelope as the model sees it: JSON, with any web text replaced by a fenced quote."""
    shown = json.loads(json.dumps(env, default=str))
    if untrusted:
        items = shown.get("result", {}).get("results", [])
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and "text" in item:
                item["text"] = quote_untrusted(str(item.get("url", "")), str(item.get("retrieved_at", "")), str(item["text"]))
            if isinstance(item, dict) and "title" in item:
                item["title"] = quote_untrusted(str(item.get("url", "")), str(item.get("retrieved_at", "")), str(item["title"]))
    return json.dumps(shown, ensure_ascii=False)


class AgentLoop:
    def __init__(self, *, llm: LLM, gateway: ToolGateway, system: str, tool_names: list[str],
                 max_tool_rounds: int = 8) -> None:
        self.llm = llm
        self.gateway = gateway
        self.system = system
        self.tool_names = [n for n in tool_names if n in gateway.specs]
        self.max_tool_rounds = max_tool_rounds

    def _tools_for_model(self) -> list[dict[str, Any]]:
        return [self.gateway.specs[n].for_model() for n in self.tool_names]

    def run(self, question: str) -> LoopResult:
        state = LoopResult(text="", runs=[], messages=[{"role": "user", "content": question}])
        return self._drive(state)

    def resume(self, state: LoopResult, note: str) -> LoopResult:
        """Continue the same turn (guard state kept) with an operator note, e.g. verifier feedback."""
        state.messages.append({"role": "user", "content": note})
        state.text = ""
        return self._drive(state)

    def _execute(self, state: LoopResult, name: str, args: dict[str, Any]) -> tuple[str, bool]:
        spec = self.gateway.specs.get(name)
        if spec is None or name not in self.tool_names:
            return f"Tool '{name}' is not available to this agent.", True
        if spec.state_changing and state.web_content_seen:
            state.blocked_calls.append(name)
            return (f"BLOCKED: '{name}' changes stored state and web content entered this turn. "
                    "Tell the officer what you would change; they can confirm it in a new turn."), True
        try:
            env = self.gateway.call(name, args)
        except (ToolError, OSError, KeyError, ValueError) as e:
            env = error_envelope(name, args, f"{type(e).__name__}: {e}")
            return render_for_model(env, False), True
        problems = check_envelope(env)
        if problems:
            state.warnings.extend(f"{name}: {p}" for p in problems)
        state.warnings.extend(str(w) for w in env.get("warnings", []))
        state.runs.append(env)
        if spec.untrusted_output:
            state.web_content_seen = True
        return render_for_model(env, spec.untrusted_output), False

    def _drive(self, state: LoopResult) -> LoopResult:
        rounds = sum(1 for m in state.messages if m["role"] == "assistant" and _has_tool_use(m))
        while True:
            turn = self.llm.step(self.system, state.messages, self._tools_for_model())
            state.messages.append({"role": "assistant", "content": turn.assistant_content})
            if not turn.tool_calls:
                state.text = turn.text
                state.stopped_reason = turn.stop_reason
                return state
            results = []
            for call in turn.tool_calls:
                content, is_error = self._execute(state, call.name, call.arguments)
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": content, "is_error": is_error})
            state.messages.append({"role": "user", "content": results})
            rounds += 1
            if rounds >= self.max_tool_rounds:
                state.text = ""
                state.stopped_reason = "max_tool_rounds"
                return state


def _has_tool_use(message: dict[str, Any]) -> bool:
    content = message.get("content")
    if not isinstance(content, list):
        return False
    for block in content:
        kind = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        if kind == "tool_use":
            return True
    return False
