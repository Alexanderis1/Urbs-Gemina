from datetime import datetime, timedelta, timezone

import pytest

from twin.beliefs.api import build_layer, exceedance_probability, layer_geojson, not_available, query, snapshot_hash
from twin.beliefs.calibration import CalibrationReport
from twin.beliefs.grid import cells_in_bbox
from twin.providers.simulated.loops import SimLoopsProvider

T0 = datetime(2026, 11, 13, 7, 0, tzinfo=timezone.utc)
CENTRE = (12.40, 41.85, 12.60, 41.95)


def road_layer():  # type: ignore[no-untyped-def]
    cells = cells_in_bbox(CENTRE, 9)
    provider = SimLoopsProvider(area=CENTRE, n_stations=20)
    return build_layer("road_speed", cells, provider, T0, T0 + timedelta(minutes=30))


def test_build_layer_from_a_provider_marks_simulated_data() -> None:
    layer = road_layer()
    out = query(layer)
    assert out["data_kinds"] == {"road_speed": "simulated"}
    assert out["synthetic"] is True
    assert out["sources"][0]["id"] == "sim_loops"
    assert out["result"]["calibration"] == "uncalibrated"
    assert out["result"]["unit"] == "km/h"
    assert out["result"]["n_observations"] == 20 * 7
    row = out["result"]["cells"][0]
    assert set(row) >= {"cell", "mean", "sd", "p5", "p50", "p95", "updated_at", "staleness_s"}


def test_query_a_subset_with_threshold_gives_exceedance() -> None:
    layer = road_layer()
    some = list(layer.cells[:5])
    out = query(layer, some, threshold=25.0)
    assert [r["cell"] for r in out["result"]["cells"]] == some
    for row in out["result"]["cells"]:
        assert 0.0 <= row["p_exceed"] <= 1.0
    assert out["inputs"]["threshold"] == 25.0


def test_unknown_cells_give_a_warning_not_a_crash() -> None:
    layer = road_layer()
    out = query(layer, ["8928308280fffff"])
    assert out["result"]["cells"] == []
    assert any("not in layer" in w for w in out["warnings"])


def test_calibration_report_shows_up() -> None:
    layer = road_layer()
    report = CalibrationReport(status="calibrated", reason="ok", n_predictions=10, coverage=0.9, z_mean=0.0, z_sd=1.0, rmse=1.0)
    out = query(layer.with_calibration(report))
    assert out["result"]["calibration"] == "calibrated"
    assert out["result"]["calibration_report"]["coverage"] == 0.9


def test_exceedance_probability() -> None:
    assert exceedance_probability(10.0, 4.0, 10.0) == pytest.approx(0.5)
    assert exceedance_probability(10.0, 4.0, 14.0) == pytest.approx(0.1587, abs=1e-3)
    assert exceedance_probability(10.0, 0.0, 9.0) == 1.0


def test_geojson_has_one_hexagon_per_cell() -> None:
    layer = road_layer()
    gj = layer_geojson(layer, list(layer.cells[:3]))
    assert gj["type"] == "FeatureCollection"
    assert len(gj["features"]) == 3
    f = gj["features"][0]
    assert f["geometry"]["type"] == "Polygon"
    assert f["properties"]["synthetic"] is True
    assert {"mean", "sd", "p5", "p95"} <= set(f["properties"])


def test_snapshot_hash_is_stable_and_changes_with_data() -> None:
    a = road_layer()
    b = road_layer()
    assert snapshot_hash(a) == snapshot_hash(b)
    later = a.at(a.as_of + timedelta(hours=1))
    assert snapshot_hash(later) != snapshot_hash(a)


def test_gate_e_updates_shows_uncertainty_and_decays_when_paused() -> None:
    layer = road_layer()
    prior_sd = layer.spec.prior.sd
    sd = layer.variance**0.5
    # Updates: cells near stations are much surer than the prior; far cells are not.
    assert sd.min() < 0.2 * prior_sd
    assert sd.max() == pytest.approx(prior_sd, rel=0.01)
    # Decay: with the feed paused for 3 time constants the layer is close to the prior again.
    paused = layer.at(layer.as_of + timedelta(hours=3 * layer.spec.relax_tau_hours))
    assert (paused.variance**0.5).min() > 0.9 * prior_sd
    stale = query(paused, list(layer.cells[:1]))["result"]["cells"][0]
    fresh_cells = [c for c in layer.cells if layer.cell_updated_at(c) is not None]
    assert fresh_cells
    assert query(paused, fresh_cells[:1])["result"]["cells"][0]["staleness_s"] >= 3 * 1800
    assert stale["sd"] >= 0.9 * prior_sd


def test_query_reports_status_ok() -> None:
    out = query(road_layer())
    assert out["status"] == "ok"
    assert out["reason"] is None


def test_not_available_payload() -> None:
    out = not_available("air_no2", "provider eea_hourly is not configured yet")
    assert out["status"] == "not_available"
    assert out["data_kinds"] == {"air_no2": "not_available"}
    assert out["result"] == {}
    assert "eea_hourly" in out["reason"]
