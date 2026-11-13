"""Simulated antenna installation register (layer ``antenna_register``).

Stand-in for the register of authorised installations, which Roma Capitale does
not hold. Site *positions* come from crowd-sourced OpenCelliD cells clustered
into sites, snapped to OpenStreetMap masts where one is close. Everything else
(sectors, heights, EIRP, authorisation status, dates) is generated from a fixed
seed and the tables in ``config/emf_params.yaml``. Without seed files the
positions are generated too, and the records say so in ``source_id``.

Record fields follow the structure of the installation application form
("Modello A", D.Lgs. 259/2003) so a real register can replace this one field by
field. The exact form fields are unconfirmed (C=60); see ``MODEL_A_LABELS_IT``.
Every record is ``synthetic=True``.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from twin.providers.base import ROME_BBOX, BBox, Observation, ProviderInfo
from twin.providers.geo import distance_m, in_bbox, offset
from twin.providers.settings import Settings, integer, number, value

PROVIDER_ID = "sim_register"
CENTRE = (12.4823, 41.8960)  # Piazza Venezia, used only to place generated sites

#: Field names of a register record, in form order.
MODEL_A_FIELDS: tuple[str, ...] = (
    "site_id",
    "operator",
    "technologies",
    "address",
    "lon",
    "lat",
    "position_source",
    "building_height_m",
    "height_above_roof_m",
    "antenna_height_agl_m",
    "bands_mhz",
    "sectors",
    "total_eirp_w",
    "authorisation_status",
    "application_date",
    "synthetic",
    "simulator_version",
)

#: Italian labels of the application form these fields map to (C=60, to be
#: confirmed with Roma Capitale, design proposal open question 5).
MODEL_A_LABELS_IT: dict[str, str] = {
    "operator": "Gestore",
    "address": "Indirizzo dell'impianto",
    "lon": "Coordinate geografiche (longitudine)",
    "lat": "Coordinate geografiche (latitudine)",
    "technologies": "Tecnologia / sistema",
    "bands_mhz": "Frequenze di trasmissione (MHz)",
    "antenna_height_agl_m": "Altezza del centro elettrico dal suolo (m)",
    "sectors": "Antenne: direzione di massimo irraggiamento, tilt, potenza",
    "total_eirp_w": "Potenza EIRP complessiva (W)",
    "authorisation_status": "Stato dell'autorizzazione",
    "application_date": "Data di presentazione dell'istanza",
}


@dataclass(frozen=True)
class Cell:
    """One OpenCelliD row (an estimated cell centroid, not a mast)."""

    radio: str
    mcc: int
    net: int
    cell: int
    lon: float
    lat: float
    samples: int = 1


@dataclass(frozen=True)
class SeedSite:
    """A cluster of cells believed to be one site of one operator."""

    net: int
    lon: float
    lat: float
    n_cells: int
    technologies: tuple[str, ...]


@dataclass(frozen=True)
class Sector:
    azimuth_deg: float
    mechanical_tilt_deg: float
    eirp_w: float


@dataclass(frozen=True)
class SiteRecord:
    site_id: str
    operator: str
    technologies: tuple[str, ...]
    lon: float
    lat: float
    position_source: str  # "opencellid" | "osm_mast" | "generated"
    building_height_m: float
    height_above_roof_m: float
    bands_mhz: tuple[str, ...]
    sectors: tuple[Sector, ...]
    authorisation_status: str
    application_date: date
    simulator_version: str
    address: str = ""
    synthetic: bool = field(default=True)

    @property
    def antenna_height_agl_m(self) -> float:
        return round(self.building_height_m + self.height_above_roof_m, 1)

    @property
    def total_eirp_w(self) -> float:
        return round(sum(sector.eirp_w for sector in self.sectors), 1)

    def to_model_a(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "operator": self.operator,
            "technologies": list(self.technologies),
            "address": self.address,
            "lon": self.lon,
            "lat": self.lat,
            "position_source": self.position_source,
            "building_height_m": self.building_height_m,
            "height_above_roof_m": self.height_above_roof_m,
            "antenna_height_agl_m": self.antenna_height_agl_m,
            "bands_mhz": list(self.bands_mhz),
            "sectors": [
                {"azimuth_deg": s.azimuth_deg, "mechanical_tilt_deg": s.mechanical_tilt_deg, "eirp_w": s.eirp_w}
                for s in self.sectors
            ],
            "total_eirp_w": self.total_eirp_w,
            "authorisation_status": self.authorisation_status,
            "application_date": self.application_date.isoformat(),
            "synthetic": self.synthetic,
            "simulator_version": self.simulator_version,
        }


# --- seed readers ---------------------------------------------------------------

def read_opencellid_csv(path: Path, mcc: int, bbox: BBox = ROME_BBOX) -> list[Cell]:
    """Read an OpenCelliD export (plain or gzipped, with or without header)."""
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    cells: list[Cell] = []
    for row in csv.reader(io.StringIO(raw.decode("utf-8", errors="replace"))):
        if len(row) < 10 or row[0].strip().lower() == "radio":
            continue
        try:
            cell = Cell(
                radio=row[0].strip().upper(),
                mcc=int(row[1]),
                net=int(row[2]),
                cell=int(row[4]),
                lon=float(row[6]),
                lat=float(row[7]),
                samples=max(1, int(float(row[9] or 1))),
            )
        except ValueError:
            continue
        if cell.mcc == mcc and in_bbox(cell.lon, cell.lat, bbox):
            cells.append(cell)
    return cells


def read_osm_masts(path: Path) -> list[tuple[float, float]]:
    """Positions of masts/towers from an Overpass JSON answer (nodes or way centres)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    masts: list[tuple[float, float]] = []
    for element in data.get("elements", []):
        if "lon" in element and "lat" in element:
            masts.append((float(element["lon"]), float(element["lat"])))
        elif isinstance(element.get("center"), dict):
            centre = element["center"]
            masts.append((float(centre["lon"]), float(centre["lat"])))
    return masts


