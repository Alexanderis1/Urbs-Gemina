"""One cell of a belief layer: a mean, a variance and when it was last updated."""
from __future__ import annotations

import math
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


def relax(belief: Belief, prior_then: Belief, prior_now: Belief, at: datetime, tau_hours: float) -> Belief:
    """Forget old readings: drift back to the prior while no data arrives.

    The cell keeps its *anomaly* (difference from the prior mean) but it shrinks
    by a factor e every ``tau_hours``; the variance grows back towards the prior
    variance at the same pace. After a long silence the cell is the prior again.
    This is the exact forecast step of a mean-reverting (Ornstein-Uhlenbeck)
    process, so it is consistent with the Kalman ``update`` above.
    """
    if tau_hours <= 0.0:
        raise ValueError("tau_hours must be positive")
    hours = max(0.0, (at - belief.updated_at).total_seconds() / 3600.0)
    keep = math.exp(-hours / tau_hours)
    mean = prior_now.mean + (belief.mean - prior_then.mean) * keep
    variance = prior_now.variance + (belief.variance - prior_then.variance) * keep * keep
    return Belief(mean=mean, variance=variance, updated_at=belief.updated_at)
