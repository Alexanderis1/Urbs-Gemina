"""Electromagnetic-field arithmetic used by the antenna module.

Simple far-field formulas only. Results are estimates with a stated spread,
never measurements. Legal thresholds are read from config/thresholds.yaml.
"""
from __future__ import annotations

import math
from typing import Iterable

#: z-score of the 95th percentile of a normal distribution
Z95 = 1.6448536269514722


def free_space_field(eirp_w: float, distance_m: float) -> float:
    """Electric field in V/m at ``distance_m`` from a source of ``eirp_w`` watts EIRP."""
    if eirp_w < 0:
        raise ValueError("EIRP cannot be negative")
    return math.sqrt(30.0 * eirp_w) / max(distance_m, 1.0)


def combine_fields(fields_v_per_m: Iterable[float]) -> float:
    """Total field of independent sources: root of the sum of squares."""
    return math.sqrt(sum(value * value for value in fields_v_per_m))


def add_to_baseline(baseline_v_per_m: float, new_source_v_per_m: float) -> float:
    """Field after adding one source to an existing baseline (e.g. the cartoradio grid)."""
    return combine_fields((baseline_v_per_m, new_source_v_per_m))


def field_range(median_v_per_m: float, sigma_db: float) -> tuple[float, float, float]:
    """(P5, P50, P95) of a field whose error is normal in decibels."""
    factor = 10.0 ** (Z95 * sigma_db / 20.0)
    return median_v_per_m / factor, median_v_per_m, median_v_per_m * factor


def exceedance_probability(median_v_per_m: float, sigma_db: float, threshold_v_per_m: float) -> float:
    """Probability that the true field is above the threshold."""
    if median_v_per_m <= 0.0:
        return 0.0
    if sigma_db <= 0.0:
        return 1.0 if median_v_per_m > threshold_v_per_m else 0.0
    gap_db = 20.0 * math.log10(threshold_v_per_m / median_v_per_m)
    return 0.5 * (1.0 - math.erf(gap_db / (sigma_db * math.sqrt(2.0))))
