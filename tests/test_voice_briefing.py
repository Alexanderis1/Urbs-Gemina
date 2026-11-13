"""Morning briefing: a fixed list of questions sent to the orchestrator, stitched in order."""
from __future__ import annotations

from voice.briefing import build_briefing, load_briefing_items
from voice.contract import TwinAnswer, TwinQuestion


class ScriptedOrchestrator:
    def __init__(self) -> None:
        self.calls: list[TwinQuestion] = []

    def ask(self, question: TwinQuestion) -> TwinAnswer:
        self.calls.append(question)
        n = len(self.calls)
        if n == 2:
            return TwinAnswer(text="Air is 99.", verified=False, run_ids=(), sources=(), data_kinds={}, synthetic=False, missing=("air stations",))
        return TwinAnswer(
            text=f"Item {n} fact.",
            verified=True,
            run_ids=(f"run{n}",),
            sources=(),
            data_kinds={f"layer{n}": "simulated" if n == 1 else "real"},
            synthetic=n == 1,
        )


def test_every_item_goes_through_the_orchestrator_in_order() -> None:
    items = load_briefing_items("en")
    assert len(items) >= 3
    orch = ScriptedOrchestrator()
    answer = build_briefing(orch, area="municipio:I", tier="office", language="en", conversation_id="c")
    assert [c.question for c in orch.calls] == [i.question.format(area="municipio:I") for i in items]
    assert all(c.mode == "briefing" and c.area == "municipio:I" and c.tier == "office" for c in orch.calls)
    assert answer.run_ids == tuple(f"run{n}" for n in range(1, len(items) + 1) if n != 2)
    assert answer.synthetic is True
    assert answer.verified is True


def test_unverified_items_say_insufficient_data_without_their_numbers() -> None:
    orch = ScriptedOrchestrator()
    answer = build_briefing(orch, area="municipio:I", tier="office", language="en", conversation_id="c")
    assert "99" not in answer.text
    assert "air stations" in answer.text
    assert answer.text.index("Item 1 fact.") < answer.text.index("air stations") < answer.text.index("Item 3 fact.")


def test_italian_items_exist() -> None:
    assert len(load_briefing_items("it")) == len(load_briefing_items("en"))
