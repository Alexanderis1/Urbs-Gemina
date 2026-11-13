"""Build the committed seed files that place simulated sensors in realistic spots.

    python -m twin.providers.build_seeds            # both seeds
    python -m twin.providers.build_seeds loops      # simulated loop station positions
    python -m twin.providers.build_seeds sites      # estimated antenna site positions

Loop stations: Roma Capitale's own traffic-signal register (``DIPMOB:Semafori``)
gives the signalised junctions. Junctions run by a central traffic-control
system (Omnia, Tmacs, Sigma...) are where detector loops are normally fitted
(C=65). We keep vehicle signals of that kind that sit on the city's major road
network (``DIPPC:grande_viabilita``, motorway to secondary), then spread the
stations out with a minimum spacing. Road class and name come from the road.

Antenna sites: OpenCelliD cells inside Roma Capitale (tokenless PMTiles mirror,
zoom 14), clustered into sites as in ``estimated.sites.cluster_sites``.

Both outputs are small GeoJSON files under ``simulated/seed_data/`` and
``estimated/seed_data/``, committed so runs are
reproducible offline. Licences: Roma Capitale GeoPortale (credit, CC BY assumed
C=60), road geometry derived from OSM (ODbL), OpenCelliD (CC BY-SA 4.0).
"""
from __future__ import annotations

import gzip
import json
import math
import random
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from twin.providers.geo import distance_m
from twin.providers.http import USER_AGENT
from twin.providers.settings import Settings, integer, number
from twin.providers.estimated.sites import Cell, cluster_sites

PROVIDERS_DIR = Path(__file__).resolve().parent
LOOPS_FILE = PROVIDERS_DIR / "simulated" / "seed_data" / "loop_stations.geojson"
SITES_FILE = PROVIDERS_DIR / "estimated" / "seed_data" / "antenna_sites.geojson"

SIGNALS_LAYER = "DIPMOB:Semafori"
ROADS_LAYER = "DIPPC:grande_viabilita"
MUNICIPI_LAYER = "DIPPC:210_RomaCapitale_Municipi"
OPENCELLID_PMTILES = "https://data.source.coop/smartmaps/opencellid/cellid.pmtiles"

#: Geofabrik/OSM shapefile road codes used by the grande_viabilita layer.
ROAD_CLASS_BY_CODE = {5111: "motorway", 5112: "trunk", 5113: "primary", 5114: "secondary"}

Polygon = list[list[tuple[float, float]]]  # outer ring then holes


# --- geometry -------------------------------------------------------------------

def polygons_of(collection: Mapping[str, Any]) -> list[Polygon]:
    out: list[Polygon] = []
    for feature in collection.get("features", []):
        geometry = feature.get("geometry") or {}
        parts = [geometry["coordinates"]] if geometry.get("type") == "Polygon" else (
            geometry["coordinates"] if geometry.get("type") == "MultiPolygon" else [])
        for part in parts:
            out.append([[(float(x), float(y)) for x, y, *_ in ring] for ring in part])
    return out


