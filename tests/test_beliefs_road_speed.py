"""Road speed starting map: free-flow speed of the roads in each cell x the city's hourly congestion profile."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from twin.beliefs import landuse
from twin.beliefs.config import load_specs
from twin.beliefs.grid import cell_of, cells_in_bbox
from twin.beliefs.layer import prior_layer

HERE = (12.4964, 41.9028)
WINDOW = (12.485, 41.895, 12.505, 41.910)


def test_fast_roads_start_faster_and_all_slow_down_in_the_rush_hour(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = load_specs()["road_speed"]
    assert spec.prior_field is not None and spec.prior_field.covariate_file is not None
    cells = cells_in_bbox(WINDOW, 9)
    fast = cell_of(*HERE, 9)
    (tmp_path / spec.prior_field.covariate_file).write_text(
        "cell,value\n" + "".join(f"{c},{90.0 if c == fast else 30.0}\n" for c in cells))
    monkeypatch.setattr(landuse, "SEARCH_DIRS", (tmp_path,))
    landuse.load_cell_covariate.cache_clear()
    slow = next(c for c in cells if c != fast)

    night = datetime(2026, 11, 14, 2, tzinfo=timezone.utc)   # 03:00 in Rome
    rush = datetime(2026, 11, 14, 7, tzinfo=timezone.utc)    # 08:00 in Rome
    at_night = prior_layer(spec, cells, night)
    in_rush = prior_layer(spec, cells, rush)
    assert at_night.belief(fast).mean > 2.5 * at_night.belief(slow).mean
    ratio_night = at_night.belief(fast).mean / at_night.belief(slow).mean
    ratio_rush = in_rush.belief(fast).mean / in_rush.belief(slow).mean
    assert ratio_rush == pytest.approx(ratio_night, rel=0.05)    # congestion scales every road alike
    assert in_rush.belief(fast).mean < 0.6 * at_night.belief(fast).mean
    assert not at_night.warnings
    landuse.load_cell_covariate.cache_clear()


def test_free_flow_speed_of_a_cell_is_the_length_weighted_mean_of_its_roads() -> None:
    speeds = landuse.free_flow_speed({"motorway": 100.0, "residential": 300.0}, {"motorway": 90.0, "residential": 30.0})
    assert speeds == pytest.approx((100 * 90 + 300 * 30) / 400)
    assert landuse.free_flow_speed({}, {"motorway": 90.0}) is None
