"""ElevenLabs agent payloads: AI disclosure, one webhook tool, map client tools, tier per agent."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from voice.agent_spec import build_agent_payload, load_client_tools

ROOT = Path(__file__).resolve().parents[1]


def tools(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return list(payload["conversation_config"]["agent"]["prompt"]["tools"])


@pytest.mark.parametrize("role", ["office", "citizen"])
def test_first_message_discloses_ai_in_every_language(role: str) -> None:
    p = build_agent_payload(role, webhook_url="https://api.example.org/voice/ask_twin", secret_id="sec_1")
    first = p["conversation_config"]["agent"]["first_message"].lower()
    assert "intelligenza artificiale" in first or " ai " in f" {first} "
    for preset in p["conversation_config"]["language_presets"].values():
        msg = preset["overrides"]["agent"]["first_message"].lower()
        assert "ai" in msg.split() or "artificial intelligence" in msg or "intelligenza artificiale" in msg


@pytest.mark.parametrize("role", ["office", "citizen"])
def test_exactly_one_webhook_tool_ask_twin_with_secret_header(role: str) -> None:
    p = build_agent_payload(role, webhook_url="https://api.example.org/voice/ask_twin", secret_id="sec_1")
    hooks = [t for t in tools(p) if t["type"] == "webhook"]
    assert [h["name"] for h in hooks] == ["ask_twin"]
    schema = hooks[0]["api_schema"]
    assert schema["url"] == "https://api.example.org/voice/ask_twin" and schema["method"] == "POST"
    assert schema["request_headers"]["X-Urbs-Voice-Secret"] == {"secret_id": "sec_1"}
    assert schema["request_headers"]["X-Conversation-Id"] == "{{system__conversation_id}}"
    props = schema["request_body_schema"]["properties"]
    assert "tier" not in props  # the tier is never chosen by the model
    assert schema["request_body_schema"]["required"] == ["question"]


def test_office_has_map_client_tools_and_citizen_prompt_differs() -> None:
    office = build_agent_payload("office", webhook_url="https://x/y", secret_id="s")
    citizen = build_agent_payload("citizen", webhook_url="https://x/y", secret_id="s")
    names = {t["name"] for t in tools(office) if t["type"] == "client"}
    assert {"fly_to", "show_area", "show_layer", "show_radius", "open_screen"} <= names
    assert all(t["expects_response"] is False for t in tools(office) if t["type"] == "client")
    assert office["conversation_config"]["agent"]["prompt"]["prompt"] != citizen["conversation_config"]["agent"]["prompt"]["prompt"]
    citizen_tool_names = {t["name"] for t in tools(citizen)}
    assert "show_radius" not in citizen_tool_names


def test_prompt_embeds_the_shared_answer_contract() -> None:
    contract = (ROOT / "agents" / "prompts" / "answer_contract.md").read_text(encoding="utf-8")
    p = build_agent_payload("office", webhook_url="https://x/y", secret_id="s")
    prompt = p["conversation_config"]["agent"]["prompt"]["prompt"]
    first_rule = next(line for line in contract.splitlines() if line.startswith("- "))
    assert first_rule in prompt


def test_client_tools_file_is_valid_and_shared_with_web() -> None:
    raw = json.loads((ROOT / "voice" / "client_tools.json").read_text(encoding="utf-8"))
    assert raw["tools"] == load_client_tools()
    for t in raw["tools"]:
        assert t["type"] == "client" and t["parameters"]["type"] == "object"


@pytest.mark.parametrize("role", ["office", "citizen"])
def test_italian_only_with_a_voice(role: str) -> None:
    p = build_agent_payload(role, webhook_url="https://x/y", secret_id="s")
    cc = p["conversation_config"]
    assert cc["agent"]["language"] == "it"
    assert cc["language_presets"] == {}
    assert "language_detection" not in cc["agent"]["prompt"]["built_in_tools"]
    hook = next(t for t in tools(p) if t["name"] == "ask_twin")
    assert hook["api_schema"]["request_body_schema"]["properties"]["language"]["enum"] == ["it"]
    assert cc["tts"]["voice_id"]


def test_unknown_role_rejected() -> None:
    with pytest.raises(ValueError):
        build_agent_payload("admin", webhook_url="https://x/y", secret_id="s")
