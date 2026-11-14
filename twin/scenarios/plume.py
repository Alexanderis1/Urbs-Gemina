"""Chemical release at a high-risk (Seveso) plant: Gaussian plume over the city, with ranges.

Steady ground-level release, Briggs urban dispersion coefficients, flat ground.
An ensemble over wind direction, wind speed, atmospheric stability and release
rate gives the probability that each place exceeds each health threshold
(config/thresholds.yaml toxic_gas). Results are compared with the plant's
official damage zones when they exist.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np

from twin.scenarios import config, impacts, layers
from twin.scenarios.area import Area
from twin.scenarios.data import ScenarioData
from twin.scenarios.terrain import FloatArray, Grid, mask_to_geojson, rasterize_mask, to_utm

# Briggs (1973) urban sigma_y, sigma_z as (a, b, c, d, e): sy = a x (1 + b x)^-0.5 ; sz = c x (1 + d x)^e
BRIGGS_URBAN: dict[str, tuple[float, float, float, float, float]] = {
    "A": (0.32, 0.0004, 0.24, 0.001, 0.5), "B": (0.32, 0.0004, 0.24, 0.001, 0.5),
    "C": (0.22, 0.0004, 0.20, 0.0, 0.0),
    "D": (0.16, 0.0004, 0.14, 0.0003, -0.5),
    "E": (0.11, 0.0004, 0.08, 0.0015, -0.5), "F": (0.11, 0.0004, 0.08, 0.0015, -0.5),
}


def _cfg() -> dict[str, Any]:
    raw: dict[str, Any] = config.load("scenarios.yaml")["chemical_plume"]
    return {k: config.value(raw, k) for k in raw}


def concentration(q_g_s: float, u: float, stability: str, downwind: FloatArray, crosswind: FloatArray,
                  release_h: float) -> FloatArray:
    """Ground-level concentration (g/m3) of a continuous point release, with ground reflection."""
    a, b, c, d, e = BRIGGS_URBAN[stability]
    x = np.where(downwind > 1.0, downwind, np.nan)
    sy = a * x * (1 + b * x) ** -0.5
    sz = c * x * (1 + d * x) ** e
    out = q_g_s / (math.pi * u * sy * sz) * np.exp(-crosswind ** 2 / (2 * sy ** 2)) * \
        np.exp(-release_h ** 2 / (2 * sz ** 2))
    result: FloatArray = np.nan_to_num(out, nan=0.0)
    return result


def find_site(change: Mapping[str, Any]) -> tuple[float, float, str]:
    if "lon" in change and "lat" in change:
        return float(change["lon"]), float(change["lat"]), str(change.get("site", "release point"))
    name = str(change.get("site", "")).casefold()
    if not name:
        raise ValueError("chemical_plume change needs 'site' (plant name) or 'lon' and 'lat'")
    for file_name in _cfg()["sites_files"]:
        path = layers.find(str(file_name))
        if path is None:
            continue
        for f in layers.read(path).get("features", []):
            props = f.get("properties") or {}
            label = str(props.get("nome") or props.get("denominaz") or "")
            if name in label.casefold() and f.get("geometry"):
                g = f["geometry"]
                if g["type"] == "Point":
                    return float(g["coordinates"][0]), float(g["coordinates"][1]), label
                ring = g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0]
                return (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring), label)
    raise ValueError(f"No hazardous site matching {change.get('site')!r}")


def _wind(change: Mapping[str, Any], data: ScenarioData) -> tuple[float, float, str]:
    """(speed m/s, direction the wind blows FROM in degrees, kind)."""
    wind = change.get("wind")
    if isinstance(wind, Mapping) and "speed_ms" in wind and "from_deg" in wind:
        return float(wind["speed_ms"]), float(wind["from_deg"]), "hypothetical"
    if wind == "forecast":
        if data.wind is None:
            raise LookupError("No wind forecast available")
        return float(data.wind[0]), float(data.wind[1]), "estimated"
    raise ValueError("chemical_plume change needs 'wind': {'speed_ms', 'from_deg'} or 'wind': 'forecast'")


def _thresholds(substance: str) -> dict[str, float]:
    table = config.load("thresholds.yaml")["toxic_gas"]["substances"]
    if substance not in table:
        raise ValueError(f"Unknown substance {substance!r}; known: {', '.join(sorted(table))}")
    return {k.removesuffix("_mg_m3"): float(v) for k, v in table[substance].items() if k.endswith("_mg_m3")}


def run_chemical_plume(area: Area, change: Mapping[str, Any], data: ScenarioData) -> dict[str, Any]:
    cfg = _cfg()
    warnings: list[str] = []
    lon, lat, site_name = find_site(change)
    substance = str(change.get("substance", "ammonia"))
    limits = _thresholds(substance)
    try:
        u0, from_deg, wind_kind = _wind(change, data)
    except LookupError as exc:
        return {"result": {"status": "not_available", "reason": str(exc)}, "data_kinds": {"wind": "not_available"},
                "sources": [], "synthetic": False, "warnings": [str(exc)]}
    density = float(cfg["relative_density"].get(substance, 1.0))
    if density > 1.1:
        warnings.append(f"{substance.replace('_', ' ').capitalize()} is heavier than air ({density:.2f} x air): it "
                        "slumps and runs along low ground, which this passive-gas model does not show. Near the "
                        "plant the real cloud is wider and lower; check with a heavy-gas model (ALOHA).")
    warnings.append(f"Expected accuracy of this model: {cfg['expected_accuracy']}.")
    release = float(change.get("release_kg_s", cfg["default_release_kg_s"]))
    if "release_kg_s" not in change:
        warnings.append(f"Release rate {release} kg/s is the default assumption; enter the plant's safety-report scenario.")
    if release <= 0:
        raise ValueError("release_kg_s must be positive")
    if u0 < float(cfg["min_wind_ms"]):
        warnings.append(f"Wind {u0} m/s is near calm: raised to {cfg['min_wind_ms']} m/s; a calm-air release pools "
                        "around the plant and this model does not show it.")

    # grid centred on the source
    cell, reach = float(cfg["cell_m"]), float(cfg["max_distance_m"])
    (sx,), (sy_,) = to_utm([lon], [lat])
    n = int(2 * reach / cell)
    x0, y0 = sx - reach, sy_ + reach
    grid = Grid(np.zeros((n, n)), x0, y0, cell, {"id": "plume_grid", "kind": "estimated"})
    cols = x0 + (np.arange(n) + 0.5) * cell - sx
    rows = y0 - (np.arange(n) + 0.5) * cell - sy_
    dx, dy = np.meshgrid(cols, rows)

    rng = np.random.default_rng(int(cfg["seed"]))
    members = int(cfg["members"])
    stab = list(cfg["stability_weights"].items())
    classes, weights = [k for k, _ in stab], np.asarray([float(v) for _, v in stab])
    exceed = {k: np.zeros((n, n)) for k in limits}
    max_dist = {k: [] for k in limits}  # type: dict[str, list[float]]
    release_h = float(cfg["release_height_m"])
    for _ in range(members):
        u = max(float(cfg["min_wind_ms"]), u0 * math.exp(rng.normal(0.0, float(cfg["wind_speed_sigma_ln"]))))
        to_deg = (from_deg + 180.0 + rng.normal(0.0, float(cfg["wind_direction_sigma_deg"]))) % 360.0
        theta = math.radians(to_deg)  # compass bearing the plume travels to
        ux, uy = math.sin(theta), math.cos(theta)
        downwind = dx * ux + dy * uy
        crosswind = -dx * uy + dy * ux
        q = release * 1000.0 * math.exp(rng.normal(-float(cfg["release_sigma_ln"]) ** 2 / 2,
                                                   float(cfg["release_sigma_ln"])))
        conc_mg = concentration(q, u, str(rng.choice(classes, p=weights / weights.sum())), downwind, crosswind,
                                release_h) * 1000.0
        dist = np.hypot(dx, dy)
        for key, limit in limits.items():
            hit = conc_mg >= limit
            exceed[key] += hit
            max_dist[key].append(float(dist[hit].max()) if hit.any() else 0.0)

    in_area = rasterize_mask(grid, [area.geometry], all_touched=False) if area.kind != "city" else np.ones((n, n), bool)
    zones: dict[str, Any] = {}
    for key, count in exceed.items():
        prob = count / members * in_area
        likely, possible = prob >= 0.5, prob >= 0.05
        zones[key] = {
            "threshold_mg_m3": limits[key],
            "meaning": config.load("thresholds.yaml")["toxic_gas"]["meaning"].get(key, ""),
            "area_km2": {"likely": round(float(likely.sum()) * cell * cell / 1e6, 3),
                         "possible": round(float(possible.sum()) * cell * cell / 1e6, 3)},
            "max_distance_m": impacts.quantiles(max_dist[key]),
            "residents": impacts.residents(grid, data, {"likely": likely, "possible": possible}),
            "sensitive_sites": impacts.sensitive_sites(grid, prob, 0.05, limit=50),
            "footprint_possible": mask_to_geojson(grid, possible),
        }
    official = _official_zones(site_name)
    result = {
        "model": "gaussian_plume_briggs_urban", "calibration": "uncalibrated",
        "site": {"name": site_name, "lon": round(lon, 6), "lat": round(lat, 6)},
        "substance": substance, "release_kg_s": release, "wind": {"speed_ms": u0, "from_deg": from_deg},
        "members": members, "zones": zones, "official_damage_zones": official,
    }
    warnings += [
        "Gaussian plume on flat ground: buildings, hills and street canyons are ignored; use it to see who may be "
        "exposed and where to warn first, not as a measured concentration.",
        "'likely' = at least a 50% chance of exceeding the threshold; 'possible' = at least 5%.",
    ]
    kinds = {"site": "real", "wind": wind_kind, "release": "hypothetical", "dispersion": "estimated",
             "census": "real" if zones[next(iter(zones))]["residents"] is not None else "not_available",
             "official_damage_zones": "real" if official else "not_available"}
    return {"result": result, "data_kinds": kinds, "sources": [], "synthetic": False, "warnings": warnings}


def _official_zones(site_name: str) -> list[dict[str, Any]] | None:
    path = layers.find(str(_cfg()["damage_zones_file"]))
    if path is None:
        return None
    key = site_name.split()[0].casefold() if site_name else ""
    out: list[dict[str, Any]] = []
    for f in layers.read(path).get("features", []):
        props = f.get("properties") or {}
        origin = str(props.get("origine", ""))
        if key and key in origin.casefold() or (key == "eni" and "raffineria" in origin.casefold()):
            out.append({"zone": props.get("zona"), "origin": origin, "area_m2": props.get("area_mq")})
    return out
