"""Morning briefing: one playbook question to the orchestrator, with spoken intro and outro."""
from __future__ import annotations

from voice.briefing import USE_CASE, build_briefing, spoken_area
from voice.contract import TwinAnswer, TwinQuestion


class ScriptedOrchestrator:
    def __init__(self, verified: bool = True) -> None:
        self.calls: list[TwinQuestion] = []
        self.verified = verified

    def ask(self, question: TwinQuestion) -> TwinAnswer:
        self.calls.append(question)
        return TwinAnswer(text="Bus delays 4 minutes." if self.verified else "Air is 99.", verified=self.verified,
                          run_ids=("run1",), sources=(), data_kinds={"traffic_flow": "simulated"}, synthetic=True,
                          missing=() if self.verified else ("air stations",))


def test_briefing_is_one_playbook_call_through_the_orchestrator() -> None:
    orch = ScriptedOrchestrator()
    answer = build_briefing(orch, area="municipio:1", tier="office", language="en", conversation_id="c")
    assert len(orch.calls) == 1
    q = orch.calls[0]
    assert q.use_case == USE_CASE == "municipio_briefing"
    assert q.mode == "briefing" and q.channel == "voice" and q.area == "municipio:1" and q.tier == "office"
    assert "Municipio I" in q.question
    assert "Bus delays 4 minutes." in answer.text and answer.verified and answer.synthetic
    assert answer.run_ids == ("run1",)


def test_unverified_briefing_says_insufficient_data_without_numbers() -> None:
    answer = build_briefing(ScriptedOrchestrator(verified=False), area="municipio:1", tier="office", language="en",
                            conversation_id="c")
    assert "99" not in answer.text
    assert "air stations" in answer.text
    assert not answer.verified


def test_spoken_area() -> None:
    assert spoken_area("municipio:12", "it") == "Municipio XII"
    assert spoken_area("city", "it") == "Roma"
