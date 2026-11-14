"""Citizen transport service: live notices from the Roma GTFS-RT alerts feed, placed on streets."""
from datetime import datetime, timezone
from pathlib import Path

import pytest
from google.transit import gtfs_realtime_pb2 as g

from twin.providers.open.gtfs_alerts import RomaGtfsAlertsProvider, parse_alerts
from twin.tools import transport_now as tn
from twin.tools.layers import LayerStore
from twin.tools.runtime import ToolRuntime
from twin.tools.settings import Settings

NOW = datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc)


def feed_bytes() -> bytes:
    feed = g.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = int(datetime(2026, 11, 13, 18, 25, tzinfo=timezone.utc).timestamp())

    def add(eid: str, title: str, text: str, route: str, start: int, end: int) -> None:
        e = feed.entity.add()
        e.id = eid
        e.alert.header_text.translation.add(text=title, language="it")
        e.alert.description_text.translation.add(text=text, language="it")
        e.alert.informed_entity.add(route_id=route)
        e.alert.active_period.add(start=start, end=end)

    t0, t1 = int(datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp()), int(datetime(2026, 12, 1, tzinfo=timezone.utc).timestamp())
    add("1", "Chiusa via Cavour", "Per la chiusura di via Cavour la linea devia.", "75", t0, t1)
    add("2", "Chiusa via Cavour", "Per la chiusura di via Cavour la linea notturna devia.", "n2", t0, t1)
    add("3", "Lavori in largo Rodolfo Villani", "Causa lavori la linea bus devia.", "501", t0, t1)
    add("4", "Sciopero 20 novembre", "Possibili interruzioni del servizio.", "", t1, t1 + 86400)
    add("5", "Vecchio avviso", "Finito.", "3", t0 - 86400 * 30, t0 - 86400 * 20)
    return feed.SerializeToString()


def test_parse_groups_lines_and_keeps_active(tmp_path: Path) -> None:
    alerts, stamp = parse_alerts(feed_bytes())
    assert stamp.hour == 18 and len(alerts) == 5
    assert alerts[0]["title"] == "Chiusa via Cavour" and alerts[0]["lines"] == ["75"]


def test_transport_now_categories_places_and_stale_feed(tmp_path: Path) -> None:
    streets = tmp_path / "streets.csv"
    streets.write_text("key,name,lon,lat,length_m\nvia cavour,Via Cavour,12.4932,41.8957,1500\n"
                       "largo rodolfo villani,Largo Rodolfo Villani,12.60,41.85,100\n", encoding="utf-8")
    rt = ToolRuntime(settings=Settings.load(), store=LayerStore(raw_dir=tmp_path / "raw"))
    provider = RomaGtfsAlertsProvider(None, fetch_bytes=lambda url: feed_bytes())
    env = tn.transport_now(rt, now=NOW, provider=provider, streets_path=streets)
    events = env["result"]["events"]
    titles = [e["title"] for e in events]
    assert titles.count("Chiusa via Cavour") == 1                      # same notice on two lines = one event
    cavour = next(e for e in events if e["title"] == "Chiusa via Cavour")
    assert cavour["lines"] == ["75", "n2"] and cavour["category"] == "chiusura" and cavour["lon"] == 12.4932
    assert next(e for e in events if e["title"].startswith("Lavori"))["category"] == "lavori"
    assert "Vecchio avviso" not in titles and "Sciopero 20 novembre" not in titles   # ended / not started
    feed = env["result"]["feeds"][0]
    assert feed["stale"] is True and env["data_kinds"]["transit_alerts"] == "real"
    assert "fermi" in env["result"]["summary_it"]
