"""Turn an orchestrator answer into what the voice agent says.

Run ids, hashes and URLs are kept in the response payload (shown on screen and in
the transcript) but removed from the spoken text. Unverified answers are never
spoken: they become "insufficient data" plus what is missing.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml

from twin.providers.base import ROME_BBOX

from .contract import Language, TwinAnswer

PHRASES_PATH = Path(__file__).with_name("phrases.yaml")
CLIENT_TOOL_NAMES = frozenset({"fly_to", "show_area", "show_layer", "show_radius", "open_screen"})

_RUN_TAG = re.compile(r"\[(?:run|run_id|source)[^\]]*\]", re.IGNORECASE)
_HEX = re.compile(r"\b[0-9a-f]{16,}\b", re.IGNORECASE)
_URL = re.compile(r"https?://\S+")
_MARKDOWN = re.compile(r"[*_`#>|]+")
_SPACES = re.compile(r"\s+")


@lru_cache(maxsize=1)
def phrases() -> Mapping[str, Any]:
    data = yaml.safe_load(PHRASES_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def phrase(language: Language, key: str, **fmt: str) -> str:
    text = str(phrases()[language][key])
    return text.format(**fmt) if fmt else text


def clean_for_speech(text: str) -> str:
    text = _RUN_TAG.sub("", text)
    text = _URL.sub("", text)
    text = _HEX.sub("", text)
    text = _MARKDOWN.sub("", text)
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    return _SPACES.sub(" ", text).strip()


def _truncate(text: str, language: Language) -> str:
    limit = int(phrases()["max_spoken_chars"])
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    cut = cut[: end + 1] if end > 0 else cut
    return f"{cut} {phrase(language, 'truncated')}"


def _in_rome(lon: Any, lat: Any) -> bool:
    if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        return False
    min_lon, min_lat, max_lon, max_lat = ROME_BBOX
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def safe_map_actions(actions: tuple[Mapping[str, Any], ...]) -> list[Mapping[str, Any]]:
    """Keep only known client tools; any point must lie inside Rome."""
    kept: list[Mapping[str, Any]] = []
    for action in actions:
        args = action.get("args")
        if action.get("tool") not in CLIENT_TOOL_NAMES or not isinstance(args, Mapping):
            continue
        if ("lon" in args or "lat" in args) and not _in_rome(args.get("lon"), args.get("lat")):
            continue
        kept.append(action)
    return kept


def _envelope(status: str, speak: str, answer: TwinAnswer | None) -> dict[str, Any]:
    return {
        "status": status,
        "speak": speak,
        "run_ids": list(answer.run_ids) if answer else [],
        "sources": list(answer.sources) if answer else [],
        "data_kinds": dict(answer.data_kinds) if answer else {},
        "synthetic": answer.synthetic if answer else False,
        "map_actions": safe_map_actions(answer.map_actions) if answer and answer.verified else [],
    }


def to_speech(answer: TwinAnswer, language: Language) -> dict[str, Any]:
    """Response body returned to ElevenLabs for one ``ask_twin`` call."""
    if not answer.verified:
        speak = phrase(language, "insufficient_data")
        if answer.missing:
            speak += " " + phrase(language, "missing_prefix") + ", ".join(answer.missing) + "."
        return _envelope("insufficient_data", speak, answer)
    speak = clean_for_speech(answer.text)
    if answer.synthetic or "simulated" in answer.data_kinds.values():
        speak = f"{phrase(language, 'simulated_note')} {speak}"
    return _envelope("ok", _truncate(speak, language), answer)


def error_speech(language: Language, key: str = "error") -> dict[str, Any]:
    status = "refused" if key.endswith("refused") else "error"
    return _envelope(status, phrase(language, key), None)
