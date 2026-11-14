import json
from pathlib import Path

import pytest

from twin.ingest.catalog import CatalogError, load_catalog, parse_catalog

ROOT = Path(__file__).resolve().parents[1]


def test_every_layer_has_a_known_source_and_data_kind() -> None:
    catalog = load_catalog(ROOT / "config" / "ingest.yaml")
    manifest_sources = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))["sources"]
    assert len(catalog.layers) >= 30
    for layer in catalog.layers.values():
        assert layer.data_kind in {"real", "estimated", "simulated"}
        assert layer.source in catalog.sources
        assert layer.source in manifest_sources, f"{layer.key}: add '{layer.source}' to data/manifest.json"
    for feed in catalog.live_feeds.values():
        assert feed.source in manifest_sources, f"{feed.key}: add '{feed.source}' to data/manifest.json"


def test_required_challenge_02_layers_are_listed() -> None:
    catalog = load_catalog(ROOT / "config" / "ingest.yaml")
    for key in ["schools_state", "nidi", "infanzia", "hospitals", "health_care", "care_homes_osm",
                "playgrounds_osm", "unesco", "natura2000", "sitap_art136_cd", "municipi", "urban_zones",
                "census_sections"]:
        assert key in catalog.layers


def test_241_names_its_contact_fields() -> None:
    catalog = load_catalog(ROOT / "config" / "ingest.yaml")
    assert {"ref-nome", "ref-cell", "telefono", "e-mail"} <= set(catalog.layers["health_care"].drop_fields)


def test_city_bbox_comes_from_areas_yaml() -> None:
    catalog = load_catalog(ROOT / "config" / "ingest.yaml")
    assert catalog.city_bbox == pytest.approx((12.234, 41.655, 12.856, 42.141))


def test_bad_data_kind_is_rejected() -> None:
    raw = {"privacy": {"drop_field_patterns": []},
           "sources": {"s": {"protocol": "wfs", "url": "https://x"}},
           "layers": {"a": {"source": "s", "type_name": "t", "data_kind": "made_up"}}}
    with pytest.raises(CatalogError):
        parse_catalog(raw, city_bbox=(0.0, 0.0, 1.0, 1.0))


def test_unknown_source_is_rejected() -> None:
    raw = {"privacy": {"drop_field_patterns": []}, "sources": {},
           "layers": {"a": {"source": "nope", "type_name": "t", "data_kind": "real"}}}
    with pytest.raises(CatalogError):
        parse_catalog(raw, city_bbox=(0.0, 0.0, 1.0, 1.0))


def test_wfs_layer_can_ask_for_wfs_2() -> None:
    """Some Roma GeoServer views fail on WFS 1.0.0 ("variable not found in subplan target list") but serve 2.0.0."""
    from twin.ingest.static import wfs_url

    old = wfs_url("https://x/ows", "DIPPC:422_AreePC_2026")
    new = wfs_url("https://x/ows", "DIPPC:422_AreePC_2026", version="2.0.0")
    assert "version=1.0.0" in old and "typeName=DIPPC" in old
    assert "version=2.0.0" in new and "typeNames=DIPPC" in new and "srsName=EPSG%3A4326" in new


def test_layers_that_need_wfs_2_say_so_in_the_catalogue() -> None:
    catalog = load_catalog(Path("config/ingest.yaml"))
    for key in ("civil_protection_areas", "wildfire_interface"):
        assert catalog.layers[key].options.get("wfs_version") == "2.0.0"
