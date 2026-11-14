"""How many people live where a layer is above a threshold, with a range.

Combines a belief layer (e.g. air_no2) with ISTAT 2021 census residents and
children per cell, grouped by municipio. Three numbers per group:

- ``expected``: sum over cells of residents x probability that the cell is above the threshold;
- ``low`` / ``high``: the same count if the true field sat at the low (P5) or high
  (P95) end of its range everywhere at once, widened if needed to contain ``expected``. Errors of nearby cells move
  together, so this band is wider, and more honest, than an independent-cells range.

The threshold is passed in by the caller (thresholds live in config/thresholds.yaml).
"""
from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any, Mapping, Sequence

import numpy as np

from twin.beliefs.api import calibration_of, snapshot_hash
from twin.beliefs.layer import BeliefLayer

Z95 = NormalDist().inv_cdf(0.95)


def exposure(
    layer: BeliefLayer,
    census: Mapping[str, Mapping[str, Any]],
    threshold: float,
    columns: Sequence[str] = ("residents", "children_0_14"),
) -> dict[str, Any]:
    idx = [layer.index[c] for c in census if c in layer.index]
    cells = [c for c in census if c in layer.index]
    mean = layer.mean[idx]
    sd = np.sqrt(layer.variance[idx])
    p_above = np.array([1.0 - NormalDist().cdf((threshold - m) / s) if s > 0 else float(m > threshold) for m, s in zip(mean, sd)])
    low_above = (mean - Z95 * sd) > threshold
    high_above = (mean + Z95 * sd) > threshold
    residents = np.array([float(census[c].get("residents") or 0) for c in cells])
    counts = {col: np.array([float(census[c].get(col) or 0) for c in cells]) for col in columns}
    groups = np.array([str(census[c].get("municipio")) for c in cells])

    def summary(mask: np.ndarray, name: str) -> dict[str, Any]:
        r = residents[mask]
        total = float(r.sum())
        weighted = float((r * mean[mask]).sum() / total) if total > 0 else math.nan
        # Errors of nearby cells are correlated, so the population-weighted sd is the
        # weighted mean of cell sds (fully correlated), not the smaller independent one.
        weighted_sd = float((r * sd[mask]).sum() / total) if total > 0 else math.nan
        row: dict[str, Any] = {
            "group": name,
            "mean_exposure": {"value": round(weighted, 2), "sd": round(weighted_sd, 2), "unit": layer.spec.unit},
        }
        for col, values in counts.items():
            row[col] = int(values[mask].sum())
            row[f"{col}_above"] = _count(values[mask], p_above[mask], low_above[mask], high_above[mask])
        return row

    by_group = [summary(groups == g, g) for g in sorted(set(groups.tolist()), key=_order)]
    warnings = list(layer.spec.caveats)
    warnings.append("residents are the ISTAT 2021 census (where people live, not where they are during the day)")
    calibration = calibration_of(layer)
    if calibration.status == "uncalibrated":
        warnings.append(f"the layer's uncertainty is uncalibrated: {calibration.reason}")
    return {
        "status": "ok",
        "reason": None,
        "inputs": {"layer": layer.spec.name, "threshold": threshold, "as_of": layer.as_of.isoformat()},
        "result": {
            "unit": layer.spec.unit,
            "method": "expected = sum(residents x P(above)); low/high = field at P5/P95 everywhere",
            "city": summary(np.ones(len(cells), dtype=bool), "city"),
            "groups": by_group,
        },
        "data_kinds": {layer.spec.name: "simulated" if layer.synthetic else "estimated", "census": "real"},
        "sources": [{"id": s, "retrieved_at": layer.as_of.isoformat()} for s in layer.sources] + [{"id": "istat_census_2021", "retrieved_at": None}],
        "synthetic": layer.synthetic,
        "warnings": warnings,
        "snapshot_hash": snapshot_hash(layer),
    }


def _count(people: np.ndarray, p: np.ndarray, low: np.ndarray, high: np.ndarray) -> dict[str, int]:
    """Expected count plus a band that always contains it.

    Many cells with a small chance each (below 5%) add up to an expected count
    while no single cell's P95 crosses the threshold; the band is widened to
    include the expected value so it never reads as "6, between 0 and 0".
    """
    expected = int(round(float((people * p).sum())))
    return {
        "expected": expected,
        "low": min(int(people[low].sum()), expected),
        "high": max(int(people[high].sum()), expected),
    }


def _order(group: str) -> tuple[int, str]:
    return (int(group), "") if group.isdigit() else (10**6, group)


def heat_watch(temperature: BeliefLayer, census: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Elderly residents and health/care sites where it is likely above the heat threshold (``heat`` in config).

    ``census`` rows may carry ``health_sites``: hospitals, clinics, care homes and
    Lazio-accredited facilities per cell, from ``points_per_cell(sensitive_sites,
    cells, categories=["health"])``.
    """
    import yaml

    from twin.beliefs.config import CONFIG_DIR

    raw = yaml.safe_load((CONFIG_DIR / "beliefs.yaml").read_text(encoding="utf-8"))["heat"]
    out = exposure(temperature, census, float(raw["threshold_c"]),
                   columns=("residents", "elderly_65_plus", "elderly_75_plus", "health_sites"))
    out["warnings"].append(
        "health sites = hospitals, clinics, care homes and Lazio-accredited facilities (official lists plus OSM); "
        "the accredited list does not say which ones house residents"
    )
    out["warnings"].append(f"heat threshold {raw['threshold_c']} degC is an operational assumption: {raw['basis']}")
    return out
