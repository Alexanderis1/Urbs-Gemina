"""Simulated permit inbox (layer ``antenna_applications``).

A handful of synthetic new-installation applications, listed in
``config/provider_settings.yaml``, used only to demonstrate the permit workflow.
Technical parameters are generated with the same tables as the simulated
register. Every record is ``synthetic=True``.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timezone
from typing import Any, Iterator

from twin.providers.base import BBox, Observation, ProviderInfo
from twin.providers.geo import in_bbox
from twin.providers.settings import Settings, integer, number, value

PROVIDER_ID = "sim_applications"


class SimApplicationsProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings.load()
        self._config = self._settings.section("simulators", "applications")
        self._register_config = self._settings.section("simulators", "register")
        self._emf = self._settings.emf.get("simulated_register", {}) or {}
        self._eirp_table = self._settings.emf.get("typical_eirp_w", {}) or {}
        self._seed = integer(self._config, "seed", 42)
        self._version = self._settings.simulator_version

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            id=PROVIDER_ID,
            kind="simulated",
            layer="antenna_applications",
            licence="generated (no licence)",
            cadence="on demand",
            synthetic=True,
            notes=f"{self._version}. Demonstration inbox; not real applications.",
        )

    def applications(self) -> list[dict[str, Any]]:
        records = []
        for item in self._config.get("items", []) or []:
            rng = random.Random(f"{self._seed}:{self._version}:{item['id']}")
            technology = str(item["technology"])
            bands = sorted(
                {str(b) for b in (self._register_config.get("technology_bands_mhz", {}) or {}).get(technology, [])},
                key=float,
            )
            per_sector = sum(float(value(self._eirp_table.get(band), 0.0)) for band in bands)
            azimuths = [float(a) for a in self._emf.get("sector_azimuths_deg", [0, 120, 240])]
            rotation = rng.uniform(0.0, 360.0 / max(1, len(azimuths)))
            mast = self._emf.get("mast_height_above_roof_m", {}) or {}
            tilt = self._emf.get("mechanical_tilt_deg", {}) or {}
            height = number(self._register_config, "building_height_m", 18.0) + rng.uniform(
                float(mast.get("min", 3)), float(mast.get("max", 6))
            )
            records.append({
                "application_id": str(item["id"]),
                "address": str(item["address"]),
                "lon": float(item["lon"]),
                "lat": float(item["lat"]),
                "operator": str(item["operator"]),
                "technologies": [technology],
                "bands_mhz": bands,
                "antenna_height_agl_m": round(height, 1),
                "sectors": [
                    {
                        "azimuth_deg": round((a + rotation) % 360.0, 1),
                        "mechanical_tilt_deg": round(rng.uniform(float(tilt.get("min", 2)), float(tilt.get("max", 8))), 1),
                        "eirp_w": round(per_sector, 1),
                    }
                    for a in azimuths
                ],
                "total_eirp_w": round(per_sector * len(azimuths), 1),
                "submitted": str(item["submitted"]),
                "status": "submitted",
                "synthetic": True,
                "simulator_version": self._version,
            })
        return records

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        end_aware = end if end.tzinfo is not None else end.replace(tzinfo=timezone.utc)
        for record in self.applications():
            submitted = datetime.combine(date.fromisoformat(record["submitted"]), datetime.min.time(), tzinfo=timezone.utc)
            if submitted > end_aware or not in_bbox(record["lon"], record["lat"], bbox):
                continue
            yield Observation(
                entity_id=f"urn:ngsi-ld:AntennaApplication:{record['application_id']}",
                entity_type="AntennaApplication",
                lon=record["lon"],
                lat=record["lat"],
                observed_at=submitted,
                values={
                    "total_eirp_w": record["total_eirp_w"],
                    "antenna_height_agl_m": record["antenna_height_agl_m"],
                    "n_sectors": float(len(record["sectors"])),
                },
                sigma={"total_eirp_w": 0.0, "antenna_height_agl_m": 0.0, "n_sectors": 0.0},
                source_id=PROVIDER_ID,
                synthetic=True,
            )
