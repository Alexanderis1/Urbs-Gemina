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
from twin.ingest.arcgis import export_image, query_features
from twin.ingest.census import build_census_sections
from twin.ingest.health_areas import build_asl_areas
from twin.ingest.osm_extract import extract_file, read_elements
from twin.ingest.sensitive_sites import build_sensitive_sites
from twin.ingest.tables import AddressIndex, geocoded_frame, osm_address_records, points_frame, read_table
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
    """Nodes become points; ways become lines when they carry a geometry, else their centre point."""
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
        line = element.get("geometry") or []
        geometry = ({"type": "LineString", "coordinates": [[p["lon"], p["lat"]] for p in line]} if len(line) >= 2
                    else {"type": "Point", "coordinates": [lon, lat]})
        features.append({"type": "Feature", "id": osm_id, "geometry": geometry, "properties": properties})
    return {"type": "FeatureCollection", "features": features}


def split_bbox(bbox: BBox, n: int) -> list[BBox]:
    """Split a bbox into n x n tiles, row by row from the south-west corner."""
    west, south, east, north = bbox
    dx, dy = (east - west) / n, (north - south) / n
    return [(round(west + i * dx, 6), round(south + j * dy, 6),
             round(west + (i + 1) * dx, 6), round(south + (j + 1) * dy, 6))
            for j in range(n) for i in range(n)]


def _overpass_tile(urls: Sequence[str], selectors: Sequence[str], bbox: BBox,
                   fetch: Fetch) -> tuple[dict[str, Any], str]:
    body = urllib.parse.urlencode({"data": overpass_query(selectors, bbox)}).encode("utf-8")
    errors: list[str] = []
    for url in urls:
        try:
            raw = fetch(HttpRequest(url, body=body, content_type="application/x-www-form-urlencoded",
                                    timeout_s=240.0))
            payload: dict[str, Any] = json.loads(raw)
            if "remark" in payload and "runtime error" in str(payload["remark"]):
                raise RuntimeError(str(payload["remark"])[:200])  # Overpass timeout inside a 200 answer
            return payload, url
        except Exception as error:  # noqa: BLE001 - try the next mirror
            errors.append(f"{urllib.parse.urlparse(url).netloc}: {type(error).__name__}: {error}")
    raise ConnectionError("all Overpass mirrors failed: " + "; ".join(errors))


def _download(layer: LayerSpec, catalog: Catalog, fetch: Fetch) -> tuple[bytes, str]:
    """Return (raw bytes, URL actually used)."""
    source = catalog.sources[layer.source]
    if source.protocol == "wfs":
        assert layer.type_name is not None
        bbox = catalog.city_bbox if layer.clip_to_city else None
        url = wfs_url(source.urls[0], layer.type_name, bbox)
        return fetch(HttpRequest(url)), url
    if source.protocol == "overpass":
        tiles = split_bbox(catalog.city_bbox, int(layer.options.get("tiles", 1)))
        seen: dict[str, dict[str, Any]] = {}
        used: list[str] = []
        for tile in tiles:
            payload, url = _overpass_tile(source.urls, layer.selectors, tile, fetch)
            used.append(url)
            for element in payload.get("elements", []):
                seen.setdefault(f"{element.get('type')}/{element.get('id')}", element)
        merged = {"elements": sorted(seen.values(), key=lambda e: (str(e.get("type")), int(e.get("id", 0))))}
        return json.dumps(merged, ensure_ascii=False).encode("utf-8"), used[0]
    if source.protocol == "osm_extract":
        url = source.urls[0]
        path, data = extract_file(url, fetch)
        digest_source = data if data is not None else path.read_bytes()
        payload = read_elements(path, layer.selectors, catalog.city_bbox, lines=bool(layer.options.get("lines")))
        payload["extract_sha256"] = hashlib.sha256(digest_source).hexdigest()
        return json.dumps(payload, ensure_ascii=False).encode("utf-8"), url
    if source.protocol == "arcgis_features":
        features, urls = query_features(layer, source.urls[0], catalog.city_bbox, fetch)
        collection = {"type": "FeatureCollection", "features": features}
        return json.dumps(collection, ensure_ascii=False).encode("utf-8"), urls[0]
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
    if protocol in ("wfs", "arcgis_features"):
        return _frame_from_features(_parse_geojson(raw).get("features", []))
    if protocol in ("overpass", "osm_extract"):
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


