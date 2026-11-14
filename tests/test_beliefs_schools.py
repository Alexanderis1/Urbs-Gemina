"""Schools to check: every pollutant at every school, worst first, with children nearby."""
import json
from datetime import datetime, timezone
from pathlib import Path

from twin.beliefs.config import load_specs
from twin.beliefs.grid import cell_of, cells_in_bbox
from twin.beliefs.layer import assimilate, prior_layer
from twin.beliefs.schools import schools_to_check
from twin.providers.base import Observation

T0 = datetime(2026, 11, 14, 8, 0, tzinfo=timezone.utc)
WINDOW = (12.40, 41.85, 12.55, 41.95)
NEAR = (12.48, 41.895)
FAR = (12.42, 41.86)


def sites(tmp_path: Path) -> Path:
    feats = [{"type": "Feature", "properties": {"site_id": sid, "category": cat, "subtype": "school", "name": sid},
              "geometry": {"type": "Point", "coordinates": list(pt)}}
             for sid, cat, pt in (("near", "education", NEAR), ("far", "education", FAR), ("hosp", "health", NEAR))]
    path = tmp_path / "sites.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return path


def test_worst_school_first_with_reason_and_children(tmp_path: Path) -> None:
    cells = cells_in_bbox(WINDOW, 9)
    no2 = assimilate(prior_layer(load_specs()["air_no2"], cells, T0),
                     [Observation("e", "AirQualityObserved", *NEAR, T0, {"no2": 180.0}, {"no2": 3.0}, "eea_hourly", False)])
    pm10 = prior_layer(load_specs()["air_pm10"], cells, T0)
    census = {cell_of(*NEAR, 9): {"residents": 900, "children_0_14": 120}}
    out = schools_to_check({"air_no2": (no2, 200.0), "air_pm10": (pm10, 50.0)}, sites(tmp_path), census, top=10)
    rows = out["result"]["schools"]
    assert [r["site_id"] for r in rows] == ["near", "far"]  # hospital is not a school
    first = rows[0]
    assert first["worst"] == "air_no2"
    assert first["pollutants"]["air_no2"]["share_of_limit"] > 0.8
    assert first["children_0_14_in_cell"] == 120
    assert rows[1]["children_0_14_in_cell"] is None
    assert out["inputs"]["thresholds"] == {"air_no2": 200.0, "air_pm10": 50.0}
    assert any("averaging" in w for w in out["warnings"])


def test_top_limits_the_list(tmp_path: Path) -> None:
    cells = cells_in_bbox(WINDOW, 9)
    pm25 = prior_layer(load_specs()["air_pm25"], cells, T0)
    out = schools_to_check({"air_pm25": (pm25, 25.0)}, sites(tmp_path), {}, top=1)
    assert len(out["result"]["schools"]) == 1
    assert out["result"]["schools_checked"] == 2
