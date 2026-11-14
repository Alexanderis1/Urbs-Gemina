"""Morning briefing per municipio.

Never bypasses the orchestrator: the briefing is one question with ``mode="briefing"``, which the
orchestrator runs as the ``municipio_briefing`` playbook (``config/use_cases.yaml``): code calls the
same fixed tools every morning and the model writes one verified text. The voice layer only adds the
spoken intro and outro. No number is written here.

Before 14 Nov 2026 this sent six separate questions (six agent loops); one playbook run gives the
same topics with one model call.
"""
from __future__ import annotations

from dataclasses import replace

from .contract import Language, Orchestrator, Tier, TwinAnswer, TwinQuestion
from .speech import phrase

USE_CASE = "municipio_briefing"
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
    question = ("Briefing mattutino per {area}." if language == "it" else "Morning briefing for {area}.").format(area=name)
    answer = orchestrator.ask(
        TwinQuestion(question=question, tier=tier, language=language, area=area, mode="briefing",
                     conversation_id=conversation_id, channel="voice", use_case=USE_CASE)
    )
    intro = phrase(language, "briefing_intro", area=name)
    outro = phrase(language, "briefing_outro")
    if not answer.verified:
        # The unverified text may hold unbacked figures: say only that data are insufficient (and why, in English).
        reason = f" {phrase(language, 'missing_prefix')}{', '.join(answer.missing)}." if answer.missing and language == "en" else ""
        return replace(answer, text=f"{intro} {phrase(language, 'insufficient_data')}{reason} {outro}", map_actions=())
    return replace(answer, text=f"{intro} {answer.text} {outro}", map_actions=tuple(answer.map_actions[:1]))
