"""Citizen service: where can I practise a sport, or visit a museum or gallery, at a chosen day and time?

Venues: the merged sports facility layer (WS10: official registries, school gyms, OSM) and OpenStreetMap
museums and galleries (``museums_osm``). Hours: OSM ``opening_hours`` or Roma open-data Italian text,
read by twin/tools/opening_hours.py. A place whose hours are missing or not understood is listed with
``open_at: null`` ("orari non noti"), never guessed. Open places come first, then unknown, then closed;
inside each group the nearest first.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from twin.tools.context_check import distance_to_geometry_m
from twin.tools.envelope import Source, ToolError
from twin.tools.opening_hours import ROME, from_italian, is_open
from twin.tools.query_layer import parse_time
from twin.tools.runtime import ToolRuntime
from twin.tools.settings import value

TOOL = "places_open"
KINDS = ("sport", "museum")
MUSEUM_LABEL = {"museum": "museo", "gallery": "galleria"}
_FACILITIES: dict[tuple[str, float], list[Any]] = {}
_OSM_HOURS: dict[str, dict[str, str]] = {}


def _osm_hours(rt: ToolRuntime) -> dict[str, str]:
    """OSM id ('way/123') -> opening_hours, from the OSM sports layer (the merged layer keeps few hours)."""
    path = rt.settings.paths.data / "processed" / "osm_sports.geojson"
    key = str(path)
    if key not in _OSM_HOURS:
        table: dict[str, str] = {}
        snapshot = rt.store.get("osm_sports")
        for feature in snapshot.near((12.0, 41.4, 13.1, 42.4)) if snapshot is not None else []:
            props = feature.get("properties") or {}
            if props.get("opening_hours") and props.get("osm_id"):
                table[str(props["osm_id"])] = str(props["opening_hours"])
        _OSM_HOURS[key] = table
    return _OSM_HOURS[key]


def _hours_open(text: Any, at: datetime) -> bool | None:
    if text is None or not str(text).strip():
        return None
    raw = str(text)
    found = is_open(raw, at)
    return found if found is not None else is_open(from_italian(raw), at)


def _load_facilities(rt: ToolRuntime) -> list[Any]:
    from twin.modules.sports.pipeline import load_facilities
    path = rt.settings.paths.data / str(rt.settings.tool("sports", "facilities_file"))
    key = (str(path), path.stat().st_mtime)
    if key not in _FACILITIES:
        _FACILITIES.clear()
        _FACILITIES[key] = list(load_facilities(path))
    return _FACILITIES[key]


def _museums(rt: ToolRuntime, at: datetime) -> tuple[list[dict[str, Any]], list[Source]]:
    snapshot = rt.store.get("museums_osm")
    if snapshot is None:
        return [], []
    out = []
    for feature in snapshot.near((12.0, 41.4, 13.1, 42.4)):
        props = feature.get("properties") or {}
        if not props.get("name"):
            continue
        geometry = feature["geometry"]
        coords = geometry.get("coordinates") if geometry.get("type") == "Point" else None
        street = " ".join(str(props[k]) for k in ("addr:street", "addr:housenumber") if props.get(k))
        hours = props.get("opening_hours")
        out.append({"name": props["name"], "category": MUSEUM_LABEL.get(str(props.get("tourism")), "museo"),
                    "address": street or None, "opening_hours": hours, "open_at": _hours_open(hours, at),
                    "fee": props.get("fee"), "wheelchair": props.get("wheelchair"), "website": props.get("website"),
                    "source": "OpenStreetMap (ODbL)", "_geometry": geometry,
                    "lon": coords[0] if coords else None, "lat": coords[1] if coords else None})
    return out, [snapshot.source()]


def _sports(rt: ToolRuntime, at: datetime, sport: str | None, facilities: Sequence[Any] | None
            ) -> tuple[list[dict[str, Any]], str | None]:
    from twin.modules.sports.config import load_config
    from twin.modules.sports.disciplines import discipline_id
    config = load_config()
    wanted = (discipline_id(sport, config) or sport.strip().lower()) if sport else None
    items = list(facilities) if facilities is not None else _load_facilities(rt)
    osm_hours = _osm_hours(rt)
    unnamed_label = "Impianto sportivo senza nome"
    out = []
    for f in items:
        if f.lon is None or f.lat is None or not f.usable:
            continue
        if wanted and wanted not in f.disciplines:
            continue

        def get(name: str, fields: Mapping[str, Any] = f.fields) -> Any:
            entry = fields.get(name)
            return entry.value if entry is not None else None

        hours = get("hours")
        hours_label = f.fields["hours"].label if hours and f.fields.get("hours") is not None else None
        if not hours:
            hours = next((osm_hours[m[4:]] for m in f.members if m.startswith("osm:") and m[4:] in osm_hours), None)
        out.append({"name": get("name") or unnamed_label, "category": get("kind"),
                    "address": get("address"), "opening_hours": hours, "open_at": _hours_open(hours, at),
                    "hours_note": hours_label, "disciplines": sorted(f.disciplines), "access": f.access,
                    "source": ", ".join(sorted({m.split(":")[0] for m in f.members})) or None,
                    "_geometry": {"type": "Point", "coordinates": [f.lon, f.lat]}, "lon": f.lon, "lat": f.lat})
    return out, wanted


def places_open(rt: ToolRuntime, kind: str, at: str | None = None, point: Sequence[float] | None = None,
                radius_m: float | None = None, sport: str | None = None,
                facilities: Sequence[Any] | None = None) -> dict[str, Any]:
    if kind not in KINDS:
        raise ToolError(f"kind must be one of {', '.join(KINDS)}")
    cfg: Mapping[str, Any] = rt.settings.tools["citizen"]["places"]
    moment = parse_time(at)
    radius = float(radius_m or value(cfg["default_radius_m"]))
    inputs: dict[str, Any] = {"kind": kind, "at": moment.isoformat(), "point": list(point) if point else None,
                              "radius_m": radius if point else None, "sport": sport}
    sources: list[Source] = []
    if kind == "museum":
        places, sources = _museums(rt, moment)
        kinds = {"museums_osm": "real" if places or rt.store.get("museums_osm") else "not_available"}
        wanted = None
    else:
        try:
            places, wanted = _sports(rt, moment, sport, facilities)
        except (ImportError, OSError) as error:
            return rt.envelope(TOOL, inputs, None, {"sports_facilities": "not_available"}, [],
                               status="not_available", reason=f"sports facility layer not available ({error})")
        kinds = {"sports_facilities": "real"}
        now = datetime.now(timezone.utc).isoformat()
        sources = [Source(id="sports_facilities", retrieved_at=now)]
    if point is not None:
        lon, lat = float(point[0]), float(point[1])
        for p in places:
            p["distance_m"] = round(distance_to_geometry_m(lon, lat, p["_geometry"]))
        places = [p for p in places if p["distance_m"] <= radius]
    rank = {True: 0, None: 1, False: 2}
    unnamed = "Impianto sportivo senza nome"
    places.sort(key=lambda p: (rank[p["open_at"]], p["name"] == unnamed, p.get("distance_m", 0), str(p["name"])))
    total = len(places)
    with_hours = sum(1 for p in places if p["open_at"] is not None)
    shown = places[: int(value(cfg["max_results"]))]
    for p in shown:
        p.pop("_geometry", None)
    open_now = sum(1 for p in places if p["open_at"])
    local = moment.astimezone(ROME).strftime("%d/%m alle %H:%M")
    what = "luoghi della cultura" if kind == "museum" else ("impianti" + (f" per {sport}" if sport else ""))
    summary = (f"{open_now} {what} aperti il {local}" + (f" entro {radius / 1000:g} km" if point else "") +
               f"; {total - with_hours} senza orari noti.")
    result = {"kind": kind, "at": moment.isoformat(), "places": shown, "count": total, "open_count": open_now,
              "coverage": {"with_hours": with_hours, "total": total}, "summary_it": summary,
              "note_it": "Orari da OpenStreetMap e dati aperti di Roma Capitale: verificare sul sito del luogo prima di andare."}
    if wanted:
        result["sport"] = wanted
    warnings = [] if total == 0 or with_hours / total >= 0.5 else [
        f"Only {with_hours} of {total} places have readable opening hours; the others are listed as unknown."]
    return rt.envelope(TOOL, inputs, result, kinds, sources, warnings)


__all__ = ["KINDS", "places_open"]
