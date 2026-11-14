"""Learn a belief layer's settings from real history instead of guessing them.

Three plain steps, each a standard statistical estimate:

1. **Model bias** (``fit_bias``): the background model (CAMS) against real stations,
   ``station = offset + scale * model``, by least squares. What is left over is the
   model's real error at a station.
2. **Spatial covariance** (``fit_covariance``): the left-over errors of many stations at
   the same moment are treated as one draw of a Gaussian field with covariance
   ``sd^2 * exp(-d / L)`` plus a local part ``nugget^2`` that does not spread. The three
   numbers are chosen by maximum likelihood over all moments (type-II maximum likelihood,
   the usual way to fit kriging hyperparameters).
3. **Persistence** (``fit_persistence``): how fast a station's left-over error forgets
   itself, ``corr(lag) = exp(-lag / tau)``, fitted on short lags. This is the layer's
   ``relax_tau_hours``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Sequence

import numpy as np
import numpy.typing as npt

Array = npt.NDArray[np.float64]


@dataclass(frozen=True)
class BiasFit:
    offset: float
    scale: float
    residual_sd: float
    n: int


@dataclass(frozen=True)
class SpatialGroup:
    """Left-over errors of several stations at one moment, with their positions in km."""

    xy: Array
    residual: Array


@dataclass(frozen=True)
class CovarianceFit:
    sd: float
    length_km: float
    nugget_sd: float
    n_groups: int
    neg_log_likelihood: float

    @property
    def total_sd(self) -> float:
        return math.hypot(self.sd, self.nugget_sd)

    @property
    def spatial_share(self) -> float:
        total = self.sd**2 + self.nugget_sd**2
        return self.sd**2 / total if total > 0 else 1.0


@dataclass(frozen=True)
class PersistenceFit:
    tau_hours: float
    correlations: tuple[tuple[float, float], ...]


def fit_bias(observed: Sequence[float] | Array, model: Sequence[float] | Array) -> BiasFit:
    obs = np.asarray(observed, dtype=np.float64)
    mod = np.asarray(model, dtype=np.float64)
    if len(obs) < 3:
        raise ValueError("need at least 3 pairs to fit a bias")
    scale, offset = np.polyfit(mod, obs, 1)
    resid = obs - (offset + scale * mod)
    return BiasFit(offset=float(offset), scale=float(scale), residual_sd=float(np.std(resid)), n=len(obs))


def _distances(xy: Array) -> Array:
    d: Array = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(axis=2))
    return d


def fit_covariance(groups: Sequence[SpatialGroup], max_length_km: float = 50.0,
                   min_length_km: float = 0.2) -> CovarianceFit:
    """Maximum-likelihood ``sd``, ``L`` and ``nugget`` of an exponential field plus local noise."""
    from scipy.optimize import minimize  # type: ignore[import-untyped]

    usable = [(_distances(np.asarray(g.xy, dtype=np.float64)), np.asarray(g.residual, dtype=np.float64))
              for g in groups if len(g.residual) >= 2]
    if not usable:
        raise ValueError("need moments with at least 2 stations")
    total_var = float(np.var(np.concatenate([r for _, r in usable])))
    lo, hi = math.log(min_length_km), math.log(max_length_km)

    def nll(p: Array) -> float:
        s2, n2 = math.exp(p[0]), math.exp(p[2])
        length = math.exp(min(max(p[1], lo), hi))
        tot = 0.0
        for d, r in usable:
            k = s2 * np.exp(-d / length) + n2 * np.eye(len(r))
            try:
                c = np.linalg.cholesky(k)
            except np.linalg.LinAlgError:
                return 1e12
            a = np.linalg.solve(c, r)
            tot += 0.5 * float(a @ a) + float(np.log(np.diag(c)).sum())
        return tot / len(usable)

    best = None
    for length0 in (1.0, 3.0, 10.0, 30.0):
        if not min_length_km <= length0 <= max_length_km:
            continue
        start = np.log([0.7 * total_var, length0, 0.3 * total_var])
        res = minimize(nll, start, method="Nelder-Mead", options={"maxiter": 600, "xatol": 1e-3, "fatol": 1e-6})
        if best is None or res.fun < best.fun:
            best = res
    assert best is not None
    s2, n2 = math.exp(best.x[0]), math.exp(best.x[2])
    length = math.exp(min(max(best.x[1], lo), hi))
    return CovarianceFit(sd=math.sqrt(s2), length_km=length, nugget_sd=math.sqrt(n2),
                         n_groups=len(usable), neg_log_likelihood=float(best.fun))


def fit_persistence(series: Mapping[str, Mapping[datetime, float]], lags_hours: Sequence[float]) -> PersistenceFit:
    """``tau`` from the lag correlation of each station's own left-over error, pooled over stations.

    Least squares of ``log(corr) = -lag / tau`` through the origin, over lags with positive correlation.
    """
    pairs: list[tuple[float, float]] = []
    for lag in lags_hours:
        x: list[float] = []
        y: list[float] = []
        step = timedelta(hours=lag)
        for values in series.values():
            for t, v in values.items():
                w = values.get(t + step)
                if w is not None:
                    x.append(v)
                    y.append(w)
        if len(x) >= 10:
            pairs.append((float(lag), float(np.corrcoef(x, y)[0, 1])))
    good = [(lag, rho) for lag, rho in pairs if rho > 0.0]
    if not good:
        raise ValueError("no lag with positive correlation")
    lags = np.array([lag for lag, _ in good])
    logs = np.array([math.log(rho) for _, rho in good])
    slope = float(lags @ logs / (lags @ lags))
    tau = -1.0 / slope if slope < 0 else math.inf
    return PersistenceFit(tau_hours=tau, correlations=tuple(pairs))


__all__ = ["BiasFit", "CovarianceFit", "PersistenceFit", "SpatialGroup", "fit_bias", "fit_covariance",
           "fit_persistence"]
