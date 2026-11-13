"""WS2: G0 LoD1 block model built from footprints, heights and terrain."""
import shutil
from pathlib import Path

import numpy as np
import pytest

gpd = pytest.importorskip("geopandas")
pa = pytest.importorskip("pyarrow")
rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin  # noqa: E402
from shapely.geometry import Polygon, box  # noqa: E402

from twin.model.config import load_model_config  # noqa: E402
from twin.model.lod1 import METRIC_CRS, build_lod1, frame_from_overture  # noqa: E402
from twin.model.rasters import sample_ground, sample_polygon_stat  # noqa: E402
from twin.model.tiles import tippecanoe_command, write_tiles  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CFG = load_model_config(ROOT / "config" / "model.yaml")

# Three buildings around Piazza Navona, in metres (UTM 33N), plus a shed and a basement.
X0, Y0 = 290_500.0, 4_640_500.0


def _footprints() -> "gpd.GeoDataFrame":
    rows = [
        ("tagged", 24.0, None, False, box(X0, Y0, X0 + 20, Y0 + 20)),
        ("floors", None, 5, False, box(X0 + 40, Y0, X0 + 60, Y0 + 20)),
        ("nothing", None, None, False, box(X0 + 80, Y0, X0 + 100, Y0 + 20)),
        ("shed", None, None, False, box(X0 + 120, Y0, X0 + 121, Y0 + 1)),
        ("basement", 3.0, None, True, box(X0 + 140, Y0, X0 + 160, Y0 + 20)),
    ]
    frame = gpd.GeoDataFrame(
        {
            "id": [r[0] for r in rows],
            "height": [r[1] for r in rows],
            "num_floors": [r[2] for r in rows],
            "is_underground": [r[3] for r in rows],
            "class": ["residential"] * len(rows),
        },
        geometry=[r[4] for r in rows],
        crs=METRIC_CRS,
    )
    return frame.to_crs("EPSG:4326")


def _raster(path: Path, value: float, ground: bool = False) -> Path:
    """10 m raster over the test area; `ground` adds a roof-like bump in the middle."""
    data = np.full((10, 30), value, dtype="float32")
    if ground:
        data[3:6, 0:15] = value + 25.0
    with rasterio.open(
        path, "w", driver="GTiff", height=10, width=30, count=1, dtype="float32",
        crs=METRIC_CRS, transform=from_origin(X0 - 50, Y0 + 50, 10, 10), nodata=-9999.0,
    ) as dst:
        dst.write(data, 1)
    return path


def test_build_lod1_resolves_heights_and_filters(tmp_path: Path) -> None:
    raster = _raster(tmp_path / "bh.tif", 6.0)  # Urban Atlas class 6 = 15-20 m
    out = build_lod1(
        _footprints(), CFG,
        raster_heights=lambda g: sample_polygon_stat(raster, g, "mode", min_valid=1.0),
        ground=lambda g: np.full(len(g), 30.0),
    )
    by_id = out.set_index("id")
    assert set(by_id.index) == {"tagged", "floors", "nothing"}  # shed too small, basement underground
    assert by_id.loc["tagged", "height_source"] == "osm_tag"
    assert by_id.loc["tagged", "data_kind"] == "real"
    assert by_id.loc["floors", "height_source"] == "raster"  # raster beats floor count
    assert by_id.loc["floors", "h_floors"] == pytest.approx(16.0)
    assert by_id.loc["nothing", "height_m"] == pytest.approx(17.5)
    assert by_id.loc["nothing", "raster_class"] == 6
    assert by_id.loc["tagged", "roof_m"] == pytest.approx(54.0)
    assert not out["synthetic"].any()
    assert out.crs.to_epsg() == 4326


