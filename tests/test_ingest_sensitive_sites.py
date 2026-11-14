from datetime import datetime, timezone
from pathlib import Path

import pytest

gpd = pytest.importorskip("geopandas")
from shapely.geometry import Point, box  # noqa: E402

from twin.ingest.catalog import load_catalog  # noqa: E402
from twin.ingest.sensitive_sites import OUTPUT_COLUMNS, build_sensitive_sites  # noqa: E402
from twin.ingest.static import ingest_layer  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CATALOG = load_catalog(ROOT / "config" / "ingest.yaml")
NOW = datetime(2026, 11, 13, 22, 30, tzinfo=timezone.utc)
LAYER = CATALOG.layers["sensitive_sites"]
M = 1 / 111_195.0  # about one metre in degrees of latitude


def write(folder: Path, key: str, rows: list[dict[str, object]]) -> None:
    geometries = [row.pop("geometry") for row in rows]
    gpd.GeoDataFrame(rows, geometry=geometries, crs="EPSG:4326").to_parquet(folder / f"{key}.parquet")


@pytest.fixture()
def processed(tmp_path: Path) -> Path:
    write(tmp_path, "hospitals", [{"feature_id": "Ospedali.1", "DESCRIZION": "Sant'Andrea",
                                   "geometry": Point(12.50, 41.90)}])
    write(tmp_path, "emergency_hospitals", [{"feature_id": "ps.1", "denominazione": "Sant'Andrea PS",
                                             "geometry": Point(12.50, 41.90 + 20 * M)}])
    write(tmp_path, "schools_state", [
        {"feature_id": "s.1", "denominazione": "DE AMICIS", "geometry": Point(12.48, 41.89)},
        {"feature_id": "s.2", "denominazione": "NO PLACE", "geometry": None},
    ])
    write(tmp_path, "hazardous_sites", [{"feature_id": "h.1", "denominaz": "Raffineria", "tipologia":
                                         "Stabilimenti a incidente a rischio rilevante",
                                         "geometry": Point(12.32, 41.85)}])
    write(tmp_path, "parks_municipal", [{"feature_id": "p.1", "name": "Parco Garbatella",
                                         "geometry": box(12.48, 41.86, 12.49, 41.87)}])
    write(tmp_path, "osm_sensitive_pois", [
        # duplicate of the official hospital, 40 m away: dropped
        {"osm_id": "way/1", "amenity": "hospital", "name": "Ospedale Sant'Andrea",
         "geometry": Point(12.50, 41.90 + 40 * M)},
        # a clinic the official layers do not have: kept
        {"osm_id": "node/2", "amenity": "clinic", "name": "Poliambulatorio",
         "geometry": Point(12.52, 41.91)},
        # a substation: kept as critical infrastructure
        {"osm_id": "node/3", "power": "substation", "name": None, "geometry": Point(12.45, 41.88)},
        # a school 500 m from the official one: a different school, kept
        {"osm_id": "node/4", "amenity": "school", "name": "Liceo", "geometry": Point(12.48, 41.89 + 500 * M)},
        # an untagged-for-us feature: ignored
        {"osm_id": "node/5", "amenity": "bench", "name": None, "geometry": Point(12.40, 41.80)},
    ])
    return tmp_path