#: Overpass query that produces the masts file for Rome (run by the ingest stream).
OVERPASS_MASTS_QUERY = (
    "[out:json][timeout:120];"
    "(nwr[\"man_made\"~\"^(mast|tower)$\"][\"tower:type\"=\"communication\"]({s},{w},{n},{e});"
    "nwr[\"communication:mobile_phone\"=\"yes\"]({s},{w},{n},{e}););out center;"
)


def read_seed_sites(path: Path) -> list[SeedSite]:
    """Pre-clustered sites from the committed GeoJSON seed (see build_seeds)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    sites: list[SeedSite] = []
    for feature in data.get("features", []):
        lon, lat = feature["geometry"]["coordinates"][:2]
        props = feature.get("properties") or {}
        sites.append(SeedSite(net=int(props.get("net", 0)), lon=float(lon), lat=float(lat),
                              n_cells=int(props.get("n_cells", 1)),
                              technologies=tuple(str(t) for t in props.get("technologies", ["LTE"]))))
    return sites


# --- clustering -----------------------------------------------------------------

def cluster_sites(cells: Sequence[Cell], shift_bits: Mapping[str, int], merge_distance_m: float) -> list[SeedSite]:
    """Cells -> sites: group by base-station id, then merge close groups of one operator."""
    groups: dict[tuple[int, str, int], list[Cell]] = {}
    for cell in cells:
        shift = shift_bits.get(cell.radio)
        station = cell.cell >> shift if shift is not None else cell.cell
        groups.setdefault((cell.net, cell.radio, station), []).append(cell)

    seeds = [_weighted(net, members) for (net, _radio, _station), members in sorted(groups.items())]
    seeds.sort(key=lambda s: (-s.n_cells, s.net, s.lon, s.lat))

    merged: list[SeedSite] = []
    for seed in seeds:
        target = next(
            (i for i, site in enumerate(merged)
             if site.net == seed.net and distance_m(site.lon, site.lat, seed.lon, seed.lat) <= merge_distance_m),
            None,
        )
        if target is None:
            merged.append(seed)
        else:
            merged[target] = _combine(merged[target], seed)
    return merged


def _weighted(net: int, members: Sequence[Cell]) -> SeedSite:
    weight = sum(cell.samples for cell in members)
    return SeedSite(
        net=net,
        lon=sum(cell.lon * cell.samples for cell in members) / weight,
        lat=sum(cell.lat * cell.samples for cell in members) / weight,
        n_cells=len(members),
        technologies=tuple(sorted({cell.radio for cell in members})),
    )


def _combine(a: SeedSite, b: SeedSite) -> SeedSite:
    n = a.n_cells + b.n_cells
    return SeedSite(
        net=a.net,
        lon=(a.lon * a.n_cells + b.lon * b.n_cells) / n,
        lat=(a.lat * a.n_cells + b.lat * b.n_cells) / n,
        n_cells=n,
        technologies=tuple(sorted(set(a.technologies) | set(b.technologies))),
    )


# --- provider -------------------------------------------------------------------

class SimRegisterProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings.load()
        self._config = self._settings.section("simulators", "register")
        self._emf = self._settings.emf.get("simulated_register", {}) or {}
        self._eirp_table: Mapping[str, Any] = self._settings.emf.get("typical_eirp_w", {}) or {}
        self._seed = int(self._emf.get("seed", 42))
        self._version = self._settings.simulator_version
        self._sites: list[SiteRecord] | None = None
        self._origin = "generated"

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            id=PROVIDER_ID,
            kind="simulated",
            layer="antenna_register",
            licence="generated; positions inherit CC BY-SA (OpenCelliD) / ODbL (OSM) when seeded",
            cadence="static",
            synthetic=True,
            notes=f"{self._version}. Positions: {self._position_note()}. Parameters are synthetic.",
        )

    def sites(self) -> list[SiteRecord]:
        if self._sites is None:
            self._sites = self._build()
        return self._sites

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        rel_sigma = float(value(self._emf.get("eirp_relative_sigma"), 0.5))
        height_sigma = float(value(self._emf.get("height_sigma_m"), 3.0))
        source = f"{PROVIDER_ID}:{self._origin_after_build()}"
        for site in self.sites():
            observed = datetime.combine(site.application_date, datetime.min.time(), tzinfo=timezone.utc)
            if observed > _aware(end) or not in_bbox(site.lon, site.lat, bbox):
                continue
            yield Observation(
                entity_id=f"urn:ngsi-ld:AntennaSite:{site.site_id}",
                entity_type="AntennaSite",
                lon=site.lon,
                lat=site.lat,
                observed_at=observed,
                values={
                    "total_eirp_w": site.total_eirp_w,
                    "antenna_height_agl_m": site.antenna_height_agl_m,
                    "n_sectors": float(len(site.sectors)),
                },
                sigma={
                    "total_eirp_w": round(rel_sigma * site.total_eirp_w, 1),
                    "antenna_height_agl_m": height_sigma,
                    "n_sectors": 0.0,
                },
                source_id=source,
                synthetic=True,
            )

    # -- building the register --

    def _position_note(self) -> str:
        for key in ("opencellid_csv", "sites_geojson"):
            path = self._settings.path(str(self._config.get(key, "")))
            if path is not None and path.exists():
                return "OpenCelliD cell clusters, snapped to OSM masts where available (estimated)"
        return "generated (no seed file)"

    def _origin_after_build(self) -> str:
        self.sites()
        return self._origin

    def _build(self) -> list[SiteRecord]:
        seeds = self._seed_sites()
        if seeds is None:
            self._origin = "generated"
            seeds_with_source = [(seed, "generated") for seed in self._generated_seeds()]
        else:
            self._origin = "opencellid"
            seeds_with_source = self._snap_to_masts(seeds)
        seeds_with_source.sort(key=lambda item: (round(item[0].lon, 6), round(item[0].lat, 6), item[0].net))
        return [self._record(index, seed, source) for index, (seed, source) in enumerate(seeds_with_source, start=1)]

    def _seed_sites(self) -> list[SeedSite] | None:
        cells_path = self._settings.path(str(self._config.get("opencellid_csv", "")))
        if cells_path is None or not cells_path.exists():
            sites_path = self._settings.path(str(self._config.get("sites_geojson", "")))
            if sites_path is not None and sites_path.exists():
                known = self._operators()
                # Unknown network codes (MVNO or bad crowd rows) are dropped.
                return [site for site in read_seed_sites(sites_path) if site.net in known]
            return None
        cells = read_opencellid_csv(cells_path, mcc=integer(self._config, "mcc", 222))
        shifts_node = self._config.get("site_id_shift_bits", {}) or {}
        shifts = {str(k): int(v) for k, v in shifts_node.items() if k != "basis"}
        return cluster_sites(cells, shifts, number(self._config, "merge_distance_m", 150.0))

    def _snap_to_masts(self, seeds: list[SeedSite]) -> list[tuple[SeedSite, str]]:
        masts_path = self._settings.path(str(self._config.get("osm_masts_json", "")))
        masts = read_osm_masts(masts_path) if masts_path is not None and masts_path.exists() else []
        snap = number(self._config, "osm_snap_distance_m", 200.0)
        out: list[tuple[SeedSite, str]] = []
        for seed in seeds:
            best = min(masts, key=lambda m: distance_m(seed.lon, seed.lat, m[0], m[1]), default=None)
            if best is not None and distance_m(seed.lon, seed.lat, best[0], best[1]) <= snap:
                out.append((SeedSite(seed.net, best[0], best[1], seed.n_cells, seed.technologies), "osm_mast"))
            else:
                out.append((seed, "opencellid"))
        return out

    def _generated_seeds(self) -> list[SeedSite]:
        rng = random.Random(f"{self._seed}:{self._version}:positions")
        n_sites = integer(self._config, "fallback_n_sites", 1500)
        spread_m = number(self._config, "fallback_spread_km", 6.0) * 1000.0
        nets = sorted(self._operators())
        shares_node = self._emf.get("technology_shares", {}) or {}
        techs = [str(k) for k in shares_node if k != "basis"] or ["LTE"]
        weights = [float(shares_node[k]) for k in techs] if shares_node else [1.0]
        seeds: list[SeedSite] = []
        while len(seeds) < n_sites:
            lon, lat = offset(*CENTRE, east_m=rng.gauss(0.0, spread_m), north_m=rng.gauss(0.0, spread_m))
            if not in_bbox(lon, lat, ROME_BBOX):
                continue
            tech = rng.choices(techs, weights=weights)[0]
            seeds.append(SeedSite(net=rng.choice(nets), lon=lon, lat=lat, n_cells=0, technologies=(tech,)))
        return seeds

    def _operators(self) -> dict[int, str]:
        node = self._config.get("operators", {}) or {}
        return {int(k): str(v) for k, v in node.items()} or {1: "TIM"}

    def _record(self, index: int, seed: SeedSite, source: str) -> SiteRecord:
        site_id = f"sim-site-{index:05d}"
        rng = random.Random(f"{self._seed}:{self._version}:{site_id}")
        azimuths = [float(a) for a in self._emf.get("sector_azimuths_deg", [0, 120, 240])]
        rotation = rng.uniform(0.0, 360.0 / max(1, len(azimuths)))
        tilt = self._emf.get("mechanical_tilt_deg", {}) or {}
        mast = self._emf.get("mast_height_above_roof_m", {}) or {}
        bands = self._bands(seed.technologies)
        per_sector_eirp = sum(float(value(self._eirp_table.get(band), 0.0)) for band in bands)
        sectors = tuple(
            Sector(
                azimuth_deg=round((azimuth + rotation) % 360.0, 1),
                mechanical_tilt_deg=round(rng.uniform(float(tilt.get("min", 2)), float(tilt.get("max", 8))), 1),
                eirp_w=round(per_sector_eirp, 1),
            )
            for azimuth in azimuths
        )
        return SiteRecord(
            site_id=site_id,
            operator=self._operators().get(seed.net, f"MNC {seed.net}"),
            technologies=seed.technologies,
            lon=round(seed.lon, 6),
            lat=round(seed.lat, 6),
            position_source=source,
            building_height_m=number(self._config, "building_height_m", 18.0),
            height_above_roof_m=round(rng.uniform(float(mast.get("min", 3)), float(mast.get("max", 6))), 1),
            bands_mhz=bands,
            sectors=sectors,
            authorisation_status=self._status(rng),
            application_date=self._date(rng),
            simulator_version=self._version,
        )

    def _bands(self, technologies: Sequence[str]) -> tuple[str, ...]:
        table = self._config.get("technology_bands_mhz", {}) or {}
        bands = {str(b) for tech in technologies for b in table.get(tech, [])}
        return tuple(sorted(bands, key=float)) or ("1800",)

    def _status(self, rng: random.Random) -> str:
        node = self._config.get("status_shares", {}) or {}
        names = [str(k) for k in node if k != "basis"] or ["authorised"]
        weights = [float(node[k]) for k in names] if node else [1.0]
        return rng.choices(names, weights=weights)[0]

    def _date(self, rng: random.Random) -> date:
        node = self._emf.get("application_dates", {}) or {}
        first = date.fromisoformat(str(node.get("first", "2015-01-01")))
        last = date.fromisoformat(str(node.get("last", "2026-10-31")))
        return first + timedelta(days=rng.randint(0, max(0, (last - first).days)))


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


__all__ = [
    "Cell",
    "MODEL_A_FIELDS",
    "MODEL_A_LABELS_IT",
    "OVERPASS_MASTS_QUERY",
    "SeedSite",
    "Sector",
    "SimRegisterProvider",
    "SiteRecord",
    "cluster_sites",
    "read_opencellid_csv",
    "read_osm_masts",
    "read_seed_sites",
]
