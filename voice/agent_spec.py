"""Build the ElevenLabs agent payloads (office and citizen) from voice/agents.yaml.

The payload follows POST /v1/convai/agents/create (checked against the ElevenLabs
docs on 2026-11-13). The shared answer contract is pasted into each prompt so the
voice and the chat follow the same rules.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import yaml

from .contract import TIERS

VOICE_DIR = Path(__file__).resolve().parent
ANSWER_CONTRACT = VOICE_DIR.parent / "agents" / "prompts" / "answer_contract.md"


def _config() -> Mapping[str, Any]:
    data = yaml.safe_load((VOICE_DIR / "agents.yaml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def load_client_tools() -> list[dict[str, Any]]:
    data = json.loads((VOICE_DIR / "client_tools.json").read_text(encoding="utf-8"))
    tools = data["tools"]
    assert isinstance(tools, list)
    return tools


def _contract_rules() -> str:
    lines = ANSWER_CONTRACT.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if line.startswith("- "))


def ask_twin_tool(webhook_url: str, secret_id: str, languages: list[str], use_cases: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "webhook",
        "name": "ask_twin",
        "description": (
            "Ask the Urbs Gemina digital twin. It runs the deterministic tools, checks every number "
            "and returns the text to speak. Use it for every question about Rome."
        ),
        # Playbooks run several tools; 120 s is the ElevenLabs maximum. The agent says a short
        # "un momento" before the call so the wait is not silent.
        "response_timeout_secs": 120,
        "pre_tool_speech": "force",
        "api_schema": {
            "url": webhook_url,
            "method": "POST",
            "request_headers": {
                "X-Urbs-Voice-Secret": {"secret_id": secret_id},
                "X-Conversation-Id": "{{system__conversation_id}}",
            },
            "request_body_schema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The user's question, in their own words"},
                    "area": {
                        "type": "string",
                        "description": "Optional: 'city', 'municipio:<1-15>' (e.g. 'municipio:1' for Municipio I) or 'zone:<CODE>' for an urban zone",
                    },
                    "language": {"type": "string", "enum": languages, "description": "Language of the conversation"},
                    "mode": {
                        "type": "string",
                        "enum": ["question", "briefing"],
                        "description": "'briefing' only when the officer asks for the morning briefing",
                    },
                    "use_case": {
                        "type": "string",
                        "enum": list(use_cases or []),
                        "description": "Optional ready-made check, only when the request clearly matches one listed in the prompt",
                    },
                    "attendees": {
                        "type": "integer",
                        "description": "event_planning only: expected attendance, only if the officer said it",
                    },
                    "tmax_c": {
                        "type": "number",
                        "description": "heat_plan_elderly only: a what-if maximum temperature in °C, only if the officer said it",
                    },
                    "discipline": {
                        "type": "string",
                        "description": "sport_deserts only: the sport asked about, in Italian (e.g. 'nuoto'), only if the user said it",
                    },
                    "place": {
                        "type": "string",
                        "description": "Optional address or place name in Rome, for use cases that need a place",
                    },
                },
                "required": ["question"],
            },
        },
    }


def _language_tools(other_languages: list[str]) -> dict[str, Any]:
    if not other_languages:
        return {}
    return {
        "language_detection": {
            "type": "system",
            "name": "language_detection",
            "description": "Switch language when the user speaks another supported language or asks to switch.",
            "params": {"system_tool_type": "language_detection"},
        }
    }


def build_agent_payload(role: str, *, webhook_url: str, secret_id: str, voice_id: str | None = None) -> dict[str, Any]:
    if role not in TIERS:
        raise ValueError(f"role must be one of {TIERS}")
    cfg = _config()
    common, agent = cfg["common"], cfg[role]
    prompt = (VOICE_DIR / agent["prompt_file"]).read_text(encoding="utf-8").replace("{{answer_contract}}", _contract_rules())
    wanted = set(agent["client_tools"])
    client_tools = [t for t in load_client_tools() if t["name"] in wanted]
    default_lang = common["default_language"]
    languages = [default_lang, *common["other_languages"]]
    first = agent["first_message"]
    tts: dict[str, Any] = {"model_id": common["tts_model_id"]}
    if voice_id or common.get("voice_id"):
        tts["voice_id"] = voice_id or common["voice_id"]
    return {
        "name": agent["name"],
        "tags": ["urbs-gemina", role],
        "platform_settings": {"auth": {"enable_auth": bool(agent["private"])}},
        "conversation_config": {
            "agent": {
                "first_message": first[default_lang],
                "language": default_lang,
                "prompt": {
                    "prompt": prompt,
                    "llm": common["llm"],
                    "temperature": common["temperature"],
                    "timezone": common["timezone"],
                    "tools": [ask_twin_tool(webhook_url, secret_id, languages, list(agent.get("use_cases") or [])), *client_tools],
                    "built_in_tools": _language_tools(common["other_languages"]),
                },
            },
            "language_presets": {
                lang: {"overrides": {"agent": {"first_message": first[lang]}}} for lang in common["other_languages"]
            },
            "tts": tts,
        },
    }
