"""Assemble system prompts from the shared answer contract and the agent's own prompt."""
from __future__ import annotations

from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
#: Agents that call run_scenario themselves and need the change shapes of each kind.
WITH_SCENARIO_KINDS = frozenset({"orchestrator", "scenario"})


def system_prompt(agent: str, language: str = "it", tier: str = "office") -> str:
    parts = [(PROMPT_DIR / "answer_contract.md").read_text(encoding="utf-8"),
             (PROMPT_DIR / "citations.md").read_text(encoding="utf-8"),
             (PROMPT_DIR / f"{agent}.md").read_text(encoding="utf-8")]
    if agent in WITH_SCENARIO_KINDS:
        parts.append((PROMPT_DIR / "scenario_kinds.md").read_text(encoding="utf-8"))
    if language == "it":
        parts.append("Answer in Italian. Name data kinds in Italian: reale, stimato (stima), simulato. Translate any "
                     "fixed phrase quoted in these instructions (e.g. 'estimate, not a measurement' = 'stima, non "
                     "misura'; 'insufficient data' = 'dati insufficienti'; 'timetable, estimated' = 'orario "
                     "programmato, stimato'). Keep tool and layer names as they are.")
    else:
        parts.append("Answer in English: the officer wrote in English.")
    parts.append(f"The caller's tier is '{tier}'"
                 + (": give aggregated figures only, no technical antenna fields." if tier == "citizen" else "."))
    return "\n\n".join(parts)
