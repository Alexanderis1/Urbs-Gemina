"""WS3: the only simulated sensors, the road loop stations, and their realistic placement."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from twin.providers.base import ROME_BBOX
from twin.providers.geo import distance_m, offset
from twin.providers.settings import Settings
from twin.providers.simulated.loops import SimLoopsProvider

T0 = datetime(2026, 11, 13, 8, 0, tzinfo=timezone.utc)
CENTRE = (12.4823, 41.8960)
SETTINGS = Settings.load()
ROOT_DIR = Path(__file__).resolve().parents[1]


# --- geometry helpers ---------------------------------------------------------

def test_offset_and_distance_agree() -> None:
    lon, lat = offset(*CENTRE, east_m=300.0, north_m=400.0)
    assert abs(distance_m(*CENTRE, lon, lat) - 500.0) < 1.0


# --- loops: settings-driven and versioned -------------------------------------

def test_loops_read_station_positions_from_a_geojson_file(tmp_path: Path) -> None:
    stations = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [12.49, 41.90]},
         "properties": {"road_class": "primary"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [12.52, 41.88]}, "properties": {}},
    ]}
    path = tmp_path / "stations.geojson"
    path.write_text(json.dumps(stations), encoding="utf-8")
    provider = SimLoopsProvider(seed=5, stations_path=path)
    observations = list(provider.fetch(ROME_BBOX, T0, T0))
    assert [(obs.lon, obs.lat) for obs in observations] == [(12.49, 41.90), (12.52, 41.88)]


def test_loops_from_settings_carry_the_simulator_version() -> None:
    provider = SimLoopsProvider.from_settings(SETTINGS)
    assert SETTINGS.simulator_version in provider.describe().notes
    assert len(list(provider.fetch(ROME_BBOX, T0, T0))) == 93


def test_committed_loop_seed_sits_on_major_roads_at_controlled_signals() -> None:
    seed = ROOT_DIR / "twin/providers/simulated/seed_data/loop_stations.geojson"
    data = json.loads(seed.read_text(encoding="utf-8"))
    features = data["features"]
    assert len(features) == 93
    for feature in features:
        props = feature["properties"]
        assert props["road_class"] in {"motorway", "trunk", "primary", "secondary"}
        assert props["control_system"] and props["road_name"]
    points = [tuple(f["geometry"]["coordinates"]) for f in features]
    closest = min(distance_m(*a, *b) for i, a in enumerate(points) for b in points[i + 1:])
    assert closest >= 600.0
    provider = SimLoopsProvider.from_settings(SETTINGS)
    assert "signalised junctions" in provider.describe().notes
    assert {(obs.lon, obs.lat) for obs in provider.fetch(ROME_BBOX, T0, T0)} == set(points)


def test_loop_selection_keeps_controlled_vehicle_signals_near_major_roads() -> None:
    from twin.providers.build_seeds import select_loop_stations

    road = {"type": "Feature", "properties": {"code": 5113, "name": "Via Nomentana"},
            "geometry": {"type": "LineString", "coordinates": [[12.50, 41.91], [12.52, 41.91]]}}
    track = {"type": "Feature", "properties": {"code": 5141, "name": "Vicolo"},
             "geometry": {"type": "LineString", "coordinates": [[12.50, 41.95], [12.52, 41.95]]}}

    def signal(lon: float, lat: float, kind: str = "V", system: str | None = "Omnia") -> dict[str, object]:
        return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {"TIPO": kind, "SISTEMA_1": system, "COD_IMP": "1"}}

    signals = {"features": [
        signal(12.505, 41.9101),                # on the primary road: kept
        signal(12.5052, 41.9101),               # 17 m from the first: dropped by spacing
        signal(12.515, 41.9101, kind="P"),      # pedestrian signal: dropped
        signal(12.516, 41.9101, system=None),   # not centrally controlled: dropped
        signal(12.51, 41.9501),                 # next to a minor road only: dropped
    ]}
    result = select_loop_stations(signals, {"features": [road, track]}, n_stations=10, snap_m=40.0,
                                  spacing_m=600.0, seed=1)
    assert [f["properties"]["road_name"] for f in result["features"]] == ["Via Nomentana"]


def test_point_in_polygon_respects_holes() -> None:
    from twin.providers.build_seeds import in_polygons

    square = [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)],
              [(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0), (4.0, 4.0)]]
    assert in_polygons(1.0, 1.0, [square])
    assert not in_polygons(5.0, 5.0, [square])
    assert not in_polygons(11.0, 5.0, [square])
