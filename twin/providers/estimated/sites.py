"""Antenna site positions from crowd-sourced data (estimated, not official).

OpenCelliD cells are estimated cell centroids, not masts (100 m-1 km off,
C=70). They are grouped by base-station id and merged within a distance per
operator. OpenStreetMap masts, where present, give better positions.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from twin.providers.base import ROME_BBOX, BBox
from twin.providers.geo import distance_m, in_bbox

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
    """Positions of masts/towers from an Overpass JSON answer (nodes or way centres) or GeoJSON points."""
    data = json.loads(path.read_text(encoding="utf-8"))
    masts: list[tuple[float, float]] = []
    for feature in data.get("features", []):
        geometry = feature.get("geometry") or {}
        if geometry.get("type") == "Point":
            lon, lat = geometry["coordinates"][:2]
            masts.append((float(lon), float(lat)))
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

