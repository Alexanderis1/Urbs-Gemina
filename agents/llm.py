"""The model seam. The loop talks to ``LLM.step``; ``AnthropicLLM`` implements it with Claude.

Tests use scripted fakes, so the guardrails are tested without network or API credit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from agents.config import AgentConfig, load_agent_config


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMTurn:
    text: str
    tool_calls: list[ToolCall]
    #: Content to append verbatim as the assistant message (keeps thinking blocks intact).
    assistant_content: list[Any]
    stop_reason: str
    extra: dict[str, Any] = field(default_factory=dict)


class LLM(Protocol):
    def step(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMTurn: ...


class ModelRefused(RuntimeError):
    pass


class AnthropicLLM:
    """Claude through the official SDK. Model and effort come from config/agents.yaml."""

    FALLBACK_BETA = "server-side-fallback-2026-07-01"

    def __init__(self, role: str = "orchestrator", config: AgentConfig | None = None, client: Any = None) -> None:
        cfg = config or load_agent_config()
        self.model = cfg.models[role]
        self.effort = cfg.effort
        self.max_tokens = cfg.max_tokens
        if client is None:
            import anthropic  # optional dependency group "agents"

            client = anthropic.Anthropic()
        self.client = client

    def step(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMTurn:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "output_config": {"effort": self.effort},
            # On a safety decline the API re-runs the request on a fallback model in the same call.
            "betas": [self.FALLBACK_BETA],
            "fallbacks": "default",
        }
        if tools:
            kwargs["tools"] = tools
        response = self.client.beta.messages.create(**kwargs)
        if response.stop_reason == "refusal":
            raise ModelRefused("the model declined this request")
        calls: list[ToolCall] = []
        texts: list[str] = []
        for block in response.content:
            if block.type == "tool_use":
                calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input)))
            elif block.type == "text":
                texts.append(block.text)
        return LLMTurn(text="".join(texts), tool_calls=calls, assistant_content=list(response.content),
                       stop_reason=str(response.stop_reason))
