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


def test_numbers_from_the_officers_question_may_be_echoed() -> None:
    r = context_run()
    text = f"Within 300 m of Via del Corso 1, one school lies 182 m away [run:{r['run_id'][:12]}]."
    assert verify(text, runs(r), question="Schools within 300 m of Via del Corso 1?").ok
    assert not verify("Via del Corso 7 has 3 schools.", runs(r), question="Via del Corso 1?").ok


def test_legal_abbreviations_do_not_split_the_sentence() -> None:
    legal = make_envelope(
        tool="legal_lookup", inputs={"question": "q"},
        result={"results": [{"url": "https://www.normattiva.it/x", "title": "Legge 30 dicembre 2023, n. 214", "text": "art. 10: valore di attenzione 15 V/m"}]},
        data_kinds={"law": "real"}, sources=[{"id": "exa", "url": "https://www.normattiva.it/x", "retrieved_at": "2026-11-13T10:00:00Z"}])
    text = "The attention value is 15 V/m in art. 10 of Legge 30 dicembre 2023, n. 214 [src:https://www.normattiva.it/x]."
    assert verify(text, runs(legal)).ok


def test_source_retrieval_date_may_be_quoted() -> None:
    legal = make_envelope(
        tool="legal_lookup", inputs={"question": "q"},
        result={"results": [{"url": "https://www.normattiva.it/x", "title": "Legge 214/2023", "text": "15 V/m"}]},
        data_kinds={"law": "real"}, sources=[{"id": "exa", "url": "https://www.normattiva.it/x", "retrieved_at": "2026-11-13T10:00:00Z"}])
    assert verify("The attention value is 15 V/m (retrieved 2026-11-13) [src:https://www.normattiva.it/x].", runs(legal)).ok


def test_area_names_are_identifiers_not_figures() -> None:
    r = context_run()
    rid = r["run_id"][:12]
    assert verify(f"Entro 300 m da Piazza Venezia (Municipio 1, zona 1A) ci sono siti a 182 m [run:{rid}].", runs(r),
                  question="Cosa c'è entro 300 metri da Piazza Venezia?").ok
    assert verify(f"In municipio I, urban zone 6B, a school is 182 m away [run:{rid}].", runs(r)).ok


def test_citation_at_end_of_line_covers_the_sentences_before_it() -> None:
    r = context_run()
    rid = r["run_id"][:12]
    text = (f"- Scuole: 1 sito, Scuola A, a 182,4 m. Il dato è reale. [run:{rid}]\n"
            f"- Conteggio: 1. [run:{rid}]")
    assert verify(text, runs(r)).ok, verify(text, runs(r)).problems
    # A citation never reaches back across another citation or onto another line.
    two = f"Count 1 [run:{rid}]. Distance 95 m. Real data [run:{rid}]."
    assert not verify(two, runs(r)).ok
    lines = f"A school is 182 m away.\nReal data [run:{rid}]."
    assert "uncited_number" in {p.code for p in verify(lines, runs(r)).problems}


def test_natura_2000_is_a_name() -> None:
    assert verify("Nessun sito Natura 2000 risulta disponibile: insufficient data.", {}).ok


def test_auto_cite_attaches_the_run_that_holds_every_figure_on_a_line() -> None:
    from agents.verifier import auto_cite

    r, f = context_run(), field_run()
    text = "**Siti sensibili: 1**\n- Scuola A: 182,4 m\n- Distanza inventata: 95 m"
    fixed = auto_cite(text, runs(r, f))
    lines = fixed.splitlines()
    assert lines[0].endswith(f"[run:{r['run_id'][:12]}]")
    assert lines[1].endswith(f"[run:{r['run_id'][:12]}]")
    assert "[run:" not in lines[2]  # 95 is in no tool output: left uncited, so still blocked
    report = verify(fixed, runs(r, f))
    assert [p.code for p in report.problems] == ["uncited_number"]


def test_hex_ids_in_prose_are_not_figures() -> None:
    assert verify("The run id is 80811ab03827; insufficient data otherwise.", {}).ok
