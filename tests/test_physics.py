"""Building-aware propagation: antenna pattern, knife-edge diffraction, entry loss, buildings, Monte Carlo."""
from __future__ import annotations

import math
import struct

import numpy as np
import pytest

from twin.physics import bel, diffraction, pattern
from twin.physics.buildings import Buildings, parse_wkb
from twin.physics.field import FieldEngine, Receptor, Sector, Transmitter, free_space_v_per_m

LON, LAT = 12.4823, 41.8960


# --- antenna pattern (3GPP TR 38.901 Table 7.3-1) ---------------------------------

def test_pattern_boresight_is_zero_and_half_beamwidth_is_minus_three() -> None:
    assert pattern.gain_db(0.0, 0.0, tilt_deg=0.0) == pytest.approx(0.0)
    assert pattern.gain_db(32.5, 0.0, tilt_deg=0.0) == pytest.approx(-3.0, abs=1e-6)
    assert pattern.gain_db(0.0, 3.5, tilt_deg=0.0) == pytest.approx(-3.0, abs=1e-6)


def test_pattern_back_is_capped_at_front_to_back() -> None:
    assert pattern.gain_db(180.0, 0.0, tilt_deg=0.0) == pytest.approx(-30.0)
    assert pattern.gain_db(180.0, 60.0, tilt_deg=0.0) == pytest.approx(-30.0)


def test_downtilt_points_the_beam_down() -> None:
    assert pattern.gain_db(0.0, 6.0, tilt_deg=6.0) == pytest.approx(0.0)
    assert pattern.gain_db(0.0, 0.0, tilt_deg=6.0) < -5.0


# --- diffraction (ITU-R P.526) -------------------------------------------------------

def test_knife_edge_loss_reference_values() -> None:
    assert diffraction.knife_edge_db(np.array([0.0]))[0] == pytest.approx(6.03, abs=0.02)
    assert diffraction.knife_edge_db(np.array([-1.0]))[0] == 0.0
    assert diffraction.knife_edge_db(np.array([2.4]))[0] == pytest.approx(20.6, abs=0.3)


def test_deygout_without_edges_is_zero() -> None:
    loss = diffraction.deygout_db(np.zeros(0), np.zeros((0, 4)), 30.0, 1.5, 200.0, 0.16)
    assert loss.shape == (4,) and np.all(loss == 0.0)


def test_deygout_single_edge_matches_knife_edge() -> None:
    lam, d, d1, h = 0.163, 200.0, 100.0, 20.0
    zt, zr = 30.0, 1.5
    los = zt + (zr - zt) * d1 / d
    nu = (h - los) * math.sqrt(2 * d / (lam * d1 * (d - d1)))
    loss = diffraction.deygout_db(np.array([d1]), np.full((1, 1), h), zt, zr, d, lam)
    assert loss[0] == pytest.approx(diffraction.knife_edge_db(np.array([nu]))[0])


def test_deygout_two_edges_is_more_than_one() -> None:
    one = diffraction.deygout_db(np.array([100.0]), np.full((1, 1), 20.0), 30.0, 1.5, 200.0, 0.16)
    two = diffraction.deygout_db(np.array([60.0, 150.0]), np.full((2, 1), 20.0), 30.0, 1.5, 200.0, 0.16)
    assert two[0] > one[0]


# --- building entry loss (ITU-R P.2109-2) ---------------------------------------------

def test_p2109_median_traditional_at_2ghz() -> None:
    # Hand-computed from P.2109-2 eq. (1)-(5): about 15.0 dB for traditional buildings, horizontal path
    assert bel.loss_db(2.0, 0.0, 0.5, "traditional") == pytest.approx(14.97, abs=0.05)


def test_p2109_thermally_efficient_buildings_lose_more() -> None:
    assert bel.loss_db(2.0, 0.0, 0.5, "thermally_efficient") > bel.loss_db(2.0, 0.0, 0.5, "traditional") + 10


