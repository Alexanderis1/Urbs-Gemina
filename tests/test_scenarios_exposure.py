"""Population exposure: residents of census sections above a field level, baseline vs variant."""
import math
from pathlib import Path
from typing import Any

import json

import pytest

from twin.scenarios import engine, exposure
from twin.scenarios.data import FieldSample, ScenarioData

LON, LAT = 12.4823, 41.8960
M_PER_DEG_LAT = 111_195.0
M_PER_DEG_LON = M_PER_DEG_LAT * math.cos(math.radians(LAT))


def section(east_m: float, sid: str, pop: int, side_m: float = 50.0) -> dict[str, Any]:
    cx, h = LON + east_m / M_PER_DEG_LON, side_m / 2
    dx, dy = h / M_PER_DEG_LON, h / M_PER_DEG_LAT
    ring = [[cx - dx, LAT - dy], [cx + dx, LAT - dy], [cx + dx, LAT + dy], [cx - dx, LAT + dy], [cx - dx, LAT - dy]]
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"sez_id": sid, "residents": pop, "children_0_14": pop // 10,
                           "municipio": 1, "zone": "1A", "phone": "drop me"}}


CENSUS = {"type": "FeatureCollection", "features": [section(0.0, "near", 120), section(250.0, "far", 300)]}
CHANGE = {"action": "add", "site": {"lon": LON, "lat": LAT, "height_m": 6.0}, "eirp_w": 5000.0}


def data() -> ScenarioData:
    return ScenarioData(baseline_field=lambda lon, lat: FieldSample(1.0, 4.0), baseline_kind="real", census=CENSUS)


def test_residents_near_a_strong_antenna_are_counted(tmp_path: Path) -> None:
    out = engine.run("population_exposure", "city", CHANGE, data=data(), cache_dir=tmp_path)
    result = out["result"]
    assert result["baseline"]["residents_flagged_attention"] == 0
    assert result["variant"]["residents_flagged_attention"] == 120
    assert result["variant"]["children_0_14_flagged_attention"] == 12
    assert result["residents_total"] == 420
    assert out["data_kinds"]["census"] == "real"


def test_only_aggregates_leave_the_tool(tmp_path: Path) -> None:
    out = engine.run("population_exposure", "city", CHANGE, data=data(), cache_dir=tmp_path)
    text = str(out)
    assert "drop me" not in text
    for row in out["result"]["sections"]:
        assert set(row) <= {"sez_id", "residents", "children_0_14", "baseline_p50", "variant_p50",
                            "baseline_p_exceed_attention", "variant_p_exceed_attention"}


def test_missing_census_is_not_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exposure, "census_path", lambda: tmp_path / "missing.geojson")
    out = engine.run("population_exposure", "city", CHANGE, data=ScenarioData(), cache_dir=tmp_path)
    assert out["status"] == "not_available"
    assert "census" in out["reason"].lower()
    assert not list(tmp_path.glob("*.json"))


def test_census_file_is_read_when_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "census_sections.geojson"
    path.write_text(json.dumps(CENSUS), encoding="utf-8")
    monkeypatch.setattr(exposure, "census_path", lambda: path)
    out = engine.run("population_exposure", "city", CHANGE, data=ScenarioData(), cache_dir=tmp_path / "c")
    assert out["status"] == "ok"
    assert out["result"]["residents_total"] == 420
