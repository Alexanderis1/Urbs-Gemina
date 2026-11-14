"""WS3: Roma Capitale public Wi-Fi sessions as a real crowd proxy (layer activity_wifi)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from twin.providers.base import ROME_BBOX
from twin.providers.open.roma_wifi import (
    RomaWifiProvider,
    address_keys,
    hourly_counts,
    parse_hotspot_kml,
    parse_sessions,
)
from twin.providers.settings import Settings

HEADER = ('"STARTDATE","STARTTIME","ENDDATE","ENDTIME","DURATION","DOWNLOAD","UPLOAD","DOMAIN",'
          '"LOGINCOUNT","MUNICIPIO","DUG","DUF","CIVICO","LOCALITA","SERVICEPROFILE","DTLN"\n')


def _row(start: str, end: str, dug: str = "Via", duf: str = "della Stamperia", civ: str = "86") -> str:
    d0, t0 = start.split()
    d1, t1 = end.split()
    return (f'"{d0}","{t0}","{d1}","{t1}","60","1","1","REGISTERED","151","Municipio I",'
            f'"{dug}","{duf}","{civ}","Roma","DigitRoma_PP","it"\n')


KML = """<?xml version="1.0"?><kml><Document>
<Placemark><name>Via della Stamperia, 86</name><description>VIA DELLA STAMPERIA, 86 - SEDE</description>
<Polygon><outerBoundaryIs><LinearRing><coordinates>12.4830,41.9010 12.4832,41.9010 12.4832,41.9012 12.4830,41.9010</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><name>Via Luigi Petroselli, 50</name>
<Point><coordinates>12.4805,41.8902</coordinates></Point></Placemark>
</Document></kml>"""


def test_address_keys_tolerate_accents_case_and_missing_first_names() -> None:
    assert "VIA DELLA STAMPERIA 86" in address_keys("Via della  Stamperia, 86")
    assert address_keys("Via Petroselli 50") & address_keys("Via Luigi Petroselli, 50")
    assert "PIAZZA SANT EGIDIO 1" in address_keys("Piazza Sant'Egidio 1/B")


def test_hotspot_kml_gives_one_point_per_address() -> None:
    sites = parse_hotspot_kml(KML)
    lon, lat = sites["VIA DELLA STAMPERIA 86"]
    assert abs(lon - 12.4831) < 1e-3 and abs(lat - 41.9011) < 1e-3
    assert "~PETROSELLI 50" in sites


def test_sessions_drop_personal_fields_and_count_per_hour() -> None:
    text = HEADER + _row("12/11/2026 09:10:00", "12/11/2026 10:20:00") \
        + _row("12/11/2026 09:50:00", "12/11/2026 09:55:00") \
        + _row("12/11/2026 09:50:00", "12/11/2026 09:55:00")  # duplicate export row: counted once
    sessions = parse_sessions(text)
    assert len(sessions) == 2
    assert not hasattr(sessions[0], "login_count")
    counts = hourly_counts(sessions)
    # Rome is UTC+1 in November: local 09:00-10:00 is 08:00-09:00 UTC.
    key = ("VIA DELLA STAMPERIA 86", datetime(2026, 11, 12, 8, tzinfo=timezone.utc))
    assert counts[key] == 2
    assert counts[("VIA DELLA STAMPERIA 86", datetime(2026, 11, 12, 9, tzinfo=timezone.utc))] == 1


def test_provider_emits_crowd_flow_per_site_and_hour() -> None:
    package = {"success": True, "result": {"resources": [
        {"name": "20261112.csv", "url": "https://example.org/20261112.csv"},
        {"name": "20261113.csv", "url": "https://example.org/20261113.csv"},
    ]}}
    files = {
        "https://example.org/20261112.csv": HEADER + _row("12/11/2026 09:10:00", "12/11/2026 10:20:00")
        + _row("12/11/2026 09:15:00", "12/11/2026 09:30:00", duf="Petroselli", civ="50")
        + _row("12/11/2026 09:15:00", "12/11/2026 09:30:00", duf="Nowhere", civ="1"),
        "https://example.org/20261113.csv": HEADER,
    }

    def fetch(url: str) -> bytes:
        if "package_show" in url:
            return json.dumps(package).encode()
        return files[url].encode("cp1252")

    provider = RomaWifiProvider(Settings.load(), fetch_bytes=fetch, sites=parse_hotspot_kml(KML))
    info = provider.describe()
    assert info.layer == "activity_wifi" and info.synthetic is False and info.kind == "open"
    obs = list(provider.fetch(ROME_BBOX, datetime(2026, 11, 12, 8, tzinfo=timezone.utc),
                              datetime(2026, 11, 12, 10, tzinfo=timezone.utc)))
    assert {o.entity_type for o in obs} == {"CrowdFlowObserved"}
    at_8 = sorted((o.lon, o.values["peopleCount"]) for o in obs
                  if o.observed_at == datetime(2026, 11, 12, 9, tzinfo=timezone.utc))
    assert [count for _, count in at_8] == [1.0, 1.0]  # the unknown address is left out
    assert all(o.sigma["peopleCount"] >= 1.0 for o in obs)
    assert provider.unmatched_sessions == 1


def test_committed_hotspot_seed_covers_the_busiest_sites() -> None:
    sites = RomaWifiProvider(Settings.load(), fetch_bytes=lambda url: b"").sites
    assert len(sites) > 500
    for address in ["VIA DELLA STAMPERIA 86", "LARGO GIOVANNI DA VERRAZZANO 7"]:
        lon, lat = sites[address]
        assert 12.2 < lon < 12.9 and 41.6 < lat < 42.1


def test_a_now_window_returns_the_latest_published_hours() -> None:
    package = {"success": True, "result": {"resources": [
        {"name": "20261112.csv", "url": "https://example.org/20261112.csv"}]}}
    day = HEADER + _row("12/11/2026 09:10:00", "12/11/2026 09:20:00")

    def fetch(url: str) -> bytes:
        return json.dumps(package).encode() if "package_show" in url else day.encode()

    provider = RomaWifiProvider(Settings.load(), fetch_bytes=fetch, sites=parse_hotspot_kml(KML))
    now = datetime(2026, 11, 13, 7, 0, tzinfo=timezone.utc)  # the next morning: today's file is not out yet
    obs = list(provider.fetch(ROME_BBOX, now, now))
    assert [o.observed_at for o in obs] == [datetime(2026, 11, 12, 9, tzinfo=timezone.utc)]
