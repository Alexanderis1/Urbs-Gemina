"""Learning a layer's settings from real history: model bias, spatial covariance, persistence."""
from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from twin.beliefs import learn
from twin.beliefs.calibration import CalibrationRules, leave_one_station_out
from twin.beliefs.config import FieldSpec, LayerSpec, PriorSpec, load_specs
from twin.beliefs.grid import cell_of, cells_in_bbox
from twin.beliefs.layer import posterior, prior_layer
from twin.providers.base import Observation

T0 = datetime(2026, 11, 13, 8, 0, tzinfo=timezone.utc)
WINDOW = (12.46, 41.88, 12.50, 41.91)
HERE = (12.48, 41.895)


def test_bias_fit_recovers_offset_and_scale() -> None:
    rng = np.random.default_rng(1)
    model = rng.uniform(5, 40, 2000)
    obs = 12.0 + 0.7 * model + rng.normal(0, 3.0, 2000)
    fit = learn.fit_bias(obs, model)
    assert fit.offset == pytest.approx(12.0, abs=0.6)
    assert fit.scale == pytest.approx(0.7, abs=0.03)
    assert fit.residual_sd == pytest.approx(3.0, abs=0.2)


def _gp_groups(sd: float, length: float, nugget: float, n_times: int, seed: int) -> list[learn.SpatialGroup]:
    rng = np.random.default_rng(seed)
    xy = rng.uniform(-10, 10, (12, 2))
    d = np.sqrt(((xy[:, None] - xy[None]) ** 2).sum(-1))
    k = sd**2 * np.exp(-d / length) + nugget**2 * np.eye(len(xy))
    chol = np.linalg.cholesky(k)
    return [learn.SpatialGroup(xy=xy, residual=chol @ rng.normal(size=len(xy))) for _ in range(n_times)]


def test_covariance_fit_recovers_spread_reach_and_local_part() -> None:
    fit = learn.fit_covariance(_gp_groups(sd=6.0, length=4.0, nugget=3.0, n_times=400, seed=2))
    assert fit.sd == pytest.approx(6.0, rel=0.15)
    assert fit.length_km == pytest.approx(4.0, rel=0.35)
    assert fit.nugget_sd == pytest.approx(3.0, rel=0.15)
    assert fit.spatial_share == pytest.approx(36.0 / 45.0, abs=0.06)


def test_covariance_fit_caps_the_reach() -> None:
    # A city-wide offset (huge reach) is reported at the cap, not as thousands of km.
    fit = learn.fit_covariance(_gp_groups(sd=5.0, length=5000.0, nugget=2.0, n_times=300, seed=3), max_length_km=50.0)
    assert fit.length_km == pytest.approx(50.0)


def test_persistence_fit_recovers_relaxation_time() -> None:
    rng = np.random.default_rng(4)
    tau = 6.0
    phi = math.exp(-1.0 / tau)
    x = np.zeros(20000)
    for i in range(1, len(x)):
        x[i] = phi * x[i - 1] + math.sqrt(1 - phi * phi) * rng.normal()
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    series = {"s1": {t0 + timedelta(hours=i): float(v) for i, v in enumerate(x)}}
    fit = learn.fit_persistence(series, lags_hours=[1, 2, 3, 6])
    assert fit.tau_hours == pytest.approx(tau, rel=0.15)


def test_full_spatial_share_is_the_plain_kriging_update() -> None:
    xy = np.array([[0.0, 0.0], [1.0, 0.0], [3.0, 0.0]])
    args = (xy, np.zeros(3), np.full(3, 4.0), xy[:1], np.zeros(1), np.full(1, 4.0), np.array([2.0]), np.array([0.5]), 2.0)
    a = posterior(*args)
    b = posterior(*args, spatial_share=1.0)
    assert np.allclose(a[0], b[0]) and np.allclose(a[1], b[1])


def test_local_part_stays_in_the_station_cell() -> None:
    xy = np.array([[0.0, 0.0], [0.5, 0.0]])
    args = (xy, np.zeros(2), np.full(2, 4.0), xy[:1], np.zeros(1), np.full(1, 4.0), np.array([2.0]), np.array([0.01]), 10.0)
    full_mean, _ = posterior(*args)
    part_mean, part_var = posterior(*args, spatial_share=0.4)
    assert part_mean[0] == pytest.approx(full_mean[0], rel=1e-3)  # the station's own cell takes the reading
    assert part_mean[1] < 0.5 * full_mean[1]  # the neighbour only takes the shared part
    assert part_var[1] > 4.0 * (1 - 0.4) - 1e-9  # the local part of its spread is untouched


def _air_spec(spatial_share: float = 1.0, **field: float) -> LayerSpec:
    return LayerSpec(spatial_share=spatial_share,
        name="air_test", unit="ug/m3", entity_types=("AirQualityObserved",), value_key="no2",
        prior=PriorSpec(mean=30.0, sd=15.0), correlation_length_km=10.0, relax_tau_hours=7.0, min_value=0.0,
        calibration_method="loso", calibration_note="",
        prior_field=FieldSpec(source="air_quality_model", entity_types=("AirQualityForecast",), value_key="no2",
                              method="idw", **field),
    )


def test_learned_bias_and_spread_set_the_starting_map() -> None:
    cams = [Observation("c1", "AirQualityForecast", HERE[0], HERE[1], T0, {"no2": 20.0}, {"no2": 10.0}, "cams", False)]
    cells = cells_in_bbox(WINDOW, 9)
    layer = prior_layer(_air_spec(offset=13.0, scale=0.66, sd=11.6), cells, T0, prior_field=cams)
    b = layer.belief(cell_of(*HERE, 9))
    assert b.mean == pytest.approx(13.0 + 0.66 * 20.0)
    assert b.variance == pytest.approx(11.6**2)


