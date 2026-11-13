"""Cartoradio national E-field grid (layer ``emf_baseline``). Restricted, estimated.

Source: MIMIT / Fondazione Ugo Bordoni, one cloud-optimised GeoTIFF of
estimated field values in V/m on 100 m Web Mercator cells (nodata -9999).
Its legal notes forbid reuse without written consent, which is pending. So:

- the Rome window is read **at runtime** by HTTP byte range (GDAL /vsicurl/),
  held in memory only, and never written to disk, the repo or any published
  dataset (``redistribution=False``);
- every value carries the credit "Fonte: Cartoradio - MIMIT/FUB" in notes;
- values at the cap (15 V/m in the inspected tile) are flagged ``at_cap=1``
  and should be read as "15 or more" (C=55);
- the one-sigma spread is a log-normal ``sigma_db`` (assumption, C=60).

The grid is a static snapshot, so ``fetch`` ignores the time window and stamps
every value with the snapshot date.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterator

from twin.providers.base import BBox, Observation, ProviderInfo
from twin.providers.raster import read_cells
from twin.providers.settings import Settings, number, text

PROVIDER_ID = "cartoradio_grid"
DEFAULT_URL = "https://d3r7svb6d8d7og.cloudfront.net/tiles/tiles/cartoradio.tiff"


class CartoradioGridProvider:
    def __init__(self, settings: Settings | None = None, source: str | None = None) -> None:
        settings = settings or Settings.load()
        config = settings.section("restricted", PROVIDER_ID)
        self.source = source or "/vsicurl/" + text(config, "url", DEFAULT_URL)
        self._credit = text(config, "credit", "Fonte: Cartoradio - MIMIT/FUB")
        self._date = date.fromisoformat(text(config, "data_date", "2026-09-08"))
        self._sigma_db = number(config, "sigma_db", 4.0)
        self._cap = number(config, "cap_v_m", 15.0)

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            id=PROVIDER_ID,
            kind="restricted",
            layer="emf_baseline",
            licence="reuse forbidden without written consent (MIMIT/FUB); consent pending",
            cadence=f"static snapshot {self._date.isoformat()}",
            synthetic=False,
            redistribution=False,
            notes=(f"{self._credit}. Estimated field, not a measurement. Read at runtime, never stored. "
                   f"Values at {self._cap:g} V/m mean '{self._cap:g} or more'."),
        )

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        observed = datetime.combine(self._date, datetime.min.time(), tzinfo=timezone.utc)
        spread = 10.0 ** (self._sigma_db / 20.0) - 1.0
        for cell in read_cells(self.source, bbox):
            if cell.value < 0.0:
                continue
            yield Observation(
                entity_id=f"urn:ngsi-ld:EMFEstimate:cartoradio-r{cell.row}-c{cell.col}",
                entity_type="EMFEstimate",
                lon=cell.lon,
                lat=cell.lat,
                observed_at=observed,
                values={"electricField": round(cell.value, 3), "at_cap": 1.0 if cell.value >= self._cap else 0.0},
                sigma={"electricField": round(cell.value * spread, 3), "at_cap": 0.0},
                source_id=PROVIDER_ID,
                synthetic=False,
            )
