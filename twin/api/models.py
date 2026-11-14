"""Strict request models of the tool API. Their JSON schemas are published in ``twin/api/schemas``."""
from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _in_rome(point: list[float]) -> list[float]:
    lon, lat = point
    if not (12.0 <= lon <= 13.1 and 41.4 <= lat <= 42.4):
        raise ValueError("point must be [lon, lat] in WGS84 inside the Rome area")
    return point


#: A point as GeoJSON orders it: [lon, lat] in WGS84.
Point = Annotated[list[float], Field(min_length=2, max_length=2, description="[lon, lat] WGS84"),
                  AfterValidator(_in_rome)]


#: "city", "municipio:<id>", "zone:<id>" or a GeoJSON Polygon / MultiPolygon in WGS84.
Area = Union[str, dict[str, Any]]
AREA_DESCRIPTION = ("Operating area: 'city', 'municipio:<n>' (1-15), 'zone:<CODE>' (urban-zone code, upper case) "
                    "or a GeoJSON Polygon/MultiPolygon in WGS84 [lon, lat].")


class Antenna(Strict):
    lon: float = Field(ge=12.0, le=13.1)
    lat: float = Field(ge=41.4, le=42.4)
    height_m: float | None = Field(default=None, gt=0, le=300, description="Height above ground; default from config")
    eirp_w: float | None = Field(default=None, ge=0, le=100_000, description="Total EIRP in watts")
    band_mhz: Literal[800, 1800, 2100, 3500] | None = Field(
        default=None, description="Used for a typical EIRP when eirp_w is missing (assumption)")


class Variant(Strict):
    add_antennas: list[Antenna] = Field(default_factory=list, max_length=20)


class ResolvePlaceIn(Strict):
    """Turn an address, place name or 'lat, lon' into coordinates, municipio and urban zone."""

    text: str = Field(min_length=2, max_length=300)


class ContextCheckIn(Strict):
    """List sensitive sites and constraints within a radius (default 300 m). Distance is context, not a ban."""

    point: Point
    radius_m: float | None = Field(default=None, gt=0, le=2000)


class EstimateFieldIn(Strict):
    """Electric field P5/P50/P95 in V/m and probability of exceeding the legal thresholds, at a point or over an area."""

    point: Point | None = None
    area: Area | None = Field(default=None, description=AREA_DESCRIPTION)
    variant: Variant | None = Field(default=None, description="Proposed change, e.g. antennas to add")


class QueryLayerIn(Strict):
    """Values of a layer (belief, live/simulated provider, or static context layer) inside an area at a time."""

    layer: str = Field(min_length=1, max_length=80)
    area: Area = Field(default="city", description=AREA_DESCRIPTION)
    time: str | None = Field(default=None, description="ISO 8601; default now")
    limit: int | None = Field(default=None, ge=1, le=5000)


class RunScenarioIn(Strict):
    """Run a what-if scenario on an operating area: baseline vs variant with ranges."""

    kind: str = Field(min_length=1, max_length=80)
    area: Area = Field(description=AREA_DESCRIPTION)
    change: dict[str, Any] = Field(default_factory=dict)


class LegalLookupIn(Strict):
    """Search official legal sources (normattiva, gazzetta ufficiale, AgID, ...) and return URLs with retrieval time."""

    question: str = Field(min_length=3, max_length=500)


class FindDatasetIn(Strict):
    """Find an open dataset for a need: publisher, licence, format, update cadence."""

    need: str = Field(min_length=3, max_length=500)


class DataStatusIn(Strict):
    """Honesty panel: every layer with provider, real/estimated/simulated, licence and last update."""


class PermitReportIn(Strict):
    """Cited permit-context report: location, 300 m context, field estimate, legal references, provenance."""

    place: str | None = Field(default=None, min_length=2, max_length=300)
    point: Point | None = None
    proposed_antennas: list[Antenna] | None = Field(default=None, max_length=20)
    radius_m: float | None = Field(default=None, gt=0, le=2000)


class SportsFacilitiesIn(Strict):
    """Sports facilities (Challenge 04) in an area: merged official, school and web sources. Web-derived fields are labelled "from the web, unverified"."""

    area: Area = Field(default="city", description=AREA_DESCRIPTION)
    discipline: str | None = Field(default=None, max_length=60)
    type: Literal["public", "school", "private"] | None = Field(
        default=None, description="private = known only from OpenStreetMap or the web")
    accessible: bool | None = Field(default=None, description="true keeps only facilities a source states are accessible")


class SchoolGym(Strict):
    name: str = Field(min_length=1, max_length=120)
    lon: float = Field(ge=12.0, le=13.1)
    lat: float = Field(ge=41.4, le=42.4)
    disciplines: list[str] | None = None


class SportCoverageIn(Strict):
    """Sport deserts: residents without a facility for a discipline within walking time; optional what-if opening school gyms (simulated)."""

    area: Area = Field(default="city", description=AREA_DESCRIPTION)
    discipline: str = Field(min_length=1, max_length=60)
    max_minutes: float | None = Field(default=None, ge=0, le=60, description="Walking time; default from config")
    open_school_gyms: list[SchoolGym] = Field(default_factory=list, max_length=10)


class AskIn(Strict):
    """A question for the orchestrator (chat). The tier is set by the server from the API key."""

    question: str = Field(min_length=1, max_length=2000)
    language: Literal["it", "en"] = "it"
    area: str | None = Field(default=None, max_length=200)
    mode: Literal["question", "briefing"] = "question"
    conversation_id: str | None = Field(default=None, max_length=200)
    use_case: str | None = Field(default=None, max_length=60, description="Playbook id from GET /use_cases")
    params: dict[str, Any] = Field(default_factory=dict, description="Playbook inputs, e.g. {\"place\": \"Circo Massimo\"}")


class SourceOut(BaseModel):
    id: str
    url: str | None = None
    retrieved_at: str


class EnvelopeOut(BaseModel):
    """Response of every tool (shared interface 3)."""

    run_id: str = Field(description="SHA-256 of tool name + inputs + data snapshot hashes + config file hashes")
    tool: str
    status: Literal["ok", "not_available", "refused"] = Field(
        description="not_available: an input is missing; refused: a guardrail said no")
    reason: str | None = Field(default=None, description="Why the status is not ok")
    inputs: dict[str, Any]
    result: Any
    data_kinds: dict[str, Literal["real", "estimated", "simulated", "not_available"]]
    sources: list[SourceOut]
    synthetic: bool
    warnings: list[str]
    cached: bool = False
