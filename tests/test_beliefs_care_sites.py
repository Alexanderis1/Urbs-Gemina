"""Air quality at hospitals and care homes: worst first, with older residents nearby."""
import json
from datetime import datetime, timezone
from pathlib import Path

from twin.beliefs.config import load_specs
from twin.beliefs.grid import cell_of, cells_in_bbox
from twin.beliefs.layer import assimilate, prior_layer
from twin.beliefs.schools import care_sites_to_check
from twin.providers.base import Observation

T0 = datetime(2026, 11, 14, 8, 0, tzinfo=timezone.utc)
WINDOW = (12.40, 41.85, 12.55, 41.95)
NEAR = (12.48, 41.895)
FAR = (12.42, 41.86)


def sites(tmp_path: Path) -> Path:
    feats = [{"type": "Feature", "properties": {"site_id": sid, "category": cat, "subtype": sub, "name": sid},
              "geometry": {"type": "Point", "coordinates": list(pt)}}
             for sid, cat, sub, pt in (("hosp", "health", "hospital", NEAR), ("home", "health", "care_home", FAR),
                                       ("school", "education", "school", NEAR))]
    path = tmp_path / "sites.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return path


def test_care_sites_worst_first_with_elderly(tmp_path: Path) -> None:
    cells = cells_in_bbox(WINDOW, 9)
    no2 = assimilate(prior_layer(load_specs()["air_no2"], cells, T0),
                     [Observation("e", "AirQualityObserved", *NEAR, T0, {"no2": 180.0}, {"no2": 3.0}, "eea_hourly", False)])
    census = {cell_of(*NEAR, 9): {"residents": 900, "elderly_65_plus": 250}}
    out = care_sites_to_check({"air_no2": (no2, 200.0)}, sites(tmp_path), census)
    rows = out["result"]["sites"]
    assert [r["site_id"] for r in rows] == ["hosp", "home"]  # the school is not a care site
    assert rows[0]["subtype"] == "hospital"
    assert rows[0]["elderly_65_plus_in_cell"] == 250
    assert rows[1]["elderly_65_plus_in_cell"] is None
    assert out["result"]["sites_checked"] == 2
