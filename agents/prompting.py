"""Assemble system prompts from the shared answer contract and the agent's own prompt."""
from __future__ import annotations

from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


def system_prompt(agent: str, language: str = "en", tier: str = "office") -> str:
    parts = [(PROMPT_DIR / "answer_contract.md").read_text(encoding="utf-8"),
             (PROMPT_DIR / "citations.md").read_text(encoding="utf-8"),
             (PROMPT_DIR / f"{agent}.md").read_text(encoding="utf-8")]
    lang = "Italian" if language == "it" else "English"
    parts.append(f"Answer in {lang}. The caller's tier is '{tier}'"
                 + (": give aggregated figures only, no technical antenna fields." if tier == "citizen" else "."))
    return "\n\n".join(parts)
