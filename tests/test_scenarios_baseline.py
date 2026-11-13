"""Cartoradio grid as the scenario baseline: nearest-cell lookup, nothing stored."""
import math
from datetime import datetime, timezone
from pathlib import Path

import pytest

from twin.providers.base import Observation
from twin.scenarios import engine
from twin.scenarios.baselines import antenna_bbox, grid_field, live_data

T = datetime(2026, 9, 8, tzinfo=timezone.utc)
R = 6_378_137.0
SIZE = 100.0  # Web Mercator metres


def cell(row: int, col: int, value: float, x0: float = 1_389_000.0, y0: float = 5_146_000.0) -> Observation:
    x, y = x0 + (col + 0.5) * SIZE, y0 - (row + 0.5) * SIZE
    lon = math.degrees(x / R)
    lat = math.degrees(2 * math.atan(math.exp(y / R)) - math.pi / 2)
    spread = 10 ** (4.0 / 20) - 1
    return Observation(f"urn:ngsi-ld:EMFEstimate:cartoradio-r{row}-c{col}", "EMFEstimate", lon, lat, T,
                       {"electricField": value, "at_cap": 0.0}, {"electricField": value * spread, "at_cap": 0.0},
                       "cartoradio_grid", False)


CELLS = [cell(r, c, 1.0 + r + 10 * c) for r in range(3) for c in range(3)]


def test_lookup_returns_the_cell_under_the_point() -> None:
    field = grid_field(CELLS)
    target = CELLS[4]  # row 1, col 1 -> 1 + 1 + 10 = 12.0
    sample = field(target.lon, target.lat)
    assert sample is not None and sample.median_v_per_m == pytest.approx(12.0)
    assert sample.sigma_db == pytest.approx(4.0, abs=0.01)
    # about 16 m east of the centre is still the same cell
    nearby = field(target.lon + 0.0002, target.lat)
    assert nearby is not None and nearby.median_v_per_m == pytest.approx(12.0)


def test_points_off_the_grid_have_no_value() -> None:
    assert grid_field(CELLS)(13.5, 42.5) is None


def test_antenna_bbox_covers_the_neighbourhood() -> None:
    w, s, e, n = antenna_bbox({"action": "add", "site": {"lon": 12.48, "lat": 41.9, "height_m": 20}, "eirp_w": 1})
    assert w < 12.48 < e and s < 41.9 < n
    assert (e - w) * 111_000 * math.cos(math.radians(41.9)) > 600


def test_live_data_uses_the_provider_and_labels_it_estimated(tmp_path: Path) -> None:
    class Fake:
        def fetch(self, bbox: object, start: object, end: object) -> list[Observation]:
            return CELLS

    change = {"action": "add", "site": {"lon": CELLS[4].lon, "lat": CELLS[4].lat, "height_m": 30.0}, "eirp_w": 10.0}
    data = live_data("antenna", "city", change, provider=Fake())
    assert data.baseline_kind == "estimated"
    assert data.baseline_source is not None and "Cartoradio" in str(data.baseline_source["credit"])
    out = engine.run("antenna", "city", change, data=data, cache_dir=tmp_path)
    assert out["data_kinds"]["emf_baseline"] == "estimated"
    peak = min(out["result"]["points"], key=lambda p: p["distance_m"])
    assert peak["baseline"]["p50"] == pytest.approx(12.0)
