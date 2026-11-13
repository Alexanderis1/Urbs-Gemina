"""Roma Capitale public Wi-Fi (DigitRoma) sessions as a crowd proxy (layer ``activity_wifi``). Real, open.

Source: dati.comune.roma.it dataset ``wifi<year>`` ("Sessioni anonimizzate di
navigazione web", CC BY 4.0), one CSV per day with every session's start, end
and hotspot address. Each daily file holds the sessions that ended that day, so
it lags about one day behind real time.

We keep only start, end and the hotspot address. DOMAIN, LOGINCOUNT, traffic
volumes and language are dropped at parse time, and only counts per hotspot
site and hour leave this module. ``peopleCount`` is the number of sessions
active at any time in that hour: a lower bound on people there (C=60), since
most visitors never log in.

Hotspot positions come from the hotspot maps published in dataset D.192 (KML),
turned into a committed address -> point gazetteer by
``python -m twin.providers.build_seeds wifi``.
"""
from __future__ import annotations

import csv
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator, Mapping
from zoneinfo import ZoneInfo

from twin.providers import http
from twin.providers.base import BBox, Observation, ProviderInfo
from twin.providers.geo import distance_m, in_bbox
from twin.providers.settings import Settings, number, text

PROVIDER_ID = "roma_wifi"
ROME = ZoneInfo("Europe/Rome")
PACKAGE_URL = "https://dati.comune.roma.it/catalog/api/3/action/package_show?id={dataset}"
SITES_FILE = Path(__file__).parent / "seed_data" / "wifi_sites.json"

Sites = dict[str, tuple[float, float]]


def _normalise(address: str) -> str:
    plain = unicodedata.normalize("NFKD", address).encode("ascii", "ignore").decode().upper()
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", plain).split())


def address_keys(address: str) -> set[str]:
    """Match keys for an address: full text, street + civic number, and last street word + number.

    The last form (``~WORD 12``) matches "Via Petroselli 50" with "Via Luigi Petroselli, 50".
    """
    full = _normalise(address)
    keys = {full} if full else set()
    match = re.match(r"(.*?)\s+(\d+)", full)
    if match:
        street, civic = match.group(1), match.group(2)
        keys.add(f"{street} {civic}")
        words = street.split()
        if len(words) >= 2:
            keys.add(f"~{words[-1]} {civic}")
    return keys


def _centroid(coordinates: str) -> tuple[float, float] | None:
    points = []
    for item in coordinates.split():
        parts = item.split(",")
        try:
            points.append((float(parts[0]), float(parts[1])))
        except (IndexError, ValueError):
            continue
    if not points:
        return None
    return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)


