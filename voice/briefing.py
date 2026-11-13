"""Morning briefing per municipio.

Never bypasses the orchestrator: the briefing is a fixed list of questions
(``briefing.yaml``), each sent to the orchestrator like any other question. Only
verified answers are kept; the others become "insufficient data" for that topic.
No number is written here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


def build_briefing(
    orchestrator: Orchestrator,
    *,
    area: str,
    tier: Tier,
    language: Language,
    conversation_id: str | None,
) -> TwinAnswer:
    parts = [phrase(language, "briefing_intro", area=area)]
    run_ids: list[str] = []
    sources: list[str] = []
    kinds: dict[str, str] = {}
    synthetic = False
    actions = []
    for item in load_briefing_items(language):
        answer = orchestrator.ask(
            TwinQuestion(
                question=item.question.format(area=area),
                tier=tier,
                language=language,
                area=area,
                mode="briefing",
                conversation_id=conversation_id,
            )
        )
        if not answer.verified:
            missing = ", ".join(answer.missing) or item.topic
            parts.append(f"{item.topic}: {phrase(language, 'insufficient_data')} {phrase(language, 'missing_prefix')}{missing}.")
            continue
        parts.append(answer.text)
        run_ids += [r for r in answer.run_ids if r not in run_ids]
        sources += [s for s in answer.sources if s not in sources]
        kinds.update(answer.data_kinds)
        synthetic = synthetic or answer.synthetic
        actions += list(answer.map_actions)
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
    )
