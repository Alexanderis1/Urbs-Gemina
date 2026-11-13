"""Simulated EMF monitoring points (layer ``emf_measurements``).

Stand-in for ARPA Lazio's measurement points. Each point sits near a site of the
simulated register. Its hourly value is the free-space field of the register's
sites within ``radius_m`` (scaled by the hour's network load and an off-axis
factor) combined with a background, times a log-normal error whose spread is
the model error in ``config/emf_params.yaml``. Every record is ``synthetic=True``.
The real ARPA rooftop station stays a separate, real point.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator

from twin.providers.base import BBox, Observation, ProviderInfo
from twin.providers.geo import distance_m, in_bbox, offset
from twin.providers.settings import Settings, integer, number, value
from twin.providers.simulated.register import SimRegisterProvider
from twin.tools.emf import free_space_field

PROVIDER_ID = "sim_emf_points"
RECEIVER_HEIGHT_M = 1.5


@dataclass(frozen=True)
class _Point:
    point_id: str
    lon: float
    lat: float
    #: Sum of squared fields (V/m)^2 of nearby sites at full load.
    full_load_sq: float


def network_load(hour: float, night: float, peak: float) -> float:
    """Share of peak transmit power by hour: lowest around 04:00, highest around 16:00."""
    shape = 0.5 - 0.5 * math.cos(2.0 * math.pi * (hour - 4.0) / 24.0)
    return night + (peak - night) * shape


class SimEmfPointsProvider:
    def __init__(self, settings: Settings | None = None, register: SimRegisterProvider | None = None) -> None:
        self._settings = settings or Settings.load()
        self._config = self._settings.section("simulators", "emf_points")
        self._register = register or SimRegisterProvider(self._settings)
        self._seed = integer(self._config, "seed", 42)
        self._version = self._settings.simulator_version
        self._sigma_db = float(value(self._settings.emf.get("model_error_sigma_db"), 4.0))
        self._step = timedelta(minutes=integer(self._config, "cadence_minutes", 60))
        load = self._config.get("load_profile", {}) or {}
        self._night = float(load.get("night", 0.35))
        self._peak = float(load.get("peak", 1.0))
        self._background = number(self._config, "background_v_m", 0.2)
        self._points: list[_Point] | None = None

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            id=PROVIDER_ID,
            kind="simulated",
            layer="emf_measurements",
            licence="generated (no licence)",
            cadence=f"{int(self._step.total_seconds() // 60)} min",
            synthetic=True,
            notes=(f"{self._version}. Free-space field of the simulated register x log-normal error "
                   f"({self._sigma_db} dB). Placeholder for ARPA Lazio measurement points."),
        )

    def points(self) -> list[_Point]:
        if self._points is None:
            self._points = self._place_points()
        return self._points

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        spread = 10.0 ** (self._sigma_db / 20.0) - 1.0
        slot = _ceil_to_step(_aware(start), self._step)
        while slot <= _aware(end):
            load = network_load(slot.hour + slot.minute / 60.0, self._night, self._peak)
            for index, point in enumerate(self.points()):
                if not in_bbox(point.lon, point.lat, bbox):
                    continue
                rng = random.Random(f"{self._seed}:{self._version}:{index}:{slot.isoformat()}")
                model = math.sqrt(self._background**2 + load * point.full_load_sq)
                measured = model * 10.0 ** (rng.gauss(0.0, self._sigma_db) / 20.0)
                yield Observation(
                    entity_id=f"urn:ngsi-ld:ElectromagneticFieldObserved:{point.point_id}",
                    entity_type="ElectromagneticFieldObserved",
                    lon=point.lon,
                    lat=point.lat,
                    observed_at=slot,
                    values={"electricField": round(measured, 3)},
                    sigma={"electricField": round(max(measured * spread, 0.001), 3)},
                    source_id=PROVIDER_ID,
                    synthetic=True,
                )
            slot += self._step

    def _place_points(self) -> list[_Point]:
        sites = self._register.sites()
        if not sites:
            return []
        rng = random.Random(f"{self._seed}:{self._version}:points")
        n_points = integer(self._config, "n_points", 40)
        dist = self._config.get("distance_from_site_m", {}) or {}
        d_min, d_max = float(dist.get("min", 30)), float(dist.get("max", 250))
        radius = number(self._config, "radius_m", 1000.0)
        off_axis = number(self._config, "off_axis_factor", 0.1)
        points: list[_Point] = []
        for i in range(n_points):
            anchor = sites[rng.randrange(len(sites))]
            bearing = rng.uniform(0.0, 2.0 * math.pi)
            d = rng.uniform(d_min, d_max)
            lon, lat = offset(anchor.lon, anchor.lat, east_m=d * math.sin(bearing), north_m=d * math.cos(bearing))
            total = 0.0
            for site in sites:
                ground = distance_m(lon, lat, site.lon, site.lat)
                if ground > radius:
                    continue
                slant = math.hypot(ground, site.antenna_height_agl_m - RECEIVER_HEIGHT_M)
                total += free_space_field(site.total_eirp_w * off_axis, slant) ** 2
            points.append(_Point(f"sim-emf-{i + 1:03d}", round(lon, 6), round(lat, 6), total))
        return points


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


def _ceil_to_step(moment: datetime, step: timedelta) -> datetime:
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    seconds = int(step.total_seconds())
    elapsed = int((moment - epoch).total_seconds())
    return epoch + timedelta(seconds=-(-elapsed // seconds) * seconds)
