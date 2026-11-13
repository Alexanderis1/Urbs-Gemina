"""WS7: the verifier blocks any figure that does not trace to a cited tool run or source."""
from __future__ import annotations

from typing import Any

from agents.envelope import make_envelope
from agents.verifier import verify


def context_run() -> dict[str, Any]:
    return make_envelope(
        tool="context_check",
        inputs={"lon": 12.4823, "lat": 41.896, "radius_m": 300},
        result={"sites": [{"layer": "schools", "name": "Scuola A", "distance_m": 182.4}], "count": 1},
        data_kinds={"schools": "real"},
        sources=[{"id": "roma_geoserver", "retrieved_at": "2026-11-13T10:00:00Z"}],
    )


def field_run(synthetic: bool = False) -> dict[str, Any]:
    return make_envelope(
        tool="estimate_field",
        inputs={"area": "point"},
        result={"p5": 0.8, "p50": 1.4, "p95": 2.6, "exceedance_probability": 0.012, "calibration": "uncalibrated"},
        data_kinds={"emf": "estimated"},
        sources=[{"id": "cartoradio_grid", "retrieved_at": "2026-11-13T10:00:00Z"}],
        synthetic=synthetic,
    )


def runs(*envs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {e["run_id"]: e for e in envs}


def test_run_id_is_deterministic() -> None:
    assert context_run()["run_id"] == context_run()["run_id"]
    assert len(context_run()["run_id"]) == 64


def test_cited_number_passes() -> None:
    r = context_run()
    text = f"One school lies 182 m from the site [run:{r['run_id'][:12]}]. This is context for the officer."
    report = verify(text, runs(r))
    assert report.ok, report.problems


def test_uncited_number_is_blocked() -> None:
    r = context_run()
    report = verify("One school lies 182 m from the site.", runs(r))
    assert not report.ok
    assert report.problems[0].code == "uncited_number"


def test_number_not_in_cited_run_is_blocked() -> None:
    r = context_run()
    report = verify(f"One school lies 95 m from the site [run:{r['run_id'][:12]}].", runs(r))
    assert [p.code for p in report.problems] == ["untraced_number"]


def test_unknown_run_id_is_blocked() -> None:
    report = verify("A school lies 182 m away [run:deadbeef0000].", runs(context_run()))
    assert "unknown_citation" in [p.code for p in report.problems]


def test_estimate_needs_range_and_calibration() -> None:
    f = field_run()
    rid = f["run_id"][:12]
    bad = verify(f"The field is 1.4 V/m [run:{rid}].", runs(f))
    codes = {p.code for p in bad.problems}
    assert {"missing_range", "missing_calibration"} <= codes
    good = verify(
        f"Estimate, not a measurement: median 1.4 V/m, range 0.8 to 2.6 V/m, uncalibrated [run:{rid}]. "
        f"Chance of exceeding the attention value: 1.2% [run:{rid}].",
        runs(f),
    )
    assert good.ok, good.problems


def test_simulated_data_must_be_named() -> None:
    f = field_run(synthetic=True)
    rid = f["run_id"][:12]
    text = f"Estimate: median 1.4 V/m, range 0.8 to 2.6 V/m, uncalibrated [run:{rid}]."
    assert "missing_simulated_label" in {p.code for p in verify(text, runs(f)).problems}
    assert verify(text + " Based on simulated antenna data.", runs(f)).ok


def test_decision_words_are_blocked() -> None:
    r = context_run()
    report = verify(f"The antenna is prohibited because a school is 182 m away [run:{r['run_id'][:12]}].", runs(r))
    assert "decision_language" in {p.code for p in report.problems}


def test_names_like_5g_and_p95_are_not_figures() -> None:
    assert verify("This 5G site needs the P95 value, which is not available yet.", {}).ok


def test_source_citation_allows_number_from_its_snippet() -> None:
    legal = make_envelope(
        tool="legal_lookup",
        inputs={"question": "attention value"},
        result={"results": [{"url": "https://www.normattiva.it/x", "title": "Legge 214/2023", "snippet": "valore di attenzione 15 V/m"}]},
        data_kinds={"law": "real"},
        sources=[{"id": "exa", "url": "https://www.normattiva.it/x", "retrieved_at": "2026-11-13T10:00:00Z"}],
    )
    ok = verify("The attention value is 15 V/m [src:https://www.normattiva.it/x].", runs(legal))
    assert ok.ok, ok.problems
    bad = verify("The attention value is 6 V/m [src:https://www.normattiva.it/x].", runs(legal))
    assert not bad.ok


def test_italian_decimal_comma() -> None:
    f = field_run()
    rid = f["run_id"][:12]
    text = f"Stima, non una misura: mediana 1,4 V/m, intervallo 0,8 - 2,6 V/m, non calibrato [run:{rid}]."
    assert verify(text, runs(f)).ok


def test_not_available_run_cannot_vouch_for_numbers() -> None:
    na = make_envelope(tool="estimate_field", inputs={"area": "x"}, result={"p50": 1.4}, data_kinds={"emf": "not_available"},
                       sources=[], status="not_available", reason="cartoradio window unreadable")
    assert na["status"] == "not_available" and na["reason"] and na["cached"] is False
    report = verify(f"The field is 1.4 V/m [run:{na['run_id'][:12]}].", runs(na))
    assert "untraced_number" in {p.code for p in report.problems}


def test_envelope_check_accepts_hub_additions() -> None:
    from agents.envelope import check_envelope

    assert check_envelope(context_run()) == []
    bad = dict(context_run(), status="maybe")
    assert check_envelope(bad)
