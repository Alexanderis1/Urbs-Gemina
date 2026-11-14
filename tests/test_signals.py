"""Citizen reports merged into candidate live events (twin/tools/signals.py)."""
from __future__ import annotations

import math
from typing import Any

import pytest

from twin.tools.signals import (
    cluster_reports,
    load_signal_config,
    parse_reports,
    score_cluster,
    signal_events,
    twin_evidence,
)

LON, LAT = 12.4823, 41.8960
M_LAT = 111_195.0
M_LON = M_LAT * math.cos(math.radians(LAT))


def at(east_m: float, north_m: float) -> tuple[float, float]:
    return LON + east_m / M_LON, LAT + north_m / M_LAT


def rep(rid: str, category: str = "flood", east: float = 0, north: float = 0, minute: int = 0,
        reporter: str | None = None, photo: bool = False, text: str = "acqua alta") -> dict[str, Any]:
    lon, lat = at(east, north)
    return {"id": rid, "category": category, "lon": lon, "lat": lat,
            "time": f"2026-11-14T05:{minute:02d}:00Z", "reporter": reporter or f"r-{rid}",
            "has_photo": photo, "text": text, "photo_gps_distance_m": 30.0, "photo_age_min": 3.0}


@pytest.fixture(scope="module")
def cfg() -> dict[str, Any]:
    return load_signal_config()


def test_config_has_every_category_and_a_basis(cfg: dict[str, Any]) -> None:
    for cat in ("flood", "pothole", "traffic", "roadworks", "public_event"):
        assert cfg["categories"][cat]["radius_m"] > 0
        assert cat in cfg["twin_checks"]
    assert "basis" in cfg["confidence"] and "basis" in cfg["categories"]


def test_nearby_reports_of_same_category_merge(cfg: dict[str, Any]) -> None:
    reports = parse_reports([rep("a"), rep("b", east=120, minute=5), rep("c", north=-100, minute=9)], cfg)
    clusters = cluster_reports(reports, cfg)
    assert len(clusters) == 1
    assert clusters[0].report_ids == ["a", "b", "c"]


def test_far_apart_or_other_category_or_late_reports_stay_separate(cfg: dict[str, Any]) -> None:
    raw = [rep("a"), rep("far", east=2000), rep("fire", category="pothole", minute=1),
           rep("late", category="traffic", minute=0), rep("late2", category="traffic", minute=0)]
    raw[-1]["time"] = "2026-11-14T08:00:00Z"  # 3 h later, window is 90 min
    clusters = cluster_reports(parse_reports(raw, cfg), cfg)
    assert sorted(len(c.report_ids) for c in clusters) == [1, 1, 1, 1, 1]


def test_same_reporter_counts_once(cfg: dict[str, Any]) -> None:
    reports = parse_reports([rep("a", reporter="x"), rep("b", reporter="x", minute=2), rep("c", reporter="x", minute=3)], cfg)
    [cluster] = cluster_reports(reports, cfg)
    assert cluster.n_reports == 3 and cluster.n_reporters == 1


def test_confidence_rises_with_independent_reporters(cfg: dict[str, Any]) -> None:
    one = cluster_reports(parse_reports([rep("a")], cfg), cfg)[0]
    three = cluster_reports(parse_reports([rep("a"), rep("b", minute=1), rep("c", minute=2)], cfg), cfg)[0]
    p1 = score_cluster(one, cfg)["confidence"]
    p3 = score_cluster(three, cfg)["confidence"]
    assert 0.2 < p1 < 0.4  # one report alone stays 'unconfirmed'
    assert p3 > 0.75
    assert score_cluster(one, cfg)["level"] == "unconfirmed"
    assert score_cluster(three, cfg)["level"] == "likely"


def test_reporter_cap(cfg: dict[str, Any]) -> None:
    many = [rep(str(i), minute=i) for i in range(20)]
    five = [rep(str(i), minute=i) for i in range(5)]
    c20 = cluster_reports(parse_reports(many, cfg), cfg)[0]
    c5 = cluster_reports(parse_reports(five, cfg), cfg)[0]
    assert score_cluster(c20, cfg)["confidence"] == score_cluster(c5, cfg)["confidence"]


