"""Italian first: answers are in Italian unless the officer writes in English (Alessandro, 14 Nov 2026)."""
from __future__ import annotations

from dataclasses import replace

from agents.contract import TwinQuestion
from agents.language import answer_language, detect_language
from agents.prompting import system_prompt


def test_detects_clear_english_and_clear_italian_only() -> None:
    assert detect_language("What is the air quality in Municipio V this morning?") == "en"
    assert detect_language("Com'è la qualità dell'aria nel Municipio V stamattina?") == "it"
    assert detect_language("Circo Massimo") is None          # a place name says nothing
    assert detect_language("municipio:5") is None


def test_italian_unless_the_officer_writes_in_english() -> None:
    q = TwinQuestion(question="Quanti anziani sono esposti al caldo nel Municipio V?", tier="office", language="en")
    assert answer_language(q) == "it"                        # the text wins over the client setting
    q_en = replace(q, question="How many elderly people are exposed to heat in Municipio V?", language="it")
    assert answer_language(q_en) == "en"
    q_place = replace(q, question="Circo Massimo", language="it")
    assert answer_language(q_place) == "it"                  # no signal: the client setting (Italian by default)


def test_system_prompt_is_italian_by_default_with_italian_data_labels() -> None:
    text = system_prompt("orchestrator")
    assert "Answer in Italian" in text and "stimato" in text and "simulato" in text


def test_plain_problems_and_withheld_notes_are_in_italian() -> None:
    from agents.orchestrator import plain_problem
    from agents.verifier import Problem

    assert plain_problem(Problem("uncited_number", "'42' has no run id"), "it").startswith("una cifra")
    assert plain_problem(Problem("uncited_number", "'42' has no run id"), "en").startswith("a figure")