def _in_ring(lon: float, lat: float, ring: Sequence[tuple[float, float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def in_polygons(lon: float, lat: float, polygons: Sequence[Polygon]) -> bool:
    for rings in polygons:
        if rings and _in_ring(lon, lat, rings[0]) and not any(_in_ring(lon, lat, hole) for hole in rings[1:]):
            return True
    return False


def _segment_distance_m(lon: float, lat: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    kx = 111_320.0 * math.cos(math.radians(lat))
    ky = 110_540.0
    ax, ay = (a[0] - lon) * kx, (a[1] - lat) * ky
    bx, by = (b[0] - lon) * kx, (b[1] - lat) * ky
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length2))
    return math.hypot(ax + t * dx, ay + t * dy)


def _lines(geometry: Mapping[str, Any]) -> list[list[tuple[float, float]]]:
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "LineString":
        return [[(float(x), float(y)) for x, y, *_ in coords]]
    if kind == "MultiLineString":
        return [[(float(x), float(y)) for x, y, *_ in line] for line in coords]
    return []


# --- loop stations --------------------------------------------------------------

def select_loop_stations(signals: Mapping[str, Any], roads: Mapping[str, Any], n_stations: int,
                         snap_m: float, spacing_m: float, seed: int,
                         class_priority: Sequence[str] = ("motorway", "trunk", "primary", "secondary"),
                         ) -> dict[str, Any]:
    """Pick up to ``n_stations`` centrally controlled vehicle signals on major roads."""
    segments: list[tuple[str, str, tuple[float, float], tuple[float, float]]] = []
    for feature in roads.get("features", []):
        props = feature.get("properties") or {}
        road_class = ROAD_CLASS_BY_CODE.get(int(props.get("code") or 0))
        if road_class is None:
            continue
        name = str(props.get("name") or props.get("topon_osm") or "")
        for line in _lines(feature.get("geometry") or {}):
            segments.extend((road_class, name, a, b) for a, b in zip(line, line[1:]))

    candidates: list[dict[str, Any]] = []
    for feature in signals.get("features", []):
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        if geometry.get("type") != "Point" or props.get("TIPO") != "V" or not props.get("SISTEMA_1"):
            continue
        lon, lat = (float(v) for v in geometry["coordinates"][:2])
        near = [(s, _segment_distance_m(lon, lat, s[2], s[3])) for s in segments
                if abs(s[2][0] - lon) < 0.01 and abs(s[2][1] - lat) < 0.01]
        near = [(s, d) for s, d in near if d <= snap_m]
        if not near:
            continue
        best_class = min((s[0] for s, _ in near), key=class_priority.index)
        segment = min((item for item in near if item[0][0] == best_class), key=lambda item: item[1])[0]
        candidates.append({"lon": lon, "lat": lat, "road_class": best_class, "road_name": segment[1],
                           "signal_code": str(props.get("COD_IMP") or ""), "control_system": str(props["SISTEMA_1"])})

    rng = random.Random(seed)
    rng.shuffle(candidates)
    candidates.sort(key=lambda c: class_priority.index(c["road_class"]))
    chosen: list[dict[str, Any]] = []
    for candidate in candidates:
        if len(chosen) >= n_stations:
            break
        if all(distance_m(candidate["lon"], candidate["lat"], c["lon"], c["lat"]) >= spacing_m for c in chosen):
            chosen.append(candidate)
    chosen.sort(key=lambda c: (c["lon"], c["lat"]))
    return {
        "type": "FeatureCollection",
        "basis": ("Centrally controlled vehicle signals (Roma Capitale DIPMOB:Semafori) on major roads "
                  "(DIPPC:grande_viabilita, OSM-derived). Loop positions are plausible, not the real ones."),
        "features": [
            {"type": "Feature",
             "geometry": {"type": "Point", "coordinates": [round(c["lon"], 6), round(c["lat"], 6)]},
             "properties": {k: v for k, v in c.items() if k not in ("lon", "lat")}}
            for c in chosen
        ],
    }


# --- antenna sites --------------------------------------------------------------

def _tile_range(bbox: tuple[float, float, float, float], zoom: int) -> Iterable[tuple[int, int]]:
    def tile(lon: float, lat: float) -> tuple[int, int]:
        n = 2**zoom
        x = int((lon + 180.0) / 360.0 * n)
        y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
        return x, y

    x0, y0 = tile(bbox[0], bbox[3])
    x1, y1 = tile(bbox[2], bbox[1])
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            yield x, y


def fetch_opencellid_cells(bbox: tuple[float, float, float, float], mcc: int, zoom: int = 14) -> list[Cell]:
    """Cells from the OpenCelliD PMTiles mirror. Needs the optional ``pmtiles`` and
    ``mapbox-vector-tile`` packages (seed building only)."""
    import importlib

    mapbox_vector_tile: Any = importlib.import_module("mapbox_vector_tile")
    reader_class: Any = importlib.import_module("pmtiles.reader").Reader

    cache: dict[tuple[int, int], bytes] = {}

    def get(offset: int, length: int) -> bytes:
        # Header and directories are asked for again on every tile: cache them.
        if (offset, length) in cache:
            return cache[(offset, length)]
        request = urllib.request.Request(
            OPENCELLID_PMTILES, headers={"Range": f"bytes={offset}-{offset + length - 1}", "User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            data: bytes = response.read()
        if offset < 16_384 or length > 4_096:
            cache[(offset, length)] = data
        return data

    reader = reader_class(get)
    cells: list[Cell] = []
    n = 2**zoom
    tiles = list(_tile_range(bbox, zoom))
    reader.get(zoom, *tiles[0])  # warm the header and directory cache before going parallel
    with ThreadPoolExecutor(max_workers=16) as pool:
        raws = list(pool.map(lambda xy: (xy, reader.get(zoom, *xy)), tiles))
    for (x, y), raw in raws:
        if not raw:
            continue
        decoded = mapbox_vector_tile.decode(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
        for layer in decoded.values():
            extent = float(layer.get("extent", 4096))
            for feature in layer["features"]:
                props = feature["properties"]
                px, py = feature["geometry"]["coordinates"]
                lon = (x + px / extent) / n * 360.0 - 180.0
                # Vector-tile y grows downward, but this decoder flips it (y_coord_down=False).
                lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1 - py / extent) / n))))
                if int(props.get("mcc", 0)) != mcc:
                    continue
                cells.append(Cell(radio=str(props.get("radio", "")).upper(), mcc=mcc, net=int(props["net"]),
                                  cell=int(props["cell"]), lon=lon, lat=lat, samples=max(1, int(props.get("samples", 1)))))
    return cells


