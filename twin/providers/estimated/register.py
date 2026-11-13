"""Estimated antenna register (layer ``antenna_register``). Estimated, derived from restricted data.

No official register of installations is open, so this one is built by fusing
three real sources with a physical model. Nothing in it is invented:

1. **Positions.** OpenCelliD cell clusters (committed seed or raw CSV). Where an
   OpenStreetMap mast is close, the site moves to the mast.
2. **Position refinement.** Cartoradio's grid is computed by MIMIT/FUB from the
   operators' real register, so its local maxima sit near real masts. A site
   within ``peak_snap_m`` of a peak moves to the peak. Strong peaks with no
   site nearby become new sites with operator "unknown".
3. **Power.** Each site's *effective* EIRP (the power that reaches ground level)
   comes from a non-negative least-squares fit of the free-space model,
   ``E^2 = background + sum_i P_i * 30 / d_i^2``, to the Cartoradio cells
   around it. Rows are weighted by the Cartoradio relative error. Each site gets
   a one-sigma range from the residuals.

Azimuth, tilt, height, operator band plan and authorisation status are not
observable from these sources, so they are reported as ``None`` ("unknown"),
never guessed.

Because the fit uses Cartoradio values, the result is a derived dataset of a
restricted source: it is computed at runtime, held in memory and marked
``redistribution=False``. Calibration status: ``uncalibrated`` until real
measurements (ARPA) are available to check it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator, Sequence

from twin.providers.base import ROME_BBOX, BBox, Observation, ProviderInfo
from twin.providers.estimated.sites import (
    SeedSite,
    cluster_sites,
    read_opencellid_csv,
    read_osm_masts,
    read_seed_sites,
)
from twin.providers.geo import distance_m, in_bbox
from twin.providers.raster import RasterCell
from twin.providers.restricted.cartoradio import CartoradioGridProvider
from twin.providers.settings import Settings, integer, number

PROVIDER_ID = "est_register"

#: Register record fields, aligned with the installation application form
#: ("Modello A", D.Lgs. 259/2003) so a real register maps one-to-one (C=60).
#: Fields the sources cannot observe are always ``None``.
MODEL_A_FIELDS: tuple[str, ...] = (
    "site_id",
    "operator",
    "technologies",
    "lon",
    "lat",
    "position_source",
    "position_sigma_m",
    "effective_eirp_w",
    "effective_eirp_sigma_w",
    "fit_cells",
    "antenna_height_agl_m",
    "sectors",
    "bands_mhz",
    "authorisation_status",
    "application_date",
    "data_kind",
    "calibration",
)

#: Italian labels of the form fields these map to (to be confirmed with Roma Capitale).
MODEL_A_LABELS_IT: dict[str, str] = {
    "operator": "Gestore",
    "lon": "Coordinate geografiche (longitudine)",
    "lat": "Coordinate geografiche (latitudine)",
    "technologies": "Tecnologia / sistema",
    "bands_mhz": "Frequenze di trasmissione (MHz)",
    "antenna_height_agl_m": "Altezza del centro elettrico dal suolo (m)",
    "sectors": "Antenne: direzione di massimo irraggiamento, tilt, potenza",
    "effective_eirp_w": "Potenza EIRP (stimata, verso il suolo) (W)",
    "authorisation_status": "Stato dell'autorizzazione",
    "application_date": "Data di presentazione dell'istanza",
}


@dataclass(frozen=True)
class EstimatedSite:
    site_id: str
    operator: str
    technologies: tuple[str, ...]
    lon: float
    lat: float
    position_source: str  # opencellid | osm_mast | cartoradio_peak | cartoradio_peak_only
    position_sigma_m: float
    effective_eirp_w: float
    effective_eirp_sigma_w: float
    fit_cells: int

    def to_model_a(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "operator": self.operator,
            "technologies": list(self.technologies),
            "lon": self.lon,
            "lat": self.lat,
            "position_source": self.position_source,
            "position_sigma_m": self.position_sigma_m,
            "effective_eirp_w": self.effective_eirp_w,
            "effective_eirp_sigma_w": self.effective_eirp_sigma_w,
            "fit_cells": self.fit_cells,
            "antenna_height_agl_m": None,
            "sectors": None,
            "bands_mhz": None,
            "authorisation_status": None,
            "application_date": None,
            "data_kind": "estimated",
            "calibration": "uncalibrated",
        }


# --- fusion steps (pure functions) -----------------------------------------------

def find_peaks(cells: Sequence[RasterCell], min_value: float) -> list[RasterCell]:
    """Local maxima: cells at least ``min_value`` and not below any of their 8 neighbours.

    On a plateau of equal values (e.g. cells at the 15 V/m cap) only the
    top-left cell counts, so one mast gives one peak.
    """
    grid = {(c.row, c.col): c.value for c in cells}
    peaks: list[RasterCell] = []
    for cell in cells:
        if cell.value < min_value:
            continue
        here = (cell.row, cell.col)
        higher_or_tied_first = False
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                key = (cell.row + dr, cell.col + dc)
                value = grid.get(key)
                if key == here or value is None:
                    continue
                if value > cell.value or (value == cell.value and key < here):
                    higher_or_tied_first = True
        if not higher_or_tied_first:
            peaks.append(cell)
    return peaks


def snap_to_points(lon: float, lat: float, points: Sequence[tuple[float, float]],
                   max_m: float) -> tuple[float, float] | None:
    best = min(points, key=lambda p: distance_m(lon, lat, p[0], p[1]), default=None)
    if best is not None and distance_m(lon, lat, best[0], best[1]) <= max_m:
        return best
    return None


def fit_effective_eirp(sites: Sequence[tuple[float, float]], cells: Sequence[RasterCell], *,
                       radius_m: float, height_m: float, sigma_db: float, cap: float | None,
                       ) -> tuple[list[float], list[float], list[int], float, float]:
    """Non-negative least squares of ``E^2 = b + sum_i P_i * 30 / d_i^2`` on Cartoradio cells.

    Returns (P per site in W, one-sigma per site in W, cells used per site,
    background b in (V/m)^2, median absolute model-vs-Cartoradio error in dB).
    Capped cells are left out, because their true value is only a lower bound.
    """
    import numpy as np
    from scipy.optimize import lsq_linear  # type: ignore[import-untyped]
    from scipy.sparse import coo_matrix, diags  # type: ignore[import-untyped]

    if not sites:
        return [], [], [], 0.0, 0.0
    usable = [c for c in cells if c.value > 0.0 and (cap is None or c.value < cap)]
    if not usable:
        return [0.0] * len(sites), [0.0] * len(sites), [0] * len(sites), 0.0, 0.0
    lons = np.array([c.lon for c in usable])
    lats = np.array([c.lat for c in usable])
    e2 = np.array([c.value for c in usable]) ** 2
    kx = 111_320.0 * math.cos(math.radians(float(lats.mean())))
    ky = 110_540.0
    rows: list[Any] = []
    cols: list[Any] = []
    vals: list[Any] = []
    counts: list[int] = []
    for index, (slon, slat) in enumerate(sites):
        dx = (lons - slon) * kx
        dy = (lats - slat) * ky
        near = np.nonzero((np.abs(dx) <= radius_m) & (np.abs(dy) <= radius_m))[0]
        d2 = dx[near] ** 2 + dy[near] ** 2
        keep = near[d2 <= radius_m**2]
        d2 = d2[d2 <= radius_m**2] + height_m**2
        rows.append(keep)
        cols.append(np.full(keep.size, index))
        vals.append(30.0 / d2)
        counts.append(int(keep.size))
    used = np.unique(np.concatenate(rows)) if rows else np.array([], dtype=int)
    if used.size == 0:
        return [0.0] * len(sites), [0.0] * len(sites), counts, 0.0, 0.0
    remap = -np.ones(len(usable), dtype=int)
    remap[used] = np.arange(used.size)
    # Relative error of E^2 is about 2 x relative error of E: weight each row by 1 / E^2.
    rel = 2.0 * (10.0 ** (sigma_db / 20.0) - 1.0)
    weights = 1.0 / (rel * e2[used])
    all_rows = remap[np.concatenate(rows)]
    all_cols = np.concatenate(cols)
    all_vals = np.concatenate(vals) * weights[all_rows]
    n_sites = len(sites)
    # Last column = background, the same unknown for every cell.
    background_rows = np.arange(used.size)
    design = coo_matrix(
        (np.concatenate([all_vals, weights]),
         (np.concatenate([all_rows, background_rows]), np.concatenate([all_cols, np.full(used.size, n_sites)]))),
        shape=(used.size, n_sites + 1)).tocsr()
    target = e2[used] * weights
    # Columns differ by orders of magnitude: solve on unit-norm columns, then scale back.
    norms = np.sqrt(np.asarray(design.multiply(design).sum(axis=0)).ravel())
    norms[norms == 0] = 1.0
    scaled = design @ diags(1.0 / norms)
    solution = lsq_linear(scaled, target, bounds=(0.0, np.inf), method="trf", lsmr_tol=1e-10,
                          tol=1e-10, max_iter=2000)
    x = solution.x / norms
    powers = x[:n_sites]
    background = float(x[n_sites])
    residual = design @ x - target
    dof = max(1, used.size - n_sites - 1)
    scale = float(np.sum(residual**2) / dof)
    # Diagonal approximation of the parameter covariance (ignores site-site correlation).
    col_norm2 = np.asarray(design.multiply(design).sum(axis=0)).ravel()[:n_sites]
    sigmas = np.where(col_norm2 > 0, np.sqrt(scale / np.maximum(col_norm2, 1e-30)), np.inf)
    predicted = (design @ x) / weights
    error_db = 10.0 * np.log10(np.maximum(predicted, 1e-12) / e2[used])
    return powers.tolist(), sigmas.tolist(), counts, background, float(np.median(np.abs(error_db)))


# --- provider -------------------------------------------------------------------

#: Fitted registers per (area, settings), kept in memory for the process only.
_REGISTER_CACHE: dict[tuple[object, str, str], tuple[list[EstimatedSite], float, float]] = {}


class EstimatedRegisterProvider:
    def __init__(self, settings: Settings | None = None, cartoradio: CartoradioGridProvider | None = None,
                 area: BBox = ROME_BBOX) -> None:
        self._settings = settings or Settings.load()
        self._config = self._settings.section("estimated", "register")
        self._shared = cartoradio is None  # injected grids (tests) never use the process cache
        self._cartoradio = cartoradio or CartoradioGridProvider(self._settings)
        self._area = area
        self._sites: list[EstimatedSite] | None = None
        self._background = 0.0
        self._fit_error_db = 0.0

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            id=PROVIDER_ID,
            kind="restricted",
            layer="antenna_register",
            licence=("derived at runtime from OpenCelliD (CC BY-SA 4.0), OSM (ODbL) and Cartoradio "
                     "(MIMIT/FUB, reuse needs written consent)"),
            cadence="on demand (Cartoradio snapshot date)",
            synthetic=False,
            redistribution=False,
            notes=("Estimated, uncalibrated. Positions from OpenCelliD clusters refined on Cartoradio peaks; "
                   "effective EIRP fitted to the Cartoradio grid. Azimuth, height, bands and status unknown. "
                   "Fonte: Cartoradio - MIMIT/FUB."),
        )

    def sites(self) -> list[EstimatedSite]:
        """The fused register. The fit takes about 20 s, so it is held in memory for the process
        (never written to disk: Cartoradio-derived data is runtime only)."""
        if self._sites is None:
            key = (self._area, repr(sorted(self._config.items(), key=str)),
                   repr(self._settings.section("restricted", "cartoradio_grid")))
            cached = _REGISTER_CACHE.get(key) if self._shared else None
            if cached is None:
                sites = self._build()
                cached = (sites, self._background, self._fit_error_db)
                if self._shared:
                    _REGISTER_CACHE[key] = cached
            self._sites, self._background, self._fit_error_db = cached
        return self._sites

    @property
    def fit_error_db(self) -> float:
        """Median absolute difference between the fitted model and Cartoradio, in dB (validation metric)."""
        self.sites()
        return self._fit_error_db

    @property
    def background_v_m(self) -> float:
        self.sites()
        return math.sqrt(max(self._background, 0.0))

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        observed = self._cartoradio_date()
        for site in self.sites():
            if not in_bbox(site.lon, site.lat, bbox):
                continue
            yield Observation(
                entity_id=f"urn:ngsi-ld:AntennaSite:{site.site_id}",
                entity_type="AntennaSite",
                lon=site.lon,
                lat=site.lat,
                observed_at=observed,
                values={"effective_eirp_w": site.effective_eirp_w, "position_sigma_m": site.position_sigma_m},
                sigma={"effective_eirp_w": site.effective_eirp_sigma_w, "position_sigma_m": 0.0},
                source_id=f"{PROVIDER_ID}@cartoradio-{observed.date().isoformat()}",
                synthetic=False,
            )

    # -- building --

    def _cartoradio_date(self) -> datetime:
        date_text = str(self._settings.section("restricted", "cartoradio_grid").get("data_date", "2026-09-08"))
        return datetime.fromisoformat(date_text).replace(tzinfo=timezone.utc)

    def _operators(self) -> dict[int, str]:
        node = self._config.get("operators", {}) or {}
        return {int(k): str(v) for k, v in node.items()}

    def _seeds(self) -> list[tuple[SeedSite, str]]:
        cells_path = self._settings.path(str(self._config.get("opencellid_csv", "") or ""))
        known = self._operators()
        if cells_path is not None and cells_path.exists():
            shifts = {str(k): int(v) for k, v in (self._config.get("site_id_shift_bits", {}) or {}).items()
                      if k != "basis"}
            seeds = cluster_sites(read_opencellid_csv(cells_path, mcc=integer(self._config, "mcc", 222)),
                                  shifts, number(self._config, "merge_distance_m", 150.0))
        else:
            sites_path = self._settings.path(str(self._config.get("sites_geojson", "") or ""))
            seeds = read_seed_sites(sites_path) if sites_path is not None and sites_path.exists() else []
        seeds = [s for s in seeds if s.net in known and in_bbox(s.lon, s.lat, self._area)]
        masts_path = self._settings.path(str(self._config.get("osm_masts_json", "") or ""))
        masts = read_osm_masts(masts_path) if masts_path is not None and masts_path.exists() else []
        snap = number(self._config, "osm_snap_distance_m", 200.0)
        out: list[tuple[SeedSite, str]] = []
        for seed in seeds:
            mast = snap_to_points(seed.lon, seed.lat, masts, snap)
            if mast is not None:
                out.append((SeedSite(seed.net, mast[0], mast[1], seed.n_cells, seed.technologies), "osm_mast"))
            else:
                out.append((seed, "opencellid"))
        return out

    def _build(self) -> list[EstimatedSite]:
        restricted = self._settings.section("restricted", "cartoradio_grid")
        cap = number(restricted, "cap_v_m", 15.0)
        sigma_db = number(restricted, "sigma_db", 4.0)
        now = datetime.now(timezone.utc)
        cells = [obs_to_cell(obs) for obs in self._cartoradio.fetch(self._area, now, now)]
        peaks = find_peaks(cells, number(self._config, "peak_min_v_m", 1.5))
        peak_points = [(p.lon, p.lat) for p in peaks]
        peak_snap = number(self._config, "peak_snap_m", 300.0)
        sigma_osm = number(self._config, "position_sigma_osm_m", 30.0)
        sigma_peak = number(self._config, "position_sigma_peak_m", 75.0)
        sigma_cells = number(self._config, "position_sigma_opencellid_m", 300.0)

        placed: list[tuple[SeedSite, str, float]] = []
        used_peaks: set[tuple[float, float]] = set()
        for seed, source in self._seeds():
            if source == "osm_mast":
                placed.append((seed, source, sigma_osm))
                continue
            peak = snap_to_points(seed.lon, seed.lat, peak_points, peak_snap)
            if peak is not None:
                used_peaks.add(peak)
                placed.append((SeedSite(seed.net, peak[0], peak[1], seed.n_cells, seed.technologies),
                               "cartoradio_peak", sigma_peak))
            else:
                placed.append((seed, source, sigma_cells))
        new_min = number(self._config, "new_site_min_v_m", 3.0)
        for peak_cell in peaks:
            point = (peak_cell.lon, peak_cell.lat)
            if peak_cell.value >= new_min and point not in used_peaks and all(
                    distance_m(point[0], point[1], s.lon, s.lat) > peak_snap for s, _src, _sg in placed):
                placed.append((SeedSite(0, point[0], point[1], 0, ()), "cartoradio_peak_only", sigma_peak))

        placed.sort(key=lambda item: (round(item[0].lon, 6), round(item[0].lat, 6), item[0].net))
        powers, sigmas, counts, background, self._fit_error_db = fit_effective_eirp(
            [(s.lon, s.lat) for s, _src, _sg in placed], cells,
            radius_m=number(self._config, "fit_radius_m", 500.0),
            height_m=number(self._config, "assumed_height_above_receiver_m", 20.0),
            sigma_db=sigma_db, cap=cap)
        self._background = background
        operators = self._operators()
        return [
            EstimatedSite(
                site_id=f"est-site-{index:05d}",
                operator=operators.get(seed.net, "unknown"),
                technologies=seed.technologies,
                lon=round(seed.lon, 6),
                lat=round(seed.lat, 6),
                position_source=source,
                position_sigma_m=position_sigma,
                effective_eirp_w=round(power, 1),
                effective_eirp_sigma_w=round(sigma, 1) if math.isfinite(sigma) else -1.0,
                fit_cells=count,
            )
            for index, ((seed, source, position_sigma), power, sigma, count)
            in enumerate(zip(placed, powers, sigmas, counts), start=1)
        ]


def obs_to_cell(obs: Observation) -> RasterCell:
    """Rebuild a raster cell (row/col from the Cartoradio entity id) from an observation."""
    tail = obs.entity_id.rsplit(":", 1)[-1]  # cartoradio-r{row}-c{col}
    parts = tail.split("-")
    row = int(parts[-2][1:])
    col = int(parts[-1][1:])
    return RasterCell(row=row, col=col, lon=obs.lon, lat=obs.lat, value=obs.values["electricField"])
