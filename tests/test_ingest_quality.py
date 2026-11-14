"""Quality checks on processed layers: empty, broken or misplaced geometries, duplicates."""
from pathlib import Path

import pytest

gpd = pytest.importorskip("geopandas")
from shapely.geometry import Point, Polygon  # noqa: E402

from twin.ingest.quality import check_frame, check_layers  # noqa: E402

BBOX = (12.2, 41.6, 12.9, 42.2)


def test_check_frame_finds_each_kind_of_problem() -> None:
    bowtie = Polygon([(12.4, 41.8), (12.5, 41.9), (12.5, 41.8), (12.4, 41.9)])  # self-intersecting
    frame = gpd.GeoDataFrame({"name": ["a", "b", "c", "d", "e"], "empty": [None] * 5},
                             geometry=[Point(12.5, 41.9), Point(12.5, 41.9), None, bowtie, Point(9.0, 45.0)],
                             crs="EPSG:4326")
    report = check_frame(frame, BBOX)
    assert report["features"] == 5
    assert report["null_geometries"] == 1
    assert report["invalid_geometries"] == 1
    assert report["outside_city"] == 1
    assert report["duplicate_geometries"] == 1
    assert report["empty_columns"] == ["empty"]
    assert report["issues"]  # a plain-language list of what to fix


def test_clean_layer_has_no_issues(tmp_path: Path) -> None:
    gpd.GeoDataFrame({"name": ["a"]}, geometry=[Point(12.5, 41.9)], crs="EPSG:4326").to_parquet(tmp_path / "ok.parquet")
    reports = check_layers(tmp_path, ["ok", "missing"], BBOX)
    assert reports["ok"]["issues"] == []
    assert reports["missing"]["issues"] == ["file missing"]
