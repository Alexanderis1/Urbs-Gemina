"""Simulated road loop stations (flow, speed, occupancy every 5 minutes).

Stand-in for Roma Mobilita's loop network, which is not public. Values are a
daily profile times noise, reproducible from the seed. Station positions come
from a GeoJSON of points on main arterials when ``stations_path`` exists (built
from OSM by the ingest stream); otherwise they are placeholders inside the
bounding box. Every record is flagged ``synthetic=True``.
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Mapping, Sequence

from twin.providers.base import BBox, Observation, ProviderInfo, ROME_BBOX
from twin.providers.settings import Settings, integer, number

STEP = timedelta(minutes=5)


def daily_profile(hour: float) -> float:
    """Share of peak flow by hour of day: two rush-hour bumps over a night floor."""
    morning = math.exp(-((hour - 8.5) ** 2) / (2 * 1.5**2))
    evening = math.exp(-((hour - 18.0) ** 2) / (2 * 2.0**2))
    return 0.12 + 0.88 * max(morning, 0.9 * evening)


def read_station_points(path: Path) -> list[tuple[float, float, str | None]]:
    """(lon, lat, road_class) of each Point in a GeoJSON FeatureCollection, in file order."""
    data = json.loads(path.read_text(encoding="utf-8"))
    points: list[tuple[float, float, str | None]] = []
    for feature in data.get("features", []):
        geometry = feature.get("geometry") or {}
        if geometry.get("type") == "Point":
            lon, lat = geometry["coordinates"][:2]
            road_class = (feature.get("properties") or {}).get("road_class")
            points.append((float(lon), float(lat), str(road_class) if road_class else None))
    return points


class SimLoopsProvider:
    def __init__(
        self,
        seed: int = 42,
        n_stations: int = 93,
        area: BBox = ROME_BBOX,
        stations_path: Path | None = None,
        version: str = "sim-unversioned",
        peak_flow_vph: tuple[float, float] = (600.0, 2400.0),
        free_speeds_kmh: Sequence[float] = (30.0, 50.0, 70.0),
        noise_flow: float = 0.08,
        noise_speed: float = 0.05,
        class_peak_flow_vph: Mapping[str, tuple[float, float]] | None = None,
        class_free_speed_kmh: Mapping[str, float] | None = None,
    ) -> None:
        self._seed = seed
        self._version = version
        self._noise_flow = noise_flow
        self._noise_speed = noise_speed
        class_peak = class_peak_flow_vph or {}
        class_speed = class_free_speed_kmh or {}
        rng = random.Random(seed)
        min_lon, min_lat, max_lon, max_lat = area
        positions: list[tuple[float, float, str | None]]
        if stations_path is not None and stations_path.exists():
            positions = read_station_points(stations_path)
            self._positions_note = f"stations at signalised junctions on major roads ({stations_path.name})"
        else:
            positions = [(rng.uniform(min_lon, max_lon), rng.uniform(min_lat, max_lat), None)
                         for _ in range(n_stations)]
            self._positions_note = "placeholder positions (no stations seed file)"
        self._stations: list[tuple[str, float, float, float, float]] = []
        for i, (lon, lat, road_class) in enumerate(positions):
            peak_range = class_peak.get(road_class or "", peak_flow_vph)
            peak = rng.uniform(*peak_range)  # peak flow, vehicles per hour
            if road_class and road_class in class_speed:
                free_speed = float(class_speed[road_class])
            else:
                free_speed = float(rng.choice(list(free_speeds_kmh)))  # free-flow speed, km/h
            self._stations.append((f"urn:ngsi-ld:TrafficFlowObserved:sim-loop-{i:03d}", lon, lat, peak, free_speed))

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "SimLoopsProvider":
        settings = settings or Settings.load()
        config = settings.section("simulators", "loops")
        peaks = {str(k): (float(v["min"]), float(v["max"]))
                 for k, v in (config.get("peak_flow_vph", {}) or {}).items() if isinstance(v, dict)}
        speeds = {str(k): float(v) for k, v in (config.get("free_speed_kmh", {}) or {}).items() if k != "basis"}
        return cls(
            seed=integer(config, "seed", 42),
            n_stations=integer(config, "n_stations", 93),
            stations_path=settings.path(str(config.get("stations_path", ""))),
            version=settings.simulator_version,
            peak_flow_vph=peaks.get("default", (600.0, 2400.0)),
            free_speeds_kmh=[speeds.get("default", 50.0)],
            noise_flow=number(config, "noise_flow", 0.08),
            noise_speed=number(config, "noise_speed", 0.05),
            class_peak_flow_vph=peaks,
            class_free_speed_kmh=speeds,
        )

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            id="sim_loops",
            kind="simulated",
            layer="traffic_flow",
            licence="generated (no licence)",
            cadence="5 min",
            synthetic=True,
            notes=(f"{self._version}. Placeholder for Roma Mobilita loop stations (DATEX II); "
                   f"{self._positions_note}."),
        )

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        min_lon, min_lat, max_lon, max_lat = bbox
        slot = _floor_to_step(start)
        if slot < start:
            slot += STEP
        while slot <= end:
            hour = slot.hour + slot.minute / 60.0
            load = daily_profile(hour)
            for index, (entity_id, lon, lat, peak, free_speed) in enumerate(self._stations):
                if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
                    continue
                # One generator per (seed, station, slot) keeps values reproducible
                # whatever window is requested.
                rng = random.Random(f"{self._seed}:{index}:{slot.isoformat()}")
                flow = max(0.0, peak * load * rng.gauss(1.0, self._noise_flow))
                speed = max(5.0, free_speed * (1.0 - 0.55 * load) * rng.gauss(1.0, self._noise_speed))
                occupancy = min(100.0, 100.0 * flow / (speed * 140.0))
                yield Observation(
                    entity_id=entity_id,
                    entity_type="TrafficFlowObserved",
                    lon=lon,
                    lat=lat,
                    observed_at=slot,
                    values={
                        "intensity": round(flow, 1),
                        "averageVehicleSpeed": round(speed, 1),
                        "occupancy": round(occupancy, 2),
                    },
                    sigma={
                        "intensity": round(self._noise_flow * flow, 1),
                        "averageVehicleSpeed": round(self._noise_speed * speed, 1),
                        "occupancy": 2.0,
                    },
                    source_id="sim_loops",
                    synthetic=True,
                )
            slot += STEP


def _floor_to_step(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    minute = moment.minute - moment.minute % 5
    return moment.replace(minute=minute, second=0, microsecond=0)
