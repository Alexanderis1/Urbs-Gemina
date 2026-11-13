import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

gpd = pytest.importorskip("geopandas")

from twin.ingest.catalog import load_catalog  # noqa: E402
from twin.ingest.http import HttpRequest  # noqa: E402
from twin.ingest.manifest import record_snapshots  # noqa: E402
from twin.ingest.static import ingest_layer, overpass_query, overpass_to_geojson, run  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CATALOG = load_catalog(ROOT / "config" / "ingest.yaml")
NOW = datetime(2026, 11, 13, 20, 0, tzinfo=timezone.utc)

HEALTH = {
    "type": "FeatureCollection",
    "features": [
        {"type": "Feature", "id": "241.1",
         "geometry": {"type": "Point", "coordinates": [12.4823, 41.8960]},
         "properties": {"nome": "Casa della Salute", "ref-nome": "Mario Rossi", "ref-cell": "3331234567",
                        "telefono": "06123456", "e-mail": "a@b.it", "municipio": "I"}},
        {"type": "Feature", "id": "241.2",
         "geometry": {"type": "Point", "coordinates": [12.50, 41.90]},
         "properties": {"nome": "Poliambulatorio", "ref-nome": "Anna Bianchi", "municipio": "II"}},
    ],
}
HEALTH_BYTES = json.dumps(HEALTH).encode()


def fake_wfs(request: HttpRequest) -> bytes:
    query = parse_qs(urlparse(request.url).query)
    if query["typeName"] == ["DIPPC:241_ServiziSanitarieAssistenziali"]:
        assert query["srsName"] == ["EPSG:4326"]
        return HEALTH_BYTES
    # GeoServer answers an unknown layer with an XML exception and HTTP 200.
    return b'<?xml version="1.0"?><ServiceExceptionReport><ServiceException>Unknown</ServiceException></ServiceExceptionReport>'


def test_ingest_drops_contacts_and_writes_geoparquet(tmp_path: Path) -> None:
    entry = ingest_layer(CATALOG.layers["health_care"], CATALOG, fake_wfs, tmp_path, NOW)
    assert entry["status"] == "ok"
    assert entry["features"] == 2
    assert entry["data_kind"] == "real" and entry["synthetic"] is False
    assert entry["raw_sha256"] == hashlib.sha256(HEALTH_BYTES).hexdigest()
    assert entry["dropped_fields"] == ["e-mail", "ref-cell", "ref-nome", "telefono"]

    parquet = tmp_path / "health_care.parquet"
    frame = gpd.read_parquet(parquet)
    assert set(frame.columns) == {"feature_id", "nome", "municipio", "geometry"}
    assert list(frame["feature_id"]) == ["241.1", "241.2"]
    assert frame.crs.to_epsg() == 4326
    assert entry["files"]["geoparquet"]["sha256"] == hashlib.sha256(parquet.read_bytes()).hexdigest()

    geojson = tmp_path / "health_care.geojson"
    text = geojson.read_text(encoding="utf-8")
    for secret in ["Mario Rossi", "Anna Bianchi", "3331234567", "a@b.it", "06123456"]:
        assert secret not in text
        assert secret.encode() not in parquet.read_bytes()


def test_failed_layer_is_marked_not_available(tmp_path: Path) -> None:
    entry = ingest_layer(CATALOG.layers["hospitals"], CATALOG, fake_wfs, tmp_path, NOW)
    assert entry["status"] == "not_available"
    assert "error" in entry and not (tmp_path / "hospitals.parquet").exists()


def test_regional_layers_are_clipped_to_the_city_bbox(tmp_path: Path) -> None:
    seen: list[str] = []

    def fetch(request: HttpRequest) -> bytes:
        seen.append(request.url)
        return json.dumps({"type": "FeatureCollection", "features": []}).encode()

    entry = ingest_layer(CATALOG.layers["natura2000"], CATALOG, fetch, tmp_path, NOW)
    query = parse_qs(urlparse(seen[0]).query)
    assert query["bbox"] == ["12.234000,41.655000,12.856000,42.141000,EPSG:4326"]
    assert entry["status"] == "ok" and entry["features"] == 0
    assert entry["warnings"] == ["0 features in the requested area"]


