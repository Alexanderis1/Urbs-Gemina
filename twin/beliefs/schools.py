"""Schools to check: every pollutant at every school, worst first.

For each school in ``sensitive_sites`` (category ``education``) and each air
layer, it reads the school's cell: the middle value, the high end (P95), the
chance of being above that pollutant's limit, and ``share_of_limit`` = P50 /
limit. A school's rank is its worst pollutant: first by chance above the limit
(when it is at least 5%; smaller chances mostly reflect a wide prior), then by
share of the limit. That keeps the list useful on clean days, when every
chance is near zero. Children aged 0-14 living in the school's cell (ISTAT 2021)
are shown for context. Limits come from the caller (config/thresholds.yaml).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from twin.beliefs.layer import BeliefLayer
from twin.beliefs.sites import site_values


def schools_to_check(
    layers: Mapping[str, tuple[BeliefLayer, float]],
    sites_path: Path,
    census: Mapping[str, Mapping[str, Any]],
    top: int = 10,
) -> dict[str, Any]:
    per_school: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    data_kinds: dict[str, str] = {"sensitive_sites": "real", "census": "real"}
    sources: dict[str, dict[str, Any]] = {}
    synthetic = False
    for name, (layer, limit) in layers.items():
        out = site_values(layer, sites_path, threshold=limit, categories=("education",))
        data_kinds.update(out["data_kinds"])
        synthetic = synthetic or bool(out["synthetic"])
        for s in out["sources"]:
            sources[str(s["id"])] = s
        warnings.extend(w for w in out["warnings"] if w not in warnings)
        for row in out["result"]["sites"]:
            school = per_school.setdefault(str(row["site_id"]), {
                "site_id": row["site_id"],
                "name": row["name"],
                "cell": row["cell"],
                "pollutants": {},
            })
            school["pollutants"][name] = {
                "p50": row["p50"],
                "p95": row["p95"],
                "limit": limit,
                "p_exceed": row["p_exceed"],
                "share_of_limit": round(float(row["p50"]) / limit, 3) if limit > 0 else None,
            }
    ranked = []
    for school in per_school.values():
        worst = max(school["pollutants"], key=lambda n: _key(school["pollutants"][n]))
        school["worst"] = worst
        child = census.get(school["cell"], {}).get("children_0_14")
        school["children_0_14_in_cell"] = int(child) if child is not None else None
        ranked.append(school)
    ranked.sort(key=lambda s: _key(s["pollutants"][s["worst"]]), reverse=True)
    warnings.append(
        "limits have legal averaging periods (hourly, daily, annual) while these are near-instant estimates: "
        "a high value is a reason to check, not a legal exceedance"
    )
    return {
        "status": "ok",
        "reason": None,
        "inputs": {"thresholds": {n: lim for n, (_, lim) in layers.items()}, "top": top},
        "result": {
            "rank": "worst pollutant first: chance above its limit (if 5% or more), then middle value as a share of the limit",
            "schools_checked": len(ranked),
            "schools": ranked[:top],
        },
        "data_kinds": data_kinds,
        "sources": list(sources.values()),
        "synthetic": synthetic,
        "warnings": warnings,
    }


#: Chances below this are noise from a wide prior, not a signal; rank those by share of the limit.
MEANINGFUL_P = 0.05


def _key(p: Mapping[str, Any]) -> tuple[float, float]:
    chance = float(p["p_exceed"])
    return (chance if chance >= MEANINGFUL_P else 0.0, float(p["share_of_limit"] or 0.0))
