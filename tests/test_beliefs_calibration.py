from datetime import datetime, timedelta, timezone

import numpy as np

from twin.beliefs.calibration import CalibrationRules, leave_one_station_out
from twin.beliefs.config import LayerSpec, PriorSpec
from twin.beliefs.grid import local_xy_km
from twin.providers.base import Observation

T0 = datetime(2026, 11, 13, 8, 0, tzinfo=timezone.utc)
RULES = CalibrationRules(interval=0.9, coverage_ok=(0.75, 0.98), z_sd_ok=(0.6, 1.5), min_stations=5)


def spec(prior_sd: float) -> LayerSpec:
    return LayerSpec(
        name="air_no2",
        unit="ug/m3",
        entity_types=("AirQualityObserved",),
        value_key="no2",
        prior=PriorSpec(mean=30.0, sd=prior_sd),
        correlation_length_km=4.0,
        relax_tau_hours=3.0,
        min_value=0.0,
        calibration_method="loso",
        calibration_note="",
    )


def stations(claimed_sigma: float, true_noise: float, n: int = 25, hours: int = 8) -> list[Observation]:
    """Stations reading a random field drawn from the same model the layer assumes
    (prior mean 30, sd 12, correlation length 4 km) plus noise of a known size."""
    rng = np.random.default_rng(7)
    sites = [(float(rng.uniform(12.35, 12.65)), float(rng.uniform(41.80, 42.00))) for _ in range(n)]
    xy = np.array(local_xy_km(sites))
    dist = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(axis=2))
    chol = np.linalg.cholesky(144.0 * np.exp(-dist / 4.0) + 1e-9 * np.eye(n))
    out = []
    for h in range(hours):
        at = T0 + timedelta(hours=h)
        field = 30.0 + chol @ rng.standard_normal(n)
        for i, (lon, lat) in enumerate(sites):
            out.append(
                Observation(
                    entity_id=f"st{i}",
                    entity_type="AirQualityObserved",
                    lon=lon,
                    lat=lat,
                    observed_at=at,
                    values={"no2": float(field[i] + rng.normal(0.0, true_noise))},
                    sigma={"no2": claimed_sigma},
                    source_id="eea_hourly",
                    synthetic=False,
                )
            )
    return out


def test_honest_uncertainty_passes() -> None:
    report = leave_one_station_out(spec(prior_sd=12.0), stations(claimed_sigma=2.0, true_noise=2.0), RULES)
    assert report.status == "calibrated", report.reason
    assert report.n_predictions == 25 * 8
    assert 0.75 <= report.coverage <= 0.98


def test_overconfident_layer_is_labelled_uncalibrated() -> None:
    # The prior claims to be very sure and the stations claim to be precise, but
    # the field varies a lot: errors are far bigger than the stated uncertainty.
    report = leave_one_station_out(spec(prior_sd=0.5), stations(claimed_sigma=0.1, true_noise=4.0), RULES)
    assert report.status == "uncalibrated"
    assert report.coverage < 0.75
    assert "coverage" in report.reason


def test_too_few_stations_is_uncalibrated() -> None:
    report = leave_one_station_out(spec(prior_sd=12.0), stations(2.0, 2.0, n=3), RULES)
    assert report.status == "uncalibrated"
    assert "stations" in report.reason


def test_emf_style_layers_are_never_calibrated() -> None:
    s = spec(prior_sd=12.0)
    emf = LayerSpec(**{**s.__dict__, "calibration_method": "none", "calibration_note": "no real measurements"})
    report = leave_one_station_out(emf, stations(2.0, 2.0), RULES)
    assert report.status == "uncalibrated"
    assert report.reason == "no real measurements"
