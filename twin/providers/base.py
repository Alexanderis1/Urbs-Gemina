"""Provider contract: every data source, real or simulated, looks the same.

A layer of the twin (traffic flow, antenna register, air quality...) has exactly
one active provider, chosen in config/providers.yaml. The public administration
goes live by switching a layer from a simulated provider to its own ("pa") one.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Literal, Protocol, runtime_checkable

ProviderKind = Literal["open", "simulated", "pa", "restricted"]

#: (min_lon, min_lat, max_lon, max_lat) in WGS84
BBox = tuple[float, float, float, float]

#: Rough bounding box of Roma Capitale, used as the default extent.
ROME_BBOX: BBox = (12.234, 41.655, 12.856, 42.141)


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    kind: ProviderKind
    layer: str
    licence: str
    cadence: str
    #: True when values are generated, not measured. Must reach the UI as a badge.
    synthetic: bool
    #: False when the data may be read at runtime but not copied or republished.
    redistribution: bool = True
    notes: str = ""


@dataclass(frozen=True)
class Observation:
    entity_id: str
    #: Smart Data Models type where one exists, e.g. "TrafficFlowObserved".
    entity_type: str
    lon: float
    lat: float
    observed_at: datetime
    values: dict[str, float]
    #: One standard deviation per value, same keys as ``values``.
    sigma: dict[str, float]
    #: Provider id (plus snapshot hash where available) for provenance.
    source_id: str
    synthetic: bool


@runtime_checkable
class Provider(Protocol):
    def describe(self) -> ProviderInfo: ...

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterable[Observation]: ...


class ProviderNotConfigured(RuntimeError):
    """Raised when a provider exists in the design but has no access yet."""