def test_p2109_higher_probability_means_more_loss() -> None:
    assert bel.loss_db(1.8, 10.0, 0.9) > bel.loss_db(1.8, 10.0, 0.5) > bel.loss_db(1.8, 10.0, 0.1)


# --- buildings ---------------------------------------------------------------------------

def _wkb_polygon(ring: list[tuple[float, float]]) -> bytes:
    out = struct.pack("<BII", 1, 3, 1) + struct.pack("<I", len(ring))
    for x, y in ring:
        out += struct.pack("<dd", x, y)
    return out


def _square(cx: float, cy: float, half_deg: float) -> list[tuple[float, float]]:
    return [(cx - half_deg, cy - half_deg), (cx + half_deg, cy - half_deg), (cx + half_deg, cy + half_deg),
            (cx - half_deg, cy + half_deg), (cx - half_deg, cy - half_deg)]


def test_wkb_polygon_round_trip() -> None:
    ring = _square(LON, LAT, 0.0001)
    polys = parse_wkb(_wkb_polygon(ring))
    assert len(polys) == 1 and np.allclose(np.array(polys[0][0]), np.array(ring))


def _wall_city(height: float = 20.0, sd: float = 0.0) -> Buildings:
    """One 40 m x 40 m block 100 m east of the antenna."""
    east = 100.0 / (111_320.0 * math.cos(math.radians(LAT)))
    ring = _square(LON + east, LAT, 20.0 / (111_320.0 * math.cos(math.radians(LAT))))
    return Buildings.from_rings(["b1"], [[ring]], np.array([height]), np.array([sd]), LON, LAT)


def test_ray_crossing_finds_both_walls() -> None:
    city = _wall_city()
    rx = np.array([[200.0, 0.0]])
    crossings = city.crossings(np.array([0.0, 0.0]), rx)
    dist = sorted(d for d, _ in crossings[0])
    assert dist == pytest.approx([80.0, 120.0], abs=0.5)


def test_point_inside_a_building() -> None:
    city = _wall_city()
    assert city.building_at(np.array([[100.0, 0.0], [0.0, 0.0]])).tolist() == [0, -1]


# --- field engine --------------------------------------------------------------------------

def _engine(city: Buildings | None, samples: int = 64) -> FieldEngine:
    return FieldEngine(buildings=city, samples=samples, seed=1, los_sigma_db=0.0, nlos_sigma_db=0.0,
                       diffuse_loss_db=35.0)


def test_open_field_matches_free_space_on_boresight() -> None:
    tx = Transmitter(x=0.0, y=0.0, height_m=30.0, frequency_mhz=1840.0,
                     sectors=(Sector(eirp_w=1000.0, azimuth_deg=90.0, tilt_deg=0.0),), eirp_sigma_db=0.0)
    rx = [Receptor(x=200.0, y=0.0, height_m=30.0)]
    samples = _engine(None).field_samples([tx], rx)
    # the declared azimuth carries a small installation tolerance, so the peak is the free-space value
    assert samples[0].max() == pytest.approx(free_space_v_per_m(1000.0, 200.0), rel=1e-3)
    assert np.median(samples[0]) == pytest.approx(free_space_v_per_m(1000.0, 200.0), rel=0.02)


def test_building_shadow_lowers_street_level_field() -> None:
    tx = Transmitter(x=0.0, y=0.0, height_m=15.0, frequency_mhz=1840.0,
                     sectors=(Sector(eirp_w=1000.0, azimuth_deg=90.0, tilt_deg=0.0),), eirp_sigma_db=0.0)
    rx = [Receptor(x=200.0, y=0.0, height_m=1.5)]
    open_field = float(np.median(_engine(None).field_samples([tx], rx)[0]))
    shadowed = float(np.median(_engine(_wall_city(25.0)).field_samples([tx], rx)[0]))
    loss_db = 20.0 * math.log10(open_field / shadowed)
    assert 10.0 < loss_db <= 35.0 + 1e-6  # never deeper than the diffuse multipath floor


