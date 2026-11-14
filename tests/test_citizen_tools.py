"""Citizen services: air and EMF here, city heat maps (numbers from layers, levels from config)."""
from datetime import datetime
from pathlib import Path
from typing import Any

import h3
import pytest

from twin.beliefs.config import grid_resolution
from twin.tools import citizen
from twin.tools.envelope import ToolError
from twin.tools.layers import LayerStore
from twin.tools.runtime import ToolRuntime
from twin.tools.settings import Settings

POINT = [12.4823, 41.8960]  # Piazza Venezia
CELL = h3.latlng_to_cell(POINT[1], POINT[0], grid_resolution())
NEIGHBOURS = sorted(h3.grid_disk(CELL, 2))


@pytest.fixture()
def rt(tmp_path: Path) -> ToolRuntime:
    citizen._CACHE.clear()
    return ToolRuntime(settings=Settings.load(), store=LayerStore(raw_dir=tmp_path / "raw"))


def fake_build(values: dict[str, float], kind: str = "estimated", calls: list[str] | None = None) -> Any:
    def build(rt: ToolRuntime, layer: str, at: datetime) -> dict[str, Any]:
        if calls is not None:
            calls.append(layer)
        v = values[layer]
        cells = [{"cell": c, "mean": v, "sd": 1.0, "p5": v * 0.8, "p50": v, "p95": v * 1.2} for c in NEIGHBOURS]
        return {"status": "ok", "result": {"cells": cells}, "data_kinds": {layer: kind},
                "sources": [{"id": f"src_{layer}", "retrieved_at": "2026-11-14T08:00:00+00:00"}],
                "warnings": [], "synthetic": kind == "simulated"}
    return build


AIR = {"air_no2": 30.0, "air_pm10": 20.0, "air_pm25": 8.0, "air_o3": 40.0}


def test_band_edges() -> None:
    assert citizen.band(5, [5, 15]) == 1
    assert citizen.band(5.1, [5, 15]) == 2
    assert citizen.band(99, [5, 15]) == 3


def test_air_here_levels_come_from_the_eea_bands(rt: ToolRuntime) -> None:
    env = citizen.air_here(rt, POINT, build=fake_build(AIR))
    assert env["status"] == "ok"
    by_id = {p["id"]: p for p in env["result"]["pollutants"]}
    assert by_id["no2"]["level"]["label_it"] == "Moderata"     # 25 < 30 <= 60
    assert by_id["pm25"]["level"]["label_it"] == "Discreta"    # 5 < 8 <= 15
    assert by_id["o3"]["level"]["index"] == 1
    assert env["result"]["worst"] == "no2"
    assert "moderata" in env["result"]["summary_it"]
    assert {r["name"] for r in by_id["no2"]["references"]} == {"no2_hourly_limit", "no2_annual_limit"}
    assert by_id["no2"]["references"][0]["value"] in (200.0, 40.0)
    assert env["data_kinds"]["air_no2"] == "estimated" and env["synthetic"] is False


def test_one_city_build_per_layer_and_slot(rt: ToolRuntime) -> None:
    calls: list[str] = []
    build = fake_build({**AIR, "emf": 0.5}, calls=calls)
    citizen.air_here(rt, POINT, time="2026-11-14T08:01:00Z", build=build)
    citizen.air_here(rt, POINT, time="2026-11-14T08:07:00Z", build=build)
    citizen.city_heatmap(rt, "air_no2", time="2026-11-14T08:05:00Z", build=build)
    assert sorted(calls) == sorted(AIR)


def test_emf_here_uses_the_legal_attention_value(rt: ToolRuntime) -> None:
    attention = float(rt.settings.thresholds["emf"]["attention_value_v_per_m"]["value"])
    low = citizen.emf_here(rt, POINT, time="2026-11-14T07:00:00Z", build=fake_build({"emf": 0.5}))  # its own slot: builds are cached per hour
    assert low["result"]["level"]["label_it"] == "Molto basso"
    high = citizen.emf_here(rt, POINT, time="2026-11-14T09:00:00Z", build=fake_build({"emf": attention}))
    assert high["result"]["level"]["label_it"] == "Sopra il valore di attenzione"   # judged on the upper end
    assert f"{attention:g} V/m" in high["result"]["summary_it"]


def test_point_outside_the_layer_is_not_available(rt: ToolRuntime) -> None:
    env = citizen.emf_here(rt, [12.70, 41.80], build=fake_build({"emf": 0.5}))
    assert env["status"] == "not_available"


def test_heatmap_aggregates_to_coarser_cells(rt: ToolRuntime) -> None:
    env = citizen.city_heatmap(rt, "air_pm10", resolution=7, build=fake_build(AIR))
    result = env["result"]
    assert result["count"] == len({h3.cell_to_parent(c, 7) for c in NEIGHBOURS})
    first = result["cells"][0]
    assert first["value"] == 20.0 and first["level"] == 2 and {"lon", "lat", "low", "high"} <= set(first)
    assert [b["label_it"] for b in result["legend"]][:2] == ["Buona", "Discreta"]
    assert result["legend"][-1]["to"] is None


def test_heatmap_congestion_is_simulated_and_banded(rt: ToolRuntime) -> None:
    env = citizen.city_heatmap(rt, "road_speed", time="2099-01-01T08:00:00Z",
                               build=fake_build({"road_speed": 15.0}, kind="simulated"))
    assert env["synthetic"] is True
    per_cell, default = citizen._free_flow(rt)
    for cell in env["result"]["cells"][:3]:
        children = [c for c in NEIGHBOURS if h3.cell_to_parent(c, h3.get_resolution(cell["cell"])) == cell["cell"]]
        free = sum((per_cell or {}).get(c, default) for c in children) / len(children)
        assert cell["level"] == citizen.congestion_level(rt, 15.0, free)["index"]
    assert env["result"]["predicted"] is True


def test_heatmap_rejects_unknown_layer(rt: ToolRuntime) -> None:
    with pytest.raises(ToolError):
        citizen.city_heatmap(rt, "schools_state")


def test_prewarm_builds_the_configured_layers(rt: ToolRuntime, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(citizen, "_build_city", fake_build({**AIR, "emf": 0.5}, calls=calls))
    done = citizen.prewarm(rt)
    assert set(done) == set(rt.settings.tools["citizen"]["prewarm_layers"]) and set(done.values()) == {"ok"}
    assert sorted(calls) == sorted(done)
