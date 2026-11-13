"""Sionna scene export: LoD1 buildings to PLY meshes + Mitsuba XML, and the ray-tracing post-processing."""
from __future__ import annotations

import math
import struct
from pathlib import Path

import numpy as np
import pytest

from twin.physics import raytrace
from twin.physics.buildings import Buildings
from twin.physics.scene import extrude, write_scene

LON, LAT = 12.4823, 41.8960
KY = 6_371_008.8 * math.pi / 180.0
KX = KY * math.cos(math.radians(LAT))


def _courtyard_block() -> Buildings:
    """A 40 m square palazzo with a 10 m square courtyard, 20 m tall."""
    def sq(half: float) -> list[tuple[float, float]]:
        hx, hy = half / KX, half / KY
        return [(LON - hx, LAT - hy), (LON + hx, LAT - hy), (LON + hx, LAT + hy), (LON - hx, LAT + hy),
                (LON - hx, LAT - hy)]
    hole = list(reversed(sq(5.0)))
    return Buildings.from_rings(["p"], [[sq(20.0), hole]], np.array([20.0]), np.array([1.0]), LON, LAT,
                                outer=[[True, False]])


def test_extrude_is_closed_and_roof_skips_the_courtyard() -> None:
    city = _courtyard_block()
    assert city.footprint_m2[0] == pytest.approx(40.0 * 40.0 - 10.0 * 10.0, rel=0.02)
    verts, faces = extrude(city)
    roof = [f for f in faces if np.allclose(verts[f][:, 2], 20.0)]
    roof_area = sum(0.5 * abs(np.cross(verts[f[1]] - verts[f[0]], verts[f[2]] - verts[f[0]])[2]) for f in roof)
    assert roof_area == pytest.approx(1500.0, rel=0.02)
    walls = [f for f in faces if not np.allclose(verts[f][:, 2], verts[f][0, 2])]
    assert len(walls) == 2 * (4 + 4)  # two triangles per wall, outer and courtyard walls


def test_wall_normals_point_out_of_the_solid() -> None:
    verts, faces = extrude(_courtyard_block())
    for f in faces:
        a, b, c = verts[f]
        n = np.cross(b - a, c - a)
        if abs(n[2]) > 1e-9:  # roofs point up
            assert n[2] > 0
            continue
        mid = (a + b + c) / 3.0
        r = math.hypot(mid[0], mid[1])
        outward = np.array([mid[0], mid[1]]) / r
        dot = float(n[:2] @ outward)
        # outer walls (r about 20 m) face away from the centre, courtyard walls (about 5 m) face it
        assert dot > 0 if r > 12 else dot < 0


def test_write_scene_files(tmp_path: Path) -> None:
    xml = write_scene(_courtyard_block(), tmp_path, ground_half_m=100.0)
    text = xml.read_text()
    assert "itu-radio-material" in text and "buildings.ply" in text and "ground.ply" in text
    head = (tmp_path / "meshes" / "buildings.ply").read_bytes()[:200]
    assert head.startswith(b"ply\nformat binary_little_endian 1.0\n")
    n = int(head.split(b"element vertex ")[1].split(b"\n")[0])
    assert n > 0


# --- post-processing of ray-traced path gains (no Sionna needed) ------------------------------

def test_path_gain_to_field_matches_free_space() -> None:
    lam = 299.792458 / 1840.0
    d = 120.0
    pg = (lam / (4 * math.pi * d)) ** 2
    e = raytrace.field_from_path_gain(np.array([pg]), eirp_w=1000.0, frequency_mhz=1840.0)
    assert e[0] == pytest.approx(math.sqrt(30 * 1000.0) / d, rel=1e-9)


def test_tri_sector_from_twelve_yaws() -> None:
    # gains of single-sector maps at yaws 0, 30, ..., 330 for 1 cell: sector k has gain k+1
    pg = np.arange(1.0, 13.0)[:, None]
    combos = raytrace.tri_sector_combinations(pg)
    assert combos.shape == (4, 1)
    assert combos[0, 0] == pytest.approx(1 + 5 + 9)
    assert combos[3, 0] == pytest.approx(4 + 8 + 12)


def test_sionna_yaw_from_compass_bearing() -> None:
    assert raytrace.yaw_deg(0.0) == pytest.approx(90.0)    # north is +y
    assert raytrace.yaw_deg(90.0) == pytest.approx(0.0)    # east is +x


def test_radio_maps_round_trip_is_compact_and_accurate() -> None:
    rng = np.random.default_rng(0)
    pg = 10.0 ** rng.uniform(-14, -6, (4, 12, 120, 120))
    pg[0, 0, :10, :10] = 0.0
    centers = np.stack(np.meshgrid(np.arange(120) * 5.0, np.arange(120) * 5.0), axis=-1)
    maps = raytrace.RadioMaps(pg, centers, np.array([1.5, 10, 20, 30]), {"cell_m": 5.0})
    blob = maps.to_bytes()
    assert len(blob) < 2 * 1024 * 1024
    back = raytrace.RadioMaps.from_bytes(blob)
    assert np.all(back.path_gain[0, 0, :10, :10] == 0.0)
    lit = pg > 0
    assert np.max(np.abs(10 * np.log10(back.path_gain[lit] / pg[lit]))) < 0.006
