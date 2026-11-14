import geopandas as gpd
import numpy as np
from shapely.geometry import box

from twin.model.lidar import (
    apply_lidar,
    chunked,
    footprint_heights,
    public_download_url,
    tile_payload,
)


def test_public_download_url_rehosts_internal_gateway():
    raw = "http://mase-api-gateway.apps.example.priv/api/v1/downloads/abc/file/12"
    assert public_download_url(raw, "https://sim.mase.gov.it/") == (
        "https://sim.mase.gov.it/core/api/esri/api/v1/downloads/abc/file/12"
    )


def test_public_download_url_keeps_public_links():
    url = "https://sim.mase.gov.it/core/api/esri/api/v1/downloads/abc/file/12"
    assert public_download_url(url, "https://sim.mase.gov.it") == url


def test_chunked():
    assert chunked(list(range(5)), 2) == [[0, 1], [2, 3], [4]]


def test_tile_payload_keeps_only_surveyed_tiles():
    rows = [
        {"fid": 1, "tavola": "A", "regione": "Lazio", "contratto": "140", "risoluzion": 1},
        {"fid": 2, "tavola": "B", "regione": "Lazio", "contratto": " ", "risoluzion": 0},
    ]
    assert tile_payload(rows) == [{"fid": "1", "tavola": "A", "regione": "Lazio", "contratto": "140"}]


def test_footprint_heights_uses_high_quantile_inside_eroded_footprint():
    ndsm = np.zeros((10, 10))
    ndsm[2:8, 2:8] = 12.0
    ndsm[4, 4] = 20.0  # a chimney
    labels = np.zeros((10, 10), dtype=np.int32)
    labels[2:8, 2:8] = 1
    dtm = np.full((10, 10), 30.0)
    h, ground, n_px = footprint_heights(ndsm, dtm, labels, n=2, quantile=0.9, min_px=4)
    assert h[0] == 12.0
    assert ground[0] == 30.0
    assert n_px[0] == 16  # 6x6 eroded by one pixel
    assert np.isnan(h[1]) and n_px[1] == 0


def test_apply_lidar_replaces_height_and_keeps_newer_buildings():
    model = gpd.GeoDataFrame(
        {
            "height_m": [10.0, 15.0, 8.0],
            "height_sd_m": [2.0, 2.0, 2.0],
            "height_source": ["gba", "gba", "gba"],
            "data_kind": ["estimated"] * 3,
            "height_conflict": [False, False, False],
        },
        geometry=[box(0, 0, 1, 1)] * 3,
    )
    h_lidar = np.array([12.0, 0.5, np.nan])  # 2nd: no building in 2008 (newer)
    out, stats = apply_lidar(model, h_lidar, sd_m=0.5, min_height_m=2.0, survey="2008")
    assert out.loc[0, "height_m"] == 12.0
    assert out.loc[0, "height_source"] == "lidar"
    assert out.loc[0, "data_kind"] == "real"
    assert out.loc[0, "height_sd_m"] == 0.5
    assert out.loc[1, "height_m"] == 15.0 and out.loc[1, "height_source"] == "gba"
    assert bool(out.loc[1, "lidar_missing_building"])
    assert out.loc[2, "height_source"] == "gba"
    assert stats["replaced"] == 1 and stats["newer_than_survey"] == 1


def test_fit_linear_recovers_scale_and_ignores_outliers():
    from twin.model.lidar import fit_linear

    rng = np.random.default_rng(0)
    x = rng.uniform(3, 40, 2000)
    y = 1.0 + 1.4 * x + rng.normal(0, 1.0, x.size)
    y[:100] = 0.0  # demolished or misplaced buildings
    fit = fit_linear(x, y)
    assert abs(fit.slope - 1.4) < 0.05
    assert abs(fit.intercept - 1.0) < 0.5
    assert 0.7 < fit.sd_m < 1.5
    assert fit.n == 2000
    assert np.allclose(fit.apply(np.array([10.0])), [fit.intercept + fit.slope * 10.0])


def test_holdout_correction_reports_gain_on_unseen_cells():
    from twin.model.lidar import holdout_correction

    rng = np.random.default_rng(1)
    x = rng.uniform(3, 40, 4000)
    y = 1.3 * x + rng.normal(0, 1.0, x.size)
    cells = rng.integers(0, 50, x.size)
    res = holdout_correction(x, y, cells)
    assert res["mae_after_m"] < res["mae_before_m"]
    assert res["n_test"] > 1000
