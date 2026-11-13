from datetime import datetime, timedelta, timezone

import pytest

from twin.beliefs.cell import Belief, relax, update
from twin.beliefs.config import LayerSpec, PriorSpec, load_specs
from twin.beliefs.grid import cell_of, cells_in_bbox
from twin.beliefs.layer import assimilate, prior_layer
from twin.providers.base import Observation

T0 = datetime(2026, 11, 13, 8, 0, tzinfo=timezone.utc)
WINDOW = (12.46, 41.88, 12.50, 41.91)


def spec(correlation_length_km: float = 1.0, tau_hours: float = 1.0) -> LayerSpec:
    return LayerSpec(
        name="test_speed",
        unit="km/h",
        entity_types=("TrafficFlowObserved",),
        value_key="averageVehicleSpeed",
        prior=PriorSpec(mean=30.0, sd=10.0),
        correlation_length_km=correlation_length_km,
        relax_tau_hours=tau_hours,
        min_value=0.0,
        calibration_method="loso",
        calibration_note="",
    )


def obs(lon: float, lat: float, value: float, sigma: float, at: datetime, entity: str = "s1", synthetic: bool = True) -> Observation:
    return Observation(
        entity_id=entity,
        entity_type="TrafficFlowObserved",
        lon=lon,
        lat=lat,
        observed_at=at,
        values={"averageVehicleSpeed": value},
        sigma={"averageVehicleSpeed": sigma},
        source_id="sim_loops",
        synthetic=synthetic,
    )


def test_prior_layer_has_prior_everywhere() -> None:
    cells = cells_in_bbox(WINDOW, 9)
    layer = prior_layer(spec(), cells, T0)
    assert len(layer.cells) == len(cells)
    assert layer.belief(cells[0]).mean == 30.0
    assert layer.belief(cells[0]).variance == pytest.approx(100.0)
    assert layer.n_observations == 0
    assert layer.cell_updated_at(cells[0]) is None


def test_observation_corrects_its_cell_most_and_far_cells_little() -> None:
    cells = cells_in_bbox(WINDOW, 9)
    layer = prior_layer(spec(correlation_length_km=0.5), cells, T0)
    layer = assimilate(layer, [obs(12.48, 41.895, 50.0, 2.0, T0)])
    here = layer.belief(cell_of(12.48, 41.895, 9))
    near = layer.belief(cell_of(12.485, 41.895, 9))  # about 0.4 km east
    far = layer.belief(cell_of(12.499, 41.909, 9))  # about 2 km away
    assert here.mean > near.mean > far.mean >= 30.0
    assert here.variance < near.variance < far.variance <= 100.0
    assert here.mean == pytest.approx(30.0 + 100.0 / 104.0 * 20.0, rel=1e-6)
    assert far.mean - 30.0 < 0.5
    assert layer.cell_updated_at(cell_of(12.48, 41.895, 9)) == T0
    assert layer.synthetic is True
    assert layer.sources == ("sim_loops",)


def test_tiny_correlation_length_reduces_to_the_cell_kalman_update() -> None:
    cells = cells_in_bbox(WINDOW, 9)
    layer = prior_layer(spec(correlation_length_km=1e-6), cells, T0)
    layer = assimilate(layer, [obs(12.48, 41.895, 50.0, 4.0, T0)])
    expected = update(Belief(30.0, 100.0, T0), 50.0, 16.0, T0)
    got = layer.belief(cell_of(12.48, 41.895, 9))
    assert got.mean == pytest.approx(expected.mean)
    assert got.variance == pytest.approx(expected.variance)
    neighbour = layer.belief(cell_of(12.485, 41.895, 9))
    assert neighbour.mean == pytest.approx(30.0)


