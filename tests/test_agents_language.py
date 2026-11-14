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


def test_citizens_get_an_information_disclosure_not_the_office_one() -> None:
    """The office line 'decide il funzionario' is wrong for a resident; they get 'information only, 112'."""
    from agents.config import load_agent_config

    cfg = load_agent_config()
    office, citizen = cfg.disclosure_for("office", "it"), cfg.disclosure_for("citizen", "it")
    assert "funzionario" in office
    assert "funzionario" not in citizen and "112" in citizen and "intelligenza artificiale" in citizen
    assert "112" in cfg.disclosure_for("citizen", "en")


def test_citizen_use_case_answer_opens_with_the_citizen_disclosure() -> None:
    from agents.orchestrator import TwinOrchestrator
    from tests.test_use_cases import CitingLLM, FakeGateway

    orch = TwinOrchestrator(llm=CitingLLM(), gateway=FakeGateway())
    q = TwinQuestion(question="Via del Corso 1", tier="citizen", language="it", use_case="citizen_area_info")
    text = orch.ask(q).text
    assert text.startswith("Sono un assistente") and "112" in text.split("\n\n")[0]
    assert "funzionario" not in text.split("\n\n")[0]
