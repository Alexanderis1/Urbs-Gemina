"""Build the merged sports-facility layer from whatever source files are present.

    python -m twin.modules.sports.pipeline fetch     # pools, OSM (needs network)
    python -m twin.modules.sports.pipeline build     # merge -> data/processed/sports/

Inputs (data/raw/, git-ignored). A missing file is reported "not_available",
never treated as empty:
  sports_municipal.geojson   DIPPC:243_ServiziSportivi (scripts/fetch_static_layers.py)
  sports_pools.geojson       GABSIN:piscine (``fetch`` below)
  osm_sports.json            Overpass JSON (``fetch`` below)
  sports_d30.csv             open data d30 "Centri Sportivi Municipali 2018" (manual download)
  school_gyms.csv            MIM school-building register rows with a gym
  sports_web/*.json          validated outputs of agents/sports_scout and sports_enrich
  sports_manager_updates.jsonl   confirmed manager updates (from the web app)
"""
from __future__ import annotations

import csv
import re
import hashlib
import json
import sys
import time
from dataclasses import replace
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from twin.modules.sports.config import SportsConfig, load_config
from twin.modules.sports.deserts import PopulationPoint, population_from_census
from twin.modules.sports.manager import ManagerUpdate, apply_manager_update
from twin.modules.sports.matching import build_facilities
from twin.modules.sports.model import Candidate, Facility, facility_from_feature
from twin.modules.sports.sources import from_geoserver_pools, from_geoserver_sports, from_osm, from_rows
from twin.modules.sports.web_fields import apply_enrichment, scout_candidates, validate_enrichment
from twin.providers.base import ROME_BBOX

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "sports"
OVERPASS = "https://overpass-api.de/api/interpreter"
#: Geocoder precisions good enough to put a facility on the map (house number level).
GEOCODE_PRECISE = frozenset({"house", "house_number", "address", "building", "rooftop"})


def overpass_query(bbox: tuple[float, float, float, float] = ROME_BBOX) -> str:
    min_lon, min_lat, max_lon, max_lat = bbox
    b = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    parts = "".join(
        f'nwr["leisure"="{v}"]({b});' for v in
        ("sports_centre", "pitch", "fitness_centre", "swimming_pool", "stadium", "track", "ice_rink", "sports_hall"))
    return f"[out:json][timeout:180];({parts});out center tags;"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch(raw: Path = RAW) -> dict[str, str]:
    """Download the sources this module needs beyond fetch_static_layers.py."""
    from twin.providers.open.roma_wfs import fetch_layer

    raw.mkdir(parents=True, exist_ok=True)
    status: dict[str, str] = {}
    try:
        pools = fetch_layer("GABSIN:piscine")
        (raw / "sports_pools.geojson").write_text(json.dumps(pools, ensure_ascii=False), encoding="utf-8")
        status["sports_pools"] = "ok"
    except Exception as error:  # noqa: BLE001 - report and carry on
        status["sports_pools"] = f"not_available: {type(error).__name__}: {error}"
    try:
        body = urllib.parse.urlencode({"data": overpass_query()}).encode("utf-8")
        with urllib.request.urlopen(OVERPASS, data=body, timeout=240) as response:  # noqa: S310 (fixed host)
            (raw / "osm_sports.json").write_bytes(response.read())
        status["osm_sports"] = "ok"
    except Exception as error:  # noqa: BLE001
        status["osm_sports"] = f"not_available: {type(error).__name__}: {error}"
    return status


