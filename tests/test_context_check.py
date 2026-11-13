import math

import pytest

from twin.tools.context_check import context_check, distance_to_geometry_m

# Piazza Venezia
LON, LAT = 12.4823, 41.8960
M_PER_DEG_LAT = 111_195.0
M_PER_DEG_LON = M_PER_DEG_LAT * math.cos(math.radians(LAT))


def offset(east_m: float, north_m: float) -> list[float]:
    return [LON + east_m / M_PER_DEG_LON, LAT + north_m / M_PER_DEG_LAT]


def point(east_m: float, north_m: float, **props: object) -> dict[str, object]:
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": offset(east_m, north_m)}, "properties": props}


def test_point_distance_matches_offset() -> None:
    geometry = {"type": "Point", "coordinates": offset(300.0, 400.0)}
    assert distance_to_geometry_m(LON, LAT, geometry) == pytest.approx(500.0, abs=1.0)


def test_inside_polygon_is_zero_and_hole_is_not() -> None:
    square = [offset(-100, -100), offset(100, -100), offset(100, 100), offset(-100, 100), offset(-100, -100)]
    hole = [offset(-10, -10), offset(10, -10), offset(10, 10), offset(-10, 10), offset(-10, -10)]
    assert distance_to_geometry_m(LON, LAT, {"type": "Polygon", "coordinates": [square]}) == 0.0
    with_hole = {"type": "Polygon", "coordinates": [square, hole]}
    assert distance_to_geometry_m(LON, LAT, with_hole) == pytest.approx(10.0, abs=0.5)


def test_distance_to_polygon_edge() -> None:
    square = [offset(200, -50), offset(400, -50), offset(400, 50), offset(200, 50), offset(200, -50)]
    assert distance_to_geometry_m(LON, LAT, {"type": "Polygon", "coordinates": [square]}) == pytest.approx(200.0, abs=1.0)


def test_line_distance() -> None:
    line = {"type": "LineString", "coordinates": [offset(-500, 120), offset(500, 120)]}
    assert distance_to_geometry_m(LON, LAT, line) == pytest.approx(120.0, abs=1.0)


def test_context_check_filters_sorts_and_reports_missing_layers() -> None:
    schools = {"type": "FeatureCollection", "features": [point(250, 0, name="far"), point(50, 0, name="near"), point(301, 0, name="out")]}
    report = context_check(LON, LAT, {"schools": schools, "playgrounds": None}, radius_m=300.0)
    names = [hit["properties"]["name"] for hit in report["layers"]["schools"]["hits"]]
    assert names == ["near", "far"]
    assert report["layers"]["schools"]["count"] == 2
    assert report["layers"]["playgrounds"]["status"] == "not_available"


def test_unknown_geometry_is_rejected() -> None:
    with pytest.raises(ValueError):
        distance_to_geometry_m(LON, LAT, {"type": "GeometryCollection", "coordinates": []})
