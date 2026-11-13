"""Morning briefing per municipio.

Never bypasses the orchestrator: the briefing is a fixed list of questions
(``briefing.yaml``), each sent to the orchestrator like any other question. Only
verified answers are kept; the others become "insufficient data" for that topic.
No number is written here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from .contract import Language, Orchestrator, Tier, TwinAnswer, TwinQuestion
from .speech import phrase

BRIEFING_PATH = Path(__file__).with_name("briefing.yaml")


@dataclass(frozen=True)
class BriefingItem:
    topic: str
    question: str


def load_briefing_items(language: Language) -> list[BriefingItem]:
    data = yaml.safe_load(BRIEFING_PATH.read_text(encoding="utf-8"))
    return [BriefingItem(topic=str(i["topic"]), question=str(i["question"])) for i in data[language]]


_ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV")


def spoken_area(area: str, language: Language) -> str:
    """'municipio:1' -> 'Municipio I', 'zone:6a' -> 'zona 6a', 'city' -> 'Roma'."""
    kind, _, code = area.partition(":")
    if kind == "municipio" and code.isdigit() and 1 <= int(code) <= len(_ROMAN):
        return f"Municipio {_ROMAN[int(code) - 1]}"
    if kind == "zone" and code:
        return f"{'zona' if language == 'it' else 'zone'} {code}"
    return "Roma" if language == "it" else "Rome"


def build_briefing(
    orchestrator: Orchestrator,
    *,
    area: str,
    tier: Tier,
    language: Language,
    conversation_id: str | None,
) -> TwinAnswer:
    name = spoken_area(area, language)
    parts = [phrase(language, "briefing_intro", area=name)]
    run_ids: list[str] = []
    sources: list[str] = []
    kinds: dict[str, str] = {}
    synthetic = False
    actions = []
    citations: list[Mapping[str, Any]] = []
    for item in load_briefing_items(language):
        answer = orchestrator.ask(
            TwinQuestion(
                question=item.question.format(area=name),
                tier=tier,
                language=language,
                area=area,
                mode="briefing",
                conversation_id=conversation_id,
                channel="voice",
            )
        )
        if not answer.verified:
            # Verifier reasons are English: spoken only in an English briefing.
            reason = f" {phrase(language, 'missing_prefix')}{', '.join(answer.missing)}." if answer.missing and language == "en" else ""
            parts.append(f"{item.topic}: {phrase(language, 'insufficient_data')}{reason}")
            continue
        parts.append(answer.text)
        run_ids += [r for r in answer.run_ids if r not in run_ids]
        sources += [s for s in answer.sources if s not in sources]
        kinds.update(answer.data_kinds)
        synthetic = synthetic or answer.synthetic
        actions += list(answer.map_actions)
        citations += list(answer.citations)
    parts.append(phrase(language, "briefing_outro"))
    return TwinAnswer(
        text=" ".join(parts),
        # Each kept part was verified; unverified parts carry no figures.
        verified=True,
        run_ids=tuple(run_ids),
        sources=tuple(sources),
        data_kinds=kinds,
        synthetic=synthetic,
        map_actions=tuple(actions[:1]),
        citations=tuple(citations),
    )
