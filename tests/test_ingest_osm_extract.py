import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

osmium = pytest.importorskip("osmium")
gpd = pytest.importorskip("geopandas")

from twin.ingest.catalog import load_catalog  # noqa: E402
from twin.ingest.http import HttpRequest  # noqa: E402
from twin.ingest.osm_extract import parse_selector  # noqa: E402
from twin.ingest.static import ingest_layer  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CATALOG = load_catalog(ROOT / "config" / "ingest.yaml")
NOW = datetime(2026, 11, 13, 21, 0, tzinfo=timezone.utc)

OSM_XML = """<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="test">
  <node id="1" version="1" lat="41.90" lon="12.50"><tag k="man_made" v="mast"/><tag k="tower:type" v="communication"/><tag k="phone" v="06"/></node>
  <node id="2" version="1" lat="41.90" lon="12.51"><tag k="man_made" v="mast"/><tag k="tower:type" v="lighting"/></node>
  <node id="3" version="1" lat="45.00" lon="9.00"><tag k="man_made" v="mast"/><tag k="tower:type" v="communication"/></node>
  <node id="10" version="1" lat="41.80" lon="12.40"/>
  <node id="11" version="1" lat="41.80" lon="12.42"/>
  <node id="12" version="1" lat="41.82" lon="12.42"/>
  <node id="13" version="1" lat="41.82" lon="12.40"/>
  <way id="20" version="1"><nd ref="10"/><nd ref="11"/><nd ref="12"/><nd ref="13"/><nd ref="10"/>
    <tag k="leisure" v="pitch"/><tag k="sport" v="soccer"/><tag k="email" v="x@y.it"/></way>
</osm>
"""


def test_selector_parsing() -> None:
    assert parse_selector('nwr["man_made"="mast"]["tower:type"="communication"]') == \
        [("man_made", "mast"), ("tower:type", "communication")]


def fetch_xml(tmp_path: Path) -> object:
    def fetch(request: HttpRequest) -> bytes:
        assert request.url.endswith(".osm.pbf")
        return OSM_XML.encode()
    return fetch


def test_masts_come_from_the_extract_and_are_clipped(tmp_path: Path) -> None:
    entry = ingest_layer(CATALOG.layers["masts_osm"], CATALOG, fetch_xml(tmp_path), tmp_path, NOW)  # type: ignore[arg-type]
    assert entry["status"] == "ok", entry.get("error")
    assert entry["features"] == 1  # lighting mast and the Milan mast are excluded
    assert entry["dropped_fields"] == ["phone"]


def test_ways_become_centre_points_in_overpass_json(tmp_path: Path) -> None:
    entry = ingest_layer(CATALOG.layers["osm_sports"], CATALOG, fetch_xml(tmp_path), tmp_path, NOW)  # type: ignore[arg-type]
    assert entry["status"] == "ok", entry.get("error")
    raw = json.loads((tmp_path / "osm_sports.json").read_text(encoding="utf-8"))
    (way,) = raw["elements"]
    assert way["type"] == "way" and way["id"] == 20
    assert way["center"]["lat"] == pytest.approx(41.81, abs=1e-6)
    assert way["center"]["lon"] == pytest.approx(12.41, abs=1e-6)
    assert way["tags"] == {"leisure": "pitch", "sport": "soccer"}


def test_key_only_conditions_are_parsed() -> None:
    assert parse_selector('way["highway"]["tunnel"="yes"]') == [("highway", None), ("tunnel", "yes")]


LINES_XML = """<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="test">
  <node id="1" version="1" lat="41.90" lon="12.50"/>
  <node id="2" version="1" lat="41.90" lon="12.51"/>
  <node id="3" version="1" lat="41.91" lon="12.52"/>
  <way id="30" version="1"><nd ref="1"/><nd ref="2"/>
    <tag k="highway" v="primary"/><tag k="tunnel" v="yes"/><tag k="name" v="Sottopasso Uno"/><tag k="surface" v="asphalt"/></way>
  <way id="31" version="1"><nd ref="2"/><nd ref="3"/><tag k="railway" v="rail"/><tag k="tunnel" v="yes"/></way>
  <way id="32" version="1"><nd ref="1"/><nd ref="3"/><tag k="highway" v="residential"/><tag k="layer" v="-1"/></way>
  <way id="40" version="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="waterway" v="river"/><tag k="name" v="Tevere"/></way>
</osm>
"""


def test_underpasses_and_rivers_are_lines_with_few_columns(tmp_path: Path) -> None:
    def fetch(request: HttpRequest) -> bytes:
        return LINES_XML.encode()

    entry = ingest_layer(CATALOG.layers["road_underpasses_osm"], CATALOG, fetch, tmp_path, NOW)
    assert entry["status"] == "ok", entry.get("error")
    frame = gpd.read_parquet(tmp_path / "road_underpasses_osm.parquet")
    assert sorted(frame["osm_id"]) == ["way/30", "way/32"]  # the railway tunnel is not a road
    assert set(frame.geom_type) == {"LineString"}
    assert set(frame.columns) == {"osm_id", "name", "highway", "tunnel", "layer", "geometry"}

    entry = ingest_layer(CATALOG.layers["rivers_osm"], CATALOG, fetch, tmp_path, NOW)
    assert entry["status"] == "ok", entry.get("error")
    rivers = gpd.read_parquet(tmp_path / "rivers_osm.parquet")
    (river,) = rivers.itertuples()
    assert river.name == "Tevere" and river.waterway == "river"
    assert len(river.geometry.coords) == 3
