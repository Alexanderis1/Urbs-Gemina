"""Antenna what-if: add or move a site and compare the field with the baseline.

Model: free-space, isotropic worst case (main beam assumed towards every point).
Baseline: the Cartoradio grid (official estimate) read at runtime.
Totals combine as power sums of log-normal sources (Fenton-Wilkinson).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from twin.scenarios import config
from twin.scenarios.area import Area
from twin.scenarios.data import FieldSample, ScenarioData
from twin.scenarios.geometry import from_xy, to_xy
from twin.tools.emf import exceedance_probability, field_range, free_space_field

DB_TO_LN = math.log(10.0) / 10.0  # sigma of a power (or field) in dB -> sigma of ln(power)


@dataclass(frozen=True)
class Site:
    lon: float
    lat: float
    height_m: float
    eirp_w: float


def combine_lognormal(sources: Sequence[tuple[float, float]]) -> tuple[float, float]:
    """Total field of independent log-normal sources given as (median V/m, sigma dB).

    Powers (E^2) add. The sum is approximated by one log-normal with the same
    mean and variance (Fenton-Wilkinson). Returns (median V/m, sigma dB).
    """
    mean = var = 0.0
    for median, sigma_db in sources:
        if median <= 0.0:
            continue
        mu, s = math.log(median * median), sigma_db * DB_TO_LN
        mean += math.exp(mu + s * s / 2.0)
        var += (math.exp(s * s) - 1.0) * math.exp(2.0 * mu + s * s)
    if mean <= 0.0:
        return 0.0, 0.0
    s2 = math.log(1.0 + var / (mean * mean))
    mu_total = math.log(mean) - s2 / 2.0
    return math.sqrt(math.exp(mu_total)), math.sqrt(s2) / DB_TO_LN


def _parse_site(raw: Mapping[str, Any], fallback: Mapping[str, Any], warnings: list[str]) -> Site:
    try:
        lon, lat, height = float(raw["lon"]), float(raw["lat"]), float(raw["height_m"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("A site needs numeric lon, lat and height_m") from exc
    eirp = raw.get("eirp_w", fallback.get("eirp_w"))
    band = raw.get("band", fallback.get("band"))
    if eirp is None and band is not None:
        table = config.load("emf_params.yaml")["typical_eirp_w"]
        if str(band) not in table:
            raise ValueError(f"Unknown band {band!r}; known: {', '.join(sorted(table))}")
        entry = table[str(band)]
        eirp = entry["value"]
        warnings.append(f"EIRP for band {band} MHz taken from config/emf_params.yaml ({entry['basis']}).")
    if eirp is None:
        raise ValueError("A site needs eirp_w (watts) or a band listed in config/emf_params.yaml")
    if float(eirp) < 0:
        raise ValueError("EIRP cannot be negative")
    return Site(lon, lat, height, float(eirp))


def _grid(centres: Sequence[Site], radius_m: float, step_m: float) -> list[tuple[float, float]]:
    seen: set[tuple[float, float]] = set()
    points: list[tuple[float, float]] = []
    n = int(radius_m // step_m)
    lon0, lat0 = centres[0].lon, centres[0].lat
    for c in centres:
        cx, cy = to_xy(c.lon, c.lat, lon0, lat0)
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                if math.hypot(i * step_m, j * step_m) > radius_m:
                    continue
                key = (round((cx + i * step_m) / step_m * 2) / 2, round((cy + j * step_m) / step_m * 2) / 2)
                if key in seen:
                    continue
                seen.add(key)
                points.append(from_xy(cx + i * step_m, cy + j * step_m, lon0, lat0))
    return points


def _distance_3d(site: Site, lon: float, lat: float, receptor_m: float) -> tuple[float, float]:
    x, y = to_xy(lon, lat, site.lon, site.lat)
    horizontal = math.hypot(x, y)
    return horizontal, math.hypot(horizontal, site.height_m - receptor_m)


def thresholds() -> dict[str, dict[str, Any]]:
    emf = config.load("thresholds.yaml")["emf"]
    return {
        "attention_value_v_per_m": {"value": float(emf["attention_value_v_per_m"]["value"]),
                                    "source": str(emf["attention_value_v_per_m"]["source"])},
        "exposure_limit_v_per_m": {"value": float(emf["exposure_limit_v_per_m"]["value"]),
                                   "source": str(emf["exposure_limit_v_per_m"]["source"])},
    }


def _side(median: float, sigma_db: float, limits: Mapping[str, Mapping[str, Any]]) -> dict[str, float]:
    if median <= 0.0:
        return {"p5": 0.0, "p50": 0.0, "p95": 0.0, "sigma_db": 0.0, "p_exceed_attention": 0.0,
                "p_exceed_limit": 0.0}
    p5, p50, p95 = field_range(median, sigma_db)
    return {
        "p5": round(p5, 4), "p50": round(p50, 4), "p95": round(p95, 4), "sigma_db": round(sigma_db, 3),
        "p_exceed_attention": round(exceedance_probability(
            median, sigma_db, float(limits["attention_value_v_per_m"]["value"])), 4),
        "p_exceed_limit": round(exceedance_probability(
            median, sigma_db, float(limits["exposure_limit_v_per_m"]["value"])), 4),
    }


@dataclass(frozen=True)
class FieldModel:
    """Baseline and variant field at any point, for a parsed change."""

    new: Site
    old: Site | None
    data: ScenarioData
    model_sigma_db: float
    default_baseline_sigma_db: float
    receptor_m: float

    def baseline(self, lon: float, lat: float) -> FieldSample:
        if self.data.baseline_field is None:
            return FieldSample(0.0, 0.0)
        sample = self.data.baseline_field(lon, lat)
        return sample if sample is not None else FieldSample(0.0, 0.0)

    def at(self, lon: float, lat: float) -> tuple[FieldSample, FieldSample]:
        base = self.baseline(lon, lat)
        residual = base
        if self.old is not None:
            _, d_old = _distance_3d(self.old, lon, lat, self.receptor_m)
            old_field = free_space_field(self.old.eirp_w, d_old)
            residual = FieldSample(math.sqrt(max(base.median_v_per_m ** 2 - old_field ** 2, 0.0)), base.sigma_db)
        _, d_new = _distance_3d(self.new, lon, lat, self.receptor_m)
        new_field = free_space_field(self.new.eirp_w, d_new)
        median, sigma = combine_lognormal([(residual.median_v_per_m, residual.sigma_db),
                                           (new_field, self.model_sigma_db)])
        return base, FieldSample(median, sigma)


def build_model(change: Mapping[str, Any], data: ScenarioData, warnings: list[str]) -> FieldModel:
    action = change.get("action", "add")
    if action not in ("add", "move"):
        raise ValueError("antenna change 'action' must be 'add' or 'move'")
    if "site" not in change:
        raise ValueError("antenna change needs a 'site' with lon, lat, height_m")
    new = _parse_site(change["site"], change, warnings)
    old = None
    if action == "move":
        if "from" not in change:
            raise ValueError("a 'move' needs 'from': the current site with lon, lat, height_m and eirp_w or band")
        old = _parse_site(change["from"], {}, warnings)
    scen = config.load("scenarios.yaml")["antenna"]
    return FieldModel(
        new=new, old=old, data=data,
        model_sigma_db=float(config.value(config.load("emf_params.yaml"), "model_error_sigma_db")),
        default_baseline_sigma_db=float(config.value(scen, "baseline_sigma_db")),
        receptor_m=float(config.value(scen, "receptor_height_m")),
    )


def _summary(rows: list[dict[str, Any]], side: str, flag_p: float) -> dict[str, Any]:
    vals = [r[side] for r in rows]
    if not vals:
        return {"max_p50_v_per_m": None, "max_p95_v_per_m": None, "mean_p50_v_per_m": None,
                "points_flagged_attention": 0, "points_flagged_limit": 0}
    return {
        "max_p50_v_per_m": max(v["p50"] for v in vals),
        "max_p95_v_per_m": max(v["p95"] for v in vals),
        "mean_p50_v_per_m": round(sum(v["p50"] for v in vals) / len(vals), 4),
        "points_flagged_attention": sum(v["p_exceed_attention"] >= flag_p for v in vals),
        "points_flagged_limit": sum(v["p_exceed_limit"] >= flag_p for v in vals),
    }


def run_antenna(area: Area, change: Mapping[str, Any], data: ScenarioData) -> dict[str, Any]:
    warnings: list[str] = []
    model = build_model(change, data, warnings)
    scen = config.load("scenarios.yaml")["antenna"]
    radius, step = float(config.value(scen, "radius_m")), float(config.value(scen, "grid_step_m"))
    flag_p = float(config.value(scen, "exceedance_report_probability"))
    limits = thresholds()

    centres = [model.new] + ([model.old] if model.old else [])
    rows: list[dict[str, Any]] = []
    for lon, lat in _grid(centres, radius, step):
        if not area.contains(lon, lat):
            continue
        base, variant = model.at(lon, lat)
        horizontal, _ = _distance_3d(model.new, lon, lat, model.receptor_m)
        rows.append({
            "lon": round(lon, 6), "lat": round(lat, 6), "distance_m": round(horizontal, 1),
            "baseline": _side(base.median_v_per_m, base.sigma_db, limits),
            "variant": _side(variant.median_v_per_m, variant.sigma_db, limits),
        })
    for r in rows:
        r["delta_p50"] = round(r["variant"]["p50"] - r["baseline"]["p50"], 4)

    warnings.append("Free-space isotropic model: buildings and antenna patterns are ignored, "
                    "so values near the mast are a worst case. Ray tracing (Sionna RT) refines a district.")
    if data.baseline_field is None:
        warnings.append("EMF baseline (Cartoradio) not available: the variant shows the changed antenna alone.")
    if model.old is not None:
        warnings.append("Move: the current site's contribution is modelled from simulated parameters "
                        "and subtracted from the baseline; treat the reduction as indicative.")
    if not rows:
        warnings.append("No grid point of the antenna neighbourhood falls inside the area.")

    kinds = {"emf_baseline": data.baseline_kind if data.baseline_field is not None else "not_available",
             "new_site": "estimated"}
    if model.old is not None:
        kinds["existing_site"] = "simulated"
    return {
        "result": {
            "model": "free_space_isotropic",
            "calibration": "uncalibrated",
            "grid": {"radius_m": radius, "step_m": step, "receptor_height_m": model.receptor_m},
            "thresholds": limits,
            "flag_probability": flag_p,
            "summary": {"baseline": _summary(rows, "baseline", flag_p), "variant": _summary(rows, "variant", flag_p)},
            "points": rows,
        },
        "data_kinds": kinds,
        "sources": [s for s in [data.baseline_source] if s],
        "synthetic": model.old is not None or (data.baseline_field is not None and data.baseline_kind == "simulated"),
        "warnings": warnings,
    }
