"""Antenna what-if: baseline (Cartoradio) vs variant (baseline + new antenna)."""
import math
from pathlib import Path
from typing import Any

import pytest

from twin.scenarios import antenna, engine
from twin.scenarios.antenna import combine_lognormal
from twin.scenarios.data import FieldSample, ScenarioData
from twin.tools.emf import free_space_field

LON, LAT = 12.4823, 41.8960
SITE = {"lon": LON, "lat": LAT, "height_m": 25.0}
ADD = {"action": "add", "site": SITE, "eirp_w": 2000.0}


@pytest.fixture(autouse=True)
def free_space_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Most tests pin the free-space engine so their numbers hold whether or not twin/physics is installed."""
    monkeypatch.setattr(antenna, "physics_engine", lambda: None)


def flat_baseline(value: float) -> ScenarioData:
    return ScenarioData(baseline_field=lambda lon, lat: FieldSample(value, 4.0), baseline_kind="estimated",
                        baseline_source={"id": "cartoradio_grid", "retrieved_at": "2026-11-13T00:00:00Z"})


def test_combining_with_a_zero_source_keeps_the_other() -> None:
    median, sigma = combine_lognormal([(2.0, 4.0), (0.0, 4.0)])
    assert median == pytest.approx(2.0, rel=1e-6)
    assert sigma == pytest.approx(4.0, rel=1e-6)


def test_combined_median_is_close_to_root_sum_square() -> None:
    median, sigma = combine_lognormal([(3.0, 4.0), (4.0, 4.0)])
    assert 4.5 < median < 5.6  # rss of medians is 5.0; lognormal sum shifts it slightly
    assert sigma < 4.0  # averaging two independent errors narrows the spread


def test_add_antenna_raises_the_field_everywhere(tmp_path: Path) -> None:
    out = engine.run("antenna", "city", ADD, data=flat_baseline(1.0), cache_dir=tmp_path)
    points = out["result"]["points"]
    assert len(points) > 300
    for p in points:
        assert p["variant"]["p50"] >= p["baseline"]["p50"] - 1e-9
        assert p["variant"]["p5"] <= p["variant"]["p50"] <= p["variant"]["p95"]
        assert 0.0 <= p["variant"]["p_exceed_attention"] <= 1.0


def test_peak_is_below_the_mast_and_matches_free_space(tmp_path: Path) -> None:
    out = engine.run("antenna", "city", ADD, data=ScenarioData(), cache_dir=tmp_path)
    peak = max(out["result"]["points"], key=lambda p: p["variant"]["p50"])
    assert peak["distance_m"] == pytest.approx(0.0, abs=1.0)
    # no baseline: variant equals the new antenna alone, 23.5 m above the receptor
    assert peak["variant"]["p50"] == pytest.approx(free_space_field(2000.0, 23.5), abs=1e-3)


def test_thresholds_come_from_config(tmp_path: Path) -> None:
    out = engine.run("antenna", "city", ADD, data=flat_baseline(1.0), cache_dir=tmp_path)
    thresholds = out["result"]["thresholds"]
    assert thresholds["attention_value_v_per_m"]["value"] == 15.0
    assert thresholds["exposure_limit_v_per_m"]["value"] == 20.0
    assert "214" in thresholds["attention_value_v_per_m"]["source"]


def test_powerful_close_antenna_is_flagged(tmp_path: Path) -> None:
    change = {"action": "add", "site": {**SITE, "height_m": 6.0}, "eirp_w": 5000.0}
    out = engine.run("antenna", "city", change, data=flat_baseline(1.0), cache_dir=tmp_path)
    summary = out["result"]["summary"]
    assert summary["variant"]["points_flagged_attention"] > 0
    assert summary["baseline"]["points_flagged_attention"] == 0
    assert summary["variant"]["max_p50_v_per_m"] > 15.0


def test_band_reads_eirp_from_config(tmp_path: Path) -> None:
    by_band = engine.run("antenna", "city", {"action": "add", "site": SITE, "band": "1800"},
                         data=ScenarioData(), cache_dir=tmp_path)
    by_value = engine.run("antenna", "city", ADD, data=ScenarioData(), cache_dir=tmp_path)
    assert by_band["result"]["summary"]["variant"]["max_p50_v_per_m"] == pytest.approx(
        by_value["result"]["summary"]["variant"]["max_p50_v_per_m"])
    assert any("assumption" in w for w in by_band["warnings"])


def test_missing_baseline_is_said_not_hidden(tmp_path: Path) -> None:
    out = engine.run("antenna", "city", ADD, data=ScenarioData(), cache_dir=tmp_path)
    assert out["data_kinds"]["emf_baseline"] == "not_available"
    assert any("baseline" in w.lower() for w in out["warnings"])
    assert out["result"]["calibration"] == "uncalibrated"


def test_move_removes_the_old_site_estimated_from_cartoradio(tmp_path: Path) -> None:
    old = {"lon": LON + 0.003, "lat": LAT, "height_m": 25.0}
    change = {"action": "move", "site": SITE, "eirp_w": 2000.0, "from": {**old, "eirp_w": 2000.0}}
    out = engine.run("antenna", "city", change, data=flat_baseline(3.0), cache_dir=tmp_path)
    near_old = min(out["result"]["points"], key=lambda p: math.hypot(p["lon"] - old["lon"], p["lat"] - old["lat"]))
    assert near_old["variant"]["p50"] < near_old["baseline"]["p50"]
    assert out["synthetic"] is False  # only traffic loops may be simulated
    assert out["data_kinds"]["existing_site"] == "estimated"
    assert any("fitted to cartoradio" in w.lower() for w in out["warnings"])
    assert any("direction is unknown" in w and "uncalibrated" in w for w in out["warnings"])
    # the 9 dB uncertainty of the existing site widens the range where its removed share is large
    assert max(p["variant"]["sigma_db"] for p in out["result"]["points"]) > 4.0


def test_simulated_baseline_is_not_accepted() -> None:
    with pytest.raises(ValueError, match="baseline_kind"):
        ScenarioData(baseline_field=lambda lon, lat: FieldSample(1.0, 4.0), baseline_kind="simulated")


def test_points_outside_the_area_are_dropped(tmp_path: Path) -> None:
    d = 100.0 / 111_195.0
    tiny = {"type": "Polygon", "coordinates": [[[LON - d, LAT - d], [LON + d, LAT - d], [LON + d, LAT + d],
                                                [LON - d, LAT + d], [LON - d, LAT - d]]]}
    out = engine.run("antenna", tiny, ADD, data=ScenarioData(), cache_dir=tmp_path)
    assert 0 < len(out["result"]["points"]) < 100


def test_bad_change_is_rejected() -> None:
    with pytest.raises(ValueError):
        engine.run("antenna", "city", {"action": "add", "site": SITE})  # no eirp_w or band


def _fake_engine(value: float, sigma: float, calls: list[dict[str, Any]]) -> Any:
    def run(site: Any, points: Any, receptor_h: float) -> tuple[list[tuple[float, float]], str]:
        calls.append({"site": dict(site), "points": len(points), "receptor_h": receptor_h})
        return [(value, sigma)] * len(points), "building_aware"
    return run


def test_building_aware_physics_replaces_free_space(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(antenna, "physics_engine", lambda: _fake_engine(0.5, 6.0, calls))
    sectors = [{"azimuth_deg": 0}, {"azimuth_deg": 120}, {"azimuth_deg": 240}]
    change = {**ADD, "band": "1800", "site": {**SITE, "sectors": sectors}}
    out = engine.run("antenna", "city", change, data=ScenarioData(), cache_dir=tmp_path)
    r = out["result"]
    assert r["model"] == "building_aware"
    peak = max(r["points"], key=lambda p: p["variant"]["p50"])
    assert peak["variant"]["p50"] == pytest.approx(0.5, rel=1e-6)  # far below free space under the mast
    assert calls and calls[0]["site"]["sectors"] == sectors and calls[0]["site"]["eirp_w"] == 2000.0
    assert calls[0]["receptor_h"] == 1.5
    assert out["data_kinds"]["field_model"] == "estimated"
    assert any("buildings" in w and "3GPP" in w for w in out["warnings"])


def test_physics_failure_falls_back_to_free_space(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def broken() -> Any:
        def run(site: Any, points: Any, receptor_h: float) -> Any:
            raise RuntimeError("city model unreadable")
        return run
    monkeypatch.setattr(antenna, "physics_engine", broken)
    out = engine.run("antenna", "city", ADD, data=ScenarioData(), cache_dir=tmp_path)
    assert out["result"]["model"] == "free_space_isotropic"
    peak = max(out["result"]["points"], key=lambda p: p["variant"]["p50"])
    assert peak["variant"]["p50"] == pytest.approx(free_space_field(2000.0, 23.5), abs=1e-3)
    assert any("city model unreadable" in w for w in out["warnings"])


def test_real_physics_engine_stays_below_free_space(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pytest.importorskip("twin.physics.api")
    monkeypatch.setattr(antenna, "physics_engine", antenna.default_physics_engine)
    out = engine.run("antenna", "city", ADD, data=ScenarioData(), cache_dir=tmp_path, use_cache=False)
    r = out["result"]
    assert r["model"] in ("building_aware", "raytrace", "open_ground")
    peak = max(r["points"], key=lambda p: p["variant"]["p50"])
    assert 0 < peak["variant"]["p50"] <= free_space_field(2000.0, 23.5) * 1.05
