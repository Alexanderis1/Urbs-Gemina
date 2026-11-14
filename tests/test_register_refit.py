"""Register v2: empirical path-loss exponent, tri-sector azimuth recovery, censored (capped) cells, LiDAR heights."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest

from twin.providers.estimated import refit

LON, LAT = 12.50, 41.90
KX = 6_371_008.8 * math.pi / 180.0 * math.cos(math.radians(LAT))
KY = 6_371_008.8 * math.pi / 180.0


def _grid(step: float = 100.0, half: int = 8) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = np.meshgrid(np.arange(-half, half + 1) * step + 50.0, np.arange(-half, half + 1) * step + 50.0)
    return xs.ravel(), ys.ravel()


def _truth(offset: float, power: float, exponent: float, height: float = 30.0) -> refit.Problem:
    x, y = _grid()
    sites = np.array([[0.0, 0.0], [900.0, 900.0]])
    heights = np.array([height, height])
    model = refit.Model(exponent=exponent, receptor_m=1.5, tilt_deg=6.0)
    g0 = refit.gain_table(sites[0], heights[0], x, y, model)[refit.offset_index(offset)]
    g1 = refit.gain_table(sites[1], heights[1], x, y, model)[0]
    e2 = power * g0 + 0.5 * power * g1 + 0.01
    return refit.Problem(sites=sites, heights=heights, cell_x=x, cell_y=y, e2=e2, at_cap=np.zeros(x.size, bool))


def test_recovers_azimuth_offset_power_and_exponent() -> None:
    prob = _truth(offset=60.0, power=800.0, exponent=3.0)
    best = refit.select_exponent(prob, exponents=(2.0, 2.5, 3.0, 3.5), sigma_db=4.0, radius_m=1500.0, seed=0)
    assert best.model.exponent == 3.0
    assert best.offsets_deg[0] == pytest.approx(60.0)
    assert best.powers_w[0] == pytest.approx(800.0, rel=0.05)
    assert best.holdout_median_abs_db < 0.5


def test_capped_cells_are_lower_bounds() -> None:
    prob = _truth(offset=0.0, power=5000.0, exponent=2.0, height=12.0)
    cap = 3.0 ** 2  # a low cap so several cells near the mast are censored
    capped = prob.e2 >= cap
    assert capped.any()
    prob = refit.Problem(prob.sites, prob.heights, prob.cell_x, prob.cell_y, np.minimum(prob.e2, cap), capped)
    fit = refit.fit(prob, refit.Model(exponent=2.0, receptor_m=1.5, tilt_deg=6.0), sigma_db=4.0, radius_m=1500.0)
    pred = fit.predicted
    assert np.all(pred[capped] >= cap * 0.9)          # the model honours "15 or more"
    assert fit.powers_w[0] == pytest.approx(5000.0, rel=0.15)


def test_mast_height_from_roof() -> None:
    assert refit.mast_height(roof_m=22.0, on_building=True) == pytest.approx(22.0 + refit.mast_offset_m())
    assert refit.mast_height(roof_m=None, on_building=False) == pytest.approx(refit.tower_height_m())


def test_refit_settings_read_once_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fit asks for mast heights once per site; re-reading YAML each time cost ~140 s live."""
    from twin.providers.estimated import refit as refit_module
    from twin.providers.settings import Settings

    calls = {"n": 0}
    real_load = Settings.load

    def counting_load(*args: Any, **kwargs: Any) -> Settings:
        calls["n"] += 1
        return real_load(*args, **kwargs)

    refit_module._refit_section.cache_clear()
    monkeypatch.setattr(Settings, "load", staticmethod(counting_load))
    for _ in range(50):
        refit_module.tower_height_m()
        refit_module.mast_offset_m()
    assert calls["n"] == 1
