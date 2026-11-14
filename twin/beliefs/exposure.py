"""How many people live where a layer is above a threshold, with a range.

Combines a belief layer (e.g. air_no2) with ISTAT 2021 census residents and
children per cell, grouped by municipio. Three numbers per group:

- ``expected``: sum over cells of residents x probability that the cell is above the threshold;
- ``low`` / ``high``: the same count if the true field sat at the low (P5) or high
  (P95) end of its range everywhere at once. Errors of nearby cells move
  together, so this band is wider, and more honest, than an independent-cells range.

The threshold is passed in by the caller (thresholds live in config/thresholds.yaml).
"""
from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any, Mapping

import numpy as np

from twin.beliefs.api import calibration_of, snapshot_hash
from twin.beliefs.layer import BeliefLayer

Z95 = NormalDist().inv_cdf(0.95)


def exposure(layer: BeliefLayer, census: Mapping[str, Mapping[str, Any]], threshold: float) -> dict[str, Any]:
    idx = [layer.index[c] for c in census if c in layer.index]
    cells = [c for c in census if c in layer.index]
    mean = layer.mean[idx]
    sd = np.sqrt(layer.variance[idx])
    p_above = np.array([1.0 - NormalDist().cdf((threshold - m) / s) if s > 0 else float(m > threshold) for m, s in zip(mean, sd)])
    low_above = (mean - Z95 * sd) > threshold
    high_above = (mean + Z95 * sd) > threshold
    residents = np.array([float(census[c]["residents"]) for c in cells])
    children = np.array([float(census[c].get("children_0_14") or 0) for c in cells])
    groups = np.array([str(census[c].get("municipio")) for c in cells])

    def summary(mask: np.ndarray, name: str) -> dict[str, Any]:
        r = residents[mask]
        k = children[mask]
        total = float(r.sum())
        weighted = float((r * mean[mask]).sum() / total) if total > 0 else math.nan
        # Errors of nearby cells are correlated, so the population-weighted sd is the
        # weighted mean of cell sds (fully correlated), not the smaller independent one.
        weighted_sd = float((r * sd[mask]).sum() / total) if total > 0 else math.nan
        return {
            "group": name,
            "residents": int(total),
            "children_0_14": int(k.sum()),
            "mean_exposure": {"value": round(weighted, 2), "sd": round(weighted_sd, 2), "unit": layer.spec.unit},
            "people_above": _count(r, p_above[mask], low_above[mask], high_above[mask]),
            "children_above": _count(k, p_above[mask], low_above[mask], high_above[mask]),
        }

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
        "data_kinds": {layer.spec.name: "simulated" if layer.synthetic else "estimated", "residents": "real"},
        "sources": [{"id": s, "retrieved_at": layer.as_of.isoformat()} for s in layer.sources] + [{"id": "istat_census_2021", "retrieved_at": None}],
        "synthetic": layer.synthetic,
        "warnings": warnings,
        "snapshot_hash": snapshot_hash(layer),
    }


def _count(people: np.ndarray, p: np.ndarray, low: np.ndarray, high: np.ndarray) -> dict[str, int]:
    return {
        "expected": int(round(float((people * p).sum()))),
        "low": int(people[low].sum()),
        "high": int(people[high].sum()),
    }


def _order(group: str) -> tuple[int, str]:
    return (int(group), "") if group.isdigit() else (10**6, group)
