"""Maintenance mission planner (twin/tools/maintenance.py): crews routed by distance and priority."""
from __future__ import annotations

from typing import Any

import pytest

from twin.tools.maintenance import plan_maintenance
from twin.tools.signals import load_signal_config


@pytest.fixture(scope="module")
def cfg() -> dict[str, Any]:
    return load_signal_config()


def ev(i: int, kind: str, lon: float, lat: float, conf: float = 0.8, scored: bool = True) -> dict[str, Any]:
    return {"id": f"e{i}", "category": kind, "lon": lon, "lat": lat, "confidence": conf, "scored": scored,
            "category_label": kind}


EAST = [ev(i, "pothole", 12.55 + 0.002 * i, 41.89 + 0.001 * i) for i in range(6)]
NORTH = [ev(10 + i, "flood", 12.49 + 0.002 * i, 41.95 - 0.001 * i) for i in range(3)]


def test_routes_cover_every_item_once_and_save_on_one_trip_each(cfg: dict[str, Any]) -> None:
    out = plan_maintenance(EAST + NORTH, cfg, crews={"roads": 2, "sewers": 1})
    served = [s["id"] for r in out["routes"] for s in r["stops"]]
    assert sorted(served) == sorted(e["id"] for e in EAST + NORTH)
    assert out["unserved"] == []
    assert out["total"]["km"] < out["baseline"]["km"]
    assert 0 < out["savings"]["cost_pct"] < 100
    # Sewer problems go to the sewer crew, potholes to road crews
    for r in out["routes"]:
        kinds = {s["kind"] for s in r["stops"]}
        assert kinds <= ({"pothole", "roadworks"} if r["crew_type"] == "roads" else {"flood"})


def test_low_confidence_and_public_events_are_left_out(cfg: dict[str, Any]) -> None:
    items = [ev(1, "pothole", 12.55, 41.89, conf=0.2), ev(2, "public_event", 12.5, 41.9, conf=0, scored=False),
             ev(3, "traffic", 12.5, 41.9), ev(4, "pothole", 12.551, 41.891, conf=0.2)]
    items[3]["confirmed"] = True  # an officer confirmed it: always planned
    out = plan_maintenance(items, cfg, crews={"roads": 1, "sewers": 1})
    assert [s["id"] for r in out["routes"] for s in r["stops"]] == ["e4"]
    assert {x["id"] for x in out["skipped"]} == {"e1", "e2", "e3"}


def test_shift_limit_leaves_work_for_the_next_shift(cfg: dict[str, Any]) -> None:
    many = [ev(i, "pothole", 12.45 + 0.01 * (i % 10), 41.85 + 0.01 * (i // 10)) for i in range(40)]
    out = plan_maintenance(many, cfg, crews={"roads": 1, "sewers": 0})
    [route] = out["routes"]
    assert route["hours"] <= cfg["maintenance"]["shift_hours"] + 1e-6
    assert len(route["stops"]) + len(out["unserved"]) == 40 and out["unserved"]


def test_same_input_same_plan(cfg: dict[str, Any]) -> None:
    a = plan_maintenance(EAST + NORTH, cfg, crews={"roads": 2, "sewers": 1})
    b = plan_maintenance(list(reversed(EAST + NORTH)), cfg, crews={"roads": 2, "sewers": 1})
    assert a == b


def test_higher_priority_is_served_first_when_time_is_short(cfg: dict[str, Any]) -> None:
    far_sure = ev(1, "pothole", 12.60, 41.80, conf=0.95)
    near_unsure = [ev(10 + i, "pothole", 12.56 + 0.003 * i, 41.89, conf=0.5) for i in range(12)]
    out = plan_maintenance([far_sure, *near_unsure], cfg, crews={"roads": 1, "sewers": 0}, shift_hours=2.5)
    served = [s["id"] for r in out["routes"] for s in r["stops"]]
    assert "e1" in served


def test_plan_maintenance_tool_is_office_only() -> None:
    from tests.test_signals import _client

    client = _client()
    body = {"events": [{"id": "e1", "category": "pothole", "lon": 12.55, "lat": 41.89, "confidence": 0.8}],
            "crews": {"roads": 1, "sewers": 0}}
    assert client.post("/tools/plan_maintenance", json=body).json()["status"] == "refused"
    office = client.post("/tools/plan_maintenance", json=body, headers={"Authorization": "Bearer office-key"}).json()
    assert office["status"] == "ok" and office["result"]["total"]["stops"] == 1
    assert office["data_kinds"]["crew_routes"] == "estimated"


def test_merging_duplicate_reports_is_part_of_the_saving(cfg: dict[str, Any]) -> None:
    one = plan_maintenance([{**ev(1, "pothole", 12.55, 41.89), "n_reports": 1}], cfg, crews={"roads": 1})
    three = plan_maintenance([{**ev(1, "pothole", 12.55, 41.89), "n_reports": 3}], cfg, crews={"roads": 1})
    assert three["total"] == one["total"]
    assert three["baseline"]["km"] == pytest.approx(3 * one["baseline"]["km"], rel=0.02)
