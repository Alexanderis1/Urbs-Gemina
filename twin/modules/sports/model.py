"""Records of the sports module.

A ``Candidate`` is one facility as one source describes it. A ``Facility`` is
the merged record: every field keeps its status and where it came from, so the
UI can show "official", "from the web, unverified" or "confirmed by manager".
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal, Mapping

#: How far a field value can be trusted, from most to least.
FieldStatus = Literal["manager_confirmed", "official", "open_data", "web_unverified", "simulated", "not_known"]

#: Status given to every field coming from a source, by source id.
SOURCE_STATUS: dict[str, FieldStatus] = {
    "manager": "manager_confirmed",
    "roma_sports_municipal": "official",
    "roma_pools": "official",
    "roma_d30_centres": "official",
    "school_gyms": "official",
    "osm": "open_data",
    "web": "web_unverified",
    "what_if": "simulated",
}

#: Higher rank wins when a field is set by two sources.
STATUS_RANK: dict[FieldStatus, int] = {
    "manager_confirmed": 5, "official": 4, "open_data": 3, "web_unverified": 2, "simulated": 1, "not_known": 0,
}

#: Fields shown on the facility page. "not known" unless a source sets them.
STANDARD_FIELDS = ("name", "kind", "address", "municipio", "hours", "accessibility", "manager", "contact")

#: Facility kinds used for matching ("same kind, very close").
FacilityKind = str


@dataclass(frozen=True)
class Provenance:
    source: str
    record_id: str
    url: str | None = None
    retrieved_at: str | None = None
    confidence: float | None = None
    quote: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass(frozen=True)
class FieldValue:
    value: Any
    status: FieldStatus
    provenance: tuple[Provenance, ...] = ()
    #: Text the UI must show next to the value, e.g. "from the web, unverified".
    label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"value": self.value, "status": self.status,
                               "sources": [p.to_dict() for p in self.provenance]}
        if self.label:
            out["label"] = self.label
        return out


NOT_KNOWN = FieldValue(value=None, status="not_known")


@dataclass(frozen=True)
class Candidate:
    source: str
    record_id: str
    name: str
    lon: float | None
    lat: float | None
    kind: FacilityKind
    municipio: str | None
    address: str | None
    disciplines: frozenset[str]
    attributes: Mapping[str, Any]
    url: str | None = None
    retrieved_at: str | None = None
    confidence: float | None = None
    synthetic: bool = False

    @property
    def key(self) -> str:
        return f"{self.source}:{self.record_id}"

    @property
    def located(self) -> bool:
        return self.lon is not None and self.lat is not None

    def provenance(self, quote: str | None = None) -> Provenance:
        return Provenance(self.source, self.record_id, self.url, self.retrieved_at, self.confidence, quote)


@dataclass(frozen=True)
class Facility:
    facility_id: str
    lon: float | None
    lat: float | None
    fields: dict[str, FieldValue]
    disciplines: dict[str, FieldValue]
    members: tuple[str, ...]
    synthetic: bool = False
    extra: dict[str, FieldValue] = field(default_factory=dict)

    def with_changes(self, **changes: Any) -> Facility:
        return replace(self, **changes)

    def offers(self, discipline: str, include_unverified: bool = True) -> bool:
        value = self.disciplines.get(discipline)
        if value is None:
            return False
        return include_unverified or value.status != "web_unverified"

    def to_feature(self) -> dict[str, Any]:
        """GeoJSON Feature for the map and the facility page."""
        geometry = None if self.lon is None or self.lat is None else {
            "type": "Point", "coordinates": [round(self.lon, 7), round(self.lat, 7)]}
        props: dict[str, Any] = {
            "facility_id": self.facility_id,
            "name": self.fields["name"].value,
            "kind": self.fields["kind"].value,
            "municipio": self.fields["municipio"].value,
            "disciplines": sorted(self.disciplines),
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
            "discipline_details": {k: v.to_dict() for k, v in sorted(self.disciplines.items())},
            "extra": {k: v.to_dict() for k, v in sorted(self.extra.items())},
            "members": list(self.members),
            "synthetic": self.synthetic,
        }
        return {"type": "Feature", "id": self.facility_id, "geometry": geometry, "properties": props}
