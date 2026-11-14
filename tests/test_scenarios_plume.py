"""Chemical plume: Gaussian dispersion with an ensemble, thresholds from config/thresholds.yaml."""
from pathlib import Path

import numpy as np
import pytest

from twin.scenarios import engine, layers
from twin.scenarios.plume import concentration, dense_centreline, dense_half_width, is_dense

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


def test_plume_conserves_mass_across_the_wind() -> None:
    """Ground release: integral of C over y at ground = Q sqrt(2/pi) / (u sigma_z) (Briggs urban, class D)."""
    import math

    import numpy as np

    from twin.scenarios.plume import concentration

    q, u, x = 1000.0, 3.0, 800.0
    y = np.linspace(-3000, 3000, 60001)
    c = concentration(q, u, "D", np.full_like(y, x), y, 0.0)
    sz = 0.14 * x * (1 + 0.0003 * x) ** -0.5
    expected = q * math.sqrt(2 / math.pi) / (u * sz)
    assert float(np.trapezoid(c, y)) == pytest.approx(expected, rel=1e-4)
    # centreline value against the textbook formula Q / (pi u sy sz)
    sy = 0.16 * x * (1 + 0.0004 * x) ** -0.5
    assert float(c[30000]) == pytest.approx(q / (math.pi * u * sy * sz), rel=1e-9)


def test_dense_gas_is_flagged(tmp_path: Path) -> None:
    out = engine.run("chemical_plume", "city", {"lon": 12.48, "lat": 41.90, "substance": "chlorine",
                                                "release_kg_s": 1.0, "wind": {"speed_ms": 3, "from_deg": 270}},
                     cache_dir=tmp_path)
    assert any("heavier than air" in w for w in out["warnings"])
    assert out["result"]["model"] == "gaussian_plume_briggs_urban+britter_mcquaid_dense"


def test_britter_mcquaid_centreline_follows_the_workbook() -> None:
    """Continuous dense plume (Britter & McQuaid 1988; CCPS fits): ratio to the source concentration."""
    rho_cl2, u = 2.99, 3.0
    q0 = 5.0 / rho_cl2  # m3/s of pure gas
    d = (q0 / u) ** 0.5
    near = dense_centreline(q0, rho_cl2, u, np.array([0.0, 10 * d, 30 * d]))
    assert near[0] == pytest.approx(1.0)
    assert near[2] == pytest.approx(306 / (306 + 900), rel=1e-6)  # near-field formula up to x/D = 30
    g0 = 9.81 * (rho_cl2 - 1.2) / 1.2
    alpha = 0.2 * np.log10(g0 ** 2 * q0 / u ** 5)
    assert -0.14 < alpha <= 1.0  # chlorine at 5 kg/s, 3 m/s sits in the workbook's upper alpha band
    x01 = d * 10 ** (-0.50 * alpha + 1.78)  # workbook point for Cm/C0 = 0.1 in that band
    assert dense_centreline(q0, rho_cl2, u, np.array([x01]))[0] == pytest.approx(0.1, rel=1e-3)
    far = dense_centreline(q0, rho_cl2, u, np.geomspace(50, 5000, 30))
    assert np.all(np.diff(far) < 0)  # falls steadily with distance
    assert is_dense(q0, rho_cl2, u) and not is_dense(q0, 1.2 * 0.59, u)  # chlorine yes, ammonia no
    assert dense_half_width(q0, rho_cl2, u, np.array([100.0]))[0] > d  # spreads sideways as it slumps


def test_heavy_gas_makes_the_near_field_zone_wider(tmp_path: Path) -> None:
    base = {"lon": 12.48, "lat": 41.90, "release_kg_s": 5.0, "wind": {"speed_ms": 3, "from_deg": 270}}
    dense = engine.run("chemical_plume", "city", {**base, "substance": "chlorine"}, cache_dir=tmp_path)
    passive = engine.run("chemical_plume", "city", {**base, "substance": "chlorine", "dense_gas": False},
                         cache_dir=tmp_path)
    for zone in ("aegl3", "aegl2"):
        if zone in dense["result"]["zones"]:
            assert (dense["result"]["zones"][zone]["area_km2"]["likely"]
                    >= passive["result"]["zones"][zone]["area_km2"]["likely"])
    assert passive["result"]["model"] == "gaussian_plume_briggs_urban"


def test_dense_plume_hands_over_smoothly_to_a_passive_plume() -> None:
    from twin.scenarios.plume import _bm_curve_end, dense_concentration

    q, rho, u = 5.0, 2.99, 3.0
    x_end = _bm_curve_end(q / rho, rho, u)
    near = dense_concentration(q, rho, u, "D", np.array([x_end * 0.999, x_end * 1.001]), np.zeros(2))
    assert near[1] == pytest.approx(near[0], rel=0.05)  # no jump at the hand-over
    assert dense_concentration(q, 1.2 * 0.59, u, "D", np.array([100.0]), np.zeros(1))[0] == 0.0
