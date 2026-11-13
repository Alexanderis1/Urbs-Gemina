"""Public entry points of the building-aware field model (used by twin/scenarios and the tools).

A *site* is a mapping with ``lon``, ``lat``, ``height_m`` (antenna centre above
ground) and either ``eirp_w`` (per sector) or ``band`` (typical EIRP from
config/emf_params.yaml). Optional: ``band`` (sets the frequency),
``frequency_mhz``, ``sectors`` (list of ``{azimuth_deg, tilt_deg, eirp_w}``;
missing values are unknown and sampled), ``eirp_sigma_db``.

Buildings are read from the city model around the site (cached). Pass
``buildings=None`` for open ground (no buildings), or leave the default
``"auto"`` to load them; if the city model file is missing the result is the
open-ground value and :func:`buildings_status` says so.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Any, Literal, Mapping, Sequence, Union

import numpy as np

from twin.physics import config
from twin.physics.buildings import Buildings, buildings_path, load_window, to_local
from twin.physics.field import FieldEngine, FieldResult, Receptor, Sector, Transmitter
from twin.scenarios import config as scen_config
from twin.tools.emf import Z95

Auto = Literal["auto"]
Model = Literal["auto", "raytrace", "building_aware"]
BuildingsArg = Union[Buildings, None, Auto]
#: Buildings are loaded this far around a site (beyond it the receptor grid is not evaluated).
WINDOW_M = 600.0


def _eirp(site: Mapping[str, Any]) -> float:
    if site.get("eirp_w") is not None:
        eirp = float(site["eirp_w"])
    else:
        band = site.get("band")
        table = scen_config.load("emf_params.yaml")["typical_eirp_w"]
        if band is None or str(band) not in table:
            raise ValueError(f"A site needs eirp_w or a band in config/emf_params.yaml (got band={band!r})")
        eirp = float(table[str(band)]["value"])
    if eirp < 0:
        raise ValueError("EIRP cannot be negative")
    return eirp


def transmitter(site: Mapping[str, Any], lon0: float, lat0: float) -> Transmitter:
    try:
        lon, lat, height = float(site["lon"]), float(site["lat"]), float(site["height_m"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("A site needs numeric lon, lat and height_m") from exc
    band = site.get("band")
    table = config.load()["frequency_mhz_by_band"]["value"]
    if band is not None and str(band) not in table:
        raise ValueError(f"Unknown band {band!r}; known: {', '.join(sorted(table))}")
    eirp = _eirp(site)
    freq = float(site.get("frequency_mhz") or config.frequency_mhz(None if band is None else str(band)))
    x, y = to_local(np.array([lon]), np.array([lat]), lon0, lat0)
    sectors = None
    if site.get("sectors"):
        sectors = tuple(Sector(eirp_w=float(s.get("eirp_w", eirp)),
                               azimuth_deg=None if s.get("azimuth_deg") is None else float(s["azimuth_deg"]),
                               tilt_deg=None if s.get("tilt_deg") is None else float(s["tilt_deg"]))
                        for s in site["sectors"])
    sigma = site.get("eirp_sigma_db")
    return Transmitter(x=float(x[0]), y=float(y[0]), height_m=height, frequency_mhz=freq, sectors=sectors,
                       unknown_sector_eirp_w=eirp,
                       eirp_sigma_db=float(sigma if sigma is not None
                                           else config.value("monte_carlo", "eirp_sigma_db_new_site")))


@lru_cache(maxsize=8)
def _window(lon: float, lat: float) -> Buildings | None:
    return load_window(lon, lat, WINDOW_M)


def buildings_for(lon: float, lat: float) -> Buildings | None:
    """City-model buildings around a point (rounded to ~10 m so nearby calls share the cache)."""
    return _window(round(lon, 4), round(lat, 4))


def buildings_status() -> dict[str, Any]:
    path = buildings_path()
    return {"available": path is not None, "file": None if path is None else path.name,
            "data_kind": "estimated", "licence": "ODbL footprints; heights CC BY-NC 4.0 / CC BY 4.0 (LiDAR)"}


def field_samples(sites: Mapping[str, Any] | Sequence[Mapping[str, Any]], points: Sequence[tuple[float, float]],
                  receptor_h: float | Sequence[float] = 1.5, indoor: bool | Sequence[bool] | Auto = "auto",
                  buildings: BuildingsArg = "auto", samples: int | None = None,
                  model: Model = "auto") -> FieldResult:
    """Monte Carlo field (V/m) at (lon, lat) points from one or more sites, powers summed.

    ``indoor="auto"``: a point inside a building footprint is indoors (entry loss applies,
    its own walls do not diffract); any other point is outdoors.

    ``model="auto"`` uses Sionna ray-traced maps when every site has been traced
    (scripts/raytrace_site.py) and every point lies on the maps; otherwise the CPU
    building-aware engine. ``"raytrace"`` refuses to fall back.
    """
    site_list = [sites] if isinstance(sites, Mapping) else list(sites)
    if not site_list:
        raise ValueError("at least one site is needed")
    lon0, lat0 = float(site_list[0]["lon"]), float(site_list[0]["lat"])
    city: Buildings | None
    if isinstance(buildings, str):
        city = buildings_for(lon0, lat0)
    else:
        city = buildings
    if city is not None:
        lon0, lat0 = city.lon0, city.lat0
    txs = [transmitter(s, lon0, lat0) for s in site_list]
    lons = np.array([p[0] for p in points], dtype=np.float64)
    lats = np.array([p[1] for p in points], dtype=np.float64)
    xs, ys = to_local(lons, lats, lon0, lat0)
    heights = [float(receptor_h)] * len(points) if isinstance(receptor_h, (int, float)) else list(receptor_h)
    if isinstance(indoor, str):
        flags = ([bool(b >= 0) for b in city.building_at(np.stack([xs, ys], axis=1))] if city is not None
                 else [False] * len(points))
    elif isinstance(indoor, bool):
        flags = [indoor] * len(points)
    else:
        flags = list(indoor)
    receptors = [Receptor(x=float(xs[k]), y=float(ys[k]), height_m=heights[k], indoor=flags[k])
                 for k in range(len(points))]
    n_draws = int(config.value("monte_carlo", "samples")) if samples is None else samples
    if model != "building_aware" and city is not None:
        traced = _raytraced(site_list, txs, xs, ys, heights, flags, city, n_draws)
        if traced is not None:
            return traced
        if model == "raytrace":
            raise ValueError("no ray-traced maps cover these sites and points; run scripts/raytrace_site.py")
    engine = FieldEngine(buildings=city, samples=n_draws)
    result = engine.evaluate(txs, receptors)
    result.model = "building_aware" if city is not None else "open_ground"
    return result


def _raytraced(sites: list[Mapping[str, Any]], txs: list[Transmitter], xs: np.ndarray[Any, Any],
               ys: np.ndarray[Any, Any], heights: list[float], flags: list[bool], city: Buildings,
               n_draws: int) -> FieldResult | None:
    from twin.physics import raytrace

    total = np.zeros((len(xs), n_draws))
    facade = np.zeros(len(xs))
    seed = int(config.value("monte_carlo", "seed"))
    for k, (site, tx) in enumerate(zip(sites, txs)):
        maps = raytrace.load_cached(site, WINDOW_M / 2.0)
        if maps is None:
            return None
        # points in this site's own frame (site at the origin)
        px = xs - tx.x
        py = ys - tx.y
        half = float(maps.meta.get("radius_m", WINDOW_M / 2.0))
        if np.any(np.abs(px) > half) or np.any(np.abs(py) > half):
            return None
        eirps = ([tx.unknown_sector_eirp_w] if tx.sectors is None else [sec.eirp_w for sec in tx.sectors])
        draws, fac = raytrace.sample_field(maps, eirps, tx.frequency_mhz, np.stack([px, py], axis=1),
                                           np.asarray(heights), np.asarray(flags), n_draws, seed + k,
                                           tx.eirp_sigma_db, tx.sectors is None)
        total += draws ** 2
        facade = np.maximum(facade, fac)
    _ = city
    return FieldResult(np.sqrt(total), facade, model="raytrace")


def lognormal_summary(samples: np.ndarray[Any, Any]) -> tuple[float, float]:
    """(median V/m, sigma dB) of Monte Carlo draws, sigma read from the P5-P95 spread."""
    p5, p50, p95 = (float(v) for v in np.percentile(samples, [5, 50, 95]))
    if p50 <= 0.0 or p5 <= 0.0:
        return p50, 0.0
    return p50, 20.0 * math.log10(p95 / p5) / (2.0 * Z95)


def field_at(site: Mapping[str, Any], lon: float, lat: float, receptor_h: float = 1.5,
             indoor: bool | Auto = "auto",
             buildings: BuildingsArg = "auto") -> tuple[float, float]:
    """(median V/m, sigma dB) at one point. For grids prefer :func:`field_samples` (one call, shared draws)."""
    result = field_samples(site, [(lon, lat)], receptor_h, indoor, buildings)
    return lognormal_summary(result.samples[0])
