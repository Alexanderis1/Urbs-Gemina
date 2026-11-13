from datetime import datetime, timedelta, timezone

import pytest

from twin.beliefs.cell import Belief, decay, update

T0 = datetime(2026, 11, 13, 18, 0, tzinfo=timezone.utc)


def test_update_moves_towards_observation_and_shrinks_variance() -> None:
    prior = Belief(mean=20.0, variance=16.0, updated_at=T0)
    posterior = update(prior, observed=30.0, observation_variance=16.0, at=T0 + timedelta(minutes=5))
    assert posterior.mean == pytest.approx(25.0)
    assert posterior.variance == pytest.approx(8.0)


def test_precise_observation_dominates() -> None:
    prior = Belief(mean=20.0, variance=100.0, updated_at=T0)
    posterior = update(prior, observed=30.0, observation_variance=0.01, at=T0)
    assert posterior.mean == pytest.approx(30.0, abs=0.01)


def test_decay_grows_variance_up_to_a_cap() -> None:
    belief = Belief(mean=20.0, variance=4.0, updated_at=T0)
    assert decay(belief, T0 + timedelta(hours=2), variance_growth_per_hour=3.0, max_variance=100.0).variance == pytest.approx(10.0)
    assert decay(belief, T0 + timedelta(hours=200), variance_growth_per_hour=3.0, max_variance=100.0).variance == 100.0


def test_observation_variance_must_be_positive() -> None:
    with pytest.raises(ValueError):
        update(Belief(1.0, 1.0, T0), 1.0, 0.0, T0)
