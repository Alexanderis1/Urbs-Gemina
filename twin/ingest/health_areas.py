"""The ASL areas (local health authorities) of Roma Capitale, with official figures.

Roma Capitale is split between ASL Roma 1, Roma 2 and Roma 3 by municipio. The
Ministry of Health table "Corrispondenze ASL-Comuni e popolazione residente" lists, for
the comune of Rome, which municipi each ASL covers (e.g. "ROMA (Municipi 1, 2, 3, 13,
14, 15)") and its residents. The ASL polygons are the union of those municipi from the
Roma Capitale boundary layer, so they match the city's own boundaries exactly.

Each area also gets the Ministry's "Strutture e attività ASL" figures (GPs,
paediatricians, clinics, out-of-hours points, home care) and counts of the facilities
already ingested (hospital beds, family health centres, pharmacies), found by location.
All numbers come from these tables or from counting; ratios are simple divisions.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from twin.ingest.catalog import LayerSpec
from twin.ingest.http import Fetch, HttpRequest
from twin.ingest.tables import italian_int, read_table

_MUNICIPI = re.compile(r"municipi\s+([\d,\s]+)", re.I)


def _facts(rows: list[dict[str, str]], options: dict[str, Any]) -> dict[str, dict[str, int]]:
    columns: dict[str, str] = {str(k): str(v) for k, v in (options.get("indicator_columns") or {}).items()}
    region = str(options.get("region_code", "120"))
    facts: dict[str, dict[str, int]] = {}
    for row in rows:
        if row.get("Codice Regione", "").strip() != region:
            continue
        code = row.get("Codice Azienda Sanitaria Locale", "").strip()
        facts[code] = {out: italian_int(row.get(source, "")) for out, source in columns.items()}
    return facts


def build_asl_areas(layer: LayerSpec, processed: Path, fetch: Fetch, entry: dict[str, Any]) -> Any:
    import hashlib

    import geopandas as gpd  # type: ignore[import-untyped,import-not-found,unused-ignore]

    options = layer.options
    mapping_url, facts_url = str(options["mapping_url"]), str(options["indicators_url"])
    mapping_raw = fetch(HttpRequest(mapping_url, timeout_s=300.0))
    facts_raw = fetch(HttpRequest(facts_url, timeout_s=300.0))
    entry["request_url"] = [mapping_url, facts_url]
    entry["raw_sha256"] = {"mapping": hashlib.sha256(mapping_raw).hexdigest(),
                           "indicators": hashlib.sha256(facts_raw).hexdigest()}
    encoding = str(options.get("encoding", "latin-1"))
    mapping = read_table(mapping_raw, ";", encoding)
    facts = _facts(read_table(facts_raw, ";", encoding), options)

    municipi = gpd.read_parquet(processed / f"{options.get('municipi_layer', 'municipi')}.parquet")
    field = str(options.get("municipio_field", "municipio"))
    comune = str(options.get("comune_code", "058091"))

    records: list[dict[str, Any]] = []
    geometries = []
    for row in mapping:
        if row.get("CODICE COMUNE", "").strip() != comune:
            continue
        match = _MUNICIPI.search(row.get("COMUNE", ""))
        if not match:
            continue
        numbers = [int(n) for n in re.findall(r"\d+", match.group(1))]
        code = row.get("CODICE AZIENDA", "").strip()
        parts = municipi[municipi[field].astype(int).isin(numbers)]
        if parts.empty:
            continue
        geometries.append(parts.geometry.union_all())
        record: dict[str, Any] = {
            "asl_code": code,
            "asl_name": row.get("DENOMINAZIONE AZIENDA", "").strip(),
            "municipi": ", ".join(str(n) for n in numbers),
            "residents_2024": italian_int(row.get("TOTALE", "")),
        }
        record.update(facts.get(code, {}))
        records.append(record)

    frame = gpd.GeoDataFrame(records, geometry=geometries, crs="EPSG:4326")
    frame = frame.sort_values("asl_name").reset_index(drop=True)

    # Facilities already ingested, counted (or summed) by location.
    missing: list[str] = []
    for out, spec in (options.get("facility_counts") or {}).items():
        path = processed / f"{spec['layer']}.parquet"
        if not path.exists():
            missing.append(str(spec["layer"]))
            frame[str(out)] = None
            continue
        points = gpd.read_parquet(path)
        joined = gpd.sjoin(points[points.geometry.notna()], frame[["asl_code", "geometry"]],
                           predicate="within", how="inner")
        if spec.get("sum"):
            totals = joined.groupby("asl_code")[str(spec["sum"])].sum()
        else:
            totals = joined.groupby("asl_code").size()
        frame[str(out)] = [int(totals.get(code, 0)) for code in frame["asl_code"]]
    entry["missing_inputs"] = missing

    for out, spec in (options.get("ratios") or {}).items():
        if not isinstance(spec, dict):  # the "basis" note
            continue
        numerator, denominator = str(spec["numerator"]), str(spec["denominator"])
        scale = float(spec.get("scale", 1))
        values = []
        for num, den in zip(frame.get(numerator, []), frame.get(denominator, [])):
            ok = num is not None and den not in (None, 0)
            values.append(round(float(num) * scale / float(den), 2) if ok else None)
        frame[str(out)] = values
    return frame
