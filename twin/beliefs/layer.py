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
    #: Per-cell starting point: prior mean = generic prior at that time + offset; prior variance.
    #: The offset is zero unless a real map (``prior_field``) set the starting point.
    prior_offset: Array
    prior_var: Array
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


def prior_layer(
    spec: LayerSpec,
    cells: Sequence[str],
    at: datetime,
    resolution: int | None = None,
    prior_field: Iterable[Observation] | None = None,
) -> BeliefLayer:
    """A layer that has seen no readings.

    Every cell holds the generic prior from the config, except where a real
    gridded map (``prior_field``, e.g. the Cartoradio grid) has values: there
    the cell starts from the map's mean, with variance = the map's own error
    plus the spread of the map values inside the cell.
    """
    if not cells:
        raise ValueError("a layer needs at least one cell")
    res = resolution if resolution is not None else _resolution_of(cells[0])
    xy = np.array(local_xy_km([cell_center(c) for c in cells]), dtype=np.float64)
    n = len(cells)
    index = {c: i for i, c in enumerate(cells)}
    base = spec.prior.mean_at(at)
    offset = np.zeros(n)
    prior_var = np.full(n, spec.prior.variance)
    sources: set[str] = set()
    synthetic = False
    if prior_field is not None:
        fspec = spec.prior_field
        key = fspec.value_key if fspec is not None else spec.value_key
        types = fspec.entity_types if fspec is not None else spec.entity_types
        points = [o for o in prior_field if o.entity_type in types and key in o.values]
        sources.update(o.source_id for o in points)
        synthetic = any(o.synthetic for o in points)
        if points and fspec is not None and fspec.method == "idw":
            pxy = np.array(local_xy_km([(o.lon, o.lat) for o in points]), dtype=np.float64)
            vals = np.array([o.values[key] for o in points])
            sig2 = np.array([o.sigma.get(key, 0.0) ** 2 for o in points])
            for lo in range(0, n, CHUNK):
                d2 = ((xy[lo : lo + CHUNK, None, :] - pxy[None, :, :]) ** 2).sum(axis=2)
                w = 1.0 / np.maximum(d2, 1e-6)
                w /= w.sum(axis=1, keepdims=True)
                m = w @ vals
                offset[lo : lo + CHUNK] = m - base
                # Map error plus how much the nearby map points disagree (interpolation error).
                prior_var[lo : lo + CHUNK] = w @ sig2 + w @ (vals**2) - m**2
            prior_var = np.maximum(prior_var, 1e-6 * spec.prior.variance)
        else:
            acc: dict[int, list[tuple[float, float]]] = {}
            for o in points:
                i = index.get(cell_of(o.lon, o.lat, res))
                if i is not None:
                    acc.setdefault(i, []).append((o.values[key], o.sigma.get(key, 0.0)))
            for i, cell_vals in acc.items():
                values = np.array([v for v, _ in cell_vals])
                sigmas = np.array([sd for _, sd in cell_vals])
                offset[i] = float(values.mean()) - base
                prior_var[i] = max(float(np.mean(sigmas**2) + values.var()), 1e-6 * spec.prior.variance)
    return BeliefLayer(
        spec=spec,
        resolution=res,
        cells=tuple(cells),
        mean=base + offset,
        variance=prior_var.copy(),
        updated_at=np.full(n, np.nan),
        as_of=_utc(at),
        xy_km=xy.reshape(n, 2),
        prior_offset=offset,
        prior_var=prior_var,
        sources=tuple(sorted(sources)),
        synthetic=synthetic,
        index=index,
    )


def assimilate(layer: BeliefLayer, observations: Iterable[Observation], until: datetime | None = None) -> BeliefLayer:
    """Feed readings into the layer in time order; optionally relax on to ``until``."""
    spec = layer.spec
    usable: list[Observation] = []
    outside = 0
    refused = 0
    for o in observations:
        if o.entity_type not in spec.entity_types or spec.value_key not in o.values:
            continue
        if o.synthetic and not spec.allow_simulated:
            refused += 1
            continue
        if cell_of(o.lon, o.lat, layer.resolution) not in layer.index:
            outside += 1
            continue
        usable.append(o)
    if spec.aggregate == "count":
        usable = _count_per_cell(layer, usable)
    usable.sort(key=lambda o: _utc(o.observed_at))

    warnings = list(layer.warnings)
    if refused:
        warnings.append(f"{refused} simulated readings were refused: this layer is built from real data only")
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
    if layer.spec.correlation_length_km <= 0.0:
        # No spreading between cells: the plain per-cell Kalman update, vectorised.
        mean = layer.mean.copy()
        var = layer.variance.copy()
        gain = var[idx] / (var[idx] + 1.0 / weights)
        mean[idx] += gain * (values - mean[idx])
        var[idx] *= 1.0 - gain
        return _stamp(layer, mean, var)
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
    return _stamp(layer, mean, var)


def _stamp(layer: BeliefLayer, mean: Array, var: Array) -> BeliefLayer:
    changed = var < layer.variance * (1.0 - UPDATED_SHARE)
    updated_at = layer.updated_at.copy()
    updated_at[changed] = layer.as_of.timestamp()
    return replace(layer, mean=mean, variance=var, updated_at=updated_at)


def _count_per_cell(layer: BeliefLayer, items: Sequence[Observation]) -> list[Observation]:
    """Turn item readings (one per parked scooter, say) into one count per cell and time window.

    Cells inside the bounding box of a window's items that hold none count as 0,
    since the feed covers them. Error = Poisson, sqrt(count + 1).
    """
    spec = layer.spec
    window = spec.aggregate_window_minutes * 60.0
    groups: dict[float, list[Observation]] = {}
    for o in items:
        t = _utc(o.observed_at).timestamp()
        groups.setdefault(t - t % window, []).append(o)
    out: list[Observation] = []
    for t, group in groups.items():
        counts: dict[str, float] = {}
        for o in group:
            c = cell_of(o.lon, o.lat, layer.resolution)
            counts[c] = counts.get(c, 0.0) + o.values[spec.value_key]
        lons = [o.lon for o in group]
        lats = [o.lat for o in group]
        when = datetime.fromtimestamp(t, tz=timezone.utc)
        source = group[0].source_id
        synthetic = any(o.synthetic for o in group)
        for cell, i in layer.index.items():
            lon, lat = cell_center(cell)
            if not (min(lons) <= lon <= max(lons) and min(lats) <= lat <= max(lats)) and cell not in counts:
                continue
            n = counts.get(cell, 0.0)
            out.append(
                Observation(
                    entity_id=f"count:{cell}",
                    entity_type=spec.entity_types[0],
                    lon=lon,
                    lat=lat,
                    observed_at=when,
                    values={spec.value_key: n},
                    sigma={spec.value_key: float(np.sqrt(n + 1.0))},
                    source_id=source,
                    synthetic=synthetic,
                )
            )
    return out


def _relax(layer: BeliefLayer, moment: datetime) -> BeliefLayer:
    moment = _utc(moment)
    hours = (moment - layer.as_of).total_seconds() / 3600.0
    if hours <= 0.0:
        return layer
    prior = layer.spec.prior
    keep = float(np.exp(-hours / layer.spec.relax_tau_hours))
    then = prior.mean_at(layer.as_of) + layer.prior_offset
    now = prior.mean_at(moment) + layer.prior_offset
    mean = now + (layer.mean - then) * keep
    var = layer.prior_var + (layer.variance - layer.prior_var) * keep * keep
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
