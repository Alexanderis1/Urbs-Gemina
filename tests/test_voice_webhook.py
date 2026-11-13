"""ask_twin webhook: auth, tier from the server, orchestrator only, speech shaping."""
from __future__ import annotations

from typing import Any

from voice.contract import Tier, TwinAnswer, TwinQuestion
from voice.webhook import handle_ask_twin

SECRETS: dict[str, Tier] = {"office-secret": "office", "citizen-secret": "citizen"}
RUN = "a" * 64


class FakeOrchestrator:
    def __init__(self, answer: TwinAnswer) -> None:
        self.answer = answer
        self.calls: list[TwinQuestion] = []

    def ask(self, question: TwinQuestion) -> TwinAnswer:
        self.calls.append(question)
        return self.answer


def ok_answer(**kw: Any) -> TwinAnswer:
    base: dict[str, Any] = dict(
        text=f"Within 300 m there are 2 schools [run {RUN}]. See https://example.org/x.",
        verified=True,
        run_ids=(RUN,),
        sources=("roma_geoserver",),
        data_kinds={"schools": "real"},
        synthetic=False,
    )
    base.update(kw)
    return TwinAnswer(**base)


def call(body: dict[str, Any], secret: str = "office-secret", orch: FakeOrchestrator | None = None) -> tuple[int, dict[str, Any], FakeOrchestrator]:
    orch = orch or FakeOrchestrator(ok_answer())
    status, resp = handle_ask_twin(body, {"X-Urbs-Voice-Secret": secret, "X-Conversation-Id": "conv_1"}, orch, SECRETS)
    return status, resp, orch


def test_rejects_missing_or_wrong_secret() -> None:
    orch = FakeOrchestrator(ok_answer())
    status, _ = handle_ask_twin({"question": "hi"}, {}, orch, SECRETS)
    assert status == 401
    status, _, orch2 = call({"question": "hi"}, secret="nope")
    assert status == 401
    assert orch.calls == [] and orch2.calls == []


def test_tier_comes_from_secret_not_from_body() -> None:
    status, _, orch = call({"question": "antenna near school?", "tier": "office"}, secret="citizen-secret")
    assert status == 200
    assert orch.calls[0].tier == "citizen"


def test_question_goes_to_orchestrator_with_area_and_language() -> None:
    status, resp, orch = call({"question": "What is around Piazza Venezia?", "area": "municipio:1", "language": "en"})
    assert status == 200
    q = orch.calls[0]
    assert q.question == "What is around Piazza Venezia?"
    assert q.area == "municipio:1" and q.language == "en" and q.conversation_id == "conv_1"
    assert resp["status"] == "ok"
    assert q.channel == "voice"


def test_area_must_use_shared_ids() -> None:
    for area in ("city", "municipio:15", "zone:6a"):
        assert call({"question": "x", "area": area})[0] == 200
    for area in ("municipio:16", "municipio:I", "Trastevere", "zone:"):
        assert call({"question": "x", "area": area})[0] == 400, area


def test_speech_drops_run_ids_and_urls_but_keeps_them_in_payload() -> None:
    _, resp, _ = call({"question": "x", "language": "en"})
    assert RUN not in resp["speak"] and "https://" not in resp["speak"]
    assert "2 schools" in resp["speak"]
    assert resp["run_ids"] == [RUN]
    assert resp["sources"] == ["roma_geoserver"]


def test_unverified_answer_becomes_insufficient_data() -> None:
    orch = FakeOrchestrator(ok_answer(verified=False, text="There are 7 antennas.", missing=("antenna register",)))
    _, resp, _ = call({"question": "x", "language": "en"}, orch=orch)
    assert resp["status"] == "insufficient_data"
    assert "7" not in resp["speak"]
    assert "antenna register" in resp["speak"]


def test_simulated_data_is_announced() -> None:
    orch = FakeOrchestrator(ok_answer(synthetic=True, data_kinds={"emf": "simulated"}))
    _, resp, _ = call({"question": "x", "language": "it"}, orch=orch)
    assert resp["synthetic"] is True
    assert "simulat" in resp["speak"].lower()


def test_bad_input_is_rejected_without_calling_orchestrator() -> None:
    for body in ({}, {"question": ""}, {"question": "x" * 2000}, {"question": "x", "area": "{\"type\": \"Polygon\"}"}, {"question": "x", "language": "fr"}):
        status, _, orch = call(body)
        assert status == 400, body
        assert orch.calls == []


def test_accepts_elevenlabs_wrapped_parameters() -> None:
    status, _, orch = call({"tool_call_id": "c1", "parameters": {"question": "hello", "language": "it"}})
    assert status == 200 and orch.calls[0].question == "hello"


def test_map_actions_outside_rome_are_dropped() -> None:
    actions = (
        {"tool": "fly_to", "args": {"lon": 12.48, "lat": 41.89, "zoom": 15}},
        {"tool": "fly_to", "args": {"lon": 2.35, "lat": 48.85, "zoom": 15}},
        {"tool": "format_disk", "args": {}},
    )
    _, resp, _ = call({"question": "x"}, orch=FakeOrchestrator(ok_answer(map_actions=actions)))
    assert resp["map_actions"] == [actions[0]]


def test_orchestrator_failure_is_spoken_as_error() -> None:
    class Broken:
        def ask(self, question: TwinQuestion) -> TwinAnswer:
            raise RuntimeError("down")

    status, resp = handle_ask_twin({"question": "x", "language": "en"}, {"x-urbs-voice-secret": "office-secret"}, Broken(), SECRETS)
    assert status == 200
    assert resp["status"] == "error" and resp["run_ids"] == []


def test_briefing_is_office_only() -> None:
    status, resp, orch = call({"question": "brief me", "mode": "briefing", "area": "municipio:1"}, secret="citizen-secret")
    assert status == 200 and resp["status"] == "refused"
    assert orch.calls == []
