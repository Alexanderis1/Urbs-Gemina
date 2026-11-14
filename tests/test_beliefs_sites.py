"""Layer values at sensitive sites (schools, hospitals...), with a range and exceedance chance."""
import json
from datetime import datetime, timezone
from pathlib import Path

from twin.beliefs.config import load_specs
from twin.beliefs.grid import cells_in_bbox
from twin.beliefs.layer import assimilate, prior_layer
from twin.beliefs.sites import site_values
from twin.providers.base import Observation

T0 = datetime(2026, 11, 14, 8, 0, tzinfo=timezone.utc)
WINDOW = (12.46, 41.88, 12.50, 41.91)


def sites(tmp_path: Path) -> Path:
    poly = [[[12.464, 41.884], [12.466, 41.884], [12.466, 41.886], [12.464, 41.886], [12.464, 41.884]]]
    feats = [
        {"type": "Feature", "properties": {"site_id": "s1", "category": "education", "subtype": "school", "name": "A"},
         "geometry": {"type": "Point", "coordinates": [12.48, 41.895]}},
        {"type": "Feature", "properties": {"site_id": "h1", "category": "health", "subtype": "hospital", "name": "B"},
         "geometry": {"type": "MultiPolygon", "coordinates": [poly]}},
        {"type": "Feature", "properties": {"site_id": "g1", "category": "green", "subtype": "park", "name": "C"},
         "geometry": {"type": "Point", "coordinates": [12.49, 41.90]}},
        {"type": "Feature", "properties": {"site_id": "x1", "category": "education", "subtype": "school", "name": "Far"},
         "geometry": {"type": "Point", "coordinates": [13.5, 42.5]}},
    ]
    path = tmp_path / "sites.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return path


def test_values_at_sites_sorted_by_risk(tmp_path: Path) -> None:
    cells = cells_in_bbox(WINDOW, 9)
    layer = prior_layer(load_specs()["air_no2"], cells, T0)
    layer = assimilate(layer, [Observation("e", "AirQualityObserved", 12.48, 41.895, T0, {"no2": 70.0}, {"no2": 2.0}, "eea_hourly", False)])
    out = site_values(layer, sites(tmp_path), threshold=40.0, categories=("education", "health"))
    rows = out["result"]["sites"]
    assert [r["site_id"] for r in rows] == ["s1", "h1"]  # park excluded by category, far site outside the layer
    school = rows[0]
    assert school["p_exceed"] > 0.95 and school["p5"] < school["p50"] < school["p95"]
    assert rows[1]["p_exceed"] < school["p_exceed"]
    assert out["result"]["summary"]["education"]["sites"] == 1
    assert any("outside" in w for w in out["warnings"])
