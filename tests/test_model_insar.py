"""WS2: ground motion from ascending + descending satellite radar (InSAR)."""
import numpy as np
import pytest

from twin.model.insar import decompose, los_unit_vector


def test_los_vector_is_unit_and_points_up() -> None:
    e, n, u = los_unit_vector(incidence_deg=39.0, heading_deg=-10.0)
    assert e * e + n * n + u * u == pytest.approx(1.0)
    assert u == pytest.approx(np.cos(np.radians(39.0)))


def test_pure_subsidence_is_recovered() -> None:
    asc = los_unit_vector(incidence_deg=39.0, heading_deg=-10.0)
    desc = los_unit_vector(incidence_deg=39.0, heading_deg=-170.0)
    v_up = -5.0  # sinking 5 mm/yr
    v_asc = np.array([asc[2] * v_up])
    v_desc = np.array([desc[2] * v_up])
    up, east = decompose(v_asc, v_desc, asc, desc)
    assert up[0] == pytest.approx(-5.0, abs=1e-6) and east[0] == pytest.approx(0.0, abs=1e-6)


def test_east_motion_is_separated_from_vertical() -> None:
    asc = los_unit_vector(incidence_deg=39.0, heading_deg=-10.0)
    desc = los_unit_vector(incidence_deg=39.0, heading_deg=-170.0)
    v_e, v_u = 2.0, -1.0
    up, east = decompose(np.array([asc[0] * v_e + asc[2] * v_u]), np.array([desc[0] * v_e + desc[2] * v_u]), asc, desc)
    assert up[0] == pytest.approx(v_u, abs=1e-6) and east[0] == pytest.approx(v_e, abs=1e-6)


def test_missing_geometry_gives_nan() -> None:
    asc = los_unit_vector(incidence_deg=39.0, heading_deg=-10.0)
    desc = los_unit_vector(incidence_deg=39.0, heading_deg=-170.0)
    up, east = decompose(np.array([np.nan]), np.array([1.0]), asc, desc)
    assert np.isnan(up[0]) and np.isnan(east[0])
