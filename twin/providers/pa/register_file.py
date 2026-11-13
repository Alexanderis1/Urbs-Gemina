"""The administration's own installation register, from a GeoJSON export.

Switch ``antenna_register: pa_register_file`` in config/providers.yaml and set
``pa.register_file.path`` in config/provider_settings.yaml: the twin then reads
real records with the same field names as the simulated register (Model A
fields, see ``twin.providers.simulated.register.MODEL_A_FIELDS``). No code
changes. Records are real, so ``synthetic=False``.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from twin.providers.base import BBox, Observation, ProviderInfo, ProviderNotConfigured
from twin.providers.geo import in_bbox
from twin.providers.settings import Settings

PROVIDER_ID = "pa_register_file"


class PaRegisterFileProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or Settings.load()
        config = settings.section("pa", "register_file")
        path = settings.path(str(config.get("path", "") or ""))
        if path is None or not path.exists():
            raise ProviderNotConfigured(
                f"Provider '{PROVIDER_ID}' needs the administration's register export: set pa.register_file.path "
                "in config/provider_settings.yaml to a GeoJSON file with Model A fields.")
        self._path: Path = path
        self._licence = str(config.get("licence", "Roma Capitale, internal"))

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            id=PROVIDER_ID,
            kind="pa",
            layer="antenna_register",
            licence=self._licence,
            cadence="as exported",
            synthetic=False,
            notes=f"Administration register export ({self._path.name}).",
        )

    def records(self) -> list[dict[str, Any]]:
        data = json.loads(self._path.read_text(encoding="utf-8"))
        out = []
        for feature in data.get("features", []):
            lon, lat = feature["geometry"]["coordinates"][:2]
            out.append({**(feature.get("properties") or {}), "lon": float(lon), "lat": float(lat), "synthetic": False})
        return out

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        end_aware = end if end.tzinfo is not None else end.replace(tzinfo=timezone.utc)
        for record in self.records():
            when = record.get("application_date")
            observed = (datetime.combine(date.fromisoformat(str(when)), datetime.min.time(), tzinfo=timezone.utc)
                        if when else datetime(1970, 1, 1, tzinfo=timezone.utc))
            if observed > end_aware or not in_bbox(record["lon"], record["lat"], bbox):
                continue
            sectors = record.get("sectors") or []
            total = record.get("total_eirp_w")
            if total is None:
                total = sum(float(s.get("eirp_w", 0.0)) for s in sectors)
            values = {"total_eirp_w": float(total), "n_sectors": float(len(sectors))}
            if record.get("antenna_height_agl_m") is not None:
                values["antenna_height_agl_m"] = float(record["antenna_height_agl_m"])
            yield Observation(
                entity_id=f"urn:ngsi-ld:AntennaSite:{record.get('site_id', '')}",
                entity_type="AntennaSite",
                lon=record["lon"],
                lat=record["lat"],
                observed_at=observed,
                values=values,
                sigma={key: 0.0 for key in values},
                source_id=f"{PROVIDER_ID}@{self._path.name}",
                synthetic=False,
            )
