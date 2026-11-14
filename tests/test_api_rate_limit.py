"""Expensive endpoints (Claude questions, scenarios) are rate-limited for callers without an office key."""
from __future__ import annotations

from twin.api.ratelimit import RateLimiter


def test_keyless_caller_is_limited_per_client_and_office_is_not() -> None:
    clock = [0.0]
    rl = RateLimiter({"ask": {"per_client": 2, "global": 100, "window_s": 600}}, now=lambda: clock[0])
    assert rl.check("ask", "1.2.3.4", "citizen") is None
    assert rl.check("ask", "1.2.3.4", "citizen") is None
    wait = rl.check("ask", "1.2.3.4", "citizen")
    assert wait is not None and 0 < wait <= 600
    assert rl.check("ask", "5.6.7.8", "citizen") is None  # another visitor
    for _ in range(10):
        assert rl.check("ask", "1.2.3.4", "office") is None
    clock[0] = 601
    assert rl.check("ask", "1.2.3.4", "citizen") is None  # window passed


def test_global_cap_covers_all_keyless_callers() -> None:
    rl = RateLimiter({"scenario": {"per_client": 100, "global": 3, "window_s": 600}}, now=lambda: 0.0)
    for ip in ("a", "b", "c"):
        assert rl.check("scenario", ip, "citizen") is None
    assert rl.check("scenario", "d", "citizen") is not None


def test_unknown_bucket_is_never_limited() -> None:
    rl = RateLimiter({}, now=lambda: 0.0)
    assert rl.check("ask", "x", "citizen") is None


def test_api_answers_429_with_retry_after(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    from twin.api import app as app_module

    monkeypatch.setattr(app_module, "rate_limits", lambda: {"scenario": {"per_client": 1, "global": 100, "window_s": 600}})
    client = TestClient(app_module.create_app(api_keys={"k": "office"}))
    body = {"kind": "nope", "area": "municipio:1", "change": {}}
    first = client.post("/tools/run_scenario", json=body)
    assert first.status_code != 429
    second = client.post("/tools/run_scenario", json=body, headers={"Origin": "https://app.example"})
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) > 0
    assert second.headers.get("access-control-allow-origin") == "*"  # browsers can read the 429
    office = client.post("/tools/run_scenario", json=body, headers={"Authorization": "Bearer k"})
    assert office.status_code != 429


def _fake_modal(monkeypatch, behaviours):  # type: ignore[no-untyped-def]
    import sys
    import types

    calls = {"n": 0}

    class Fn:
        def remote(self, *args):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            b = behaviours.pop(0)
            if isinstance(b, Exception):
                raise b
            return b

    mod = types.SimpleNamespace(Function=types.SimpleNamespace(from_name=lambda app, fn: Fn()))
    monkeypatch.setitem(sys.modules, "modal", mod)
    return calls


def test_worker_start_failure_is_retried_once(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from twin.scenarios import remote
    from twin.scenarios.data import ScenarioData

    calls = _fake_modal(monkeypatch, [ConnectionError("worker starting"), {"status": "ok"}])
    assert remote.call("river_flood", "municipio:1", {}, ScenarioData(), sleep=lambda s: None) == {"status": "ok"}
    assert calls["n"] == 2


def test_bad_input_is_not_retried(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import pytest

    from twin.scenarios import remote
    from twin.scenarios.data import ScenarioData

    calls = _fake_modal(monkeypatch, [ValueError("needs rain_mm"), {"status": "ok"}])
    with pytest.raises(ValueError):
        remote.call("rain_flood", "municipio:1", {}, ScenarioData(), sleep=lambda s: None)
    assert calls["n"] == 1
