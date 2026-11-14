"""Chemical release at a high-risk (Seveso) plant: Gaussian plume over the city, with ranges.

Steady ground-level release, Briggs urban dispersion coefficients, flat ground. Gases heavier than air
also get a Britter-McQuaid dense plume (HSE workbook 1988); the map keeps the larger of the two.
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


G = 9.81
RHO_AIR = 1.2  # kg/m3

# Britter & McQuaid (1988) continuous dense plume: curve fits of the workbook figure, as tabulated by
# CCPS (1996) and Crowl & Louvar. For each Cm/C0, beta = log10(x / D) by alpha band:
# list of (upper alpha bound, slope, intercept); slope 0 = flat part of the curve.
BM_CONTINUOUS: tuple[tuple[float, tuple[tuple[float, float, float], ...]], ...] = (
    (0.1, ((-0.55, 0.0, 1.75), (-0.14, 0.24, 1.88), (1.0, -0.50, 1.78))),
    (0.05, ((-0.68, 0.0, 1.92), (-0.29, 0.36, 2.16), (-0.18, 0.0, 2.06), (1.0, -0.56, 1.96))),
    (0.02, ((-0.69, 0.0, 2.08), (-0.31, 0.45, 2.39), (-0.16, 0.0, 2.25), (1.0, -0.54, 2.16))),
    (0.01, ((-0.70, 0.0, 2.25), (-0.29, 0.49, 2.59), (-0.20, 0.0, 2.45), (1.0, -0.52, 2.35))),
    (0.005, ((-0.67, 0.0, 2.40), (-0.28, 0.59, 2.80), (-0.15, 0.0, 2.63), (1.0, -0.49, 2.56))),
    (0.002, ((-0.69, 0.0, 2.60), (-0.25, 0.39, 2.87), (-0.13, 0.0, 2.77), (1.0, -0.50, 2.71))),
)
NEAR_FIELD_X = 30.0  # x/D up to which Cm/C0 = 306 / (306 + (x/D)^2)


def _bm_scales(q0: float, rho_gas: float, u: float) -> tuple[float, float, float]:
    """(D, g0', alpha) of a continuous release of q0 m3/s of gas of density rho_gas in wind u."""
    g0 = G * (rho_gas - RHO_AIR) / RHO_AIR
    d = math.sqrt(q0 / u)
    alpha = 0.2 * math.log10(max(g0, 1e-9) ** 2 * q0 / u ** 5)
    return d, g0, alpha


def is_dense(q0: float, rho_gas: float, u: float) -> bool:
    """Britter-McQuaid test: density effects matter when (g0' q0 / (u^3 D))^(1/3) >= 0.15."""
    if rho_gas <= RHO_AIR:
        return False
    d, g0, _ = _bm_scales(q0, rho_gas, u)
    return bool((g0 * q0 / (u ** 3 * d)) ** (1 / 3) >= 0.15)


def dense_centreline(q0: float, rho_gas: float, u: float, x: FloatArray) -> FloatArray:
    """Centreline Cm/C0 of a continuous dense plume at downwind distances x (m): near-field formula,
    workbook curve in the middle (linear in log10 x/D), 1/x^2 decay beyond the last curve point."""
    d, _, alpha = _bm_scales(q0, rho_gas, u)
    a = min(alpha, 1.0)  # the workbook stops at alpha = 1
    ratios, betas = [], []
    for ratio, bands in BM_CONTINUOUS:
        slope, icpt = next(((s, c) for top, s, c in bands if a <= top), bands[-1][1:])
        ratios.append(ratio)
        betas.append(slope * a + icpt)
    beta = np.maximum.accumulate(np.asarray(betas))  # keep the curve monotonic
    beta_nf = min(math.log10(NEAR_FIELD_X), float(beta[0]) - 0.05)
    x_nf = 10 ** beta_nf
    nodes_b = np.concatenate([[beta_nf], beta])
    nodes_c = np.concatenate([[306 / (306 + x_nf ** 2)], ratios])
    xd = np.asarray(x, dtype=float) / d
    out = np.ones_like(xd)
    pos = xd > 0
    near = pos & (xd < x_nf)
    out[near] = 306 / (306 + xd[near] ** 2)
    x_ff = 10 ** float(beta[-1])
    mid = pos & (xd >= x_nf) & (xd < x_ff)
    out[mid] = np.interp(np.log10(xd[mid]), nodes_b, nodes_c)
    far = pos & (xd >= x_ff)
    out[far] = ratios[-1] * x_ff ** 2 / xd[far] ** 2
    result: FloatArray = out
    return result


def dense_half_width(q0: float, rho_gas: float, u: float, x: FloatArray) -> FloatArray:
    """Half-width (m) of the dense plume: D + 8 lb + 2.5 (lb x^2)^(1/3), lb = g0' q0 / u^3 (gravity spreading)."""
    d, g0, _ = _bm_scales(q0, rho_gas, u)
    lb = g0 * q0 / u ** 3
    result: FloatArray = d + 8 * lb + 2.5 * np.cbrt(lb * np.maximum(np.asarray(x, dtype=float), 0.0) ** 2)
    return result


def _bm_curve_end(q0: float, rho_gas: float, u: float) -> float:
    """Downwind distance (m) of the workbook's last curve point (Cm/C0 = 0.002)."""
    d, _, alpha = _bm_scales(q0, rho_gas, u)
    a = min(alpha, 1.0)
    betas = [next(((s * a + c) for top, s, c in bands if a <= top), bands[-1][1] * a + bands[-1][2])
             for _, bands in BM_CONTINUOUS]
    return d * 10 ** max(betas)


def dense_concentration(q_kg_s: float, rho_gas: float, u: float, stability: str, downwind: FloatArray,
                        crosswind: FloatArray) -> FloatArray:
    """Ground-level concentration (mg/m3) of a dense plume; 0 everywhere when the release is not dense.

    Up to the workbook's last curve point the cloud is a top-hat slab (Britter-McQuaid). Beyond it the
    diluted cloud spreads as a passive plume with the urban curves, starting from the slab's width
    (sigma_y0 = half-width / sqrt(3)) and a depth chosen so the centreline matches (sigma_z0)."""
    q0 = q_kg_s / rho_gas
    if not is_dense(q0, rho_gas, u):
        return np.zeros_like(downwind)
    d, g0, _ = _bm_scales(q0, rho_gas, u)
    lb = g0 * q0 / u ** 3
    x_end = _bm_curve_end(q0, rho_gas, u)
    c0 = rho_gas * 1e6  # mg/m3 of pure gas
    ahead = np.clip(downwind, 0.0, x_end)
    slab = (np.abs(crosswind) <= dense_half_width(q0, rho_gas, u, ahead)) & (downwind >= -(d / 2 + 2 * lb)) & \
        (downwind <= x_end)
    out = np.where(slab, dense_centreline(q0, rho_gas, u, ahead) * c0, 0.0)
    # passive far field from the slab at x_end
    c_end = float(dense_centreline(q0, rho_gas, u, np.array([x_end]))[0]) * c0 / 1000.0  # g/m3
    sy0 = float(dense_half_width(q0, rho_gas, u, np.array([x_end]))[0]) / math.sqrt(3.0)
    sz0 = q_kg_s * 1000.0 / (math.pi * u * c_end * sy0)
    a, b, c, dd, e = BRIGGS_URBAN[stability]
    xp = np.where(downwind > x_end, downwind - x_end, np.nan)
    sy = np.sqrt((a * xp * (1 + b * xp) ** -0.5) ** 2 + sy0 ** 2)
    sz = np.sqrt((c * xp * (1 + dd * xp) ** e) ** 2 + sz0 ** 2)
    far = q_kg_s * 1000.0 / (math.pi * u * sy * sz) * np.exp(-crosswind ** 2 / (2 * sy ** 2)) * 1000.0
    result: FloatArray = np.where(downwind > x_end, np.nan_to_num(far, nan=0.0), out)
    return result


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
    heavy = density > 1.1
    use_dense = heavy and bool(change.get("dense_gas", True))
    if heavy:
        what = (f"{substance.replace('_', ' ').capitalize()} is heavier than air ({density:.2f} x air): it slumps, "
                "spreads sideways and runs along low ground. ")
        warnings.append(what + ("The map takes the larger of a passive plume and a Britter-McQuaid heavy-gas plume "
                                f"({cfg['dense_gas']}). It does not follow slopes, underpasses or the river bed; "
                                "check critical cases with ALOHA." if use_dense else
                                "The heavy-gas model is switched off for this run: near the plant the real cloud "
                                "is wider and lower; check with a heavy-gas model (ALOHA)."))
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
        stability = str(rng.choice(classes, p=weights / weights.sum()))
        conc_mg = concentration(q, u, stability, downwind, crosswind, release_h) * 1000.0
        if use_dense:
            conc_mg = np.maximum(conc_mg, dense_concentration(q / 1000.0, density * RHO_AIR, u, stability,
                                                              downwind, crosswind))
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
        "model": "gaussian_plume_briggs_urban" + ("+britter_mcquaid_dense" if use_dense else ""),
        "calibration": str(_cfg()["calibration"]),
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
