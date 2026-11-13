from __future__ import annotations

import json
from pathlib import Path

from tests.sports_fixtures import geoserver_sports, osm_elements
from twin.modules.sports.pipeline import build, overpass_query


def test_overpass_query_covers_sport_places() -> None:
    q = overpass_query()
    assert 'nwr["leisure"="sports_centre"]' in q and "out center tags" in q


def test_build_merges_enriches_confirms_and_reports_missing(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    raw.mkdir()
    (raw / "sports_municipal.geojson").write_text(json.dumps(geoserver_sports()), encoding="utf-8")
    (raw / "osm_sports.json").write_text(json.dumps(osm_elements()), encoding="utf-8")
    (raw / "sports_d30.csv").write_text("NOME;MUNICIPIO\nPiscina Comunale Quadraro;7\n", encoding="utf-8")
    web = raw / "sports_web"
    web.mkdir()
    (web / "scout_VII.json").write_text(json.dumps({"retrieved_at": "2026-11-13", "candidates": [
        {"name": "Palestra IC Anagni", "municipio": "VII", "source_url": "https://x.example/a", "confidence": 0.8,
         "disciplines": ["pallavolo"]}]}), encoding="utf-8")

    first = build(raw=raw, out=out, geocoder=None)
    assert first["sources"]["roma_pools"]["status"] == "not_available"
    assert first["sources"]["roma_sports_municipal"]["records"] == 3
    layer = json.loads((out / "facilities.geojson").read_text(encoding="utf-8"))
    bern = next(f for f in layer["features"] if f["properties"]["name"].endswith("Bernardini"))
    fid = bern["id"]

    (web / f"enrich_{fid}.json").write_text(json.dumps({"facility_id": fid, "retrieved_at": "2026-11-13", "hours": {
        "value": "9-22", "source_url": "https://x.example/b", "confidence": 0.9}}), encoding="utf-8")
    (raw / "sports_manager_updates.jsonl").write_text(json.dumps({
        "facility_id": fid, "field": "disciplines", "value": ["calcio", "padel"], "account_ref": "org:asd",
        "confirmed_at": "2026-11-14T09:00:00Z"}) + "\n", encoding="utf-8")
    second = build(raw=raw, out=out, geocoder=None)
    assert second["manager_updates_applied"] == 1
    layer = json.loads((out / "facilities.geojson").read_text(encoding="utf-8"))
    bern = next(f for f in layer["features"] if f["id"] == fid)
    assert bern["properties"]["disciplines"] == ["football", "padel"]
    assert bern["properties"]["fields"]["hours"]["label"] == "from the web, unverified"
    assert any("IC Anagni" in f["properties"]["name"] for f in layer["features"])


def test_load_facilities_round_trips(tmp_path: Path) -> None:
    from twin.modules.sports.config import load_config
    from twin.modules.sports.matching import build_facilities
    from twin.modules.sports.pipeline import load_facilities
    from twin.modules.sports.sources import from_geoserver_sports

    facilities, _ = build_facilities(from_geoserver_sports(geoserver_sports(), load_config(), "x"), load_config())
    path = tmp_path / "f.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [f.to_feature() for f in facilities]}))
    loaded = load_facilities(path)
    assert [f.to_feature() for f in loaded] == [f.to_feature() for f in facilities]


def test_geocoding_locates_house_matches_only_and_caches(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    (raw / "sports_web").mkdir(parents=True)
    (raw / "sports_web" / "scout_VII.json").write_text(json.dumps({"retrieved_at": "2026-11-13", "candidates": [
        {"name": "IC Mommsen Primaria Verdi", "address": "Via Gela, 22", "municipio": "VII",
         "source_url": "https://x.example/a", "confidence": 0.9, "disciplines": ["judo"]},
        {"name": "Campo Vago", "address": "Via Lunga", "municipio": "VII",
         "source_url": "https://x.example/b", "confidence": 0.9}]}), encoding="utf-8")
    calls: list[str] = []

    def fake(text: str) -> dict[str, object]:
        calls.append(text)
        precise = "Gela" in text
        return {"status": "ok", "run_id": "r" * 64, "result": {
            "lon": 12.53, "lat": 41.87, "precision": "house" if precise else "street", "label": text}}

    summary = build(raw=raw, out=out, geocoder=fake)
    assert summary["sources"]["geocoding"] == {"to_geocode": 2, "located": 1}
    layer = json.loads((out / "facilities.geojson").read_text(encoding="utf-8"))
    located = [f for f in layer["features"] if f["geometry"]]
    assert len(located) == 1 and "geocoded" in located[0]["properties"]["extra"]
    build(raw=raw, out=out, geocoder=fake)
    assert len(calls) == 2  # second build answered from the cache
