"""ARPA Lazio EMF measurement points (layer ``emf_measurements``). Real, open.

ARPA Lazio measures the electric field at addresses on request (art. 14,
L. 36/2001); Roma Capitale publishes the results as open data, and ARPA runs a
continuous station in Via Boncompagni whose monthly reports are graphs only.
This provider reads a table of those measurements in a fixed schema:

    lon, lat, measured_on (YYYY-MM-DD), e_v_m [, uncertainty_v_m] [, location]

The table path is set in ``config/provider_settings.yaml`` (open.arpa_points).
Until it exists the provider raises ``ProviderNotConfigured``, so the layer
shows "not available" instead of anything made up. Personal data (names of
the people who asked for a measurement) must not be in the table.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone
from typing import Iterator

from twin.providers.base import BBox, Observation, ProviderInfo, ProviderNotConfigured
from twin.providers.geo import in_bbox
from twin.providers.settings import Settings, number

PROVIDER_ID = "arpa_points"
FORBIDDEN_COLUMNS = ("nome", "cognome", "name", "esponente", "richiedente", "tel", "mail")


def parse_measurements(text: str, relative_sigma: float, source_id: str) -> list[Observation]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    columns = [c.lower() for c in reader.fieldnames or []]
    if any(hint in column for column in columns for hint in FORBIDDEN_COLUMNS):
        raise ValueError("ARPA table contains personal-data columns; drop them at ingest")
    out: list[Observation] = []
    for index, row in enumerate(reader):
        try:
            lon, lat, value = float(row["lon"]), float(row["lat"]), float(row["e_v_m"])
            measured = date.fromisoformat(row["measured_on"].strip())
        except (KeyError, ValueError):
            continue
        given = (row.get("uncertainty_v_m") or "").strip()
        sigma = float(given) if given else relative_sigma * value
        out.append(Observation(
            entity_id=f"urn:ngsi-ld:ElectromagneticFieldObserved:arpa-{index:05d}",
            entity_type="ElectromagneticFieldObserved",
            lon=lon,
            lat=lat,
            observed_at=datetime.combine(measured, datetime.min.time(), tzinfo=timezone.utc),
            values={"electricField": value},
            sigma={"electricField": round(sigma, 4)},
            source_id=source_id,
            synthetic=False,
        ))
    return out


class ArpaPointsProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or Settings.load()
        config = settings.section("open", PROVIDER_ID)
        path = settings.path(str(config.get("table_path", "") or ""))
        if path is None or not path.exists():
            raise ProviderNotConfigured(
                f"Provider '{PROVIDER_ID}' has no measurement table yet: set open.arpa_points.table_path in "
                "config/provider_settings.yaml (ARPA Lazio results published on dati.comune.roma.it).")
        self._path = path
        self._relative_sigma = number(config, "relative_sigma", 0.26)

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            id=PROVIDER_ID,
            kind="open",
            layer="emf_measurements",
            licence="Roma Capitale open data (credit ARPA Lazio / Roma Capitale)",
            cadence="campaigns (static table)",
            synthetic=False,
            notes=f"Real ARPA Lazio measurements from {self._path.name}. Credit: ARPA Lazio.",
        )

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        end_aware = end if end.tzinfo is not None else end.replace(tzinfo=timezone.utc)
        text = self._path.read_text(encoding="utf-8")
        for obs in parse_measurements(text, self._relative_sigma, f"{PROVIDER_ID}@{self._path.name}"):
            if obs.observed_at <= end_aware and in_bbox(obs.lon, obs.lat, bbox):
                yield obs
