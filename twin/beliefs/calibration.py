"""Is the stated uncertainty honest? Leave-one-station-out check.

For each moment and each station: hide that station, rebuild the belief from
the prior plus all the *other* stations, and predict the hidden reading. If the
layer's uncertainty is honest, about 90% of hidden readings fall inside the
predicted 90% range, and the standardised errors have a spread close to 1.
If not, the layer is labelled "uncalibrated" and the reason is reported.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from statistics import NormalDist
from typing import Any, Iterable, Literal, Mapping

import numpy as np

from twin.beliefs.config import LayerSpec
from twin.beliefs.grid import local_xy_km
from twin.beliefs.layer import posterior
from twin.providers.base import Observation

Status = Literal["calibrated", "uncalibrated"]


@dataclass(frozen=True)
class CalibrationRules:
    interval: float
    coverage_ok: tuple[float, float]
    z_sd_ok: tuple[float, float]
    min_stations: int

    @classmethod
    def from_config(cls, raw: Mapping[str, Any]) -> CalibrationRules:
        return cls(
            interval=float(raw["interval"]),
            coverage_ok=(float(raw["coverage_ok"][0]), float(raw["coverage_ok"][1])),
            z_sd_ok=(float(raw["z_sd_ok"][0]), float(raw["z_sd_ok"][1])),
            min_stations=int(raw["min_stations"]),
        )


@dataclass(frozen=True)
class CalibrationReport:
    status: Status
    reason: str
    n_predictions: int = 0
    #: Share of hidden readings inside the predicted interval (target: ``interval``).
    coverage: float = math.nan
    #: Mean and spread of (reading - prediction) / predicted sd (targets: 0 and 1).
    z_mean: float = math.nan
    z_sd: float = math.nan
    rmse: float = math.nan

    def as_dict(self) -> dict[str, Any]:
        def clean(x: float) -> float | None:
            return None if math.isnan(x) else round(x, 4)

        return {
            "status": self.status,
            "reason": self.reason,
            "n_predictions": self.n_predictions,
            "coverage": clean(self.coverage),
            "z_mean": clean(self.z_mean),
            "z_sd": clean(self.z_sd),
            "rmse": clean(self.rmse),
        }


@dataclass(frozen=True)
class Residual:
    entity_id: str
    observed_at: datetime
    error: float
    z: float


def _group(spec: LayerSpec, observations: Iterable[Observation]) -> dict[datetime, dict[str, Observation]]:
    by_time: dict[datetime, dict[str, Observation]] = {}
    for o in observations:
        if o.entity_type in spec.entity_types and spec.value_key in o.values:
            # One reading per station per moment (the last one wins).
            by_time.setdefault(o.observed_at, {})[o.entity_id] = o
    return by_time


def station_residuals(
    spec: LayerSpec,
    by_time: Mapping[datetime, Mapping[str, Observation]],
    min_stations: int,
    prior_means: Mapping[tuple[str, datetime], float] | None = None,
    prior_sd: float | None = None,
) -> list[Residual]:
    """For every moment with enough stations: predict each station from the others.

    ``prior_means`` gives the layer's own starting map at each station and moment
    (e.g. the bias-corrected CAMS forecast), so the check tests the layer as it runs.
    Without it the generic prior from the config is used. ``prior_sd`` overrides the
    starting spread (the learned ``prior_field.sd``)."""
    key = spec.value_key
    out: list[Residual] = []
    for when, group in sorted(by_time.items()):
        if len(group) < min_stations:
            continue
        readings = list(group.values())
        xy = np.array(local_xy_km([(o.lon, o.lat) for o in readings]), dtype=np.float64)
        values = np.array([o.values[key] for o in readings])
        noise = np.array([max(o.sigma.get(key, 0.0) ** 2, 1e-6 * spec.prior.variance) for o in readings])
        generic = spec.prior.mean_at(when)
        means = np.array([generic if prior_means is None else prior_means.get((o.entity_id, when), generic)
                          for o in readings])
        prior_var = spec.prior.variance if prior_sd is None else prior_sd * prior_sd
        for k in range(len(readings)):
            others = np.arange(len(readings)) != k
            n_other = int(others.sum())
            mean, var = posterior(
                xy[k : k + 1],
                means[k : k + 1],
                np.array([prior_var]),
                xy[others],
                means[others],
                np.full(n_other, prior_var),
                values[others],
                noise[others],
                spec.correlation_length_km,
                spec.spatial_share,
            )
            err = float(values[k] - mean[0])
            out.append(Residual(readings[k].entity_id, when, err, err / math.sqrt(float(var[0]) + float(noise[k]))))
    return out


def sensor_health(
    spec: LayerSpec, observations: Iterable[Observation], z_flag: float = 3.0, min_moments: int = 3, min_stations: int = 5
) -> list[dict[str, Any]]:
    """Stations whose readings keep disagreeing with what their neighbours imply.

    Uses the same leave-one-out predictions as the calibration check. The worst
    station above ``z_flag`` (median absolute standardised error over at least
    ``min_moments`` moments) is flagged and removed, then the check is repeated,
    so one broken sensor does not make its neighbours look wrong too.
    """
    by_time = _group(spec, observations)
    flagged: dict[str, dict[str, Any]] = {}
    while True:
        residuals = station_residuals(spec, by_time, min_stations)
        per_station: dict[str, list[Residual]] = {}
        for r in residuals:
            per_station.setdefault(r.entity_id, []).append(r)
        summary: dict[str, dict[str, Any]] = {
            sid: {
                "entity_id": sid,
                "moments": len(rs),
                "median_abs_z": round(float(np.median([abs(r.z) for r in rs])), 2),
                "typical_offset": round(float(np.median([r.error for r in rs])), 2),
                "flag": False,
            }
            for sid, rs in per_station.items()
        }
        candidates = [s for s in summary.values() if s["moments"] >= min_moments and s["median_abs_z"] > z_flag]
        if not candidates:
            break
        worst = max(candidates, key=lambda s: float(s["median_abs_z"]))
        worst["flag"] = True
        flagged[str(worst["entity_id"])] = worst
        by_time = {t: {k: v for k, v in g.items() if k != worst["entity_id"]} for t, g in by_time.items()}
    return sorted(list(flagged.values()) + list(summary.values()), key=lambda s: str(s["entity_id"]))


def leave_one_station_out(
    spec: LayerSpec,
    observations: Iterable[Observation],
    rules: CalibrationRules,
    prior_means: Mapping[tuple[str, datetime], float] | None = None,
    prior_sd: float | None = None,
) -> CalibrationReport:
    """Hold out each station in turn and check the predicted range (see ``station_residuals``)."""
    if spec.calibration_method == "none":
        return CalibrationReport(status="uncalibrated", reason=spec.calibration_note or "calibration not possible for this layer")

    by_time = _group(spec, observations)
    n_stations = len({sid for group in by_time.values() for sid in group})
    if n_stations < rules.min_stations:
        return CalibrationReport(
            status="uncalibrated",
            reason=f"only {n_stations} stations with readings; the check needs at least {rules.min_stations}",
        )

    residuals = station_residuals(spec, by_time, rules.min_stations, prior_means, prior_sd)
    z_scores = [r.z for r in residuals]
    errors = [r.error for r in residuals]

    if not z_scores:
        return CalibrationReport(status="uncalibrated", reason=f"no moment had {rules.min_stations} stations reporting together")

    z = np.array(z_scores)
    half_width = NormalDist().inv_cdf(0.5 + rules.interval / 2.0)
    coverage = float(np.mean(np.abs(z) <= half_width))
    z_mean = float(np.mean(z))
    z_sd = float(np.std(z))
    rmse = float(np.sqrt(np.mean(np.square(errors))))

    problems = []
    lo, hi = rules.coverage_ok
    if not lo <= coverage <= hi:
        problems.append(f"coverage of the {rules.interval:.0%} range is {coverage:.0%}, outside {lo:.0%}-{hi:.0%}")
    lo, hi = rules.z_sd_ok
    if not lo <= z_sd <= hi:
        problems.append(f"spread of standardised errors is {z_sd:.2f}, outside {lo}-{hi}")
    status: Status = "uncalibrated" if problems else "calibrated"
    reason = "; ".join(problems) if problems else f"{len(z)} held-out readings: coverage {coverage:.0%}, error spread {z_sd:.2f}"
    return CalibrationReport(
        status=status, reason=reason, n_predictions=len(z), coverage=coverage, z_mean=z_mean, z_sd=z_sd, rmse=rmse
    )
