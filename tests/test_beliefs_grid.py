import math

from twin.beliefs.grid import cell_boundary, cell_center, cells_in_bbox, cells_in_polygon, cell_of, local_xy_km

PIAZZA_VENEZIA = (12.4823, 41.8962)


def test_cell_of_a_point_contains_its_centre_nearby() -> None:
    cell = cell_of(*PIAZZA_VENEZIA, resolution=9)
    lon, lat = cell_center(cell)
    # A resolution-9 hexagon has an edge of about 0.17 km, so the centre is close.
    assert abs(lon - PIAZZA_VENEZIA[0]) < 0.003
    assert abs(lat - PIAZZA_VENEZIA[1]) < 0.003


def test_cells_in_bbox_covers_a_small_window() -> None:
    bbox = (12.47, 41.89, 12.49, 41.90)  # about 1.7 km x 1.1 km
    cells = cells_in_bbox(bbox, resolution=9)
    assert 10 < len(cells) < 40
    assert cells == sorted(cells)
    assert cell_of(12.48, 41.895, 9) in cells


def test_cells_in_polygon_accepts_geojson() -> None:
    polygon = {
        "type": "Polygon",
        "coordinates": [[[12.47, 41.89], [12.49, 41.89], [12.49, 41.90], [12.47, 41.90], [12.47, 41.89]]],
    }
    assert cells_in_polygon(polygon, resolution=9) == cells_in_bbox((12.47, 41.89, 12.49, 41.90), resolution=9)


def test_cell_boundary_is_a_closed_lon_lat_ring() -> None:
    ring = cell_boundary(cell_of(*PIAZZA_VENEZIA, resolution=9))
    assert len(ring) == 7
    assert ring[0] == ring[-1]
    assert all(12.4 < lon < 12.6 and 41.8 < lat < 42.0 for lon, lat in ring)


def test_local_xy_distances_are_in_km() -> None:
    xy = local_xy_km([(12.0, 41.9), (12.0, 42.0), (12.1, 41.9)])
    north = math.dist(xy[0], xy[1])
    east = math.dist(xy[0], xy[2])
    assert abs(north - 11.12) < 0.05
    assert abs(east - 11.12 * math.cos(math.radians(41.9))) < 0.05
