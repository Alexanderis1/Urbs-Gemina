"""Chemical plume: Gaussian dispersion with an ensemble, thresholds from config/thresholds.yaml."""
from pathlib import Path

import numpy as np
import pytest

from twin.scenarios import engine, layers
from twin.scenarios.plume import concentration

SITE = {"lon": 12.3361, "lat": 41.9577}


@pytest.fixture(autouse=True)
def no_shared_layers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(layers, "search_dirs", lambda: [tmp_path / "none"])


def test_concentration_falls_with_distance_and_off_axis() -> None:
    x = np.array([100.0, 500.0, 2000.0])
    on_axis = concentration(1000.0, 3.0, "D", x, np.zeros(3), 2.0)
    assert on_axis[0] > on_axis[1] > on_axis[2] > 0
    off = concentration(1000.0, 3.0, "D", np.array([500.0]), np.array([300.0]), 2.0)
    assert off[0] < on_axis[1]
    upwind = concentration(1000.0, 3.0, "D", np.array([-500.0]), np.array([0.0]), 2.0)
    assert upwind[0] == 0.0


def test_plume_goes_downwind(tmp_path: Path) -> None:
    change = {**SITE, "substance": "ammonia", "release_kg_s": 5, "wind": {"speed_ms": 3, "from_deg": 270}}
    out = engine.run("chemical_plume", "city", change, cache_dir=tmp_path)
    zones = out["result"]["zones"]
    assert out["status"] == "ok"
    assert zones["aegl1"]["area_km2"]["possible"] > zones["aegl2"]["area_km2"]["possible"] > 0
    ring = zones["aegl1"]["footprint_possible"]["coordinates"][0][0]
    mean_lon = sum(p[0] for p in ring) / len(ring)
    assert mean_lon > SITE["lon"]  # wind from the west carries the gas east
    assert zones["idlh"]["threshold_mg_m3"] == 210
    assert out["data_kinds"]["release"] == "hypothetical"


def test_bigger_release_reaches_further(tmp_path: Path) -> None:
    def reach(q: float) -> float:
        change = {**SITE, "substance": "chlorine", "release_kg_s": q, "wind": {"speed_ms": 4, "from_deg": 0}}
        return float(engine.run("chemical_plume", "city", change, cache_dir=tmp_path)
                     ["result"]["zones"]["aegl2"]["max_distance_m"]["p50"])
    assert reach(10.0) > reach(1.0) > 0


def test_unknown_substance_and_missing_wind() -> None:
    with pytest.raises(ValueError, match="substance"):
        engine.run("chemical_plume", "city", {**SITE, "substance": "unobtainium", "wind": {"speed_ms": 3, "from_deg": 0}},
                   use_cache=False)
    out = engine.run("chemical_plume", "city", {**SITE, "wind": "forecast"}, use_cache=False)
    assert out["status"] == "not_available"
