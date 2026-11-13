"""A belief layer over many H3 cells, and the P1 update method.

P1 in one paragraph: every cell holds a mean and a variance. When readings
arrive, each reading corrects its own cell most and nearby cells less, with a
weight that falls as ``exp(-distance / correlation_length)``. Mathematically
this is Gaussian-process regression (simple kriging) of the readings' residual
against the current belief, with each reading's ``sigma`` as noise. With a tiny
correlation length it reduces exactly to the per-cell Kalman update in
``cell.update``. Between readings the layer relaxes back to the prior
(``cell.relax``), so silent areas visibly lose confidence.

Approximation: after each update only the per-cell variances are kept, not the
covariances between cells. That keeps memory linear in the number of cells and
is the standard "diagonal" simplification; it slightly overstates confidence
when the same area is updated many times in a row.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterable, Sequence

import numpy as np
import numpy.typing as npt

from twin.beliefs.cell import Belief
from twin.beliefs.config import LayerSpec
from twin.beliefs.grid import cell_center, cell_of, local_xy_km
from twin.providers.base import Observation

if TYPE_CHECKING:
    from twin.beliefs.calibration import CalibrationReport

Array = npt.NDArray[np.float64]

#: Rows of the cell-by-reading weight matrix computed at once (memory bound).
CHUNK = 4096
#: A cell counts as "updated" by a batch when its variance drops by at least this share.
UPDATED_SHARE = 0.01


@dataclass(frozen=True)
class BeliefLayer:
    spec: LayerSpec
    resolution: int
    cells: tuple[str, ...]
    mean: Array
    variance: Array
    #: Per cell, POSIX seconds of the last reading that changed it; NaN if never.
    updated_at: Array
    #: Time the means and variances refer to.
    as_of: datetime
    xy_km: Array
    n_observations: int = 0
    sources: tuple[str, ...] = ()
    synthetic: bool = False
    warnings: tuple[str, ...] = ()
    calibration: "CalibrationReport | None" = None
    index: dict[str, int] = field(default_factory=dict, compare=False, repr=False)

    def belief(self, cell: str) -> Belief:
        i = self.index[cell]
        return Belief(mean=float(self.mean[i]), variance=float(self.variance[i]), updated_at=self.as_of)

    def cell_updated_at(self, cell: str) -> datetime | None:
        t = float(self.updated_at[self.index[cell]])
        return None if np.isnan(t) else datetime.fromtimestamp(t, tz=timezone.utc)

    def at(self, moment: datetime) -> BeliefLayer:
        """The layer as it would look at ``moment`` if no new readings arrive."""
        return _relax(self, moment)

    def with_calibration(self, report: CalibrationReport) -> BeliefLayer:
        return replace(self, calibration=report)


def prior_layer(spec: LayerSpec, cells: Sequence[str], at: datetime, resolution: int | None = None) -> BeliefLayer:
    """A layer that has seen no readings: the prior in every cell."""
    if not cells:
        raise ValueError("a layer needs at least one cell")
    res = resolution if resolution is not None else _resolution_of(cells[0])
    xy = np.array(local_xy_km([cell_center(c) for c in cells]), dtype=np.float64)
    n = len(cells)
    return BeliefLayer(
        spec=spec,
        resolution=res,
        cells=tuple(cells),
        mean=np.full(n, spec.prior.mean_at(at)),
        variance=np.full(n, spec.prior.variance),
        updated_at=np.full(n, np.nan),
        as_of=_utc(at),
        xy_km=xy.reshape(n, 2),
        index={c: i for i, c in enumerate(cells)},
    )


def assimilate(layer: BeliefLayer, observations: Iterable[Observation], until: datetime | None = None) -> BeliefLayer:
    """Feed readings into the layer in time order; optionally relax on to ``until``."""
    spec = layer.spec
    usable: list[Observation] = []
    outside = 0
    for o in observations:
        if o.entity_type not in spec.entity_types or spec.value_key not in o.values:
            continue
        if cell_of(o.lon, o.lat, layer.resolution) not in layer.index:
            outside += 1
            continue
        usable.append(o)
    usable.sort(key=lambda o: _utc(o.observed_at))

    warnings = list(layer.warnings)
    if outside:
        warnings.append(f"{outside} readings fell outside the layer's cells and were not used")
    sources = set(layer.sources)
    synthetic = layer.synthetic
    current = layer
    start = 0
    while start < len(usable):
        when = _utc(usable[start].observed_at)
        stop = start
        while stop < len(usable) and _utc(usable[stop].observed_at) == when:
            stop += 1
        batch = usable[start:stop]
        if when < current.as_of:
            warnings.append(f"{len(batch)} readings older than the layer time were skipped")
        else:
            current = _update(_relax(current, when), batch)
            sources.update(o.source_id for o in batch)
            synthetic = synthetic or any(o.synthetic for o in batch)
        start = stop

    current = replace(
        current,
        n_observations=layer.n_observations + len(usable),
        sources=tuple(sorted(sources)),
        synthetic=synthetic,
        warnings=tuple(warnings),
    )
    if until is not None and _utc(until) > current.as_of:
        current = _relax(current, until)
    return current


def posterior(
    target_xy: Array,
    target_mean: Array,
    target_var: Array,
    obs_xy: Array,
    obs_mean: Array,
    obs_var: Array,
    values: Array,
    noise_var: Array,
    correlation_length_km: float,
) -> tuple[Array, Array]:
    """Gaussian-process update of target cells from readings at observed cells.

    Prior covariance between two places = sd_a * sd_b * exp(-distance / L).
    Returns the posterior means and variances of the targets.
    """
    sd_t = np.sqrt(target_var)
    sd_o = np.sqrt(obs_var)
    k_oo = np.outer(sd_o, sd_o) * _correlation(obs_xy, obs_xy, correlation_length_km)
    k_oo[np.diag_indices_from(k_oo)] += noise_var
    chol = np.linalg.cholesky(k_oo)
    residual = values - obs_mean
    alpha = np.linalg.solve(chol.T, np.linalg.solve(chol, residual))
    mean = target_mean.copy()
    var = target_var.copy()
    for lo in range(0, len(target_xy), CHUNK):
        hi = lo + CHUNK
        k_to = np.outer(sd_t[lo:hi], sd_o) * _correlation(target_xy[lo:hi], obs_xy, correlation_length_km)
        mean[lo:hi] += k_to @ alpha
        v = np.linalg.solve(chol, k_to.T)
        var[lo:hi] -= np.sum(v * v, axis=0)
    # Guard against round-off: a variance is never below a tiny share of the prior one.
    return mean, np.maximum(var, target_var * 1e-9)


def _update(layer: BeliefLayer, batch: Sequence[Observation]) -> BeliefLayer:
    """One simultaneous batch of readings (same timestamp)."""
    key = layer.spec.value_key
    # Combine readings that fall in the same cell (inverse-variance mean), so the
    # matrix size is bounded by the number of observed cells.
    per_cell: dict[int, tuple[float, float]] = {}
    for o in batch:
        i = layer.index[cell_of(o.lon, o.lat, layer.resolution)]
        sigma = o.sigma.get(key, 0.0)
        noise = max(sigma * sigma, 1e-6 * layer.spec.prior.variance)
        w, wy = per_cell.get(i, (0.0, 0.0))
        per_cell[i] = (w + 1.0 / noise, wy + o.values[key] / noise)
    idx = np.array(sorted(per_cell), dtype=np.int64)
    weights = np.array([per_cell[int(i)][0] for i in idx])
    values = np.array([per_cell[int(i)][1] for i in idx]) / weights
    mean, var = posterior(
        layer.xy_km,
        layer.mean,
        layer.variance,
        layer.xy_km[idx],
        layer.mean[idx],
        layer.variance[idx],
        values,
        1.0 / weights,
        layer.spec.correlation_length_km,
    )
    changed = var < layer.variance * (1.0 - UPDATED_SHARE)
    updated_at = layer.updated_at.copy()
    updated_at[changed] = layer.as_of.timestamp()
    return replace(layer, mean=mean, variance=var, updated_at=updated_at)


def _relax(layer: BeliefLayer, moment: datetime) -> BeliefLayer:
    moment = _utc(moment)
    hours = (moment - layer.as_of).total_seconds() / 3600.0
    if hours <= 0.0:
        return layer
    prior = layer.spec.prior
    keep = float(np.exp(-hours / layer.spec.relax_tau_hours))
    mean = prior.mean_at(moment) + (layer.mean - prior.mean_at(layer.as_of)) * keep
    var = prior.variance + (layer.variance - prior.variance) * keep * keep
    return replace(layer, mean=mean, variance=var, as_of=moment)


def _correlation(a: Array, b: Array, length_km: float) -> Array:
    d = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=2))
    out: Array = np.exp(-d / max(length_km, 1e-12))
    return out


def _resolution_of(cell: str) -> int:
    import h3  # type: ignore[import-untyped]

    return int(h3.get_resolution(cell))


def _utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


__all__ = ["BeliefLayer", "assimilate", "posterior", "prior_layer"]
