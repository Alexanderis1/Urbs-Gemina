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
    group_by: str | None = Field(default=None, min_length=1, max_length=60,
                                 description="Static feature layers: also count all features in the area by this "
                                             "property (e.g. rischio, class_are, sottotipol)")


class CrowdsIn(Strict):
    """How busy each cell is (Wi-Fi sessions, activity, timetable supply) next to census residents, with a 'busy' flag."""

    area: Area = Field(default="city", description=AREA_DESCRIPTION)
    time: str | None = Field(default=None, description="ISO 8601; default now")


class ExposureIn(Strict):
    """Residents and children living where a layer is above a legal threshold, per municipio, expected value and range."""

    layer: Literal["emf", "air_no2", "air_pm10", "air_pm25", "air_o3"]
    area: Area = Field(default="city", description=AREA_DESCRIPTION)
    threshold: str = Field(min_length=1, max_length=60, description=(
        "emf: attention_value | exposure_limit; air_no2: no2_hourly_limit | no2_annual_limit; "
        "air_pm10: pm10_daily_limit | pm10_annual_limit; air_pm25: pm25_annual_limit; "
        "air_o3: o3_information_1h | o3_alert_1h | o3_target_8h"))
    time: str | None = Field(default=None, description="ISO 8601; default now")


class SiteValuesIn(Strict):
    """A belief layer read at each sensitive site (schools, hospitals...) in the area, riskiest first."""

    layer: str = Field(min_length=1, max_length=80, description="belief layer, e.g. emf, air_no2, air_pm10, rain")
    area: Area = Field(default="city", description=AREA_DESCRIPTION)
    threshold: str | None = Field(default=None, max_length=60,
                                  description="optional named legal threshold, same names as the exposure tool")
    categories: list[Literal["education", "health", "green", "government", "critical_infrastructure",
                             "hazardous_industry"]] | None = None
    limit: int = Field(default=50, ge=1, le=500)
    time: str | None = Field(default=None, description="ISO 8601; default now")


class CheckSensorsIn(Strict):
    """Stations of a layer that keep disagreeing with their neighbours (possible faulty sensors)."""

    layer: str = Field(min_length=1, max_length=80, description="belief layer, e.g. air_no2, air_pm10, rain")
    area: Area = Field(default="city", description=AREA_DESCRIPTION)
    time: str | None = Field(default=None, description="ISO 8601; default now")


class HeatWatchIn(Strict):
    """Elderly residents and health/care sites where it is likely above the heat threshold, per municipio."""

    area: Area = Field(default="city", description=AREA_DESCRIPTION)
    time: str | None = Field(default=None, description="ISO 8601; default now")


class FloodWatchIn(Strict):
    """Cells where heavy rain is likely on flood-prone ground (PGRA) or road underpasses: places to watch."""

    area: Area = Field(default="city", description=AREA_DESCRIPTION)
    time: str | None = Field(default=None, description="ISO 8601; default now")


class SchoolsToCheckIn(Strict):
    """Schools ranked by how close the air (NO2, PM10, PM2.5) comes to its legal limits, worst first."""

    area: Area = Field(default="city", description=AREA_DESCRIPTION)
    top: int = Field(default=10, ge=1, le=100)
    time: str | None = Field(default=None, description="ISO 8601; default now")


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


class CitizenReport(Strict):
    """One citizen report, anonymised: 'reporter' is an opaque key (one per account), never a name."""

    id: str = Field(min_length=1, max_length=80)
    category: Literal["congestion", "flood", "fire", "emergency", "other"]
    lon: float = Field(ge=12.0, le=13.1)
    lat: float = Field(ge=41.4, le=42.4)
    time: str = Field(min_length=10, max_length=40, description="ISO 8601")
    reporter: str = Field(min_length=1, max_length=80)
    has_photo: bool = False
    text: str = Field(default="", max_length=280)
    photo_ref: str | None = Field(default=None, max_length=300, description="storage path of the photo, if any")
    photo_gps_distance_m: float | None = Field(default=None, ge=0, description="photo EXIF GPS to device GPS distance")
    photo_age_min: float | None = Field(default=None, description="minutes from the photo EXIF time to sending")


class SignalCheck(Strict):
    photo: Literal["consistent", "inconsistent", "unclear", "no_photo"] | None = None
    news: Literal["confirms", "no_match"] | None = None


