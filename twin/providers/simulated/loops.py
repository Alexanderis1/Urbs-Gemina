"""Simulated road loop stations (flow, speed, occupancy every 5 minutes).

Stand-in for Roma Mobilita's loop network, which is not public. Values are a
daily profile times noise, reproducible from the seed. Station positions are
placeholders inside the bounding box until they are snapped to main arterials.
Every record is flagged ``synthetic=True``.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Iterator

from twin.providers.base import BBox, Observation, ProviderInfo, ROME_BBOX

STEP = timedelta(minutes=5)


def daily_profile(hour: float) -> float:
    """Share of peak flow by hour of day: two rush-hour bumps over a night floor."""
    morning = math.exp(-((hour - 8.5) ** 2) / (2 * 1.5**2))
    evening = math.exp(-((hour - 18.0) ** 2) / (2 * 2.0**2))
    return 0.12 + 0.88 * max(morning, 0.9 * evening)


class SimLoopsProvider:
    def __init__(self, seed: int = 42, n_stations: int = 93, area: BBox = ROME_BBOX) -> None:
        self._seed = seed
        rng = random.Random(seed)
        min_lon, min_lat, max_lon, max_lat = area
        self._stations = [
            (
                f"urn:ngsi-ld:TrafficFlowObserved:sim-loop-{i:03d}",
                rng.uniform(min_lon, max_lon),
                rng.uniform(min_lat, max_lat),
                rng.uniform(600.0, 2400.0),  # peak flow, vehicles per hour
                rng.choice([30.0, 50.0, 70.0]),  # free-flow speed, km/h
            )
            for i in range(n_stations)
        ]

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            id="sim_loops",
            kind="simulated",
            layer="traffic_flow",
            licence="generated (no licence)",
            cadence="5 min",
            synthetic=True,
            notes="Placeholder for Roma Mobilita loop stations (DATEX II).",
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
                flow = max(0.0, peak * load * rng.gauss(1.0, 0.08))
                speed = max(5.0, free_speed * (1.0 - 0.55 * load) * rng.gauss(1.0, 0.05))
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
                        "intensity": round(0.08 * flow, 1),
                        "averageVehicleSpeed": round(0.05 * speed, 1),
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
