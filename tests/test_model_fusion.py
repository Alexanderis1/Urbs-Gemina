"""WS2: height fusion (every source a measurement with a calibrated error)."""
import numpy as np
import pytest

from twin.model.fusion import (
    SourceObs,
    calibrate,
    fuse,
)

NAN = np.nan


def test_inverse_variance_mean_and_sd() -> None:
    obs = {
        "a": SourceObs(np.array([10.0]), np.array([1.0])),
        "b": SourceObs(np.array([14.0]), np.array([1.0])),
    }
    r = fuse(obs, prior_mean=9.0, prior_sd=1e6, conflict_chi2=100.0)
    assert r.mean[0] == pytest.approx(12.0, abs=1e-3)
    assert r.sd[0] == pytest.approx(1 / np.sqrt(2), abs=1e-3)
    assert r.sources[0] == "a+b"


def test_precise_source_dominates() -> None:
    obs = {
        "lidar": SourceObs(np.array([20.0]), np.array([0.5])),
        "guess": SourceObs(np.array([30.0]), np.array([5.0])),
    }
    r = fuse(obs, prior_mean=9.0, prior_sd=1e6, conflict_chi2=100.0)
    assert 20.0 < r.mean[0] < 20.2
    assert r.dominant[0] == "lidar"


def test_missing_values_are_skipped_and_prior_fills_gaps() -> None:
    obs = {"a": SourceObs(np.array([NAN, 12.0]), np.array([1.0, 1.0]))}
    r = fuse(obs, prior_mean=9.0, prior_sd=6.0, conflict_chi2=9.0)
    assert r.mean[0] == pytest.approx(9.0) and r.sd[0] == pytest.approx(6.0)
    assert r.sources[0] == "prior" and r.dominant[0] == "prior"
    assert r.sources[1] == "a"


def test_conflict_flag_when_sources_disagree() -> None:
    obs = {
        "a": SourceObs(np.array([10.0, 10.0]), np.array([1.0, 1.0])),
        "b": SourceObs(np.array([10.5, 25.0]), np.array([1.0, 1.0])),
    }
    r = fuse(obs, prior_mean=9.0, prior_sd=1e6, conflict_chi2=9.0)
    assert list(r.conflict) == [False, True]


def test_calibrate_removes_bias_and_sets_spread() -> None:
    rng = np.random.default_rng(0)
    truth = rng.uniform(5, 40, 2000)
    ref = truth + rng.normal(0, 1.0, truth.size)
    src = truth + 3.0 + rng.normal(0, 2.0, truth.size)
    cal = calibrate(src, ref, ref_sd=1.0, prior_sd=None, min_pairs=100)
    assert cal.bias_m == pytest.approx(3.0, abs=0.2)
    assert cal.sd_m == pytest.approx(2.0, abs=0.2)
    assert cal.n == 2000


def test_calibrate_scales_a_per_building_sd() -> None:
    rng = np.random.default_rng(1)
    truth = rng.uniform(5, 40, 3000)
    claimed = np.full(truth.size, 1.0)  # source claims 1 m but is really 3 m off
    src = truth + rng.normal(0, 3.0, truth.size)
    cal = calibrate(src, truth, ref_sd=0.0, prior_sd=claimed, min_pairs=100)
    assert cal.scale == pytest.approx(3.0, abs=0.3)


def test_calibrate_with_too_few_pairs_falls_back() -> None:
    cal = calibrate(np.array([1.0, 2.0]), np.array([1.0, 2.0]), ref_sd=1.0, prior_sd=None, min_pairs=100,
                    fallback_sd=4.0)
    assert cal.bias_m == 0.0 and cal.sd_m == 4.0 and cal.n == 2