def test_gba_height_is_matched_by_containing_polygon(tmp_path: Path) -> None:
    gba = gpd.GeoDataFrame(
        {"height": [27.5, 99.0], "var": [4.0, 1.0]},
        geometry=[box(X0 + 75, Y0 - 5, X0 + 105, Y0 + 25), box(X0 + 500, Y0, X0 + 520, Y0 + 20)],
        crs=METRIC_CRS,
    ).to_crs("EPSG:4326")
    raster = _raster(tmp_path / "bh.tif", 6.0)
    out = build_lod1(
        _footprints(), CFG, gba=gba,
        raster_heights=lambda g: sample_polygon_stat(raster, g, "mode", min_valid=1.0),
    ).set_index("id")
    assert out.loc["nothing", "height_source"] == "gba"
    assert out.loc["nothing", "height_m"] == pytest.approx(27.5)
    assert out.loc["nothing", "height_licence"] == "CC BY-NC 4.0"
    assert out.loc["nothing", "height_sd_m"] == pytest.approx(2.0)  # GBA variance 4 m2
    assert np.isnan(out.loc["floors", "height_sd_m"])
    assert out.loc["nothing", "h_raster"] == pytest.approx(17.5)  # kept for the height check
    assert out.loc["floors", "height_source"] == "raster"  # no GBA polygon there
    assert out.attrs["non_commercial"] is True


def test_without_raster_floors_then_default_apply() -> None:
    out = build_lod1(_footprints(), CFG, raster_heights=None, ground=None).set_index("id")
    assert out.loc["floors", "height_source"] == "floors"
    assert out.loc["floors", "height_m"] == pytest.approx(16.0)
    assert out.loc["nothing", "height_source"] == "default"
    assert np.isnan(out.loc["nothing", "ground_m"])
    assert out.attrs["non_commercial"] is False


def test_polygon_median_ignores_nodata_and_uses_centroid_for_tiny_polygons(tmp_path: Path) -> None:
    raster = _raster(tmp_path / "bh.tif", 12.0)
    g = _footprints().to_crs(METRIC_CRS)
    values = sample_polygon_stat(raster, g, "median", min_valid=2.0)
    assert values == pytest.approx([12.0] * 5)
    assert sample_polygon_stat(raster, g, "mode", min_valid=1.0) == pytest.approx([12.0] * 5)


def test_ground_takes_low_percentile_around_the_building(tmp_path: Path) -> None:
    dem = _raster(tmp_path / "dem.tif", 20.0, ground=True)
    g = _footprints().to_crs(METRIC_CRS)
    ground = sample_ground(dem, g, ring_m=30.0, percentile=10)
    assert ground[0] == pytest.approx(20.0)  # the roof bump is ignored


def test_frame_from_overture_reads_wkb_geometry() -> None:
    poly = Polygon([(12.47, 41.89), (12.4702, 41.89), (12.4702, 41.8902), (12.47, 41.8902)])
    table = pa.table({
        "id": ["a"], "height": [12.5], "num_floors": [None], "is_underground": [False],
        "class": ["residential"], "geometry": [poly.wkb],
    })
    frame = frame_from_overture(table)
    assert frame.crs.to_epsg() == 4326
    assert frame.geometry.iloc[0].equals(poly)


def test_tippecanoe_command_names_layer_and_zooms(tmp_path: Path) -> None:
    cmd = tippecanoe_command(tmp_path / "in.geojsonl", tmp_path / "out.pmtiles", CFG.tiles)
    assert cmd[0] == "tippecanoe"
    assert "--layer=buildings" in cmd and "--minimum-zoom=12" in cmd and "--maximum-zoom=16" in cmd
    assert str(tmp_path / "out.pmtiles") in " ".join(cmd)


@pytest.mark.skipif(shutil.which("tippecanoe") is None, reason="tippecanoe not installed")
def test_write_tiles_produces_a_pmtiles_archive(tmp_path: Path) -> None:
    out = build_lod1(_footprints(), CFG, raster_heights=None, ground=None)
    pm = write_tiles(out, tmp_path / "buildings.pmtiles", CFG.tiles)
    assert pm.read_bytes()[:7] == b"PMTiles"
