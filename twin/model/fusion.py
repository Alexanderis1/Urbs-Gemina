"""Height fusion: each source is a noisy measurement of the same building height.

1. Calibrate each source against a reference (the most trusted heights we have):
   bias = mean(source - reference), spread = residual standard deviation minus the
   reference's own noise. A source with its own per-building variance (GBA) gets a scale factor.
2. Fuse the bias-corrected measurements with inverse-variance weights (Gaussian product),
   with a weak prior so every building gets a value.
3. Flag buildings whose sources disagree more than chance allows (chi-square test).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional

import numpy as np
import numpy.typing as npt

Array = npt.NDArray[np.float64]


@dataclass(frozen=True)
class SourceObs:
    value: Array  # metres, NaN = no measurement
    sd: Array  # metres, one standard deviation


@dataclass(frozen=True)
class Calibration:
    bias_m: float
    sd_m: float  # spread for sources without a per-building sd
    scale: float  # multiplier for sources with a per-building sd
    n: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FusionResult:
    mean: Array
    sd: Array
    sources: npt.NDArray[np.object_]  # "osm_tag+gba" or "prior"
    dominant: npt.NDArray[np.object_]  # source with the largest weight
    conflict: npt.NDArray[np.bool_]


def calibrate(
    src: Array,
    ref: Array,
    *,
    ref_sd: float,
    prior_sd: Optional[Array],
    min_pairs: int,
    fallback_sd: float = 3.0,
) -> Calibration:
    """Bias and spread of ``src`` against ``ref`` where both exist."""
    ok = np.isfinite(src) & np.isfinite(ref)
    n = int(ok.sum())
    if n < min_pairs:
        return Calibration(0.0, fallback_sd, 1.0, n)
    res = src[ok] - ref[ok]
    bias = float(np.median(res))  # robust to the odd wrong tag
    centred = res - bias
    # Robust spread: 1.4826 x MAD estimates the standard deviation under a normal model.
    spread = float(1.4826 * np.median(np.abs(centred)))
    sd = float(np.sqrt(max(spread**2 - ref_sd**2, 0.25)))
    scale = 1.0
    if prior_sd is not None:
        claimed = prior_sd[ok]
        good = np.isfinite(claimed) & (claimed > 0)
        if good.sum() >= min_pairs:
            z = centred[good] / np.sqrt(claimed[good] ** 2 + ref_sd**2)
            scale = float(1.4826 * np.median(np.abs(z)))
    return Calibration(bias, sd, scale, n)


def fuse(
    obs: Mapping[str, SourceObs], *, prior_mean: float, prior_sd: float, conflict_chi2: float
) -> FusionResult:
    names = list(obs)
    n = len(next(iter(obs.values())).value) if obs else 0
    values = np.vstack([obs[k].value for k in names]) if names else np.zeros((0, n))
    sds = np.vstack([obs[k].sd for k in names]) if names else np.zeros((0, n))
    valid = np.isfinite(values) & np.isfinite(sds) & (sds > 0)
    w = np.where(valid, 1.0 / np.where(valid, sds, 1.0) ** 2, 0.0)
    x = np.where(valid, values, 0.0)
    # The prior is only a fallback: it fills buildings with no measurement and never pulls measured ones.
    w_meas = w.sum(axis=0)
    has = w_meas > 0
    safe = np.where(has, w_meas, 1.0)
    mean = np.where(has, (w * x).sum(axis=0) / safe, prior_mean)
    sd = np.where(has, 1.0 / np.sqrt(safe), prior_sd)

    # Chi-square of the measurements around the fused mean, with (k - 1) degrees of freedom.
    k = valid.sum(axis=0)
    chi2 = (w * (x - mean) ** 2).sum(axis=0)
    conflict = (k >= 2) & (chi2 / np.maximum(k - 1, 1) > conflict_chi2)

    srcs = np.empty(n, dtype=object)
    dom = np.empty(n, dtype=object)
    for i in range(n):
        used = [names[j] for j in range(len(names)) if valid[j, i]]
        srcs[i] = "+".join(used) if used else "prior"
        dom[i] = names[int(np.argmax(w[:, i]))] if used else "prior"
    return FusionResult(mean, sd, srcs, dom, conflict)
