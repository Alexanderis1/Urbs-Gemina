"""Turn each raw source into ``Candidate`` records.

Personal data is dropped here, before anything is matched or stored:
contact-like fields are removed, and a concession holder is kept only when its
name looks like an organisation (ASD, SSD, srl, associazione...).
"""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Iterable, Mapping

from twin.modules.sports.config import SportsConfig
from twin.modules.sports.disciplines import disciplines_from_osm, disciplines_from_text, fold
from twin.modules.sports.model import Candidate
from twin.providers.open.roma_wfs import PERSONAL_FIELD_HINTS

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV"]

#: OSM tags that make an element a place to play sport.
OSM_SPORT_LEISURE = {"sports_centre", "pitch", "fitness_centre", "swimming_pool", "stadium", "track",
                     "ice_rink", "sports_hall", "golf_course", "horse_riding"}
OSM_KEEP_TAGS = ("website", "opening_hours", "wheelchair", "operator", "access")


def municipio_id(value: Any) -> str | None:
    """'7', 7, 'VII', 'Municipio VII', 'MUNICIPIO 7' -> 'VII'. Unknown -> None."""
    if value is None:
        return None
    text = str(value).strip().upper().replace("MUNICIPIO", "").strip()
    if text.isdigit() and 1 <= int(text) <= len(ROMAN):
        return ROMAN[int(text) - 1]
    return text if text in ROMAN else None


def _is_personal_key(key: str) -> bool:
    return any(hint in key.lower() for hint in PERSONAL_FIELD_HINTS)


def is_organisation(name: str, config: SportsConfig) -> bool:
    folded = f" {fold(name)} "
    return any(re.search(rf"(?<![a-z]){re.escape(fold(m))}(?![a-z])", folded) for m in config.web.org_name_markers)


def pick(props: Mapping[str, Any], role: str, config: SportsConfig) -> Any:
    """Value of the first property whose name matches one of the role's candidate keys."""
    keys = config.source_fields.get(role, ())
    lowered = {k.lower(): k for k in props}
    for cand in keys:
        if cand in lowered and props[lowered[cand]] not in (None, ""):
            return props[lowered[cand]]
    for cand in keys:
        if len(cand) < 4:
            continue
        for low, original in lowered.items():
            if cand in low and props[original] not in (None, ""):
                return props[original]
    return None


def _url(value: Any) -> str | None:
    """Plain URL, or the href of an HTML link as GeoServer sometimes stores it."""
    if not value:
        return None
    match = re.search(r"https?://[^\s\"'<>]+", str(value))
    return match.group(0) if match else None


def _kind_from_text(text: str) -> str:
    folded = fold(text)
    if "piscin" in folded:
        return "pool"
    if "palestra" in folded or "palazzetto" in folded:
        return "gym"
    if "campo" in folded or "stadio" in folded:
        return "pitch"
    return "sports_centre"


def _from_props(source: str, record_id: str, props: Mapping[str, Any], lon: float | None, lat: float | None,
                config: SportsConfig, retrieved_at: str, default_kind: str | None, url: str | None) -> Candidate:
    clean = {k: v for k, v in props.items() if not _is_personal_key(k)}
    name = str(pick(clean, "name", config) or "").strip()
    kind_text = str(pick(clean, "kind", config) or "")
    attributes: dict[str, Any] = {}
    for role in ("active", "concession_expiry", "hours", "opening_period"):
        value = pick(clean, role, config)
        if value not in (None, ""):
            attributes[role] = value
    website = _url(pick(clean, "website", config))
    if website:
        attributes["website"] = website
    holder = pick(clean, "manager", config)
    if holder and is_organisation(str(holder), config):
        attributes["manager"] = str(holder).strip()
    address = pick(clean, "address", config)
    return Candidate(
        source=source, record_id=record_id, name=name, lon=lon, lat=lat,
        kind=default_kind or _kind_from_text(f"{kind_text} {name}"),
        municipio=municipio_id(pick(clean, "municipio", config)),
        address=str(address).strip() if address else None,
        disciplines=frozenset(disciplines_from_text(f"{kind_text} {name}", config)),
        attributes=attributes, url=url, retrieved_at=retrieved_at,
    )