def test_calibration_uses_the_layers_own_starting_map() -> None:
    rng = np.random.default_rng(5)
    xy = rng.uniform(-0.05, 0.05, (8, 2))
    obs: list[Observation] = []
    prior_means: dict[tuple[str, datetime], float] = {}
    for h in range(48):
        when = T0 + timedelta(hours=h)
        level = 40.0 + 20.0 * math.sin(h / 4.0)  # a moving level the generic prior does not know
        for i, (dx, dy) in enumerate(xy):
            sid = f"s{i}"
            prior_means[(sid, when)] = level
            obs.append(Observation(sid, "AirQualityObserved", 12.48 + dx, 41.9 + dy, when,
                                   {"no2": level + float(rng.normal(0, 3.0))}, {"no2": 1.0}, "eea", False))
    spec = _air_spec(spatial_share=0.01, sd=3.0)  # station errors here are purely local
    rules = CalibrationRules(interval=0.9, coverage_ok=(0.8, 0.97), z_sd_ok=(0.7, 1.4), min_stations=5)
    with_map = leave_one_station_out(spec, obs, rules, prior_means=prior_means, prior_sd=3.0)
    assert with_map.status == "calibrated", with_map.reason
    assert with_map.rmse < 4.5
    generic = leave_one_station_out(spec, obs, rules)
    assert generic.rmse > 2 * with_map.rmse  # the constant prior misses the moving level


def test_air_layers_carry_learned_settings() -> None:
    specs = load_specs()
    for name in ("air_no2", "air_pm10", "air_pm25"):
        s = specs[name]
        assert s.prior_field is not None and s.prior_field.sd is not None, name
        assert 0.0 < s.spatial_share < 1.0, name


class _Feed:
    def __init__(self, obs: list[Observation]) -> None:
        self._obs = obs

    def describe(self) -> object:
        return None

    def fetch(self, bbox: object, start: datetime, end: datetime) -> list[Observation]:
        return [o for o in self._obs if start <= o.observed_at <= end]


def test_daily_pm_published_a_day_late_still_counts() -> None:
    from twin.beliefs.api import build_layer

    spec = load_specs()["air_pm10"]
    assert spec.history_hours >= 30
    late = Observation("eea-1", "AirQualityObserved", HERE[0], HERE[1], T0 - timedelta(hours=30),
                       {"pm10": 45.0}, {"pm10": 4.0}, "eea_hourly", False)
    cells = cells_in_bbox(WINDOW, 9)
    layer = build_layer("air_pm10", cells, [_Feed([late])], T0 - timedelta(hours=1), T0, spec=spec)  # type: ignore[list-item]
    assert layer.n_observations == 1


def test_road_length_within_a_circle() -> None:
    import shapely

    from twin.beliefs import landuse

    # A straight east-west road through the point: 2 * radius of it lies inside the circle.
    lon_per_m = 1.0 / (111_320.0 * math.cos(math.radians(landuse.LAT0)))
    line = shapely.LineString([(HERE[0] - 500 * lon_per_m, HERE[1]), (HERE[0] + 500 * lon_per_m, HERE[1])])
    lines = landuse.project_lines([shapely.to_wkb(line)])
    got = landuse.road_length_within(lines, [HERE[0], HERE[0]], [HERE[1], HERE[1] + 0.01], 100.0)
    assert got[0] == pytest.approx(200.0, rel=0.01)
    assert got[1] == 0.0


def test_land_use_term_shifts_cells_with_more_road(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    from twin.beliefs import landuse

    assert isinstance(tmp_path, Path)
    cells = cells_in_bbox(WINDOW, 9)
    busy = cell_of(*HERE, 9)
    (tmp_path / "cov.csv").write_text("cell,value\n" + "".join(f"{c},{400.0 if c == busy else 100.0}\n" for c in cells))
    monkeypatch.setattr(landuse, "SEARCH_DIRS", (tmp_path,))
    landuse.load_cell_covariate.cache_clear()
    cams = [Observation("c1", "AirQualityForecast", HERE[0], HERE[1], T0, {"no2": 20.0}, {"no2": 10.0}, "cams", False)]
    spec = _air_spec(sd=8.0)
    field = replace(spec.prior_field, covariate_file="cov.csv", covariate_coef=0.02, covariate_center=100.0)  # type: ignore[arg-type]
    layer = prior_layer(replace(spec, prior_field=field), cells, T0, prior_field=cams)
    quiet = next(c for c in cells if c != busy)
    assert layer.belief(busy).mean - layer.belief(quiet).mean == pytest.approx(0.02 * 300.0)
    landuse.load_cell_covariate.cache_clear()


def test_missing_covariate_file_is_reported_not_invented(monkeypatch: pytest.MonkeyPatch) -> None:
    from twin.beliefs import landuse

    monkeypatch.setattr(landuse, "SEARCH_DIRS", ())
    landuse.load_cell_covariate.cache_clear()
    spec = _air_spec(sd=8.0)
    field = replace(spec.prior_field, covariate_file="nope.csv", covariate_coef=0.02)  # type: ignore[arg-type]
    cams = [Observation("c1", "AirQualityForecast", HERE[0], HERE[1], T0, {"no2": 20.0}, {"no2": 10.0}, "cams", False)]
    layer = prior_layer(replace(spec, prior_field=field), cells_in_bbox(WINDOW, 9), T0, prior_field=cams)
    assert any("land-use term off" in w for w in layer.warnings)
    landuse.load_cell_covariate.cache_clear()