def test_twin_and_checks_move_confidence_both_ways(cfg: dict[str, Any]) -> None:
    [c] = cluster_reports(parse_reports([rep("a", photo=True)], cfg), cfg)
    base = score_cluster(c, cfg)["confidence"]
    support = [{"layer": "rain", "verdict": "supports", "lr": 3.0}]
    against = [{"layer": "rain", "verdict": "contradicts", "lr": 0.8}]
    assert score_cluster(c, cfg, twin=support)["confidence"] > base
    assert score_cluster(c, cfg, twin=against)["confidence"] < base
    good = score_cluster(c, cfg, checks={"photo": "consistent", "news": "confirms"})
    bad = score_cluster(c, cfg, checks={"photo": "inconsistent", "news": "no_match"})
    assert good["confidence"] > 0.75 > base > bad["confidence"]
    # Every factor is listed so staff see why
    names = [f["factor"] for f in good["factors"]]
    assert names[0] == "prior" and "photo_check" in names and "news_check" in names


def test_twin_evidence_reads_layers_and_labels_simulated(cfg: dict[str, Any]) -> None:
    [c] = cluster_reports(parse_reports([rep("a", category="traffic")], cfg), cfg)
    calls: list[str] = []

    def read_layer(layer: str, area: dict[str, Any]) -> dict[str, Any]:
        calls.append(layer)
        assert area["type"] == "Polygon"
        if layer == "road_speed":
            return {"status": "ok", "synthetic": True, "result": {"cells": [{"mean": 9.0}, {"mean": 30.0}]}}
        return {"status": "not_available", "reason": "feed down", "result": None}

    ev = twin_evidence(c, cfg, read_layer)
    assert calls == ["road_speed", "transit_delay"]
    speed, delay = ev
    assert speed["verdict"] == "supports" and speed["value"] == 9.0 and speed["simulated_input"] is True
    assert speed["lr"] == pytest.approx(3.0 ** 0.5, abs=1e-3)
    assert delay["verdict"] == "not_available" and delay["lr"] == 1.0


