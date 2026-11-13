"""Download the whole-city context layers, drop personal fields, store GeoParquet.

For each layer in config/ingest.yaml:

1. download it (WFS, Overpass or a zipped shapefile) in WGS84;
2. hash the downloaded bytes (``raw_sha256``) so the upstream copy can be checked later;
3. drop personal fields (names, phones, e-mails) before anything is written;
4. write ``data/processed/<key>.parquet`` (GeoParquet) and ``<key>.geojson``;
5. record status, counts, hashes and the real/estimated/simulated label in
   ``data/manifest.json`` under ``snapshots``.

A layer that fails is recorded as ``not_available`` and the run carries on (gate A no-go rule).
Raw downloads are never written to disk, because some contain personal fields.
"""
from __future__ import annotations

import hashlib
import io
import json
import tempfile
import urllib.parse
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from twin.ingest.catalog import BBox, Catalog, LayerSpec
from twin.ingest.census import build_census_sections
from twin.ingest.http import Fetch, HttpRequest
from twin.ingest.manifest import record_snapshots, sha256_file
from twin.ingest.privacy import personal_columns

FeatureCollection = dict[str, Any]
Entry = dict[str, Any]


# --- Download -----------------------------------------------------------------

def wfs_url(base_url: str, type_name: str, bbox: BBox | None = None) -> str:
    """WFS 1.0.0 GetFeature in EPSG:4326 (lon, lat order) as GeoJSON."""
    params = {
        "service": "WFS",
        "version": "1.0.0",
        "request": "GetFeature",
        "typeName": type_name,
        "srsName": "EPSG:4326",
        "outputFormat": "application/json",
    }
    if bbox is not None:
        params["bbox"] = ",".join(f"{v:.6f}" for v in bbox) + ",EPSG:4326"
    return base_url + "?" + urllib.parse.urlencode(params)


def overpass_query(selectors: Sequence[str], bbox: BBox, timeout_s: int = 180) -> str:
    west, south, east, north = bbox
    box = f"({south},{west},{north},{east})"
    lines = [f"[out:json][timeout:{timeout_s}];", "("]
    lines += [f"  {selector}{box};" for selector in selectors]
    lines += [");", "out center tags;"]
    return "\n".join(lines)


def overpass_to_geojson(payload: dict[str, Any]) -> FeatureCollection:
    """Nodes become points; ways and relations become their centre point."""
    features: list[dict[str, Any]] = []
    for element in payload.get("elements", []):
        if element.get("type") == "node":
            lon, lat = element.get("lon"), element.get("lat")
        else:
            centre = element.get("center") or {}
            lon, lat = centre.get("lon"), centre.get("lat")
        if lon is None or lat is None:
            continue
        osm_id = f"{element['type']}/{element['id']}"
        properties = {"osm_id": osm_id, **(element.get("tags") or {})}
        features.append({"type": "Feature", "id": osm_id,
                         "geometry": {"type": "Point", "coordinates": [lon, lat]},
                         "properties": properties})
    return {"type": "FeatureCollection", "features": features}


def _download(layer: LayerSpec, catalog: Catalog, fetch: Fetch) -> tuple[bytes, str]:
    """Return (raw bytes, URL actually used)."""
    source = catalog.sources[layer.source]
    if source.protocol == "wfs":
        assert layer.type_name is not None
        bbox = catalog.city_bbox if layer.clip_to_city else None
        url = wfs_url(source.urls[0], layer.type_name, bbox)
        return fetch(HttpRequest(url)), url
    if source.protocol == "overpass":
        query = overpass_query(layer.selectors, catalog.city_bbox)
        body = urllib.parse.urlencode({"data": query}).encode("utf-8")
        errors: list[str] = []
        for url in source.urls:
            try:
                return fetch(HttpRequest(url, body=body, content_type="application/x-www-form-urlencoded",
                                         timeout_s=240.0)), url
            except Exception as error:  # noqa: BLE001 - try the next mirror
                errors.append(f"{urllib.parse.urlparse(url).netloc}: {type(error).__name__}: {error}")
        raise ConnectionError("all Overpass mirrors failed: " + "; ".join(errors))
    if source.protocol == "zip_shapefile":
        url = source.urls[0]
        return fetch(HttpRequest(url, timeout_s=600.0)), url
    raise ValueError(f"unknown protocol {source.protocol}")


# --- Parse into a GeoDataFrame ------------------------------------------------

def _parse_geojson(raw: bytes) -> FeatureCollection:
    try:
        collection: FeatureCollection = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        snippet = raw[:200].decode("utf-8", errors="replace").replace("\n", " ")
        raise ValueError(f"server did not return GeoJSON: {snippet}") from error
    if collection.get("type") != "FeatureCollection":
        raise ValueError(f"expected a FeatureCollection, got {collection.get('type')!r}")
    return collection


def _flatten_2d(coordinates: Any) -> Any:
    """Drop Z values. Some servers mix [x, y] and [x, y, 0] inside one ring."""
    if isinstance(coordinates, list) and coordinates and isinstance(coordinates[0], (int, float)):
        return coordinates[:2]
    if isinstance(coordinates, list):
        return [_flatten_2d(part) for part in coordinates]
    return coordinates


def _geometry_2d(geometry: Any) -> Any:
    if not isinstance(geometry, dict):
        return geometry
    if geometry.get("type") == "GeometryCollection":
        return {**geometry, "geometries": [_geometry_2d(g) for g in geometry.get("geometries", [])]}
    return {**geometry, "coordinates": _flatten_2d(geometry.get("coordinates"))}


