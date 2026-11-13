"""Tool ``estimate_field``: electric field with a range and the chance of exceeding the thresholds.

Baseline = official Cartoradio estimate (when the restricted provider is
configured). Variant = proposed antennas, modelled as free-space isotropic
sources (worst case). Both carry a log-normal error; the total is sampled with
a fixed seed so the same request always gives the same numbers.
"""
from __future__ import annotations

import math
import random
from typing import Any, Mapping, Sequence

from twin.tools.area import Area, resolve_area
from twin.tools.context_check import distance_to_geometry_m
from twin.tools.emf import combine_fields, free_space_field
from twin.tools.envelope import Source, ToolError
from twin.tools.runtime import BaselineValue, ToolRuntime
from twin.tools.settings import value

TOOL = "estimate_field"
MAX_ANTENNAS = 20


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    index = q * (len(sorted_values) - 1)
    low = math.floor(index)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (index - low)


def _thresholds(runtime: ToolRuntime) -> dict[str, dict[str, Any]]:
    emf = runtime.settings.thresholds["emf"]
    return {
        "attention_value": {"threshold_v_per_m": float(emf["attention_value_v_per_m"]["value"]),
                            "source": emf["attention_value_v_per_m"]["source"],
                            "applies_to": emf["attention_value_v_per_m"].get("applies_to", "")},
        "exposure_limit": {"threshold_v_per_m": float(emf["exposure_limit_v_per_m"]["value"]),
                           "source": emf["exposure_limit_v_per_m"]["source"],
                           "applies_to": emf["exposure_limit_v_per_m"].get("applies_to", "")},
    }


def _slant_distance_m(lon: float, lat: float, antenna: Mapping[str, Any], receptor_h: float) -> float:
    ground = distance_to_geometry_m(lon, lat, {"type": "Point", "coordinates": [antenna["lon"], antenna["lat"]]})
    return math.hypot(ground, float(antenna["height_m"]) - receptor_h)


