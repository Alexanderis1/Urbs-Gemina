"""Land-use covariates for the belief layers (land-use regression, LUR).

NO2 in a city comes mostly from traffic, so a place's long-run NO2 level follows how much road
traffic is near it. The regional model (CAMS, 10 km) cannot see that; stations can. A land-use
regression learns from the stations how much NO2 rises with road length nearby, and the map then
uses that slope in every cell (ESCAPE project method: Beelen et al. 2013, Atmos. Environ. 72:10).

Covariates here: the night-time heat island of each cell (sealed ground and trees, for the street
temperature layer; ``scripts/build_heat_island.py`` -> ``heat_island_night.csv``) and the length (m) of motor roads (Overture Maps transportation, ODbL) within a radius of a
point. Per-cell values for the whole city are precomputed by ``scripts/fit_air_fusion.py --covariates``
into ``no2_lur_covariates.csv`` (cell, value), looked for in data/model, data/processed (the deployed API) and the shared model folder.
"""
from __future__ import annotations

import csv
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import numpy.typing as npt

#: Overture road classes that carry motor traffic.
MOTOR_CLASSES = ("motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified",
                 "living_street")
#: The deployed API mounts the processed-data volume at data/processed (Modal volume urbs-gemina-processed).
#: Paths are anchored at the repository root: the Modal container does not start in it.
ROOT = Path(__file__).resolve().parents[2]
SEARCH_DIRS = (ROOT / "data/model", ROOT / "data/processed", Path("/mnt/project-files/model"))
LAT0, LON0 = 41.9, 12.5


def _to_m(lon: npt.ArrayLike, lat: npt.ArrayLike) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    kx = 111_320.0 * math.cos(math.radians(LAT0))
    return (np.asarray(lon, dtype=np.float64) - LON0) * kx, (np.asarray(lat, dtype=np.float64) - LAT0) * 110_574.0


def project_lines(wkb: Sequence[bytes]) -> Any:
    """WKB lines in lon/lat -> shapely lines in local metres."""
    import shapely  # type: ignore[import-untyped]

    def to_m(c: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        x, y = _to_m(c[:, 0], c[:, 1])
        return np.column_stack([x, y])

    return shapely.transform(shapely.from_wkb(list(wkb)), to_m)


def road_length_within(lines: Any, lons: Sequence[float], lats: Sequence[float], radius_m: float) -> npt.NDArray[np.float64]:
    """Metres of road inside a circle of ``radius_m`` around each point."""
    import shapely

    tree = shapely.STRtree(lines)
    x, y = _to_m(lons, lats)
    out = np.zeros(len(x))
    for i, (px, py) in enumerate(zip(x, y)):
        circle = shapely.buffer(shapely.Point(px, py), radius_m, quad_segs=16)
        idx = tree.query(circle)
        if len(idx):
            out[i] = float(shapely.length(shapely.intersection(lines[idx], circle)).sum())
    return out


def night_heat_island(imp: npt.ArrayLike, imp_nb: npt.ArrayLike, trees: npt.ArrayLike, trees_nb: npt.ArrayLike,
                      city: float, local: float, tree: float) -> npt.NDArray[np.float64]:
    """Night-time urban heat island (degC) above a forecast that carries none.

    Same form and coefficients as the heatwave scenario (config/scenarios.yaml heatwave.coefficients.night):
    ``city`` x sealed share of the 2.2 km district + ``local`` x (cell - district sealing)
    - ``tree`` x (cell - district tree cover). Shares are 0-1."""
    i, inb = np.asarray(imp, dtype=np.float64), np.asarray(imp_nb, dtype=np.float64)
    t, tnb = np.asarray(trees, dtype=np.float64), np.asarray(trees_nb, dtype=np.float64)
    out: npt.NDArray[np.float64] = city * inb + local * (i - inb) - tree * (t - tnb)
    return out


def free_flow_speed(length_by_class: dict[str, float], speed_by_class: dict[str, float]) -> float | None:
    """Length-weighted free-flow speed (km/h) of the roads near a point; None when there are none."""
    pairs = [(m, speed_by_class[c]) for c, m in length_by_class.items() if c in speed_by_class and m > 0.0]
    total = sum(m for m, _ in pairs)
    return None if total <= 0.0 else sum(m * v for m, v in pairs) / total


def covariate_path(name: str) -> Path | None:
    for d in SEARCH_DIRS:
        p = d / name
        if p.exists():
            return p
    return None


@lru_cache(maxsize=4)
def load_cell_covariate(name: str) -> dict[str, float] | None:
    """cell id -> covariate value, or None when the precomputed file is not available."""
    path = covariate_path(name)
    if path is None:
        return None
    with path.open(encoding="utf-8") as f:
        return {row["cell"]: float(row["value"]) for row in csv.DictReader(f)}


__all__ = ["MOTOR_CLASSES", "covariate_path", "free_flow_speed", "load_cell_covariate", "night_heat_island", "project_lines",
           "road_length_within"]