def test_two_readings_in_one_cell_are_combined() -> None:
    cells = cells_in_bbox(WINDOW, 9)
    layer = prior_layer(spec(correlation_length_km=1e-6), cells, T0)
    layer = assimilate(layer, [obs(12.48, 41.895, 40.0, 2.0, T0, "a"), obs(12.48, 41.895, 60.0, 2.0, T0, "b")])
    got = layer.belief(cell_of(12.48, 41.895, 9))
    # Combined reading 50 with noise variance 2, then the usual Kalman pull from the prior (30, var 100).
    assert got.mean == pytest.approx(30.0 + 100.0 / 102.0 * 20.0)


def test_silence_relaxes_back_to_the_prior() -> None:
    cells = cells_in_bbox(WINDOW, 9)
    layer = prior_layer(spec(tau_hours=1.0), cells, T0)
    layer = assimilate(layer, [obs(12.48, 41.895, 50.0, 1.0, T0)])
    cell = cell_of(12.48, 41.895, 9)
    fresh = layer.belief(cell)
    stale = layer.at(T0 + timedelta(hours=1)).belief(cell)
    very_stale = layer.at(T0 + timedelta(hours=24)).belief(cell)
    assert fresh.variance < stale.variance < very_stale.variance
    assert fresh.mean > stale.mean > very_stale.mean
    assert very_stale.mean == pytest.approx(30.0, abs=1e-3)
    assert very_stale.variance == pytest.approx(100.0, rel=1e-3)
    # The anomaly shrinks by e after one time constant.
    assert stale.mean - 30.0 == pytest.approx((fresh.mean - 30.0) / 2.718281828, rel=1e-3)


def test_relax_cell_function() -> None:
    b = Belief(mean=50.0, variance=1.0, updated_at=T0)
    out = relax(b, prior_then=Belief(30.0, 100.0, T0), prior_now=Belief(40.0, 100.0, T0), at=T0, tau_hours=1.0)
    assert out.mean == pytest.approx(60.0)  # same anomaly (+20) on the new prior mean
    assert out.variance == pytest.approx(1.0)


def test_observations_of_other_types_or_keys_or_outside_are_ignored() -> None:
    cells = cells_in_bbox(WINDOW, 9)
    layer = prior_layer(spec(), cells, T0)
    other = Observation("x", "AirQualityObserved", 12.48, 41.895, T0, {"no2": 50.0}, {"no2": 5.0}, "eea", False)
    outside = obs(12.3, 41.7, 80.0, 1.0, T0)
    layer = assimilate(layer, [other, outside])
    assert layer.n_observations == 0
    assert layer.belief(cell_of(12.48, 41.895, 9)).mean == 30.0
    assert any("outside" in w for w in layer.warnings)


def test_readings_arrive_in_time_order() -> None:
    cells = cells_in_bbox(WINDOW, 9)
    layer = prior_layer(spec(correlation_length_km=1e-6, tau_hours=1000.0), cells, T0)
    late = obs(12.48, 41.895, 20.0, 1.0, T0 + timedelta(minutes=10))
    early = obs(12.48, 41.895, 50.0, 1.0, T0 + timedelta(minutes=5))
    layer = assimilate(layer, [late, early])
    assert layer.as_of == T0 + timedelta(minutes=10)
    assert layer.belief(cell_of(12.48, 41.895, 9)).mean < 36.0


def test_values_never_go_below_the_minimum_in_quantiles() -> None:
    from twin.beliefs.api import query

    cells = cells_in_bbox(WINDOW, 9)
    layer = prior_layer(spec(), cells, T0)
    result = query(layer, cells[:1])
    row = result["result"]["cells"][0]
    assert row["p5"] >= 0.0
    assert row["p5"] < row["p50"] < row["p95"]


def test_config_file_loads_all_six_layers() -> None:
    specs = load_specs()
    for name in ("transit_delay", "road_speed", "air_no2", "rain", "emf", "activity"):
        assert name in specs
    assert specs["emf"].calibration_method == "none"
    hourly = specs["road_speed"].prior
    assert hourly.mean_by_hour is not None and len(hourly.mean_by_hour) == 24