def _read_csv(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t") if text.strip() else csv.excel
    return list(csv.DictReader(text.splitlines(), dialect=dialect))


def load_candidates(config: SportsConfig, raw: Path = RAW) -> tuple[list[Candidate], dict[str, Any], list[str]]:
    cands: list[Candidate] = []
    status: dict[str, Any] = {}
    warnings: list[str] = []

    def mark(key: str, path: Path, n: int) -> None:
        status[key] = {"status": "ok", "file": path.name, "sha256": _sha(path), "records": n}

    loaders: list[tuple[str, str, Any]] = [
        ("roma_sports_municipal", "sports_municipal.geojson",
         lambda p: from_geoserver_sports(json.loads(p.read_text(encoding="utf-8")), config, _mtime(p))),
        ("roma_pools", "sports_pools.geojson",
         lambda p: from_geoserver_pools(json.loads(p.read_text(encoding="utf-8")), config, _mtime(p))),
        ("osm", "osm_sports.json",
         lambda p: from_osm(json.loads(p.read_text(encoding="utf-8")), config, _mtime(p))),
        ("roma_d30_centres", "sports_d30.csv",
         lambda p: from_rows("roma_d30_centres", _read_csv(p), config, _mtime(p), "school_gym",
                             "https://dati.comune.roma.it")),
        ("school_gyms", "school_gyms.csv",
         lambda p: from_rows("school_gyms", _read_csv(p), config, _mtime(p), "school_gym")),
    ]
    for key, filename, loader in loaders:
        path = raw / filename
        if not path.exists() and (raw.parent / "processed" / filename).exists():
            path = raw.parent / "processed" / filename  # cleaned copy written by the static-data stream
        if not path.exists():
            status[key] = {"status": "not_available", "file": filename}
            warnings.append(f"{key}: not available ({filename} missing)")
            continue
        found: list[Candidate] = loader(path)
        cands.extend(found)
        mark(key, path, len(found))

    scout_dir = raw / "sports_web"
    scouted = 0
    for path in sorted(scout_dir.glob("scout_*.json")) if scout_dir.exists() else []:
        data = json.loads(path.read_text(encoding="utf-8"))
        found, warns = scout_candidates(data.get("candidates", []), config, data.get("retrieved_at", _mtime(path)))
        # Record ids must be unique across files.
        found = [replace(c, record_id=f"{path.stem}/{c.record_id}") for c in found]
        cands.extend(found)
        warnings.extend(f"{path.name}: {w}" for w in warns)
        scouted += len(found)
    status["web_scout"] = {"status": "ok" if scouted else "not_available", "records": scouted}
    return cands, status, warnings


def _mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat()


def enrich_and_confirm(facilities: list[Facility], config: SportsConfig,
                       raw: Path = RAW) -> tuple[list[Facility], list[dict[str, Any]], list[str]]:
    by_id = {f.facility_id: f for f in facilities}
    warnings: list[str] = []
    scout_dir = raw / "sports_web"
    for path in sorted(scout_dir.glob("enrich_*.json")) if scout_dir.exists() else []:
        data = json.loads(path.read_text(encoding="utf-8"))
        fid = str(data.get("facility_id", ""))
        if fid not in by_id:
            warnings.append(f"{path.name}: unknown facility {fid!r}")
            continue
        fields, warns = validate_enrichment(data, config, data.get("retrieved_at", _mtime(path)), path.stem)
        by_id[fid] = apply_enrichment(by_id[fid], fields)
        warnings.extend(f"{path.name}: {w}" for w in warns)

    audit: list[dict[str, Any]] = []
    updates = raw / "sports_manager_updates.jsonl"
    if updates.exists():
        for line in updates.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            u = ManagerUpdate(**json.loads(line))
            if u.facility_id not in by_id:
                warnings.append(f"manager update for unknown facility {u.facility_id!r}")
                continue
            try:
                by_id[u.facility_id], record = apply_manager_update(by_id[u.facility_id], u, config)
                audit.append(record)
            except ValueError as error:
                warnings.append(f"manager update rejected: {error}")
    return sorted(by_id.values(), key=lambda f: f.facility_id), audit, warnings


Geocoder = Callable[[str], Mapping[str, Any]]


def address_key(address: str) -> tuple[str, str | None]:
    """'Via T. Mommsen, 20, Roma' -> ('via mommsen', '20'). Street words + house number, for exact matching."""
    from twin.modules.sports.disciplines import fold

    text = re.sub(r"[.,;:'’/()\-]", " ", fold(address))
    tokens = [t for t in text.split() if t not in ("roma", "rm", "n", "snc")]
    number = next((re.match(r"\d+", t).group(0) for t in tokens if re.match(r"\d+", t)), None)  # type: ignore[union-attr]
    words = [t for t in tokens if not t[0].isdigit() and len(t) > 1]
    return " ".join(words), number


def locate_from_school_register(cands: list[Candidate], schools: Mapping[str, Any],
                                ) -> tuple[list[Candidate], int, list[str]]:
    """Give school gyms without coordinates the position of the state-school building at the same
    address and municipio (DIPSCU:mv_portale_rete_statale). Exact street + house number only."""
    from twin.modules.sports.sources import municipio_id

    book: dict[tuple[str, str | None, str | None], list[dict[str, Any]]] = {}
    for f in schools.get("features", []):
        props = f.get("properties") or {}
        coords = (f.get("geometry") or {}).get("coordinates")
        if not coords or not props.get("indirizzo"):
            continue
        street, number = address_key(str(props["indirizzo"]))
        book.setdefault((street, number, municipio_id(props.get("municipio"))), []).append(
            {"lon": float(coords[0]), "lat": float(coords[1]), "id": props.get("meccanografico") or props.get("feature_id")})
    out: list[Candidate] = []
    located = 0
    warnings: list[str] = []
    for c in cands:
        if c.located or not c.address or c.kind != "school_gym":
            out.append(c)
            continue
        street, number = address_key(c.address)
        hits = book.get((street, number, c.municipio)) if number else None
        if not hits and number and street:
            # Fallback: street names are written with or without first names ("Via Stabilini" /
            # "Via Pasquale Stabilini"): same last street word, number and municipio, if unique.
            last = street.split()[-1]
            keys = [k for k in book if k[1] == number and k[2] == c.municipio and k[0].split()[-1:] == [last]]
            hits = book[keys[0]] if len(keys) == 1 else None
        if not hits:
            out.append(c)
            continue
        from twin.modules.sports.geo import distance_m

        if max(distance_m(hits[0]["lon"], hits[0]["lat"], h["lon"], h["lat"]) for h in hits) > 100.0:
            warnings.append(f"{c.key}: school buildings more than 100 m apart at {c.address}; left unlocated")
            out.append(c)
            continue
        out.append(replace(c, lon=hits[0]["lon"], lat=hits[0]["lat"], attributes={
            **c.attributes, "located_by": {"source": "roma_schools_state", "school_id": hits[0]["id"],
                                           "rule": "same street, house number and municipio"}}))
        located += 1
    return out, located, warnings


def default_geocoder() -> Geocoder | None:
    """WS4's resolve_place (returns the tool envelope), or None when it is not installed."""
    try:
        from twin.tools.resolve_place import resolve  # type: ignore[import-not-found, unused-ignore]
    except ImportError:
        return None
    geocoder: Geocoder = resolve
    return geocoder


def geocode_candidates(cands: list[Candidate], geocoder: Geocoder | None, cache_path: Path,
                       pause_s: float = 1.0) -> tuple[list[Candidate], dict[str, Any], list[str]]:
    """Give coordinates to records that have an address but no position.

    Results are cached (one request per address, ever) and kept only when the
    geocoder matched a house number; a street-level match stays unlocated.
    Geocoded positions are estimated and say so in ``geocoded``.
    """
    todo = [c for c in cands if not c.located and c.address]
    status: dict[str, Any] = {"to_geocode": len(todo), "located": 0}
    if not todo:
        return cands, status, []
    cache: dict[str, Any] = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    warnings: list[str] = []
    out: list[Candidate] = []
    asked = 0
    for c in cands:
        if c.located or not c.address:
            out.append(c)
            continue
        query = f"{c.address}, Roma"
        if query not in cache:
            if geocoder is None:
                out.append(c)
                continue
            if asked:
                time.sleep(pause_s)
            asked += 1
            env = geocoder(query)
            cache[query] = {"status": env.get("status"), "result": env.get("result"), "run_id": env.get("run_id")}
        hit = cache[query]
        result = hit.get("result") or {}
        if hit.get("status") != "ok" or result.get("lon") is None:
            warnings.append(f"{c.key}: address not found ({query})")
            out.append(c)
            continue
        if str(result.get("precision", "")).lower() not in GEOCODE_PRECISE:
            warnings.append(f"{c.key}: only a {result.get('precision')!r} match for {query}; left unlocated")
            out.append(c)
            continue
        geocoded = {"precision": result.get("precision"), "label": result.get("label"), "run_id": hit.get("run_id")}
        out.append(replace(c, lon=float(result["lon"]), lat=float(result["lat"]),
                           attributes={**c.attributes, "geocoded": geocoded}))
        status["located"] += 1
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    if geocoder is None and status["located"] < len(todo):
        warnings.append("geocoder (twin.tools.resolve_place) not available: some records stay unlocated")
    return out, status, warnings


def build(config: SportsConfig | None = None, raw: Path = RAW, out: Path = OUT,
          geocoder: Geocoder | None | bool = True) -> dict[str, Any]:
    """``geocoder=True`` uses resolve_place if installed; ``None``/``False`` skips geocoding."""
    config = config or load_config()
    cands, status, warnings = load_candidates(config, raw)
    for schools_path in (raw / "schools_state.geojson", raw.parent / "processed" / "schools_state.geojson"):
        if schools_path.exists():
            cands, n, more = locate_from_school_register(
                cands, json.loads(schools_path.read_text(encoding="utf-8")))
            status["school_register_locations"] = {"status": "ok", "located": n, "sha256": _sha(schools_path)}
            warnings.extend(more)
            break
    coder = default_geocoder() if geocoder is True else (geocoder or None)
    cands, status["geocoding"], more_geo = geocode_candidates(cands, coder, raw / "sports_geocode_cache.json")
    warnings.extend(more_geo)
    facilities, report = build_facilities(cands, config)
    facilities, audit, more = enrich_and_confirm(facilities, config, raw)
    warnings.extend(more)
    out.mkdir(parents=True, exist_ok=True)
    layer = {"type": "FeatureCollection", "features": [f.to_feature() for f in facilities]}
    (out / "facilities.geojson").write_text(json.dumps(layer, ensure_ascii=False), encoding="utf-8")
    summary = {
        "built_at": _now(), "sources": status, "facilities": len(facilities),
        "with_disciplines": sum(1 for f in facilities if f.disciplines),
        "unlocated": len(report.unlocated), "links": len(report.links), "warnings": warnings,
        "manager_updates_applied": len(audit),
    }
    (out / "match_report.json").write_text(json.dumps({**summary, "match": report.to_dict()}, ensure_ascii=False,
                                                      indent=1), encoding="utf-8")
    return summary


def load_facilities(path: Path = OUT / "facilities.geojson") -> list[Facility]:
    """Read the built layer back as Facility objects (what the tool API passes to the tools)."""
    layer = json.loads(path.read_text(encoding="utf-8"))
    return [facility_from_feature(f) for f in layer["features"]]


def load_population(path: Path = ROOT / "data" / "processed" / "census_sections.geojson") -> list[PopulationPoint]:
    """Census sections written by the static-data stream; empty list if not built yet."""
    if not path.exists():
        return []
    return population_from_census(json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "build"
    if command == "fetch":
        print(json.dumps(fetch(), indent=2))
        return 0
    if command == "build":
        summary = build()
        print(json.dumps({k: v for k, v in summary.items() if k != "warnings"}, indent=2))
        print(f"{len(summary['warnings'])} warnings, see data/processed/sports/match_report.json")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
