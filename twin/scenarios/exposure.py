"""Population exposure: residents of census sections where the field is above a threshold.

Only aggregates leave this module: section id, resident count and field values.
"""
from __future__ import annotations

from typing import Any, Mapping

from twin.scenarios import config
from twin.scenarios.antenna import _side, build_model, thresholds
from twin.scenarios.area import Area
from twin.scenarios.data import ScenarioData
from twin.scenarios.geometry import centroid


def _unknown(counts: Mapping[str, int]) -> dict[str, None]:
    return {key: None for key in counts}


def run_population_exposure(area: Area, change: Mapping[str, Any], data: ScenarioData) -> dict[str, Any]:
    warnings: list[str] = []
    model = build_model(change, data, warnings)
    limits = thresholds()
    flag_p = float(config.value(config.load("scenarios.yaml")["antenna"], "exceedance_report_probability"))
    cfg = config.load("scenarios.yaml")["population_exposure"]
    pop_key, id_key = str(config.value(cfg, "population_property")), str(config.value(cfg, "section_id_property"))

    kinds = {"emf_baseline": data.baseline_kind if data.baseline_field is not None else "not_available",
             "new_site": "estimated", "census": "real" if data.census is not None else "not_available"}
    if model.old is not None:
        kinds["existing_site"] = "simulated"

    totals: dict[str, dict[str, int]] = {
        side: {"residents_flagged_attention": 0, "residents_flagged_limit": 0} for side in ("baseline", "variant")}
    rows: list[dict[str, Any]] = []
    residents_total: int | None = None
    if data.census is None:
        warnings.append("Census sections not available: resident counts cannot be computed.")
    else:
        residents_total = 0
        for feature in data.census.get("features", []):
            geometry = feature.get("geometry")
            props = feature.get("properties") or {}
            if not geometry:
                continue
            lon, lat = centroid(geometry)
            if not area.contains(lon, lat):
                continue
            residents = int(props.get(pop_key) or 0)
            residents_total += residents
            base, variant = model.at(lon, lat)
            sides = {"baseline": _side(base.median_v_per_m, base.sigma_db, limits),
                     "variant": _side(variant.median_v_per_m, variant.sigma_db, limits)}
            for side, values in sides.items():
                if values["p_exceed_attention"] >= flag_p:
                    totals[side]["residents_flagged_attention"] += residents
                if values["p_exceed_limit"] >= flag_p:
                    totals[side]["residents_flagged_limit"] += residents
            rows.append({"section_id": str(props.get(id_key, "")), "residents": residents,
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
            "baseline": totals["baseline"] if data.census is not None else _unknown(totals["baseline"]),
            "variant": totals["variant"] if data.census is not None else _unknown(totals["variant"]),
            "sections": rows,
        },
        "data_kinds": kinds,
        "sources": [s for s in [data.baseline_source, data.census_source] if s],
        "synthetic": model.old is not None or (data.baseline_field is not None and data.baseline_kind == "simulated"),
        "warnings": warnings,
    }
