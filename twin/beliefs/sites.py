"""A belief layer read at sensitive sites: schools, hospitals, care facilities...

For each site in WS1's ``sensitive_sites.geojson``: the layer's mean, P5-P95
range and, given a threshold, the chance of being above it. Sites are sorted by
that chance, so an officer sees first where to look. Works for any layer
(air near schools, EMF near hospitals, heat at care homes).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any, Sequence

from twin.beliefs.api import calibration_of, exceedance_probability, snapshot_hash
from twin.beliefs.grid import cell_of
from twin.beliefs.layer import BeliefLayer

Z95 = NormalDist().inv_cdf(0.95)


def _point(geometry: dict[str, Any]) -> tuple[float, float]:
    if geometry["type"] == "Point":
        lon, lat = geometry["coordinates"][:2]
        return float(lon), float(lat)
    rings = geometry["coordinates"] if geometry["type"] == "Polygon" else geometry["coordinates"][0]
    pts = rings[0][:-1]
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def site_values(
    layer: BeliefLayer,
    sites_path: Path,
    threshold: float | None = None,
    categories: Sequence[str] | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    outside = 0
    floor = layer.spec.min_value
    for feature in json.loads(sites_path.read_text(encoding="utf-8"))["features"]:
        props = feature["properties"]
        if categories is not None and props.get("category") not in categories:
            continue
        lon, lat = _point(feature["geometry"])
        i = layer.index.get(cell_of(lon, lat, layer.resolution))
        if i is None:
            outside += 1
            continue
        mean = float(layer.mean[i])
        sd = math.sqrt(float(layer.variance[i]))
        row: dict[str, Any] = {
            "site_id": props.get("site_id"),
            "cell": layer.cells[i],
            "name": props.get("name"),
            "category": props.get("category"),
            "subtype": props.get("subtype"),
            "p5": round(max(floor, mean - Z95 * sd), 2),
            "p50": round(max(floor, mean), 2),
            "p95": round(max(floor, mean + Z95 * sd), 2),
        }
        if threshold is not None:
            row["p_exceed"] = round(exceedance_probability(mean, sd, threshold), 4)
        rows.append(row)
    if threshold is not None:
        rows.sort(key=lambda r: -float(r["p_exceed"]))
    summary: dict[str, dict[str, Any]] = {}
    for r in rows:
        s = summary.setdefault(str(r["category"]), {"sites": 0, "likely_above": 0})
        s["sites"] += 1
        if threshold is not None and r["p_exceed"] >= 0.5:
            s["likely_above"] += 1
    warnings = list(layer.spec.caveats)
    if outside:
        warnings.append(f"{outside} sites lie outside the layer's area and were skipped")
    calibration = calibration_of(layer)
    if calibration.status == "uncalibrated":
        warnings.append(f"the layer's uncertainty is uncalibrated: {calibration.reason}")
    warnings.append("values are for the site's grid cell (about 0.11 km2), not the exact building")
    return {
        "status": "ok",
        "reason": None,
        "inputs": {"layer": layer.spec.name, "threshold": threshold, "categories": list(categories) if categories else None},
        "result": {"unit": layer.spec.unit, "summary": summary, "sites": rows},
        "data_kinds": {layer.spec.name: "simulated" if layer.synthetic else "estimated", "sensitive_sites": "real"},
        "sources": [{"id": s, "retrieved_at": layer.as_of.isoformat()} for s in layer.sources],
        "synthetic": layer.synthetic,
        "warnings": warnings,
        "snapshot_hash": snapshot_hash(layer),
    }
