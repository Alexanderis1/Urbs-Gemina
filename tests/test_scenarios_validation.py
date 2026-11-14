"""Validation of the scenario physics against real past events (data in eval/scenarios/)."""
import json
from pathlib import Path

import numpy as np

from twin.scenarios import config, validation
from twin.scenarios.flood import _rating

EVAL = Path(__file__).resolve().parents[1] / "eval" / "scenarios"


def test_ripetta_rating_matches_the_observed_peaks() -> None:
    peaks = json.loads((EVAL / "tiber_ripetta_peaks.json").read_text())
    fit = validation.fit_rating(peaks["pairs"])
    assert fit["rmse_m"] < 0.6
    assert fit["loo_rmse_m"] < 1.3
    gauge = config.load("scenarios.yaml")["river_flood"]["gauges"]["tevere_ripetta"]
    used = gauge["rating_power"]
    assert used["h0"] == round(fit["h0"], 2) and used["a"] == round(fit["a"], 2) and used["b"] == round(fit["b"], 4)
    assert used["sigma_m"] >= round(fit["rmse_m"], 2)


def test_the_walls_hold_a_200_year_flood_at_ripetta() -> None:
    peaks = json.loads((EVAL / "tiber_ripetta_peaks.json").read_text())
    gauge = config.load("scenarios.yaml")["river_flood"]["gauges"]["tevere_ripetta"]
    t200 = float(_rating(gauge, np.array([float(peaks["quantiles_m3s"]["T200"])]), noise=False)[0])
    t1000 = float(_rating(gauge, np.array([float(peaks["quantiles_m3s"]["T1000"])]), noise=False)[0])
    assert 17.0 < t200 < 18.45 < t1000


def test_every_checked_model_says_how_it_was_checked() -> None:
    """Results carry the validation status from config, so users see how far each model was checked."""
    from twin.scenarios import config

    cfg = config.load("scenarios.yaml")
    for kind, word in (("river_flood", "PGRA"), ("rain_flood", "cloudbursts"), ("chemical_plume", "FAC2"),
                       ("heatwave", "literature"), ("emergency_access", "118")):
        assert word in str(config.value(cfg[kind], "calibration")), kind
