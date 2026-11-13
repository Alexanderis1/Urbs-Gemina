"""Population exposure: residents of census sections where the field is above a threshold.

Census sections come from WS1 as data/processed/census_sections.geojson with the
hub-fixed fields sez_id, residents, children_0_14, municipio, zone. Only those
fields are read, and only aggregates leave this module.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from twin.scenarios import config
from twin.scenarios.antenna import _side, build_model, thresholds
from twin.scenarios.area import Area
from twin.scenarios.data import ScenarioData
from twin.scenarios.geometry import centroid

COUNTS = ("residents", "children_0_14")


def census_path() -> Path:
    return config.ROOT / str(config.value(config.load("scenarios.yaml")["population_exposure"], "census_file"))


def load_census(data: ScenarioData) -> Mapping[str, Any] | None:
    if data.census is not None:
        return data.census
    path = census_path()
    if not path.exists():
        return None
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else None


def run_population_exposure(area: Area, change: Mapping[str, Any], data: ScenarioData) -> dict[str, Any]:
    warnings: list[str] = []
    model = build_model(change, data, warnings)
    census = load_census(data)
    kinds = {"emf_baseline": data.baseline_kind if data.baseline_field is not None else "not_available",
             "new_site": "estimated", "census": "real" if census is not None else "not_available"}
    if model.old is not None:
        kinds["existing_site"] = "estimated"
    synthetic = False
    if census is None:
        reason = "Census sections not available yet (data/processed/census_sections.geojson is missing)."
        return {"result": {"status": "not_available", "reason": reason}, "data_kinds": kinds, "sources": [],
                "synthetic": synthetic, "warnings": [reason]}

    limits = thresholds()
    flag_p = float(config.value(config.load("scenarios.yaml")["antenna"], "exceedance_report_probability"))
    totals = {side: {f"{c}_flagged_{t}": 0 for c in COUNTS for t in ("attention", "limit")}
              for side in ("baseline", "variant")}
    rows: list[dict[str, Any]] = []
    residents_total = 0
    for feature in census.get("features", []):
        geometry = feature.get("geometry")
        props = feature.get("properties") or {}
        if not geometry:
            continue
        lon, lat = centroid(geometry)
        if not area.contains(lon, lat):
            continue
        counts = {c: int(props.get(c) or 0) for c in COUNTS}
        residents_total += counts["residents"]
        base, variant = model.at(lon, lat)
        sides = {"baseline": _side(base.median_v_per_m, base.sigma_db, limits),
                 "variant": _side(variant.median_v_per_m, variant.sigma_db, limits)}
        for side, values in sides.items():
            for t in ("attention", "limit"):
                if values[f"p_exceed_{t}"] >= flag_p:
                    for c in COUNTS:
                        totals[side][f"{c}_flagged_{t}"] += counts[c]
        rows.append({"sez_id": str(props.get("sez_id", "")), **counts,
                     "baseline_p50": sides["baseline"]["p50"], "variant_p50": sides["variant"]["p50"],
                     "baseline_p_exceed_attention": sides["baseline"]["p_exceed_attention"],
                     "variant_p_exceed_attention": sides["variant"]["p_exceed_attention"]})
    rows.sort(key=lambda r: r["variant_p_exceed_attention"], reverse=True)
    warnings.append("Field taken at each section's centroid; residents are assumed spread evenly in a section.")
    if data.baseline_field is None:
        warnings.append("EMF baseline (Cartoradio) not available: the variant shows the changed antenna alone.")

    return {
        "result": {
            "calibration": "uncalibrated",
            "thresholds": limits,
            "flag_probability": flag_p,
            "residents_total": residents_total,
            "baseline": totals["baseline"],
            "variant": totals["variant"],
            "sections": rows,
        },
        "data_kinds": kinds,
        "sources": [s for s in [data.baseline_source, data.census_source] if s],
        "synthetic": synthetic,
        "warnings": warnings,
    }
