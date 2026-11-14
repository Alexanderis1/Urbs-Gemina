"""Checks of the scenario physics against real past events (data sets in eval/scenarios/).

Each function returns plain numbers (errors, hit rates) that the validation report and the tests
use. Nothing here changes a model: calibrated values are copied into config with a basis note.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np


def _h_of_q(q: Any, h0: float, a: float, b: float) -> Any:
    return h0 + np.power(np.maximum(q, 1e-9) / a, 1.0 / b)


def fit_rating(pairs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Power-law stage-discharge curve h = h0 + (Q / a)^(1/b) fitted to observed pairs, with leave-one-out errors."""
    from scipy.optimize import curve_fit  # type: ignore[import-untyped]

    q = np.asarray([float(p["discharge_m3s"]) for p in pairs])
    h = np.asarray([float(p["stage_m"]) for p in pairs])
    bounds = ([0.0, 1.0, 0.8], [float(h.min()), 5000.0, 3.0])
    p0 = [float(h.min()) - 1.5, 200.0, 1.2]
    params, _ = curve_fit(_h_of_q, q, h, p0=p0, bounds=bounds, maxfev=20000)
    residuals = h - _h_of_q(q, *params)
    loo: list[float] = []
    for i in range(q.size):
        keep = np.arange(q.size) != i
        p_i, _ = curve_fit(_h_of_q, q[keep], h[keep], p0=params, bounds=bounds, maxfev=20000)
        loo.append(float(h[i] - _h_of_q(q[i], *p_i)))
    return {"h0": float(params[0]), "a": float(params[1]), "b": float(params[2]),
            "rmse_m": float(np.sqrt(np.mean(residuals ** 2))), "residuals_m": [round(float(r), 2) for r in residuals],
            "loo_rmse_m": float(np.sqrt(np.mean(np.square(loo)))), "loo_m": [round(v, 2) for v in loo]}


def skill(model: Any, reference: Any, domain: Any) -> dict[str, float]:
    """Hit rate, false alarm ratio and critical success index of a wet/dry map against a reference map."""
    m = np.asarray(model, dtype=bool) & domain
    r = np.asarray(reference, dtype=bool) & domain
    hits = float((m & r).sum())
    misses = float((~m & r).sum())
    false = float((m & ~r).sum())
    return {"hit_rate": round(hits / (hits + misses), 3) if hits + misses else float("nan"),
            "false_alarm_ratio": round(false / (hits + false), 3) if hits + false else float("nan"),
            "csi": round(hits / (hits + misses + false), 3) if hits + misses + false else float("nan")}