def parse_hotspot_kml(kml: str, max_spread_m: float = 300.0) -> Sites:
    """Address key -> mean hotspot position, from one or more D.192 KML maps.

    Points further than ``max_spread_m`` from the key's median are outliers. A key is kept only
    when most of its points agree on one place.
    """
    found: dict[str, list[tuple[float, float]]] = {}
    for placemark in re.findall(r"<Placemark.*?</Placemark>", kml, re.S):
        coords = re.search(r"<coordinates>(.*?)</coordinates>", placemark, re.S)
        point = _centroid(coords.group(1)) if coords else None
        if point is None:
            continue

        def field(name: str) -> str | None:
            m = re.search(rf'name="{name}">(.*?)<', placemark) or re.search(rf"<{name}>(.*?)</{name}>", placemark, re.S)
            return m.group(1) if m else None

        addresses = [value.split(" - ")[0] for value in (field("name"), field("description"), field("LOCAT")) if value]
        dug, duf, civic = field("DUG"), field("DUF"), field("CIVICO")
        if dug and duf and civic:
            addresses.append(f"{dug} {duf} {civic}")
        for address in addresses:
            for key in address_keys(address):
                found.setdefault(key, []).append(point)
    sites: Sites = {}
    for key, points in found.items():
        lons, lats = sorted(p[0] for p in points), sorted(p[1] for p in points)
        mid_lon, mid_lat = lons[len(lons) // 2], lats[len(lats) // 2]
        inliers = [p for p in points if distance_m(mid_lon, mid_lat, p[0], p[1]) <= max_spread_m]
        if 2 * len(inliers) > len(points):  # a clear majority agrees on the place
            sites[key] = (round(sum(p[0] for p in inliers) / len(inliers), 6),
                          round(sum(p[1] for p in inliers) / len(inliers), 6))
    return sites


def load_sites(path: Path = SITES_FILE) -> Sites:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {key: (float(v[0]), float(v[1])) for key, v in raw["sites"].items()}


@dataclass(frozen=True)
class Session:
    """One Wi-Fi session, reduced to what the twin needs. No user fields."""

    address: str
    start: datetime  # UTC
    end: datetime  # UTC


def _local(day: str, clock: str) -> datetime:
    return datetime.strptime(f"{day} {clock}", "%d/%m/%Y %H:%M:%S").replace(tzinfo=ROME).astimezone(timezone.utc)


def parse_sessions(text_csv: str) -> list[Session]:
    """Sessions from one daily CSV. Duplicate rows (same address and times) are kept once."""
    seen: set[Session] = set()
    out: list[Session] = []
    for row in csv.DictReader(text_csv.splitlines()):
        try:
            start = _local(row["STARTDATE"], row["STARTTIME"])
            end = _local(row["ENDDATE"], row["ENDTIME"])
        except (KeyError, TypeError, ValueError):
            continue
        address = " ".join(str(row.get(k) or "").strip() for k in ("DUG", "DUF", "CIVICO")).strip()
        session = Session(address=address, start=start, end=max(start, end))
        if address and session not in seen:
            seen.add(session)
            out.append(session)
    return out


def match_site(address: str, sites: Mapping[str, tuple[float, float]]) -> str | None:
    """The gazetteer key for a session address, or None. Exact forms are tried before the loose one."""
    for key in sorted(address_keys(address), key=lambda k: (k.startswith("~"), -len(k))):
        if key in sites:
            return key
    return None


def hourly_counts(sessions: list[Session], key_of: Callable[[str], str] = _normalise
                  ) -> dict[tuple[str, datetime], int]:
    """(normalised address, UTC hour start) -> sessions active at any time in that hour."""
    counts: dict[tuple[str, datetime], int] = {}
    for session in sessions:
        address = key_of(session.address)
        hour = session.start.replace(minute=0, second=0, microsecond=0)
        while hour <= session.end:
            counts[(address, hour)] = counts.get((address, hour), 0) + 1
            hour += timedelta(hours=1)
    return counts


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


class RomaWifiProvider:
    def __init__(self, settings: Settings | None = None, fetch_bytes: Callable[[str], bytes] | None = None,
                 sites: Sites | None = None) -> None:
        settings = settings or Settings.load()
        config = settings.section("open", PROVIDER_ID)
        self._dataset = text(config, "dataset", "wifi{year}")
        self._sigma_floor = number(config, "sigma_floor", 1.0)
        timeout = number(config, "timeout_s", 120.0)
        self._fetch = fetch_bytes or (lambda url: http.get_bytes(url, timeout_s=timeout))
        self.sites: Sites = sites if sites is not None else load_sites()
        self.unmatched_sessions = 0

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            id=PROVIDER_ID,
            kind="open",
            layer="activity_wifi",
            licence="CC BY 4.0, Roma Capitale (dati.comune.roma.it)",
            cadence="daily files, about one day behind",
            synthetic=False,
            redistribution=True,
            notes="Active public Wi-Fi sessions per hotspot and hour: a lower bound on people there "
                  "(C=60). Anonymised by the city; user fields dropped, only counts kept.",
        )

    def _daily_urls(self, days: set[date]) -> list[str]:
        urls: list[str] = []
        for year in sorted({d.year for d in days}):
            package = json.loads(self._fetch(PACKAGE_URL.format(dataset=self._dataset.format(year=year))))
            for resource in package.get("result", {}).get("resources", []):
                name = str(resource.get("name", ""))
                try:
                    day = datetime.strptime(name.split(".")[0], "%Y%m%d").date()
                except ValueError:
                    continue
                if day in days:
                    urls.append(str(resource["url"]))
        return urls

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        start = start if start.tzinfo is not None else start.replace(tzinfo=timezone.utc)
        end = end if end.tzinfo is not None else end.replace(tzinfo=timezone.utc)
        first, last = start.astimezone(ROME).date(), end.astimezone(ROME).date() + timedelta(days=1)
        days = {first + timedelta(days=i) for i in range((last - first).days + 1)}
        sessions: list[Session] = []
        for url in self._daily_urls(days):
            sessions.extend(parse_sessions(_decode(self._fetch(url))))
        sessions = list(dict.fromkeys(sessions))  # a session can appear in two daily files
        self.unmatched_sessions = 0
        matched: list[Session] = []
        for session in sessions:
            key = match_site(session.address, self.sites)
            if key is None:
                self.unmatched_sessions += 1
            else:
                matched.append(Session(address=key, start=session.start, end=session.end))
        per_site: dict[tuple[tuple[float, float], datetime], int] = {}
        for (key, hour), count in hourly_counts(matched, key_of=str).items():
            point = self.sites[key]
            per_site[(point, hour)] = per_site.get((point, hour), 0) + count
        for ((lon, lat), hour), count in sorted(per_site.items()):
            observed_at = hour + timedelta(hours=1)  # end of the hour, as for the EEA stations
            if not (start <= observed_at <= end) or not in_bbox(lon, lat, bbox):
                continue
            yield Observation(
                entity_id=f"urn:ngsi-ld:CrowdFlowObserved:{PROVIDER_ID}-{lon:.5f}-{lat:.5f}",
                entity_type="CrowdFlowObserved",
                lon=lon,
                lat=lat,
                observed_at=observed_at,
                values={"peopleCount": float(count)},
                sigma={"peopleCount": max(self._sigma_floor, math.sqrt(count))},
                source_id=PROVIDER_ID,
                synthetic=False,
            )