def test_twin_read_failure_never_crashes(cfg: dict[str, Any]) -> None:
    [c] = cluster_reports(parse_reports([rep("a")], cfg), cfg)

    def boom(layer: str, area: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("down")

    [ev] = twin_evidence(c, cfg, boom)
    assert ev["verdict"] == "not_available" and ev["lr"] == 1.0


def test_signal_events_result_is_anonymous_and_sorted(cfg: dict[str, Any]) -> None:
    raw = [rep("a"), rep("b", minute=2), rep("z", category="pothole", east=3000)]
    out = signal_events(raw, cfg, now="2026-11-14T05:30:00Z")
    events = out["events"]
    assert [e["n_reports"] for e in events] == [2, 1]  # most confident first
    first = events[0]
    assert first["id"].startswith("sig-") and first["category_label"] == "Allagamento o fogna"
    assert "r-a" not in str(first) and "r-b" not in str(first)  # reporter keys never leave the tool
    assert first["texts"] == ["acqua alta", "acqua alta"]
    assert first["stale"] is False
    assert out["n_reports"] == 3


def test_bad_reports_are_dropped_with_a_warning(cfg: dict[str, Any]) -> None:
    raw = [rep("a"), {**rep("b"), "category": "alien"}, {**rep("c"), "lon": 99.0}]
    out = signal_events(raw, cfg, now="2026-11-14T05:30:00Z")
    assert out["n_reports"] == 1
    assert len(out["warnings"]) == 2


def test_cluster_id_is_stable_when_reports_are_added(cfg: dict[str, Any]) -> None:
    a = signal_events([rep("a")], cfg, now="2026-11-14T05:30:00Z")["events"][0]["id"]
    b = signal_events([rep("a"), rep("b", minute=3)], cfg, now="2026-11-14T05:30:00Z")["events"][0]["id"]
    assert a == b


# --- tool API ---------------------------------------------------------------------------------------------

def _client() -> Any:
    from pathlib import Path
    import tempfile

    from fastapi.testclient import TestClient

    from twin.api.app import create_app
    from twin.tools.layers import LayerStore
    from twin.tools.runtime import ToolRuntime
    from twin.tools.settings import Settings

    rt = ToolRuntime(settings=Settings.load(), store=LayerStore(raw_dir=Path(tempfile.mkdtemp())))
    rt.providers = {}
    return TestClient(create_app(rt, api_keys={"office-key": "office"}))


def test_signal_events_tool_is_office_only_and_returns_events() -> None:
    client = _client()
    body = {"reports": [rep("a"), rep("b", minute=3)], "check_twin": False, "now": "2026-11-14T05:30:00Z"}
    citizen = client.post("/tools/signal_events", json=body).json()
    assert citizen["status"] == "refused"
    office = client.post("/tools/signal_events", json=body, headers={"Authorization": "Bearer office-key"}).json()
    assert office["status"] == "ok"
    [event] = office["result"]["events"]
    assert event["n_reports"] == 2 and event["level"] == "probable"
    assert office["data_kinds"]["citizen_reports"] == "real"


def test_signal_events_with_checks_folds_verdicts_in() -> None:
    client = _client()
    first = client.post("/tools/signal_events", json={"reports": [rep("a")], "check_twin": False},
                        headers={"Authorization": "Bearer office-key"}).json()["result"]["events"][0]
    body = {"reports": [rep("a")], "check_twin": False, "checks": {first["id"]: {"photo": "consistent", "news": "confirms"}}}
    second = client.post("/tools/signal_events", json=body, headers={"Authorization": "Bearer office-key"}).json()
    assert second["result"]["events"][0]["confidence"] > first["confidence"]


def test_verify_signal_is_office_only() -> None:
    client = _client()
    body = {"event": {"id": "sig-1", "category": "flood", "lon": 12.48, "lat": 41.89,
                      "first_seen": "2026-11-14T05:00:00Z", "texts": ["acqua"]}}
    assert client.post("/tools/verify_signal", json=body).json()["status"] == "refused"


# --- photo location and time vs device GPS (14 Nov: a report needs both) -------------------------------------

def test_photo_location_check_labels(cfg: dict[str, Any]) -> None:
    from twin.tools.signals import location_check

    assert location_check(40.0, 5.0, cfg) == "match"
    assert location_check(5000.0, 5.0, cfg) == "mismatch"      # photo taken elsewhere
    assert location_check(40.0, 60 * 24 * 3, cfg) == "mismatch"  # old photo from the gallery
    assert location_check(None, None, cfg) == "missing"


def test_mismatched_photo_does_not_raise_confidence(cfg: dict[str, Any]) -> None:
    good = [rep("a", photo=True), rep("b", minute=1, photo=True)]
    bad = [{**r, "photo_gps_distance_m": 8000.0, "photo_age_min": 2.0} for r in good]
    good = [{**r, "photo_gps_distance_m": 30.0, "photo_age_min": 2.0} for r in good]
    p_good = signal_events(good, cfg, now="2026-11-14T05:30:00Z")["events"][0]
    p_bad = signal_events(bad, cfg, now="2026-11-14T05:30:00Z")["events"][0]
    assert p_good["confidence"] > p_bad["confidence"]
    assert p_bad["n_location_mismatch"] == 2 and p_good["n_location_match"] == 2
    assert p_bad["confidence"] <= cfg["confidence"]["prior"] + 1e-9


# --- round 2 (14 Nov): Alessandro's report types -------------------------------------------------------------

def test_public_events_are_listed_without_a_score(cfg: dict[str, Any]) -> None:
    raw = [rep("e1", category="public_event"), rep("e2", category="public_event", minute=4)]
    [event] = signal_events(raw, cfg, now="2026-11-14T05:30:00Z")["events"]
    assert event["scored"] is False and event["confidence"] is None and event["level"] == "not_scored"
    assert event["n_reports"] == 2


def test_subtypes_are_counted(cfg: dict[str, Any]) -> None:
    raw = [{**rep("a", category="traffic"), "subtype": "bus"}, {**rep("b", category="traffic", minute=2), "subtype": "bus"},
           {**rep("c", category="traffic", minute=3), "subtype": "incident"}, {**rep("d", category="traffic", minute=4), "subtype": "nonsense"}]
    out = signal_events(raw, cfg, now="2026-11-14T05:30:00Z")
    [event] = out["events"]
    assert event["subtypes"] == {"bus": 2, "incident": 1}
    assert event["n_reports"] == 4  # an unknown subtype keeps the report, without the subtype


def test_potholes_a_week_apart_are_the_same_hole(cfg: dict[str, Any]) -> None:
    a = rep("a", category="pothole")
    b = {**rep("b", category="pothole", east=10), "time": "2026-11-18T05:00:00Z"}
    far = {**rep("c", category="pothole", east=80), "time": "2026-11-14T06:00:00Z"}
    events = signal_events([a, b, far], cfg, now="2026-11-18T06:00:00Z")["events"]
    assert sorted(e["n_reports"] for e in events) == [1, 2]


def test_screen_report_tool_is_office_only() -> None:
    client = _client()
    body = {"category": "pothole", "text": "Buca davanti al civico 3"}
    assert client.post("/tools/screen_report", json=body).json()["status"] == "refused"