def _frame_from_features(features: list[dict[str, Any]]) -> Any:
    import geopandas as gpd  # type: ignore[import-untyped,import-not-found,unused-ignore]

    if not features:
        return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs="EPSG:4326")
    # Keep the upstream feature id (e.g. "Ospedali.12") as a column for provenance.
    with_ids = [{**f, "geometry": _geometry_2d(f.get("geometry")),
                 "properties": ({"feature_id": f.get("id")} if f.get("id") is not None else {})
                 | (f.get("properties") or {})}
                for f in features]
    return gpd.GeoDataFrame.from_features(with_ids, crs="EPSG:4326")


def _frame_from_zip(raw: bytes, filters: dict[str, Any]) -> Any:
    import geopandas as gpd  # type: ignore[import-untyped,import-not-found,unused-ignore]

    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            shapefiles = [n for n in archive.namelist() if n.lower().endswith(".shp")]
            if len(shapefiles) != 1:
                raise ValueError(f"expected one shapefile in the zip, found {shapefiles}")
            archive.extractall(tmp)
        frame = gpd.read_file(Path(tmp) / shapefiles[0])
    for column, value in filters.items():
        frame = frame[frame[column] == value]
    return frame.to_crs("EPSG:4326")


def _to_frame(layer: LayerSpec, catalog: Catalog, raw: bytes) -> Any:
    protocol = catalog.sources[layer.source].protocol
    if protocol == "wfs":
        return _frame_from_features(_parse_geojson(raw).get("features", []))
    if protocol == "overpass":
        return _frame_from_features(overpass_to_geojson(json.loads(raw))["features"])
    return _frame_from_zip(raw, layer.filter)


def _census_frame(layer: LayerSpec, catalog: Catalog, fetch: Fetch, entry: Entry) -> Any:
    """Two downloads (shapes + population); both hashes go into the entry."""
    shapes_url = catalog.sources[layer.source].urls[0]
    population_url = str(layer.options["population_url"])
    shapes = fetch(HttpRequest(shapes_url, timeout_s=600.0))
    population = fetch(HttpRequest(population_url, timeout_s=600.0))
    entry["request_url"] = [shapes_url, population_url]
    entry["raw_sha256"] = {"shapes": hashlib.sha256(shapes).hexdigest(),
                           "population": hashlib.sha256(population).hexdigest()}
    return build_census_sections(layer, shapes, population)


# --- One layer ----------------------------------------------------------------

def _now_iso(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def ingest_layer(layer: LayerSpec, catalog: Catalog, fetch: Fetch, out_dir: Path,
                 now: datetime, root: Path | None = None) -> Entry:
    entry: Entry = {
        "source": layer.source,
        "data_kind": layer.data_kind,
        "synthetic": layer.data_kind == "simulated",
        "theme": layer.theme,
        "fetched_at": _now_iso(now),
    }
    if layer.type_name:
        entry["type_name"] = layer.type_name
    if layer.notes:
        entry["notes"] = layer.notes
    try:
        if catalog.sources[layer.source].protocol == "istat_census":
            frame = _census_frame(layer, catalog, fetch, entry)
        else:
            raw, url = _download(layer, catalog, fetch)
            entry["request_url"] = url
            entry["raw_sha256"] = hashlib.sha256(raw).hexdigest()
            frame = _to_frame(layer, catalog, raw)
            del raw  # the raw bytes may hold personal fields; only the cleaned frame goes on

        columns = [c for c in frame.columns if c != frame.geometry.name]
        dropped = personal_columns(columns, catalog.privacy_patterns, layer.drop_fields)
        frame = frame.drop(columns=dropped)

        out_dir.mkdir(parents=True, exist_ok=True)
        parquet = out_dir / f"{layer.key}.parquet"
        geojson = out_dir / f"{layer.key}.geojson"
        frame.to_parquet(parquet, index=False)
        geojson.write_text(frame.to_json(drop_id=True, ensure_ascii=False), encoding="utf-8")

        base = root or out_dir
        entry.update(
            status="ok",
            features=int(len(frame)),
            dropped_fields=dropped,
            crs="EPSG:4326",
            files={
                "geoparquet": {"path": _rel(parquet, base), "sha256": sha256_file(parquet)},
                "geojson": {"path": _rel(geojson, base), "sha256": sha256_file(geojson)},
            },
            warnings=["0 features in the requested area"] if len(frame) == 0 else [],
        )
    except Exception as error:  # noqa: BLE001 - any failure marks the layer unavailable
        entry.update(status="not_available", error=f"{type(error).__name__}: {error}"[:500])
    return entry


def _rel(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


# --- Whole run ------------------------------------------------------------------

def run(keys: Iterable[str], catalog: Catalog, fetch: Fetch, out_dir: Path, manifest_path: Path,
        root: Path, now: datetime | None = None, log: Any = print) -> int:
    """Ingest the given layers (all when empty). Exit code: 0 all ok, 1 some failed, 2 bad keys."""
    selected = list(keys) or list(catalog.layers)
    unknown = [key for key in selected if key not in catalog.layers]
    if unknown:
        log(f"Unknown layer keys: {unknown}. Known: {sorted(catalog.layers)}")
        return 2
    failures = 0
    for key in selected:
        entry = ingest_layer(catalog.layers[key], catalog, fetch, out_dir,
                             now or datetime.now(timezone.utc), root=root)
        record_snapshots(manifest_path, {key: entry})  # write after each layer: a crash keeps progress
        if entry["status"] == "ok":
            log(f"ok   {key:30s} {entry['features']:>7} features  dropped={entry['dropped_fields']}")
        else:
            failures += 1
            log(f"FAIL {key:30s} {entry['error']}")
    log(f"{len(selected) - failures}/{len(selected)} layers ok")
    return 1 if failures else 0
