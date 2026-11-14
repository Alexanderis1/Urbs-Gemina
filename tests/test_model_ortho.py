"""WS2: roof facts and shadow lengths from the 20-50 cm aerial photo."""
import numpy as np
import pytest

from twin.model.ortho import roof_stats, shadow_runs

TERRACOTTA = (190, 100, 70)
GREY = (200, 200, 200)
GREEN = (60, 130, 50)
ASPHALT = (150, 150, 150)
SHADOW = (25, 25, 30)


def _scene() -> tuple[np.ndarray, np.ndarray]:
    rgb = np.zeros((100, 100, 3), dtype=np.uint8)
    rgb[:] = ASPHALT
    labels = np.zeros((100, 100), dtype=np.int32)
    labels[10:30, 10:30] = 1
    rgb[10:30, 10:30] = TERRACOTTA
    labels[10:30, 50:70] = 2
    rgb[10:30, 50:70] = GREY
    rgb[12:20, 52:60] = GREEN  # a roof garden on building 2
    return rgb, labels


def test_roof_stats_find_tiles_flat_and_green() -> None:
    rgb, labels = _scene()
    st = roof_stats(rgb, labels, n=2)
    assert st["share_terracotta"][0] > 0.9
    assert st["share_light_flat"][1] > 0.5
    assert 0.1 < st["share_green"][1] < 0.3
    assert st["n_px"][0] > 0


def test_shadow_runs_measure_free_shadows_and_flag_blocked_ones() -> None:
    rgb, labels = _scene()
    # Shadows cast to the north (up the image): building 1 casts 12 px on open ground,
    # building 2 casts a shadow that reaches building 3 (blocked).
    rgb[0:10, 10:30] = SHADOW  # only 10 px available above building 1 -> ends at image edge
    labels_b = labels.copy()
    labels_b[40:60, 10:30] = 4
    rgb[40:60, 10:30] = TERRACOTTA
    rgb[28:40, 10:30] = ASPHALT
    rgb[30:40, 10:30] = ASPHALT
    # building 4 casts 7 px north on open ground (rows 33-39)
    rgb[33:40, 10:30] = SHADOW
    labels_b[60:80, 50:70] = 3
    rgb[60:80, 50:70] = GREY
    rgb[30:60, 50:70] = SHADOW  # building 3's shadow runs all the way to building 2: blocked
    dark = rgb.max(axis=2) < 60
    runs = shadow_runs(dark, labels_b, n=4, shadow_azimuth_deg=0.0)
    assert runs.length_px[3] == pytest.approx(7, abs=1)  # building 4
    assert runs.blocked[2]  # building 3
    assert np.isnan(runs.length_px[1])  # building 2: no shadow on its north side


def test_shadow_direction_rotation() -> None:
    lab = np.zeros((60, 60), int)
    lab[30:40, 20:30] = 1
    dark = np.zeros((60, 60), bool)
    dark[22:30, 20:30] = True  # 8 px north of the building
    assert shadow_runs(dark, lab, n=1, shadow_azimuth_deg=0.0).length_px[0] == 8
    east_lab, east_dark = np.rot90(lab, k=-1), np.rot90(dark, k=-1)  # now the shadow points east
    assert shadow_runs(east_dark, east_lab, n=1, shadow_azimuth_deg=90.0).length_px[0] == 8
    assert np.isnan(shadow_runs(east_dark, east_lab, n=1, shadow_azimuth_deg=270.0).length_px[0])
