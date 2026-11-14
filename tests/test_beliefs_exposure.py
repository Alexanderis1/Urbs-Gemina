"""People exposed to a layer above a threshold, and sensors that disagree with their neighbours."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from twin.beliefs.calibration import sensor_health
from twin.beliefs.config import load_specs
from twin.beliefs.crowds import census_per_cell
from twin.beliefs.exposure import exposure
from twin.beliefs.grid import cell_boundary, cell_of, cells_in_bbox, local_xy_km
from twin.beliefs.layer import assimilate, prior_layer
from twin.providers.base import Observation

T0 = datetime(2026, 11, 13, 8, 0, tzinfo=timezone.utc)
WINDOW = (12.46, 41.88, 12.50, 41.91)
A = (12.48, 41.895)
B = (12.465, 41.884)


def census_file(tmp_path: Path) -> Path:
    feats = []
    for (lon, lat), res, kids, mun in ((A, 1000, 150, 1), (B, 400, 40, 2)):
        ring = [list(p) for p in cell_boundary(cell_of(lon, lat, 9))]
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
                      "properties": {"residents": res, "children_0_14": kids, "municipio": mun}})
    path = tmp_path / "census.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return path


def test_census_per_cell_keeps_children_and_municipio(tmp_path: Path) -> None:
    c = census_per_cell(census_file(tmp_path), cells_in_bbox(WINDOW, 9))
    assert c[cell_of(*A, 9)] == {"residents": 1000, "children_0_14": 150, "municipio": "1"}


def test_people_above_threshold_with_a_range(tmp_path: Path) -> None:
    spec = load_specs()["air_no2"]
    cells = cells_in_bbox(WINDOW, 9)
    layer = prior_layer(spec, cells, T0)
    hot = Observation("s", "AirQualityObserved", *A, T0, {"no2": 80.0}, {"no2": 1.0}, "eea_hourly", False)
    layer = assimilate(layer, [hot])
    out = exposure(layer, census_per_cell(census_file(tmp_path), cells), threshold=40.0)
    assert out["status"] == "ok"
    by_mun = {g["group"]: g for g in out["result"]["groups"]}
    m1 = by_mun["1"]
    assert m1["residents"] == 1000
    assert m1["people_above"]["expected"] == pytest.approx(1000, rel=0.01)
    assert m1["children_above"]["expected"] == pytest.approx(150, rel=0.01)
    m2 = by_mun["2"]
    # Far from the station: near the prior (30), so a minority chance of being above 40.
    assert 0 < m2["people_above"]["expected"] < 400
    assert m2["people_above"]["low"] <= m2["people_above"]["expected"] <= m2["people_above"]["high"]
    assert m2["mean_exposure"]["value"] < m1["mean_exposure"]["value"]
    city = out["result"]["city"]
    assert city["residents"] == 1400
    assert out["inputs"]["threshold"] == 40.0
    assert any("census" in w for w in out["warnings"])


def test_a_broken_station_is_flagged() -> None:
    spec = load_specs()["air_no2"]
    rng = np.random.default_rng(3)
    sites = [(float(rng.uniform(12.40, 12.60)), float(rng.uniform(41.82, 41.98))) for _ in range(12)]
    xy = np.array(local_xy_km(sites))
    dist = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(axis=2))
    chol = np.linalg.cholesky(225.0 * np.exp(-dist / spec.correlation_length_km) + 1e-9 * np.eye(12))
    obs = []
    for h in range(6):
        field = 30.0 + chol @ rng.standard_normal(12)
        for i, (lon, lat) in enumerate(sites):
            value = float(field[i] + rng.normal(0, 2.0)) + (90.0 if i == 4 else 0.0)  # station 4 reads far too high
            obs.append(Observation(f"st{i}", "AirQualityObserved", lon, lat, T0 + timedelta(hours=h),
                                   {"no2": value}, {"no2": 2.0}, "eea_hourly", False))
    report = sensor_health(spec, obs)
    flagged = [s["entity_id"] for s in report if s["flag"]]
    assert flagged == ["st4"]
    st4 = next(s for s in report if s["entity_id"] == "st4")
    assert st4["median_abs_z"] > 3
    assert st4["typical_offset"] > 40


def test_check_sensors_reads_its_settings_from_config() -> None:
    from twin.beliefs.api import check_sensors

    assert check_sensors("air_no2", []) == []
