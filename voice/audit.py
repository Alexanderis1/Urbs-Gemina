"""Post-call audit: did the voice model say a number no tool gave it?

The ElevenLabs model only relays answers, but it could still misquote a figure.
After each call (post-call webhook or conversation API) this check lists every
number in an agent message that does not appear in a tool result or in what the
user said. Findings go to the audit log in the Admin screen.

Limit: numbers spoken as words ("trecento") are not caught.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

_NUMBER = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)?")


@dataclass(frozen=True)
class Finding:
    turn: int
    number: str
    message: str


def _norm(n: str) -> str:
    return n.replace(",", ".").rstrip("0").rstrip(".") if ("." in n or "," in n) else n.lstrip("0") or "0"


def _numbers(text: str) -> set[str]:
    return {_norm(m.group(0)) for m in _NUMBER.finditer(text)}


def _texts(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for v in value.values():
            yield from _texts(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _texts(v)


def audit_transcript(transcript: Sequence[Mapping[str, Any]]) -> list[Finding]:
    evidence: set[str] = set()
    findings: list[Finding] = []
    for turn, entry in enumerate(transcript):
        for result in entry.get("tool_results") or []:
            for text in _texts(result):
                evidence |= _numbers(text)
        message = entry.get("message")
        if not isinstance(message, str):
            continue
        if entry.get("role") == "user":
            evidence |= _numbers(message)
            continue
        for m in _NUMBER.finditer(message):
            if _norm(m.group(0)) not in evidence:
                findings.append(Finding(turn=turn, number=m.group(0), message=message))
    return findings