def test_overpass_query_lists_every_selector_with_bbox() -> None:
    query = overpass_query(['nwr["leisure"="playground"]'], (12.0, 41.0, 13.0, 42.0))
    assert query.startswith("[out:json]")
    assert 'nwr["leisure"="playground"](41.0,12.0,42.0,13.0);' in query
    assert query.rstrip().endswith("out center tags;")


def test_overpass_elements_become_points_without_contacts() -> None:
    payload = {"elements": [
        {"type": "node", "id": 1, "lat": 41.9, "lon": 12.5, "tags": {"leisure": "playground", "phone": "06"}},
        {"type": "way", "id": 2, "center": {"lat": 41.8, "lon": 12.4}, "tags": {"amenity": "nursing_home"}},
        {"type": "relation", "id": 3, "tags": {"amenity": "nursing_home"}},  # no centre: skipped
    ]}
    collection = overpass_to_geojson(payload)
    assert [f["properties"]["osm_id"] for f in collection["features"]] == ["node/1", "way/2"]
    assert collection["features"][1]["geometry"] == {"type": "Point", "coordinates": [12.4, 41.8]}


def test_overpass_falls_back_to_the_next_mirror(tmp_path: Path) -> None:
    calls: list[str] = []

    def fetch(request: HttpRequest) -> bytes:
        calls.append(request.url)
        if len(calls) == 1:
            raise ConnectionResetError("reset")
        assert request.body is not None and b"playground" in request.body
        return json.dumps({"elements": [{"type": "node", "id": 9, "lat": 41.9, "lon": 12.5,
                                         "tags": {"leisure": "playground"}}]}).encode()

    entry = ingest_layer(CATALOG.layers["playgrounds_osm"], CATALOG, fetch, tmp_path, NOW)
    assert entry["status"] == "ok" and entry["features"] == 1
    assert len(calls) == 2 and entry["request_url"] == calls[1]


def test_manifest_keeps_sources_and_other_snapshots(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sources": {"a": {"kind": "real"}},
                                     "snapshots": {"other": {"status": "ok"}}}), encoding="utf-8")
    record_snapshots(manifest, {"health_care": {"status": "ok", "features": 2}})
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["sources"] == {"a": {"kind": "real"}}
    assert data["snapshots"] == {"other": {"status": "ok"}, "health_care": {"status": "ok", "features": 2}}


def test_run_records_every_layer_and_reports_failures(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sources": {}}), encoding="utf-8")
    code = run(["health_care", "hospitals"], CATALOG, fake_wfs, tmp_path / "processed", manifest, root=tmp_path, now=NOW)
    snapshots = json.loads(manifest.read_text(encoding="utf-8"))["snapshots"]
    assert code == 1
    assert snapshots["health_care"]["status"] == "ok"
    assert snapshots["health_care"]["files"]["geoparquet"]["path"] == "processed/health_care.parquet"
    assert snapshots["hospitals"]["status"] == "not_available"


def test_run_rejects_unknown_keys(tmp_path: Path) -> None:
    assert run(["nope"], CATALOG, fake_wfs, tmp_path, tmp_path / "m.json", root=tmp_path, now=NOW) == 2


def test_mixed_2d_and_3d_coordinates_are_flattened(tmp_path: Path) -> None:
    # REGLAZ:tavola_a_paesaggi mixes [x, y] and [x, y, 0] inside one ring.
    ring = [[12.50, 41.90, 0], [12.51, 41.90], [12.51, 41.91, 0], [12.50, 41.90, 0]]
    collection = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": "p.1", "properties": {"paesaggi": "Acqua"},
         "geometry": {"type": "MultiPolygon", "coordinates": [[ring]]}}]}
    entry = ingest_layer(CATALOG.layers["ptpr_paesaggi_roma"], CATALOG,
                         lambda r: json.dumps(collection).encode(), tmp_path, NOW)
    assert entry["status"] == "ok", entry.get("error")
    frame = gpd.read_parquet(tmp_path / "ptpr_paesaggi_roma.parquet")
    assert not frame.geometry.iloc[0].has_z
