"""Sensor fusion: several real sources in one layer, and a real map as the starting point."""
from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest

from twin.beliefs.api import build_layer, layer_payload
from twin.beliefs.config import load_specs
from twin.beliefs.grid import cell_of, cells_in_bbox
from twin.beliefs.layer import assimilate, prior_layer
from twin.providers.base import BBox, Observation, ProviderInfo

T0 = datetime(2026, 11, 13, 8, 0, tzinfo=timezone.utc)
WINDOW = (12.46, 41.88, 12.50, 41.91)
HERE = (12.48, 41.895)


def reading(entity_type: str, key: str, value: float, sigma: float, source: str, synthetic: bool = False,
            lon: float = HERE[0], lat: float = HERE[1], at: datetime = T0) -> Observation:
    return Observation(f"{source}-1", entity_type, lon, lat, at, {key: value}, {key: sigma}, source, synthetic)


class FakeProvider:
    def __init__(self, pid: str, observations: list[Observation], synthetic: bool = False) -> None:
        self._pid, self._obs, self._synthetic = pid, observations, synthetic

    def describe(self) -> ProviderInfo:
        return ProviderInfo(self._pid, "simulated" if self._synthetic else "open", "x", "test", "hourly", self._synthetic)

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        return iter([o for o in self._obs if start <= o.observed_at <= end])


def test_two_real_sources_are_fused_by_their_accuracy() -> None:
    spec = load_specs()["air_no2"]
    cells = cells_in_bbox(WINDOW, 9)
    precise = FakeProvider("eea_hourly", [reading("AirQualityObserved", "no2", 40.0, 2.0, "eea_hourly")])
    rough = FakeProvider("sensor_community", [reading("AirQualityObserved", "no2", 80.0, 20.0, "sensor_community")])
    layer = build_layer("air_no2", cells, [precise, rough], T0, T0)
    got = layer.belief(cell_of(*HERE, 9)).mean
    only_precise = build_layer("air_no2", cells, [precise], T0, T0).belief(cell_of(*HERE, 9)).mean
    # The rough sensor pulls a little, the precise station dominates.
    assert only_precise < got < only_precise + 2.0
    assert layer.sources == ("eea_hourly", "sensor_community")
    assert layer.synthetic is False


def test_simulated_readings_are_refused_where_the_layer_needs_real_data() -> None:
    spec = load_specs()["air_no2"]
    assert spec.allow_simulated is False
    cells = cells_in_bbox(WINDOW, 9)
    fake = reading("AirQualityObserved", "no2", 90.0, 1.0, "sim_air", synthetic=True)
    layer = assimilate(prior_layer(spec, cells, T0), [fake])
    assert layer.n_observations == 0
    assert layer.synthetic is False
    assert any("simulated" in w for w in layer.warnings)


def test_only_road_speed_accepts_simulated_readings() -> None:
    allowed = {name for name, s in load_specs().items() if s.allow_simulated}
    assert allowed == {"road_speed"}


def test_a_real_map_sets_the_starting_point_cell_by_cell() -> None:
    spec = load_specs()["emf"]
    cells = cells_in_bbox(WINDOW, 9)
    hot = cell_of(*HERE, 9)
    grid = [reading("EMFEstimate", "electricField", 3.0, 0.5, "cartoradio_grid"),
            reading("EMFEstimate", "electricField", 5.0, 0.5, "cartoradio_grid", lon=HERE[0] + 0.0003)]
    assert cell_of(HERE[0] + 0.0003, HERE[1], 9) == hot
    layer = prior_layer(spec, cells, T0, prior_field=grid)
    b = layer.belief(hot)
    assert b.mean == pytest.approx(4.0)
    # Variance = the map's own error plus the spread of its values inside the cell.
    assert b.variance == pytest.approx(0.25 + 1.0)
    other = next(c for c in cells if c != hot)
    assert layer.belief(other).mean == spec.prior.mean  # no map value there: generic prior
    assert "cartoradio_grid" in layer.sources
    # With no new readings the layer relaxes back to the map, not to the generic prior.
    assert layer.at(T0 + timedelta(days=60)).belief(hot).mean == pytest.approx(4.0)


def test_layer_without_any_real_source_is_not_available() -> None:
    out = layer_payload("activity", cells_in_bbox(WINDOW, 9), T0, T0, providers={})
    assert out["status"] == "not_available"
    assert "no real source" in out["reason"]


def test_layer_payload_picks_sources_from_config() -> None:
    spec = load_specs()["emf"]
    assert spec.sources == ("emf_measurements",)
    assert spec.prior_field is not None and spec.prior_field.source == "emf_baseline"
    cells = cells_in_bbox(WINDOW, 9)
    baseline = FakeProvider("cartoradio_grid", [reading("EMFEstimate", "electricField", 2.0, 0.4, "cartoradio_grid")])
    out = layer_payload("emf", cells, T0, T0, providers={"emf_baseline": baseline})
    assert out["status"] == "ok"
    row = next(r for r in out["result"]["cells"] if r["cell"] == cell_of(*HERE, 9))
    assert row["mean"] == pytest.approx(2.0)
    assert out["data_kinds"] == {"emf": "estimated"}
