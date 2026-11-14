"""Official tables (CSV / tab-separated text) turned into point layers.

Two cases, both set in config/ingest.yaml:

* ``csv_points``: the table already has latitude and longitude columns
  (e.g. Regione Lazio's accredited health facilities).
* ``csv_geocoded``: the table has only a postal address (e.g. IndicePA, the
  register of public bodies). The address is matched offline against the
  ``addr:street`` / ``addr:housenumber`` tags of the OSM Lazio extract, so no
  outside geocoding service ever sees the data. An exact house number gives
  ``geocode_quality = address`` (``data_kind = real``); a known street without
  that number gives the centre of the street's addresses
  (``geocode_quality = street``, ``data_kind = estimated``). Rows that match
  nothing are left out and counted.

Only the columns listed under ``columns`` are kept (a whitelist), so names of
people, e-mails and tax codes in the source table never reach the files.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from twin.ingest.catalog import BBox

Row = dict[str, str]
Position = tuple[float, float, str]

_ABBREVIATIONS = [
    (r"^p\s*zz?a\b", "piazza"), (r"^pza\b", "piazza"), (r"^pzza\b", "piazza"),
    (r"^p\s*le\b", "piazzale"), (r"^ple\b", "piazzale"),
    (r"^v\s*le\b", "viale"), (r"^vle\b", "viale"),
    (r"^l\s*go\b", "largo"), (r"^lgo\b", "largo"),
    (r"^c\s*so\b", "corso"), (r"^cso\b", "corso"),
    (r"^v\b", "via"),
]
_STOP_WORDS = {"di", "del", "della", "dei", "degli", "delle", "dello", "dell", "d", "de", "la", "lo", "il", "e"}
_HOUSE = re.compile(r"\s*(?:n\.?\s*)?(\d{1,4})\s*(?:/?\s*([a-z])\b)?", re.I)
_POSTCODE = re.compile(r"\s+\d{5}(\s+roma)?\s*$", re.I)
_NUMBER = re.compile(r"^(?P<street>.*?)[\s,]+(?:n\.?\s*)?(?P<number>\d+)\s*(?:/?\s*(?P<suffix>[a-z]))?\s*$", re.I)


# --- Reading and filtering --------------------------------------------------------

def read_table(raw: bytes, delimiter: str = ",", encoding: str = "utf-8-sig") -> list[Row]:
    text = raw.decode(encoding)
    return [{str(k).strip(): (v or "").strip() for k, v in row.items() if k is not None}
            for row in csv.DictReader(io.StringIO(text), delimiter=delimiter)]


def _same(a: str, b: Any) -> bool:
    return a.strip().casefold() == str(b).strip().casefold()


def keep_row(row: Row, equals: Mapping[str, Any], any_of: Mapping[str, Sequence[Any]]) -> bool:
    if not all(_same(row.get(column, ""), value) for column, value in equals.items()):
        return False
    return all(any(_same(row.get(column, ""), v) for v in values) for column, values in any_of.items())


def safe_name(name: str, patterns: Sequence[str], label: str) -> str:
    """Names that carry a person's name (partnerships, doctors' practices) become a generic label."""
    return label if any(re.search(p, name, re.I) for p in patterns) else name.strip()


def italian_int(text: str) -> int:
    """'1.200' -> 1200 (Italian thousands separator); empty or '-' -> 0."""
    cleaned = str(text).strip().replace(".", "").split(",")[0]
    return int(cleaned) if cleaned.lstrip("-").isdigit() else 0


def aggregate_rows(rows: list[Row], spec: dict[str, Any]) -> list[Row]:
    """Sum rows per key. ``pivot`` turns one row per category into one column per category."""
    by = [str(c) for c in spec["by"]]
    first = [str(c) for c in spec.get("first") or []]
    pivot = spec.get("pivot") or {}
    total = spec.get("total")
    groups: dict[tuple[str, ...], Row] = {}
    for row in rows:
        key = tuple(row.get(c, "") for c in by)
        group = groups.setdefault(key, {**{c: row.get(c, "") for c in by}, **{c: row.get(c, "") for c in first}})
        if pivot:
            column = str(pivot["prefix"]) + normalise_street(row.get(str(pivot["column"]), "")).replace(" ", "_")
            value = italian_int(row.get(str(pivot["value"]), ""))
            group[column] = str(italian_int(group.get(column, "0")) + value)
            if total:
                group[str(total)] = str(italian_int(group.get(str(total), "0")) + value)
    return list(groups.values())


# --- Addresses ---------------------------------------------------------------------

def normalise_street(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    for pattern, full in _ABBREVIATIONS:
        text = re.sub(pattern, full, text)
    return re.sub(r"\s+", " ", text).strip()


def _number(text: str) -> str:
    match = re.match(r"\s*(\d+)\s*(?:/?\s*([a-z]))?", text.casefold())
    return (match.group(1) + (match.group(2) or "")) if match else text.strip().casefold()


def split_address(address: str) -> tuple[str, str | None]:
    """'Viale di Trastevere, 76/A' -> ('viale di trastevere', '76a'); no number -> None.

    After a comma, the first number is the house number and the rest (building name, city)
    is ignored. Without a comma, a trailing postcode is dropped and the last number is used.
    """
    text = address.strip()
    if "," in text:
        street, rest = text.split(",", 1)
        match = _HOUSE.match(rest)
        if match:
            return normalise_street(street), match.group(1) + (match.group(2) or "").casefold()
        return normalise_street(street), None
    text = _POSTCODE.sub("", text)
    match = _NUMBER.match(text)
    if not match:
        return normalise_street(text), None
    suffix = (match.group("suffix") or "").casefold()
    return normalise_street(match.group("street")), match.group("number") + suffix


def _significant(street: str) -> list[str]:
    return [t for t in street.split()[1:] if len(t) > 1 and t not in _STOP_WORDS]


class AddressIndex:
    """Street + house number -> position, built from (street, number, lon, lat) records."""

    def __init__(self, records: Iterable[tuple[str, str, float, float]],
                 streets: Iterable[tuple[str, float, float]] = ()) -> None:
        self._exact: dict[tuple[str, str], tuple[float, float]] = {}
        points: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for street, number, lon, lat in records:
            key = normalise_street(street)
            self._exact.setdefault((key, _number(number)), (lon, lat))
            points[key].append((lon, lat))
        # Roads with a name but no house numbers still give a street-level position.
        road_points: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for name, lon, lat in streets:
            key = normalise_street(name)
            if key not in points:
                road_points[key].append((lon, lat))
        self._streets = {k: (sum(p[0] for p in v) / len(v), sum(p[1] for p in v) / len(v))
                         for k, v in {**road_points, **points}.items()}
        self._by_last: dict[str, list[str]] = defaultdict(list)
        for street in self._streets:
            tokens = _significant(street)
            if tokens:
                self._by_last[tokens[-1]].append(street)

    def __len__(self) -> int:
        return len(self._exact)

    def _street(self, street: str) -> str | None:
        if street in self._streets:
            return street
        # "Via C. Colombo" -> "via cristoforo colombo": same street type, last word and other words.
        tokens = _significant(street)
        if not tokens:
            return None
        kind = street.split()[0]
        initials = [t for t in street.split()[1:] if len(t) == 1 and t not in _STOP_WORDS]
        candidates = [c for c in self._by_last.get(tokens[-1], [])
                      if c.split()[0] == kind and set(tokens) <= set(_significant(c))
                      and all(any(w.startswith(i) for w in _significant(c) if w not in tokens) for i in initials)]
        return candidates[0] if len(candidates) == 1 else None

    def lookup(self, address: str) -> Position | None:
        street, number = split_address(address)
        found = self._street(street)
        if found is None:
            return None
        if number is not None:
            for candidate in (number, re.sub(r"[a-z]$", "", number)):
                if (found, candidate) in self._exact:
                    lon, lat = self._exact[(found, candidate)]
                    return lon, lat, "address"
        lon, lat = self._streets[found]
        return lon, lat, "street"


def osm_address_records(path: Path, bbox: BBox) -> tuple[list[tuple[str, str, float, float]],
                                                        list[tuple[str, float, float]]]:
    """(addresses, named roads) inside bbox: every node or way with addr:street and
    addr:housenumber, and the centre of every named highway way."""
    import osmium

    west, south, east, north = bbox
    records: list[tuple[str, str, float, float]] = []
    roads: list[tuple[str, float, float]] = []

    def add(tags: Any, lon: float, lat: float) -> None:
        if west <= lon <= east and south <= lat <= north:
            records.append((str(tags["addr:street"]), str(tags["addr:housenumber"]), lon, lat))

    class Handler(osmium.SimpleHandler):  # type: ignore[misc,unused-ignore]
        def node(self, n: Any) -> None:
            if "addr:housenumber" in n.tags and "addr:street" in n.tags and n.location.valid():
                add(n.tags, n.location.lon, n.location.lat)

        def way(self, w: Any) -> None:
            is_address = "addr:housenumber" in w.tags and "addr:street" in w.tags
            is_road = "highway" in w.tags and "name" in w.tags
            if not (is_address or is_road):
                return
            points = [(nd.lon, nd.lat) for nd in w.nodes if nd.location.valid()]
            if not points:
                return
            lons, lats = [p[0] for p in points], [p[1] for p in points]
            lon, lat = (min(lons) + max(lons)) / 2, (min(lats) + max(lats)) / 2
            if is_address:
                add(w.tags, lon, lat)
            if is_road and west <= lon <= east and south <= lat <= north:
                roads.append((str(w.tags["name"]), lon, lat))

    Handler().apply_file(str(path), locations=True)
    return records, roads


# --- Frames -------------------------------------------------------------------------

def _empty_frame(columns: Sequence[str]) -> Any:
    import geopandas as gpd  # type: ignore[import-untyped,import-not-found,unused-ignore]

    return gpd.GeoDataFrame({c: [] for c in [*columns, "geometry"]}, geometry="geometry", crs="EPSG:4326")


def _selected(rows: list[Row], options: dict[str, Any]) -> tuple[list[Row], int]:
    equals = dict(options.get("filter") or {})
    any_of = {str(k): list(v) for k, v in (options.get("filter_in") or {}).items()}
    kept = [r for r in rows if keep_row(r, equals, any_of)]
    filtered = len(rows) - len(kept)
    if options.get("aggregate"):
        kept = aggregate_rows(kept, dict(options["aggregate"]))
    return kept, filtered


def _record(row: Row, options: dict[str, Any]) -> dict[str, Any]:
    columns: dict[str, str] = {str(k): str(v) for k, v in (options.get("columns") or {}).items()}
    record: dict[str, Any] = {out: row.get(source, "") for out, source in columns.items()}
    for column in options.get("numeric_columns") or []:
        record[str(column)] = italian_int(record.get(str(column), ""))
    rule = options.get("generic_name")
    if rule and "name" in record:
        record["name"] = safe_name(str(record["name"]), list(rule["patterns"]), str(rule["label"]))
    return record


def points_frame(rows: list[Row], options: dict[str, Any], bbox: BBox) -> tuple[Any, dict[str, Any]]:
    """Rows with their own coordinates. Returns (GeoDataFrame, report)."""
    import geopandas as gpd  # type: ignore[import-untyped,import-not-found,unused-ignore]
    from shapely.geometry import Point  # type: ignore[import-untyped,import-not-found,unused-ignore]

    selected, filtered = _selected(rows, options)
    west, south, east, north = bbox
    records: list[dict[str, Any]] = []
    no_position = 0
    for row in selected:
        try:
            lat = float(row.get(str(options["lat_column"]), "").replace(",", "."))
            lon = float(row.get(str(options["lon_column"]), "").replace(",", "."))
        except ValueError:
            no_position += 1
            continue
        if not (west <= lon <= east and south <= lat <= north):
            no_position += 1
            continue
        records.append({**_record(row, options), "geometry": Point(lon, lat)})
    report = {"skipped_rows": {"filtered": filtered, "no_position": no_position}}
    if not records:
        return _empty_frame(list((options.get("columns") or {}).keys())), report
    return gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326"), report


def geocoded_frame(rows: list[Row], options: dict[str, Any], index: AddressIndex) -> tuple[Any, dict[str, Any]]:
    """Rows with an address only, placed with the offline OSM address index."""
    import geopandas as gpd  # type: ignore[import-untyped,import-not-found,unused-ignore]
    from shapely.geometry import Point  # type: ignore[import-untyped,import-not-found,unused-ignore]

    selected, filtered = _selected(rows, options)
    overrides = {str(k).strip().casefold(): str(v) for k, v in (options.get("address_overrides") or {}).items() if k != "basis"}
    address_column = str(options["address_column"])
    counts = {"address": 0, "street": 0, "not_found": 0}
    records: list[dict[str, Any]] = []
    for row in selected:
        address = row.get(address_column, "")
        address = overrides.get(address.strip().casefold(), address)
        found = index.lookup(address)
        if found is None:
            counts["not_found"] += 1
            continue
        lon, lat, quality = found
        counts[quality] += 1
        records.append({**_record(row, options), "geocode_quality": quality,
                        "data_kind": "real" if quality == "address" else "estimated",
                        "geometry": Point(lon, lat)})
    report = {"skipped_rows": {"filtered": filtered}, "geocoding": counts}
    if not records:
        columns = [*list((options.get("columns") or {}).keys()), "geocode_quality", "data_kind"]
        return _empty_frame(columns), report
    return gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326"), report
