"""WS3: INGV earthquakes around Rome (layer earthquakes), real and open."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from twin.providers.base import ROME_BBOX
from twin.providers.open.ingv import IngvEarthquakeProvider, parse_events
from twin.providers.settings import Settings

FIXTURE = (Path(__file__).parent / "fixtures" / "ws3" / "ingv_events.txt").read_text(encoding="utf-8")


def test_events_are_parsed_with_magnitude_and_depth() -> None:
    events = parse_events(FIXTURE, magnitude_sigma=0.2, depth_sigma_km=2.0)
    assert len(events) == 6
    colonna = [e for e in events if e.entity_id.endswith("47028541")][0]
    assert colonna.entity_type == "EarthquakeObserved"
    assert (colonna.lon, colonna.lat) == (12.744, 41.8782)
    assert colonna.values == {"magnitude": 1.4, "depth_km": 10.1}
    assert colonna.observed_at == datetime(2026, 11, 8, 4, 36, 56, 260000, tzinfo=timezone.utc)


def test_provider_asks_a_wider_region_and_looks_back_for_a_now_window() -> None:
    urls: list[str] = []

    def fetch(url: str) -> bytes:
        urls.append(url)
        return FIXTURE.encode()

    provider = IngvEarthquakeProvider(Settings.load(), fetch_bytes=fetch)
    info = provider.describe()
    assert info.layer == "earthquakes" and info.kind == "open" and info.synthetic is False
    now = datetime(2026, 11, 14, 4, 0, tzinfo=timezone.utc)
    events = list(provider.fetch(ROME_BBOX, now, now))
    assert "starttime=2026-10-15" in urls[0]  # 30-day look-back
    assert len(events) == 6  # the region is the area plus a 60 km buffer