def test_receptor_above_the_roofs_is_not_shadowed() -> None:
    tx = Transmitter(x=0.0, y=0.0, height_m=40.0, frequency_mhz=1840.0,
                     sectors=(Sector(eirp_w=1000.0, azimuth_deg=90.0, tilt_deg=0.0),), eirp_sigma_db=0.0)
    rx = [Receptor(x=200.0, y=0.0, height_m=40.0)]
    a = _engine(None).field_samples([tx], rx)[0]
    b = _engine(_wall_city(20.0)).field_samples([tx], rx)[0]
    assert np.allclose(a, b)


def test_indoor_receptor_gets_entry_loss_not_wall_diffraction() -> None:
    tx = Transmitter(x=0.0, y=0.0, height_m=40.0, frequency_mhz=1840.0,
                     sectors=(Sector(eirp_w=1000.0, azimuth_deg=90.0, tilt_deg=0.0),), eirp_sigma_db=0.0)
    city = _wall_city(20.0)
    outdoor = _engine(None).field_samples([tx], [Receptor(x=100.0, y=0.0, height_m=10.0)])[0]
    indoor = _engine(city).field_samples([tx], [Receptor(x=100.0, y=0.0, height_m=10.0, indoor=True)])[0]
    ratio_db = 20.0 * np.log10(np.median(outdoor) / np.median(indoor))
    assert 8.0 < ratio_db < 25.0  # P.2109 median at 1.8 GHz is about 15 dB


def test_unknown_azimuth_spreads_the_result() -> None:
    tx = Transmitter(x=0.0, y=0.0, height_m=30.0, frequency_mhz=1840.0, sectors=None,
                     unknown_sector_eirp_w=1000.0, eirp_sigma_db=0.0)
    s = _engine(None, samples=256).field_samples([tx], [Receptor(x=150.0, y=0.0, height_m=1.5)])[0]
    p5, p95 = np.percentile(s, [5, 95])
    assert 20.0 * math.log10(p95 / p5) > 3.0


def test_monte_carlo_is_reproducible() -> None:
    tx = Transmitter(x=0.0, y=0.0, height_m=30.0, frequency_mhz=1840.0, sectors=None,
                     unknown_sector_eirp_w=1000.0, eirp_sigma_db=2.0)
    city = _wall_city(25.0, sd=3.0)
    rx = [Receptor(x=200.0, y=0.0, height_m=1.5)]
    a = FieldEngine(buildings=city, samples=64, seed=7).field_samples([tx], rx)
    b = FieldEngine(buildings=city, samples=64, seed=7).field_samples([tx], rx)
    assert np.array_equal(a, b)


# --- public API used by the scenario engine ---------------------------------------------------

def test_api_field_at_without_buildings_is_close_to_free_space_worst_case() -> None:
    from twin.physics import api

    site = {"lon": LON, "lat": LAT, "height_m": 25.0, "eirp_w": 2000.0,
            "sectors": [{"azimuth_deg": 90.0, "tilt_deg": 0.0}]}
    east = 150.0 / (111_320.0 * math.cos(math.radians(LAT)))
    median, sigma = api.field_at(site, LON + east, LAT, 25.0, buildings=None)
    assert median == pytest.approx(free_space_v_per_m(2000.0, 150.0), rel=0.1)
    assert 0.0 < sigma < 10.0


def test_api_batch_matches_single_points() -> None:
    from twin.physics import api

    site = {"lon": LON, "lat": LAT, "height_m": 25.0, "eirp_w": 1000.0}
    pts = [(LON + 0.001, LAT), (LON, LAT + 0.001)]
    batch = api.field_samples(site, pts, receptor_h=1.5, buildings=None)
    assert batch.samples.shape[0] == 2
    one = api.field_samples(site, pts[:1], receptor_h=1.5, buildings=None)
    assert np.allclose(np.sort(batch.samples[0]), np.sort(one.samples[0]), rtol=0.5)


def test_api_unknown_band_is_refused() -> None:
    from twin.physics import api

    with pytest.raises(ValueError):
        api.transmitter({"lon": LON, "lat": LAT, "height_m": 20.0, "band": "99"}, LON, LAT)