def _point(feature: Mapping[str, Any]) -> tuple[float | None, float | None]:
    geometry = feature.get("geometry") or {}
    coords = geometry.get("coordinates")
    if geometry.get("type") == "Point" and coords:
        return float(coords[0]), float(coords[1])
    if geometry.get("type") == "MultiPoint" and coords:
        return float(coords[0][0]), float(coords[0][1])
    return None, None


def from_feature_collection(source: str, collection: Mapping[str, Any], config: SportsConfig, retrieved_at: str,
                            default_kind: str | None = None, url: str | None = None) -> list[Candidate]:
    out = []
    for i, feature in enumerate(collection.get("features", [])):
        props = feature.get("properties") or {}
        lon, lat = _point(feature)
        record_id = str(feature.get("id") or pick(props, "id", config) or f"f/{i}")
        cand = _from_props(source, record_id, props, lon, lat, config, retrieved_at, default_kind, url)
        if cand.name or cand.located:
            out.append(cand)
    return out


def from_geoserver_sports(collection: Mapping[str, Any], config: SportsConfig, retrieved_at: str) -> list[Candidate]:
    """Roma GeoServer ``DIPPC:243_ServiziSportivi`` (municipal facilities)."""
    return from_feature_collection("roma_sports_municipal", collection, config, retrieved_at,
                                   url="https://geoportale.comune.roma.it/geoserver/ows")


def from_geoserver_pools(collection: Mapping[str, Any], config: SportsConfig, retrieved_at: str) -> list[Candidate]:
    """Roma GeoServer ``GABSIN:piscine`` (municipal pools, opening period and hours)."""
    cands = from_feature_collection("roma_pools", collection, config, retrieved_at, default_kind="pool",
                                    url="https://geoportale.comune.roma.it/geoserver/ows")
    return [replace(c, disciplines=c.disciplines | {"swimming"}) for c in cands]


def from_rows(source: str, rows: Iterable[Mapping[str, Any]], config: SportsConfig, retrieved_at: str,
              default_kind: str | None = None, url: str | None = None) -> list[Candidate]:
    """Tabular sources (open data ``d30`` CSV, school-gym register). Rows may lack coordinates."""
    out = []
    for i, row in enumerate(rows):
        lon_raw, lat_raw = pick(row, "lon", config), pick(row, "lat", config)
        try:
            lon = float(str(lon_raw).replace(",", ".")) if lon_raw not in (None, "") else None
            lat = float(str(lat_raw).replace(",", ".")) if lat_raw not in (None, "") else None
        except ValueError:
            lon = lat = None
        if lon is None or lat is None or not (-180 <= lon <= 180 and -90 <= lat <= 90):
            lon = lat = None
        cand = _from_props(source, f"row/{i}", row, lon, lat, config, retrieved_at, default_kind, url)
        if cand.name:
            out.append(cand)
    return out


def from_osm(overpass: Mapping[str, Any], config: SportsConfig, retrieved_at: str) -> list[Candidate]:
    """Overpass JSON (``out center tags``). Keeps sport places; drops phone/e-mail tags."""
    out = []
    for el in overpass.get("elements", []):
        tags: Mapping[str, str] = el.get("tags") or {}
        if tags.get("leisure") not in OSM_SPORT_LEISURE and "sport" not in tags:
            continue
        if "lon" in el and "lat" in el:
            lon, lat = float(el["lon"]), float(el["lat"])
        elif el.get("center"):
            lon, lat = float(el["center"]["lon"]), float(el["center"]["lat"])
        else:
            continue
        leisure = tags.get("leisure", "")
        kind = {"swimming_pool": "pool", "pitch": "pitch", "fitness_centre": "gym",
                "sports_hall": "gym"}.get(leisure, "sports_centre")
        osm_id = f"{el.get('type', 'node')}/{el.get('id')}"
        out.append(Candidate(
            source="osm", record_id=osm_id, name=str(tags.get("name", "")).strip(), lon=lon, lat=lat, kind=kind,
            municipio=None, address=None, disciplines=frozenset(disciplines_from_osm(tags, config)),
            attributes={k: tags[k] for k in OSM_KEEP_TAGS if k in tags},
            url=f"https://www.openstreetmap.org/{osm_id}", retrieved_at=retrieved_at,
        ))
    return out