def sites_geojson(cells: Sequence[Cell], polygons: Sequence[Polygon], shift_bits: Mapping[str, int],
                  merge_distance_m: float) -> dict[str, Any]:
    inside = [cell for cell in cells if in_polygons(cell.lon, cell.lat, polygons)]
    sites = cluster_sites(inside, shift_bits, merge_distance_m)
    sites.sort(key=lambda s: (round(s.lon, 6), round(s.lat, 6), s.net))
    return {
        "type": "FeatureCollection",
        "basis": ("OpenCelliD cells (CC BY-SA 4.0, tokenless PMTiles mirror) inside Roma Capitale, "
                  "clustered into estimated sites. Cell centroids lie 100 m-1 km from real masts (C=70)."),
        "features": [
            {"type": "Feature",
             "geometry": {"type": "Point", "coordinates": [round(s.lon, 6), round(s.lat, 6)]},
             "properties": {"net": s.net, "n_cells": s.n_cells, "technologies": list(s.technologies)}}
            for s in sites
        ],
    }


# --- command line ---------------------------------------------------------------

def _write(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(data['features'])} features)")


def main(argv: Sequence[str]) -> int:
    from twin.providers.open.roma_wfs import fetch_layer

    what = set(argv) or {"loops", "sites"}
    settings = Settings.load()
    if "loops" in what:
        config = settings.section("simulators", "loops")
        _write(LOOPS_FILE, select_loop_stations(
            fetch_layer(SIGNALS_LAYER, timeout_s=180), fetch_layer(ROADS_LAYER, timeout_s=180),
            n_stations=integer(config, "n_stations", 93), snap_m=number(config, "snap_to_road_m", 40.0),
            spacing_m=number(config, "min_spacing_m", 600.0), seed=integer(config, "seed", 42)))
    if "sites" in what:
        config = settings.section("estimated", "register")
        polygons = polygons_of(fetch_layer(MUNICIPI_LAYER, timeout_s=180))
        shifts = {str(k): int(v) for k, v in (config.get("site_id_shift_bits", {}) or {}).items() if k != "basis"}
        from twin.providers.base import ROME_BBOX

        cells = fetch_opencellid_cells(ROME_BBOX, mcc=integer(config, "mcc", 222))
        _write(SITES_FILE, sites_geojson(cells, polygons, shifts, number(config, "merge_distance_m", 150.0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
