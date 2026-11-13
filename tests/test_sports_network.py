"""Real walking reach: a street graph from Overture segments and network distances to facilities."""
from __future__ import annotations

import math

import numpy as np
import pytest

from tests.sports_fixtures import at
from twin.modules.sports.network import WalkGraph, graph_from_segments, nearest_facility_m

KY = 6_371_008.8 * math.pi / 180.0


def _line(points_m: list[tuple[float, float]]) -> bytes:
    import struct

    out = struct.pack("<BII", 1, 2, len(points_m))
    for e, n in points_m:
        lon, lat = at(e, n)
        out += struct.pack("<dd", lon, lat)
    return out


def _u_street() -> WalkGraph:
    """Two parallel streets 200 m apart joined only at the west end (a U): A-B-C plus D-E-F, link A-D."""
    rows = [
        {"geometry": _line([(0, 0), (1000, 0)]), "subtype": "road", "class": "residential",
         "connectors": [{"connector_id": "A", "at": 0.0}, {"connector_id": "B", "at": 0.5}, {"connector_id": "C", "at": 1.0}]},
        {"geometry": _line([(0, 200), (1000, 200)]), "subtype": "road", "class": "footway",
         "connectors": [{"connector_id": "D", "at": 0.0}, {"connector_id": "E", "at": 0.5}, {"connector_id": "F", "at": 1.0}]},
        {"geometry": _line([(0, 0), (0, 200)]), "subtype": "road", "class": "residential",
         "connectors": [{"connector_id": "A", "at": 0.0}, {"connector_id": "D", "at": 1.0}]},
        {"geometry": _line([(1000, 0), (1000, 200)]), "subtype": "road", "class": "motorway",   # not walkable
         "connectors": [{"connector_id": "C", "at": 0.0}, {"connector_id": "F", "at": 1.0}]},
        {"geometry": _line([(500, 0), (500, 200)]), "subtype": "rail", "class": "tram",          # not walkable
         "connectors": [{"connector_id": "B", "at": 0.0}, {"connector_id": "E", "at": 1.0}]},
    ]
    return graph_from_segments(rows)


def test_graph_keeps_walkable_ways_only() -> None:
    g = _u_street()
    assert g.node_count == 6
    assert g.edge_count == 5  # A-B, B-C, D-E, E-F, A-D (motorway and tram dropped)


def test_network_distance_goes_around_the_block() -> None:
    g = _u_street()
    facility = [at(1000, 0)]                      # at C
    person = [at(1000, 200), at(500, 0)]          # at F (other street) and at B (same street)
    d = nearest_facility_m(g, facility, person)
    assert d[0] == pytest.approx(1000 + 200 + 1000, rel=0.01)   # F -> E -> D -> A -> B -> C
    assert d[1] == pytest.approx(500, rel=0.01)


def test_snap_distance_is_added_and_far_points_are_unreachable() -> None:
    g = _u_street()
    d = nearest_facility_m(g, [at(1000, 0)], [at(500, 30), at(500, 5000)], max_snap_m=300.0)
    assert d[0] == pytest.approx(530, rel=0.01)
    assert math.isinf(d[1])


def test_save_and_load(tmp_path) -> None:  # type: ignore[no-untyped-def]
    g = _u_street()
    path = tmp_path / "g.npz"
    g.save(path)
    back = WalkGraph.load(path)
    assert back.node_count == g.node_count and np.allclose(back.edge_m, g.edge_m)