class SignalEventsIn(Strict):
    """Office only. Merge citizen reports into candidate live events, each with a confidence and its reasons."""

    reports: list[CitizenReport] = Field(max_length=2000)
    check_twin: bool = Field(default=True, description="read twin layers (rain, road speed...) around each event")
    checks: dict[str, SignalCheck] | None = Field(default=None, description="verdicts of verify_signal by event id")
    now: str | None = Field(default=None, description="ISO 8601; default now")


class SignalEvent(Strict):
    id: str = Field(min_length=1, max_length=40)
    category: Literal["congestion", "flood", "fire", "emergency", "other"]
    category_label: str | None = Field(default=None, max_length=80)
    lon: float = Field(ge=12.0, le=13.1)
    lat: float = Field(ge=41.4, le=42.4)
    first_seen: str = Field(max_length=40)
    texts: list[str] = Field(default_factory=list, max_length=20)


class VerifySignalIn(Strict):
    """Office only, costs one Claude call and one Exa search: check one event's photos and look for news about it."""

    event: SignalEvent
    place: str | None = Field(default=None, max_length=200, description="street or area name for the news search")
    photo_urls: list[str] = Field(default_factory=list, max_length=6,
                                  description="short-lived signed URLs from Lovable Cloud storage")


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
    retrieved_at: str | None = Field(default=None, description="When a live source was read; static files have none")


class EnvelopeOut(BaseModel):
    """Response of every tool (shared interface 3)."""

    run_id: str = Field(description="SHA-256 of tool name + inputs + data snapshot hashes + config file hashes")
    tool: str
    status: Literal["ok", "not_available", "refused"] = Field(
        description="not_available: an input is missing; refused: a guardrail said no")
    reason: str | None = Field(default=None, description="Why the status is not ok")
    inputs: dict[str, Any]
    result: Any
    data_kinds: dict[str, Literal["real", "estimated", "simulated", "hypothetical", "not_available"]] = Field(
        description="hypothetical: a what-if input chosen by the user (scenario variants only)")
    sources: list[SourceOut]
    synthetic: bool
    warnings: list[str]
    cached: bool = False


class AirHereIn(Strict):
    """Citizen: air quality at a point now (NO2, PM10, PM2.5, O3) with the EEA index level and the legal reference values."""

    point: Point
    time: str | None = Field(default=None, description="ISO 8601; default now")


class EmfHereIn(Strict):
    """Citizen: estimated radio-frequency electric field at a point, with its level and the legal values."""

    point: Point
    time: str | None = Field(default=None, description="ISO 8601; default now")


class CityHeatmapIn(Strict):
    """Citizen: whole-city heat map of one layer on a coarse grid (value, range and level per cell, plus a legend). road_speed at a future time = predicted congestion."""

    layer: Literal["air_no2", "air_pm10", "air_pm25", "air_o3", "emf", "road_speed"]
    time: str | None = Field(default=None, description="ISO 8601; default now")
    resolution: int | None = Field(default=None, ge=6, le=9, description="H3 resolution; default from config")


class HeatHereIn(Strict):
    """Citizen: heat risk today at a point (apparent temperature) and where to cool off at that hour: open climate refuges and cooler open-air spots within a short walk."""

    point: Point
    time: str | None = Field(default=None, description="ISO 8601 hour to plan for; default the day's hottest hour (or now if it has passed)")


class PlacesOpenIn(Strict):
    """Citizen: sports venues (optionally for one sport) or museums and galleries open at a chosen day and time, nearest first, with their opening hours."""

    kind: Literal["sport", "museum"]
    at: str | None = Field(default=None, description="ISO 8601 date and time; default now")
    point: Point | None = None
    radius_m: float | None = Field(default=None, gt=0, le=30_000, description="only with point; default from config")
    sport: str | None = Field(default=None, max_length=60, description="Italian or English name, e.g. 'nuoto', 'calcio', 'tennis'")


class TransportNowIn(Strict):
    """Citizen: live notices on Rome's streets and lines (works, closures, line deviations, strikes, events) placed on the street they name, with the feed's freshness. Congestion: city_heatmap on road_speed."""

    area: Area = Field(default="city", description=AREA_DESCRIPTION)
