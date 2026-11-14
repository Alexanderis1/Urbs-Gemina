"""Roma Mobilita GTFS-Realtime service alerts (layer ``transit_alerts``). Real, open (CC BY-SA).

Notices for passengers: line deviations, street closures, works, strikes. The feed has no
coordinates for most notices (they name lines, not stops); twin/tools/transport_now.py places
them on the street they name. ``parse_alerts`` is a pure function on the feed bytes.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from twin.providers import http
from twin.providers.base import BBox, Observation, ProviderInfo
from twin.providers.settings import Settings, number, text

PROVIDER_ID = "roma_gtfs_alerts"
DEFAULT_URL = "https://romamobilita.it/sites/default/files/rome_rtgtfs_service_alerts_feed.pb"


def _text(translated: Any) -> str:
    items = list(translated.translation)
    italian = [t.text for t in items if t.language in ("it", "")]
    return str((italian or [t.text for t in items] or [""])[0]).strip()


def parse_alerts(data: bytes) -> tuple[list[dict[str, Any]], datetime]:
    """(alerts, feed time). Each alert: id, title, description, lines, periods [(start, end or None)], cause, effect."""
    from google.transit import gtfs_realtime_pb2

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(data)
    stamp = datetime.fromtimestamp(feed.header.timestamp, tz=timezone.utc)
    out = []
    for entity in feed.entity:
        if not entity.HasField("alert"):
            continue
        alert = entity.alert
        periods = [(datetime.fromtimestamp(p.start, tz=timezone.utc) if p.start else None,
                    datetime.fromtimestamp(p.end, tz=timezone.utc) if p.end else None) for p in alert.active_period]
        out.append({"id": entity.id, "title": _text(alert.header_text), "description": _text(alert.description_text),
                    "lines": sorted({i.route_id for i in alert.informed_entity if i.route_id}),
                    "stops": sorted({i.stop_id for i in alert.informed_entity if i.stop_id}),
                    "periods": periods, "cause": int(alert.cause), "effect": int(alert.effect)})
    return out, stamp


class RomaGtfsAlertsProvider:
    def __init__(self, settings: Settings | None = None, fetch_bytes: Callable[[str], bytes] | None = None) -> None:
        settings = settings or Settings.load()
        self._config = settings.section("open", PROVIDER_ID)
        self._url = text(self._config, "service_alerts_url", DEFAULT_URL)
        timeout = number(self._config, "timeout_s", 30.0)
        self._fetch = fetch_bytes or (lambda url: http.get_bytes(url, timeout_s=timeout))

    def describe(self) -> ProviderInfo:
        return ProviderInfo(id=PROVIDER_ID, kind="open", layer="transit_alerts",
                            licence="CC BY-SA, Roma Servizi per la Mobilità", cadence="published every few minutes",
                            synthetic=False,
                            notes="Passenger notices: deviations, closures, works, strikes. Lines, not coordinates.")

    def snapshot(self) -> tuple[list[dict[str, Any]], datetime, str]:
        data = self._fetch(self._url)
        alerts, stamp = parse_alerts(data)
        return alerts, stamp, f"{PROVIDER_ID}@{hashlib.sha256(data).hexdigest()[:16]}"

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        """No point readings: notices carry lines, not positions (see twin/tools/transport_now.py)."""
        return iter(())