def test_sites_are_merged_typed_and_deduplicated(processed: Path) -> None:
    frame, report = build_sensitive_sites(LAYER, processed)
    assert list(frame.columns) == [*OUTPUT_COLUMNS, "geometry"]
    by_id = {row.site_id: row for row in frame.itertuples()}

    assert by_id["hospitals:Ospedali.1"].category == "health"
    assert by_id["hospitals:Ospedali.1"].provenance == "official"
    assert "osm_sensitive_pois:way/1" not in by_id  # same hospital as the official record
    assert by_id["osm_sensitive_pois:node/2"].subtype == "clinic"
    assert by_id["osm_sensitive_pois:node/2"].provenance == "osm"
    assert by_id["osm_sensitive_pois:node/3"].category == "critical_infrastructure"
    assert by_id["osm_sensitive_pois:node/4"].category == "education"
    assert by_id["hazardous_sites:h.1"].category == "hazardous_industry"
    assert by_id["hazardous_sites:h.1"].subtype == "seveso_plant"  # official label mapped to a code
    assert by_id["parks_municipal:p.1"].category == "green"
    assert "osm_sensitive_pois:node/5" not in by_id
    assert set(frame["data_kind"]) == {"real"}

    assert report["dropped_no_geometry"] == 1
    assert report["dropped_duplicates"] >= 2  # OSM hospital, and the PS 20 m from the hospital
    assert report["missing_inputs"] == [k for k in report["missing_inputs"]]  # listed, not fatal


def test_missing_input_layers_do_not_fail_the_build(tmp_path: Path) -> None:
    write(tmp_path, "nidi", [{"feature_id": "n.1", "denominazione": "Nido", "geometry": Point(12.5, 41.9)}])
    frame, report = build_sensitive_sites(LAYER, tmp_path)
    assert len(frame) == 1 and frame.iloc[0]["subtype"] == "nursery"
    assert "hospitals" in report["missing_inputs"]


def test_layer_is_written_through_the_normal_ingest_path(processed: Path) -> None:
    entry = ingest_layer(LAYER, CATALOG, lambda r: b"", processed, NOW)
    assert entry["status"] == "ok", entry.get("error")
    assert entry["counts_by_category"]["health"] == 2
    assert (processed / "sensitive_sites.geojson").exists()


def test_official_registers_come_before_osm_and_keep_their_row_label(tmp_path: Path) -> None:
    write(tmp_path, "health_accredited_lazio", [
        {"facility_id": "11", "name": "CASA DI CURA ALFA", "geometry": Point(12.52, 41.91)}])
    write(tmp_path, "public_bodies_ipa", [
        {"ipa_code": "m_it", "name": "Ministero dell'Interno", "geometry": Point(12.495, 41.90),
         "body_type": "Presidenza del Consiglio dei Ministri, Ministeri e Avvocatura dello Stato",
         "geocode_quality": "street", "data_kind": "estimated"}])
    write(tmp_path, "osm_sensitive_pois", [
        {"osm_id": "node/2", "amenity": "clinic", "name": "Alfa", "geometry": Point(12.52, 41.91 + 10 * M)},
        {"osm_id": "node/9", "office": "government", "name": "Viminale",
         "geometry": Point(12.495, 41.90 + 30 * M)},
    ])
    frame, _ = build_sensitive_sites(LAYER, tmp_path)
    by_id = {row.site_id: row for row in frame.itertuples()}
    clinic = by_id["health_accredited_lazio:11"]
    assert (clinic.category, clinic.subtype, clinic.provenance) == ("health", "accredited_facility", "official")
    ministry = by_id["public_bodies_ipa:m_it"]
    assert (ministry.category, ministry.subtype, ministry.data_kind) == ("government", "ministry", "estimated")
    assert "osm_sensitive_pois:node/2" not in by_id and "osm_sensitive_pois:node/9" not in by_id


def test_identical_records_in_one_layer_are_kept_once(tmp_path: Path) -> None:
    same = {"denominazione": "IC VIA X", "geometry": Point(12.48, 41.89)}
    write(tmp_path, "schools_state", [{"feature_id": "s.1", **same}, {"feature_id": "s.2", **same},
                                      {"feature_id": "s.3", "denominazione": "LICEO Y", "geometry": Point(12.48, 41.89)}])
    frame, report = build_sensitive_sites(LAYER, tmp_path)
    assert sorted(frame["name"]) == ["IC VIA X", "LICEO Y"]  # same place, different school: both kept
    assert report["dropped_identical"] == 1
