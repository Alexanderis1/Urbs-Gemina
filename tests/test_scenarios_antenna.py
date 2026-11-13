"""Antenna what-if: baseline (Cartoradio) vs variant (baseline + new antenna)."""
import math
from pathlib import Path

import pytest

from twin.scenarios import engine
from twin.scenarios.antenna import combine_lognormal
from twin.scenarios.data import FieldSample, ScenarioData
from twin.tools.emf import free_space_field

LON, LAT = 12.4823, 41.8960
SITE = {"lon": LON, "lat": LAT, "height_m": 25.0}
ADD = {"action": "add", "site": SITE, "eirp_w": 2000.0}


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
