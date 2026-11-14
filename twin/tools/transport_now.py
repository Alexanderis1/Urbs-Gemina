"""Citizen service: what is happening on Rome's streets and lines now.

Notices come from the Roma Mobilita GTFS-RT service-alerts feed (real): one event per notice text,
with every line it touches, a category from keywords in config/tools.yaml ``citizen.transport``, and
a map point on the street it names (offline street table, twin/tools/street_names.py; null when no
street is named). Congestion now and predicted is the ``city_heatmap`` tool on ``road_speed``
(simulated loops: the only simulated layer). Feeds older than ``stale_minutes`` are flagged.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from twin.tools.envelope import Source
from twin.tools.opening_hours import ROME
from twin.tools.runtime import ToolRuntime
from twin.tools.settings import value
from twin.tools.street_names import StreetIndex, normalise

TOOL = "transport_now"
_STREETS: dict[str, StreetIndex] = {}


def _streets(path: Path) -> StreetIndex | None:
    if not path.exists():
        return None
    if str(path) not in _STREETS:
        _STREETS[str(path)] = StreetIndex.load(path)
    return _STREETS[str(path)]


def categorise(text: str, categories: Mapping[str, list[str]]) -> str:
    folded = f" {normalise(text)} "
    for category, words in categories.items():
        if any(f" {normalise(w)}" in folded for w in words):
            return category
    return "avviso"


def _active(periods: list[tuple[datetime | None, datetime | None]], now: datetime) -> tuple[bool, datetime | None, datetime | None]:
    if not periods:
        return True, None, None
    for start, end in periods:
        if (start is None or start <= now) and (end is None or now <= end):
            return True, start, end
    return False, None, None


def transport_now(rt: ToolRuntime, area: Any = "city", now: datetime | None = None, provider: Any = None,
                  streets_path: Path | None = None) -> dict[str, Any]:
    cfg = rt.settings.tools["citizen"]["transport"]
    now = now or datetime.now(timezone.utc)
    inputs = {"area": area, "time": now.isoformat()}
    if provider is None:
        from twin.providers.open.gtfs_alerts import RomaGtfsAlertsProvider
        provider = RomaGtfsAlertsProvider()
    try:
        alerts, stamp, snapshot = provider.snapshot()
    except Exception as error:  # noqa: BLE001 - the tool reports the feed as unavailable
        return rt.envelope(TOOL, inputs, None, {"transit_alerts": "not_available"}, [], status="not_available",
                           reason=f"alerts feed not reachable ({type(error).__name__})")
    index = _streets(streets_path or rt.settings.paths.data / "processed" / "street_names.csv")
    bbox = None
    if area != "city":
        from twin.tools.area import resolve_area
        bbox = resolve_area(area, rt.store, rt.settings).bbox
    grouped: dict[str, dict[str, Any]] = {}
    for alert in alerts:
        active, start, end = _active(alert["periods"], now)
        if not active:
            continue
        key = normalise(alert["title"]) or alert["id"]
        event = grouped.get(key)
        if event is None:
            text = f"{alert['title']}. {alert['description']}"
            category = categorise(text, cfg["categories"])
            place = index.locate(text) if index is not None else None
            event = {"id": f"alert-{alert['id']}", "title": alert["title"], "category": category,
                     "category_label": cfg["labels_it"].get(category, category),
                     "description": alert["description"][:400], "lines": [],
                     "start": start.isoformat() if start else None, "end": end.isoformat() if end else None,
                     "street": place["name"] if place else None,
                     "lon": place["lon"] if place else None, "lat": place["lat"] if place else None,
                     "source": "Roma Mobilità, GTFS-RT avvisi"}
            grouped[key] = event
        event["lines"] = sorted(set(event["lines"]) | set(alert["lines"]))
    events = list(grouped.values())
    if bbox is not None:
        events = [e for e in events if e["lon"] is not None and bbox[0] <= e["lon"] <= bbox[2] and bbox[1] <= e["lat"] <= bbox[3]]
    order = ["sciopero", "evento", "chiusura", "lavori", "deviazione", "avviso"]
    events.sort(key=lambda e: (order.index(e["category"]) if e["category"] in order else 99, e["title"]))
    stale = now - stamp > timedelta(minutes=float(value(cfg["stale_minutes"])))
    feeds = [{"id": "roma_gtfs_alerts", "last_update": stamp.isoformat(), "stale": stale}]
    counts: dict[str, int] = {}
    for e in events:
        counts[e["category"]] = counts.get(e["category"], 0) + 1
    summary = f"{len(events)} avvisi attivi su strade e linee" + (
        f" ({', '.join(f'{n} {cfg['labels_it'][c].lower()}' for c, n in counts.items())})." if counts else ".")
    if stale:
        summary += (f" Attenzione: i dati di Roma Mobilità sono fermi dalle {stamp.astimezone(ROME).strftime('%H:%M del %d/%m')};"
                    " gli avvisi possono non essere aggiornati.")
    result = {"events": events, "count": len(events), "counts": counts, "located": sum(1 for e in events if e["lon"] is not None),
              "feeds": feeds, "summary_it": summary,
              "congestion": {"tool": "city_heatmap", "layer": "road_speed", "kind": "simulated",
                             "note_it": "Traffico stimato da sensori simulati (dati reali dei sensori non pubblici)."}}
    warnings = ["Notices name lines, not places: the map point is the street named in the text (offline street table), "
                "or null when no street is named."]
    if stale:
        warnings.append(f"The alerts feed has not been updated since {stamp.isoformat()} (source side).")
    source = Source(id=snapshot, retrieved_at=now.isoformat(), url="https://romamobilita.it/it/tecnologie/open-data")
    return rt.envelope(TOOL, inputs, result, {"transit_alerts": "real"}, [source], warnings)
