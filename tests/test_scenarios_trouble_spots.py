"""Rain trouble spots: low ground plus past flooding call-outs, checked on Rome's civil-protection log."""
import numpy as np

from twin.scenarios.susceptibility import trouble_spots
from twin.scenarios.terrain import Grid, to_utm

CFG = {"tpi_window_m": 600.0, "history_radius_m": 150.0, "history_weight": 0.5, "min_sealed": 0.3,
       "listed": 5, "spacing_m": 200.0,
       "reference": {"tpi_mean": 1.39, "tpi_sd": 5.73, "history_mean": 0.402, "history_sd": 0.585}}


def _grid() -> Grid:
    n, cell = 60, 30.0
    yy, xx = np.mgrid[0:n, 0:n]
    z = 50.0 + 0.05 * xx  # gentle slope
    z[20:24, 20:24] -= 10.0  # a hollow well below its surroundings
    x0, y0 = to_utm([12.48], [41.90])
    return Grid(z, x0[0], y0[0], cell)


def test_low_ground_with_past_call_outs_ranks_first() -> None:
    g = _grid()
    sealed = np.ones(g.shape)
    in_area = np.ones(g.shape, bool)
    lons, lats = g.lonlat(np.array([45, 45, 45]), np.array([45, 45, 45]))
    out = trouble_spots(g, in_area, sealed, list(zip(lons, lats)), CFG)
    spots = out["spots"]
    assert 1 <= len(spots) <= 5
    top = spots[0]
    hollow_lon, hollow_lat = g.lonlat(np.array([21]), np.array([21]))
    assert abs(top["lon"] - hollow_lon[0]) < 0.002 and abs(top["lat"] - hollow_lat[0]) < 0.002
    assert top["low_ground_m"] < -3
    # the cell with three past call-outs makes the list although it sits on plain ground
    assert any(s["past_call_outs"] == 3 for s in spots)
    # spots are spread out, not stacked in one hollow
    xs, ys = to_utm([s["lon"] for s in spots], [s["lat"] for s in spots])
    d = [np.hypot(xs[i] - xs[j], ys[i] - ys[j]) for i in range(len(xs)) for j in range(i)]
    assert min(d) >= 200 - 1e-6
    assert out["history"] == "real"


def test_without_the_log_it_falls_back_to_low_ground_only() -> None:
    g = _grid()
    out = trouble_spots(g, np.ones(g.shape, bool), np.ones(g.shape), None, CFG)
    assert out["history"] == "not_available"
    assert out["spots"][0]["past_call_outs"] is None
    assert out["spots"][0]["low_ground_m"] < -3


def test_open_ground_and_cells_outside_the_area_are_skipped() -> None:
    g = _grid()
    sealed = np.ones(g.shape)
    sealed[15:30, 15:30] = 0.0  # the hollow is a park
    in_area = np.ones(g.shape, bool)
    in_area[:, 40:] = False
    out = trouble_spots(g, in_area, sealed, None, CFG)
    for s in out["spots"]:
        r, c = g.rowcol([s["lon"]], [s["lat"]])
        assert sealed[r[0], c[0]] >= 0.3 and in_area[r[0], c[0]]
