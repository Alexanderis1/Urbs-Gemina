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

#: OSM operator:type values that state who runs a facility.
PRIVATE_OPERATOR_TYPES = frozenset({"private", "business", "commercial", "company"})
PUBLIC_OPERATOR_TYPES = frozenset({"public", "government", "municipal", "community"})

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

    @property
    def closed(self) -> bool:
        """True when a source says it is closed: web "appears_closed" or official "attivo = NO"."""
        flag = self.extra.get("appears_closed")
        active = self.extra.get("active")
        return (flag is not None and flag.value is True) or (
            active is not None and str(active.value).strip().upper() == "NO")

    def offers(self, discipline: str, include_unverified: bool = True) -> bool:
        if self.closed:
            return False
        value = self.disciplines.get(discipline)
        if value is None:
            return False
        return include_unverified or value.status != "web_unverified"

    @property
    def facility_type(self) -> str:
        """public | school | private | unclassified. Never inferred: "private" only when a source says so
        (OSM ``operator:type``); without such a statement the type is "unclassified" ("type not known")."""
        if self.fields["kind"].value == "school_gym":
            return "school"
        if any(SOURCE_STATUS.get(m.split(":", 1)[0]) in ("official", "manager_confirmed") for m in self.members):
            return "public"
        stated = self.extra.get("operator:type")
        value = str(stated.value).strip().lower() if stated is not None else ""
        if value in PRIVATE_OPERATOR_TYPES:
            return "private"
        if value in PUBLIC_OPERATOR_TYPES:
            return "public"
        return "unclassified"

    @property
    def accessible(self) -> bool | None:
        """True/False only when a source states it; None means "not known"."""
        acc = self.fields.get("accessibility", NOT_KNOWN)
        if acc.status == "not_known" or acc.value in (None, ""):
            return None
        text = str(acc.value).strip().lower()
        if text in ("false", "no", "non accessibile", "not accessible") or text.startswith(("non ", "not ", "no ")):
            return False
        return True

    def to_feature(self) -> dict[str, Any]:
        """GeoJSON Feature for the map and the facility page."""
        geometry = None if self.lon is None or self.lat is None else {
            "type": "Point", "coordinates": [round(self.lon, 7), round(self.lat, 7)]}
        props: dict[str, Any] = {
            "facility_id": self.facility_id,
            "name": self.fields["name"].value,
            "kind": self.fields["kind"].value,
            "municipio": self.fields["municipio"].value,
            "type": self.facility_type,
            "accessible": self.accessible,
            "closed": self.closed,
            "disciplines": sorted(self.disciplines),
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
            "discipline_details": {k: v.to_dict() for k, v in sorted(self.disciplines.items())},
            "extra": {k: v.to_dict() for k, v in sorted(self.extra.items())},
            "members": list(self.members),
            "synthetic": self.synthetic,
        }
        return {"type": "Feature", "id": self.facility_id, "geometry": geometry, "properties": props}


def _fv(d: Mapping[str, Any]) -> FieldValue:
    return FieldValue(value=d.get("value"), status=d.get("status", "not_known"),
                      provenance=tuple(Provenance(**src) for src in d.get("sources", [])), label=d.get("label"))


def facility_from_feature(feature: Mapping[str, Any]) -> Facility:
    """Inverse of :meth:`Facility.to_feature` (for the API reading data/processed/sports/facilities.geojson)."""
    props = feature["properties"]
    coords = (feature.get("geometry") or {}).get("coordinates")
    return Facility(
        facility_id=str(props["facility_id"]),
        lon=float(coords[0]) if coords else None, lat=float(coords[1]) if coords else None,
        fields={k: _fv(v) for k, v in props["fields"].items()},
        disciplines={k: _fv(v) for k, v in props["discipline_details"].items()},
        members=tuple(props["members"]), synthetic=bool(props.get("synthetic", False)),
        extra={k: _fv(v) for k, v in props.get("extra", {}).items()},
    )