def _normalise_antennas(runtime: ToolRuntime, variant: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not variant:
        return []
    unknown = set(variant) - {"add_antennas"}
    if unknown:
        raise ToolError(f"unsupported variant keys: {sorted(unknown)}; use 'add_antennas'")
    antennas = list(variant.get("add_antennas") or [])
    if len(antennas) > MAX_ANTENNAS:
        raise ToolError(f"at most {MAX_ANTENNAS} antennas per request")
    table: dict[str, Any] = runtime.settings.emf_params.get("typical_eirp_w", {})
    default_h = float(runtime.settings.tool("estimate_field", "default_antenna_height_m"))
    out: list[dict[str, Any]] = []
    for antenna in antennas:
        eirp = antenna.get("eirp_w")
        if eirp is None:
            band = str(antenna.get("band_mhz", ""))
            if band not in table:
                raise ToolError(f"antenna needs eirp_w or a band_mhz in {sorted(table)}")
            eirp = value(table[band])
        out.append({"lon": float(antenna["lon"]), "lat": float(antenna["lat"]), "eirp_w": float(eirp),
                    "height_m": float(antenna.get("height_m") or default_h),
                    "eirp_basis": "given" if antenna.get("eirp_w") is not None else "typical value (assumption)"})
    return out


class _Model:
    def __init__(self, runtime: ToolRuntime) -> None:
        s = runtime.settings
        self.runtime = runtime
        self.sigma_b = float(s.tool("estimate_field", "baseline_sigma_db"))
        self.sigma_m = float(value(s.emf_params.get("model_error_sigma_db", 4.0)))
        self.cap = float(s.tool("estimate_field", "baseline_cap_v_per_m"))
        self.receptor_h = float(s.tool("estimate_field", "receptor_height_m"))
        mc = s.tools["estimate_field"]["monte_carlo"]
        self.samples, self.area_samples, self.seed = int(mc["samples"]), int(mc["area_samples"]), int(mc["seed"])
        self.thresholds = _thresholds(runtime)

    def at(self, lon: float, lat: float, antennas: list[dict[str, Any]], n: int
           ) -> tuple[dict[str, Any], BaselineValue | None]:
        baseline = self.runtime.baseline.at(lon, lat) if self.runtime.baseline is not None else None
        new = [(a, _slant_distance_m(lon, lat, a, self.receptor_h)) for a in antennas]
        new_fields = [free_space_field(a["eirp_w"], d) for a, d in new]
        rng = random.Random(self.seed)
        base = baseline.value_v_per_m if baseline is not None else 0.0
        totals = []
        for _ in range(n):
            b = base * 10.0 ** (rng.gauss(0.0, self.sigma_b) / 20.0) if base > 0.0 else 0.0
            fs = [f * 10.0 ** (rng.gauss(0.0, self.sigma_m) / 20.0) for f in new_fields]
            totals.append(combine_fields([b, *fs]))
        totals.sort()
        out: dict[str, Any] = {
            "lon": round(lon, 6), "lat": round(lat, 6), "unit": "V/m",
            "p5": round(_percentile(totals, 0.05), 3),
            "p50": round(_percentile(totals, 0.50), 3),
            "p95": round(_percentile(totals, 0.95), 3),
            "exceedance": {
                name: {**meta, "probability": round(sum(t > meta["threshold_v_per_m"] for t in totals) / n, 4)}
                for name, meta in self.thresholds.items()
            },
            "baseline": None if baseline is None else {
                "value_v_per_m": round(baseline.value_v_per_m, 3),
                "capped": baseline.value_v_per_m >= self.cap,
                "distance_to_cell_m": round(baseline.distance_m, 1),
                "credit": "Fonte: Cartoradio - MIMIT/FUB",
            },
            "new_sources": [{**a, "distance_m": round(d, 1), "field_p50_v_per_m": round(f, 3)}
                            for (a, d), f in zip(new, new_fields)],
        }
        return out, baseline


def estimate_field(runtime: ToolRuntime, point: Mapping[str, float] | None = None, area: Any = None,
                   variant: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if (point is None) == (area is None):
        raise ToolError("give exactly one of 'point' or 'area'")
    model = _Model(runtime)
    antennas = _normalise_antennas(runtime, variant)
    inputs: dict[str, Any] = {"point": dict(point) if point else None, "area": area, "variant": variant}
    kinds: dict[str, str] = {"emf_field": "estimated"}
    sources: list[Source] = []
    warnings: list[str] = []
    if antennas:
        kinds["proposed_antennas"] = "estimated"
    if runtime.baseline is None:
        kinds["emf_baseline"] = "not_available"
        warnings.append("EMF baseline (Cartoradio) not available: the field covers only the proposed antennas "
                        "and underestimates the total.")
        if not antennas:
            kinds["emf_baseline"] = "not_available"
            return runtime.envelope(TOOL, inputs, None, kinds, sources, warnings, status="not_available",
                                    reason="No baseline and no proposed antenna: nothing to estimate.")
    else:
        kinds["emf_baseline"] = "estimated"

    common = {
        "model": str(runtime.settings.tool("estimate_field", "model")),
        "calibration": "uncalibrated",
        "error_sigma_db": {"baseline": model.sigma_b, "model": model.sigma_m},
        "averaging_note": "Instantaneous worst-case estimate; the attention value is a 24-hour average.",
    }
    if point is not None:
        estimate, baseline = model.at(float(point["lon"]), float(point["lat"]), antennas, model.samples)
        if baseline is not None:
            sources.append(baseline.source)
            if estimate["baseline"]["capped"]:
                warnings.append("Cartoradio value sits at its cap: read it as '15 V/m or more'.")
        elif runtime.baseline is not None:
            warnings.append("No Cartoradio cell near this point.")
        estimate["nearest_measurement"] = None
        if runtime.measurements is not None:
            found = runtime.measurements.at(float(point["lon"]), float(point["lat"]))
            if found is not None:
                kinds["emf_measurements"] = "real"
                sources.append(found.source)
                estimate["nearest_measurement"] = {"value_v_per_m": round(found.value_v_per_m, 3),
                                                   "distance_m": round(found.distance_m, 1),
                                                   "source": found.source.id}
        return runtime.envelope(TOOL, inputs, {"mode": "point", **common, **estimate}, kinds, sources, warnings)

    resolved = resolve_area(area, runtime.store, runtime.settings)
    if resolved.source is not None:
        sources.append(resolved.source)
    max_points = int(runtime.settings.tool("estimate_field", "area_max_points"))
    points = _grid_points(resolved, max_points)
    if not points:
        raise ToolError("area too small to sample")
    per_point = []
    for lon, lat in points:
        estimate, baseline = model.at(lon, lat, antennas, model.area_samples)
        if baseline is not None:
            sources.append(baseline.source)
        per_point.append(estimate)
    p50s = sorted(e["p50"] for e in per_point)
    hottest = max(per_point, key=lambda e: e["p95"])
    result = {
        "mode": "area", **common, "area": resolved.describe(), "sample_points": len(per_point), "unit": "V/m",
        "p50_of_points": {"median": round(_percentile(p50s, 0.5), 3), "max": round(p50s[-1], 3)},
        "max_p95": hottest["p95"],
        "hottest_point": {k: hottest[k] for k in ("lon", "lat", "p5", "p50", "p95")},
        "share_of_points_with_exceedance_over_5pct": {
            name: round(sum(e["exceedance"][name]["probability"] > 0.05 for e in per_point) / len(per_point), 4)
            for name in model.thresholds
        },
        "thresholds": model.thresholds,
    }
    return runtime.envelope(TOOL, inputs, result, kinds, sources, warnings)


def _grid_points(area: Area, max_points: int) -> list[tuple[float, float]]:
    min_lon, min_lat, max_lon, max_lat = area.bbox
    width_m = (max_lon - min_lon) * 111_195.0 * math.cos(math.radians((min_lat + max_lat) / 2))
    height_m = (max_lat - min_lat) * 111_195.0
    step_m = max(math.sqrt(max(width_m * height_m, 1.0) / max_points), 50.0)
    nx, ny = max(1, int(width_m // step_m)), max(1, int(height_m // step_m))
    points = []
    for i in range(nx):
        for j in range(ny):
            lon = min_lon + (i + 0.5) * (max_lon - min_lon) / nx
            lat = min_lat + (j + 0.5) * (max_lat - min_lat) / ny
            if area.contains(lon, lat):
                points.append((lon, lat))
    return points[:max_points]
