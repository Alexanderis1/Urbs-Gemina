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
import hashlib
import json
import sys
from dataclasses import replace
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def build(config: SportsConfig | None = None, raw: Path = RAW, out: Path = OUT) -> dict[str, Any]:
    config = config or load_config()
    cands, status, warnings = load_candidates(config, raw)
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
