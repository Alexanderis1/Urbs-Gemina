"""One cell of a belief layer: a mean, a variance and when it was last updated."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Belief:
    mean: float
    variance: float
    updated_at: datetime


def update(belief: Belief, observed: float, observation_variance: float, at: datetime) -> Belief:
    """Bayesian (Kalman) update of a cell with one noisy observation."""
    if observation_variance <= 0.0:
        raise ValueError("observation variance must be positive")
    gain = belief.variance / (belief.variance + observation_variance)
    return Belief(
        mean=belief.mean + gain * (observed - belief.mean),
        variance=(1.0 - gain) * belief.variance,
        updated_at=at,
    )


def decay(belief: Belief, at: datetime, variance_growth_per_hour: float, max_variance: float) -> Belief:
    """Lose confidence while no data arrives: variance grows with elapsed time."""
    hours = max(0.0, (at - belief.updated_at).total_seconds() / 3600.0)
    variance = min(max_variance, belief.variance + variance_growth_per_hour * hours)
    return Belief(mean=belief.mean, variance=variance, updated_at=belief.updated_at)