def _table_frame(layer: LayerSpec, catalog: Catalog, fetch: Fetch, entry: Entry) -> Any:
    """An official CSV: points from its own coordinates, or geocoded on OSM addresses offline."""
    options = layer.options
    url = str(options["url"])
    raw = fetch(HttpRequest(url, timeout_s=300.0))
    entry["request_url"] = url
    entry["raw_sha256"] = hashlib.sha256(raw).hexdigest()
    rows = read_table(raw, str(options.get("delimiter", ",")), str(options.get("encoding", "utf-8-sig")))
    del raw
    if catalog.sources[layer.source].protocol == "csv_points":
        frame, report = points_frame(rows, options, catalog.city_bbox)
    else:
        extract_url = catalog.sources[str(options["address_source"])].urls[0]
        path, data = extract_file(extract_url, fetch)
        entry["address_index_sha256"] = hashlib.sha256(data if data is not None else path.read_bytes()).hexdigest()
        addresses, roads = osm_address_records(path, catalog.city_bbox)
        frame, report = geocoded_frame(rows, options, AddressIndex(addresses, roads))
    entry.update(report)
    return frame


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
    raw_elements: list[dict[str, Any]] | None = None
    if catalog.sources[layer.source].protocol == "arcgis_image":
        return _ingest_raster(layer, catalog, fetch, out_dir, root, entry)
    try:
        if catalog.sources[layer.source].protocol == "derived":
            frame, report = build_sensitive_sites(layer, out_dir)
            entry.update(report)
        elif catalog.sources[layer.source].protocol == "istat_census":
            frame = _census_frame(layer, catalog, fetch, entry)
        elif catalog.sources[layer.source].protocol == "asl_areas":
            frame = build_asl_areas(layer, out_dir, fetch, entry)
        elif catalog.sources[layer.source].protocol in ("csv_points", "csv_geocoded"):
            frame = _table_frame(layer, catalog, fetch, entry)
        else:
            raw, url = _download(layer, catalog, fetch)
            entry["request_url"] = url
            entry["raw_sha256"] = hashlib.sha256(raw).hexdigest()
            frame = _to_frame(layer, catalog, raw)
            if catalog.sources[layer.source].protocol in ("overpass", "osm_extract"):
                parsed_raw = json.loads(raw)
                raw_elements = parsed_raw.get("elements", [])
                if "extract_sha256" in parsed_raw:
                    # Provenance is the hash of the extract file itself, not of the filtered subset.
                    entry["raw_sha256"] = parsed_raw["extract_sha256"]
            del raw  # the raw bytes may hold personal fields; only the cleaned data goes on

        for column, values in layer.exclude.items():
            if column in frame.columns:
                excluded = frame[column].isin(values)
                entry["excluded_rows"] = entry.get("excluded_rows", 0) + int(excluded.sum())
                frame = frame[~excluded]

        columns = [c for c in frame.columns if c != frame.geometry.name]
        dropped = personal_columns(columns, catalog.privacy_patterns, layer.drop_fields)
        frame = frame.drop(columns=dropped)
        if layer.options.get("clip_geometry") and len(frame):
            # Cut polygons that reach beyond the city bbox (e.g. a flood plain along the Tiber).
            frame = frame.clip(catalog.city_bbox)
            frame = frame[~frame.geometry.is_empty]
        keep = layer.options.get("keep_columns")
        if keep:
            # A short, stable schema for other workstreams; missing tags become empty columns.
            for column in keep:
                if column not in frame.columns:
                    frame[column] = None
            frame = frame[[*keep, frame.geometry.name]]

        out_dir.mkdir(parents=True, exist_ok=True)
        parquet = out_dir / f"{layer.key}.parquet"
        geojson = out_dir / f"{layer.key}.geojson"
        frame.to_parquet(parquet, index=False)
        geojson.write_text(frame.to_json(drop_id=True, ensure_ascii=False), encoding="utf-8")
        extra_files: dict[str, Path] = {}
        if layer.options.get("raw_json") and raw_elements is not None:
            raw_path = out_dir / f"{layer.key}.json"
            raw_path.write_text(json.dumps(_clean_elements(raw_elements, catalog, layer), ensure_ascii=False),
                                encoding="utf-8")
            extra_files["overpass_json"] = raw_path

        base = root or out_dir
        entry.update(
            status="ok",
            features=int(len(frame)),
            dropped_fields=dropped,
            crs="EPSG:4326",
            files={
                "geoparquet": {"path": _rel(parquet, base), "sha256": sha256_file(parquet)},
                "geojson": {"path": _rel(geojson, base), "sha256": sha256_file(geojson)},
                **{name: {"path": _rel(path, base), "sha256": sha256_file(path)}
                   for name, path in extra_files.items()},
            },
            warnings=["0 features in the requested area"] if len(frame) == 0 else [],
        )
    except Exception as error:  # noqa: BLE001 - any failure marks the layer unavailable
        entry.update(status="not_available", error=f"{type(error).__name__}: {error}"[:500])
    return entry


def _ingest_raster(layer: LayerSpec, catalog: Catalog, fetch: Fetch, out_dir: Path,
                   root: Path | None, entry: Entry) -> Entry:
    """Image services: one Cloud Optimized GeoTIFF instead of GeoParquet/GeoJSON."""
    try:
        path = out_dir / f"{layer.key}.tif"
        details = export_image(layer, catalog.sources[layer.source].urls[0], catalog.city_bbox, fetch, path)
        raw = details.pop("raw")
        entry["raw_sha256"] = hashlib.sha256(raw).hexdigest()
        del raw
        for key in ("value_range", "units"):
            if key in layer.options:
                entry[key] = layer.options[key]
        entry.update(
            status="ok", **details,
            files={"cog": {"path": _rel(path, root or out_dir), "sha256": sha256_file(path)}},
            warnings=[],
        )
    except Exception as error:  # noqa: BLE001 - any failure marks the layer unavailable
        entry.update(status="not_available", error=f"{type(error).__name__}: {error}"[:500])
    return entry


def _clean_elements(elements: list[dict[str, Any]], catalog: Catalog, layer: LayerSpec) -> dict[str, Any]:
    """Overpass-style JSON with personal tags removed (same rules as the GeoJSON)."""
    cleaned = []
    for element in elements:
        tags = element.get("tags") or {}
        drop = set(personal_columns(tags, catalog.privacy_patterns, layer.drop_fields))
        cleaned.append({**element, "tags": {k: v for k, v in tags.items() if k not in drop}})
    return {"elements": cleaned}


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
            if "features" in entry:
                log(f"ok   {key:30s} {entry['features']:>7} features  dropped={entry['dropped_fields']}")
            else:
                log(f"ok   {key:30s} raster {entry.get('width')}x{entry.get('height')} px")
        else:
            failures += 1
            log(f"FAIL {key:30s} {entry['error']}")
    log(f"{len(selected) - failures}/{len(selected)} layers ok")
    return 1 if failures else 0
