"""Register v2: fit site powers *and* sector directions to the Cartoradio grid with an urban model.

Cartoradio is computed by FUB from the operators' real register (azimuth, tilt,
gain, height) with an empirical-statistical urban path-loss model at 100 m
pixels (cartoradio.it/faq). The v1 register fitted a free-space, isotropic
model, which cannot reproduce that, hence its ~9 dB misfit. Here each cell's
squared field is modelled as

    E^2 = b + sum_i P_i * G_i(offset_i) * 30 / d0^2 * (r / d0)^-n

* ``P_i``: EIRP per sector of a tri-sector site (non-negative least squares);
* ``G_i``: 3GPP TR 38.901 sector pattern (config/physics.yaml) summed over three
  sectors at ``offset_i + 0/120/240`` degrees, downtilt from config;
* ``offset_i``: chosen per site from 0, 10, ..., 110 degrees by coordinate descent;
* ``r``: 3D distance with the mast height from the LiDAR roof under the site;
* ``n``: one city-wide path-loss exponent, chosen on held-out cells;
* cells at the Cartoradio cap are lower bounds (censored): they enter the fit
  only where the model falls below the cap.

All functions are pure; ``scripts/refit_register.py`` runs them on real data.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Sequence

import numpy as np
from numpy.typing import NDArray

from twin.physics import pattern
from twin.providers.settings import Settings

F64 = NDArray[np.float64]
OFFSETS_DEG = np.arange(0.0, 120.0, 10.0)


def _cfg(key: str) -> Any:
    node = Settings.load().section("estimated", "register").get("refit", {})[key]
    return node["value"] if isinstance(node, dict) and "value" in node else node


def mast_offset_m() -> float:
    return float(_cfg("mast_offset_m"))


def tower_height_m() -> float:
    return float(_cfg("tower_height_m"))


def mast_height(roof_m: float | None, on_building: bool) -> float:
    """Antenna centre above ground: LiDAR roof + mast offset on a building, else a typical tower."""
    if on_building and roof_m is not None and math.isfinite(roof_m):
        return float(roof_m) + mast_offset_m()
    return tower_height_m()


def offset_index(offset_deg: float) -> int:
    return int(np.argmin(np.abs(OFFSETS_DEG - (offset_deg % 120.0))))


@dataclass(frozen=True)
class Model:
    exponent: float
    receptor_m: float
    tilt_deg: float
    reference_m: float = 100.0


@dataclass(frozen=True)
class Problem:
    sites: F64           # (n, 2) local metres
    heights: F64         # (n,) antenna centre above ground
    cell_x: F64
    cell_y: F64
    e2: F64              # Cartoradio E^2, (V/m)^2
    at_cap: NDArray[np.bool_]


@dataclass
class FitResult:
    model: Model
    powers_w: F64
    offsets_deg: F64
    background: float
    predicted: F64
    train_median_abs_db: float
    holdout_median_abs_db: float
    n_holdout: int


def gain_table(site: F64, height: float, x: F64, y: F64, model: Model) -> F64:
    """(12, cells): E^2 per watt of sector EIRP for each tri-sector offset."""
    dx, dy = x - site[0], y - site[1]
    horiz = np.maximum(np.hypot(dx, dy), 1.0)
    dz = height - model.receptor_m
    r = np.hypot(horiz, dz)
    d0 = model.reference_m
    path = 30.0 / d0 ** 2 * (np.maximum(r, 1.0) / d0) ** (-model.exponent)
    bearing = np.degrees(np.arctan2(dx, dy))
    elev = np.degrees(np.arctan2(dz, horiz))
    out = np.zeros((OFFSETS_DEG.size, x.size))
    for k, off in enumerate(OFFSETS_DEG):
        g = np.zeros(x.size)
        for s in range(3):
            g += 10.0 ** (pattern.gain_db_array(bearing - (off + 120.0 * s), elev, model.tilt_deg) / 10.0)
        out[k] = g * path
    return out


def _neighbourhoods(prob: Problem, radius_m: float) -> list[NDArray[np.int64]]:
    from scipy.spatial import cKDTree  # type: ignore[import-untyped]

    tree = cKDTree(np.column_stack([prob.cell_x, prob.cell_y]))
    return [np.asarray(sorted(tree.query_ball_point(s, radius_m)), dtype=np.int64) for s in prob.sites]


def _nnls(cols: Sequence[tuple[NDArray[np.int64], F64]], rows: NDArray[np.bool_], target: F64,
          weight: F64) -> tuple[F64, float]:
    from scipy.optimize import lsq_linear  # type: ignore[import-untyped]
    from scipy.sparse import coo_matrix, diags  # type: ignore[import-untyped]

    idx = np.nonzero(rows)[0]
    remap = -np.ones(target.size, dtype=np.int64)
    remap[idx] = np.arange(idx.size)
    r_all: list[NDArray[np.int64]] = []
    c_all: list[NDArray[np.int64]] = []
    v_all: list[F64] = []
    for j, (cells, vals) in enumerate(cols):
        keep = remap[cells] >= 0
        r_all.append(remap[cells[keep]])
        c_all.append(np.full(int(keep.sum()), j))
        v_all.append(vals[keep] * weight[cells[keep]])
    n = len(cols)
    r_all.append(np.arange(idx.size))
    c_all.append(np.full(idx.size, n))
    v_all.append(weight[idx])
    a = coo_matrix((np.concatenate(v_all), (np.concatenate(r_all), np.concatenate(c_all))),
                   shape=(idx.size, n + 1)).tocsr()
    norms = np.sqrt(np.asarray(a.multiply(a).sum(axis=0)).ravel())
    norms[norms == 0] = 1.0
    sol = lsq_linear(a @ diags(1.0 / norms), target[idx] * weight[idx], bounds=(0.0, np.inf),
                     method="trf", lsmr_tol=1e-10, tol=1e-10, max_iter=2000)
    x = sol.x / norms
    return np.asarray(x[:n], dtype=np.float64), float(x[n])


def _predict(cols: Sequence[tuple[NDArray[np.int64], F64]], powers: F64, background: float, size: int) -> F64:
    pred = np.full(size, background)
    for (cells, vals), p in zip(cols, powers):
        pred[cells] += p * vals
    return pred


def fit(prob: Problem, model: Model, sigma_db: float, radius_m: float, holdout: NDArray[np.bool_] | None = None,
        search_azimuth: bool = True, passes: int = 2) -> FitResult:
    holdout = np.zeros(prob.e2.size, bool) if holdout is None else holdout
    hoods = _neighbourhoods(prob, radius_m)
    tables = [gain_table(prob.sites[i], float(prob.heights[i]), prob.cell_x[h], prob.cell_y[h], model)
              for i, h in enumerate(hoods)]
    weight = 1.0 / np.maximum(prob.e2, 1e-9)  # relative errors: every cell counts the same in dB terms
    _ = sigma_db
    target = prob.e2.copy()
    covered = np.zeros(target.size, bool)  # only cells within reach of some site inform the fit
    for h in hoods:
        covered[h] = True
    free = covered & (~holdout) & (~prob.at_cap) & (prob.e2 > 0)
    choice = np.zeros(len(hoods), dtype=np.int64)
    cols = [(h, t.mean(axis=0)) for h, t in zip(hoods, tables)]   # unknown direction: orientation average
    powers, background = _nnls(cols, free, target, weight)
    rows = free.copy()
    for _sweep in range(passes if search_azimuth else 0):
        pred = _predict(cols, powers, background, target.size)
        for i, (h, t) in enumerate(zip(hoods, tables)):
            use = rows[h]
            if not use.any():
                continue
            w = weight[h][use]
            resid = (target[h] - pred[h] + powers[i] * cols[i][1])[use] * w
            best, best_sse, best_p = choice[i], np.inf, powers[i]
            for k in range(OFFSETS_DEG.size):
                c = t[k][use] * w
                cc = float(c @ c)
                p = max(0.0, float(c @ resid) / cc) if cc > 0 else 0.0
                sse = float(np.sum((resid - p * c) ** 2))
                if sse < best_sse:
                    best, best_sse, best_p = k, sse, p
            pred[h] += best_p * t[best] - powers[i] * cols[i][1]
            choice[i], powers[i] = best, best_p
            cols[i] = (h, t[best])
        powers, background = _nnls(cols, rows, target, weight)
    # Censored cells: a capped cell says "cap or more"; it binds only where the model is below it.
    for _round in range(3):
        pred = _predict(cols, powers, background, target.size)
        binding = covered & (~holdout) & prob.at_cap & (pred < prob.e2)
        new_rows = free | binding
        if np.array_equal(new_rows, rows):
            break
        rows = new_rows
        powers, background = _nnls(cols, rows, target, weight)
    pred = _predict(cols, powers, background, target.size)
    err = np.abs(10.0 * np.log10(np.maximum(pred, 1e-12) / np.maximum(prob.e2, 1e-12)))
    test = covered & holdout & (~prob.at_cap) & (prob.e2 > 0)
    return FitResult(model=model, powers_w=powers, offsets_deg=OFFSETS_DEG[choice] if search_azimuth
                     else np.full(len(hoods), np.nan), background=background, predicted=pred,
                     train_median_abs_db=float(np.median(err[free])) if free.any() else math.nan,
                     holdout_median_abs_db=float(np.median(err[test])) if test.any() else math.nan,
                     n_holdout=int(test.sum()))


def select_exponent(prob: Problem, exponents: Sequence[float], sigma_db: float, radius_m: float, seed: int,
                    holdout_share: float = 0.2, base: Model | None = None,
                    search_azimuth: bool = True) -> FitResult:
    """Fit every exponent on the same split; keep the one with the lowest hold-out error, refit on all cells."""
    rng = np.random.default_rng(seed)
    holdout = rng.random(prob.e2.size) < holdout_share
    base = base or Model(exponent=2.0, receptor_m=1.5, tilt_deg=6.0)
    trials = [fit(prob, replace(base, exponent=float(n)), sigma_db, radius_m, holdout, search_azimuth)
              for n in exponents]
    best = min(trials, key=lambda t: t.holdout_median_abs_db)
    return best
