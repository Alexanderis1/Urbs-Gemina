"""Data freshness: is each feed behind the belief layers live, late or down right now?

For every feed named by a layer in config/beliefs.yaml (sources, starting maps,
wind), it asks the active provider for recent readings and reports how old the
newest one is. Limits per feed are in the ``freshness`` block of the config.
A snapshot feed that knows when its upstream file was last updated
(``last_feed_time``, e.g. GTFS-RT) is aged by that clock, so a frozen feed
is never shown as live. Errors are reported per feed, never raised, so one
broken source cannot hide the state of the others.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from twin.beliefs.api import _load_section
from twin.beliefs.config import load_specs
from twin.providers.base import ROME_BBOX, BBox, Provider, ProviderNotConfigured

#: Readings stamped up to this far after ``now`` still count (fetch time, small clock differences).
CLOCK_SLACK = timedelta(minutes=15)
STATUSES = ("live", "late", "down", "needs_access", "not_connected", "static")


def _used_by() -> dict[str, list[str]]:
    used: dict[str, list[str]] = {}
    for name, spec in load_specs().items():
        feeds = list(spec.source_layers)
        if spec.prior_field is not None:
            feeds.append(spec.prior_field.source)
        if spec.wind is not None:
            feeds.append(spec.wind.source)
        for feed in feeds:
            if feed != "none" and name not in used.setdefault(feed, []):
                used[feed].append(name)
    return used


def feed_freshness(
    providers: Mapping[str, Provider],
    now: datetime,
    bbox: BBox = ROME_BBOX,
) -> dict[str, Any]:
    cfg = _load_section("freshness")
    limits: dict[str, dict[str, float]] = {k: {"late": float(v["late"]), "down": float(v["down"])}
                                           for k, v in cfg["feeds"].items()}
    static = {str(s) for s in cfg.get("static", [])}
    used = _used_by()
    rows: list[dict[str, Any]] = []
    for feed in sorted(used):
        row: dict[str, Any] = {"feed": feed, "used_by": used[feed], "provider": None, "synthetic": None,
                               "newest": None, "age_minutes": None, "readings": None, "reason": ""}
        provider = providers.get(feed)
        if provider is None:
            row.update(status="not_connected", reason="no provider is active, or it still needs access (see the data status panel)")
        elif feed in static or feed not in limits:
            _describe(row, provider)
            row.update(status="static", reason="map, register or timetable: not expected to update live")
        else:
            _describe(row, provider)
            _check(row, provider, limits[feed], now, bbox)
        rows.append(row)
    summary = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    warnings = [f"{r['feed']} is {r['status']}: layers {', '.join(r['used_by'])} fall back to their starting map or prior"
                for r in rows if r["status"] in {"down", "needs_access"}]
    return {
        "status": "ok",
        "reason": None,
        "inputs": {"now": now.isoformat(), "limits_minutes": limits},
        "result": {"feeds": rows, "summary": summary},
        "data_kinds": {},
        "sources": [{"id": r["provider"], "retrieved_at": now.isoformat()} for r in rows if r["provider"]],
        "synthetic": any(bool(r["synthetic"]) for r in rows),
        "warnings": warnings,
    }


def _describe(row: dict[str, Any], provider: Provider) -> None:
    try:
        info = provider.describe()
    except ProviderNotConfigured:
        return
    row.update(provider=info.id, synthetic=info.synthetic)


def _check(row: dict[str, Any], provider: Provider, limit: Mapping[str, float], now: datetime, bbox: BBox) -> None:
    start = now - timedelta(minutes=limit["down"])
    try:
        times = [o.observed_at for o in provider.fetch(bbox, start, now + CLOCK_SLACK)]
    except ProviderNotConfigured as exc:
        row.update(status="needs_access", reason=str(exc))
        return
    except Exception as exc:  # noqa: BLE001 - a broken feed is reported, not raised
        row.update(status="down", reason=f"{type(exc).__name__}: {exc}"[:200])
        return
    row["readings"] = len(times)
    # Snapshot feeds stamp readings when they are fetched, a little after ``now``.
    past = [t for t in times if t <= now + CLOCK_SLACK]
    newest = max(past) if past else None
    feed_time = getattr(provider, "last_feed_time", None)
    if isinstance(feed_time, datetime):
        feed_time = feed_time if feed_time.tzinfo else feed_time.replace(tzinfo=timezone.utc)
        newest = feed_time if newest is None else min(newest, feed_time)
    if newest is None:
        row.update(status="down", reason=f"no readings in the last {limit['down']:.0f} minutes")
        return
    age = max(0.0, (now - newest).total_seconds() / 60.0)
    row.update(newest=newest.isoformat(), age_minutes=round(age))
    if age <= limit["late"]:
        row["status"] = "live"
    elif age <= limit["down"]:
        row.update(status="late", reason=f"newest reading is {age:.0f} min old (late after {limit['late']:.0f})")
    else:
        row.update(status="down", reason=f"newest reading is {age:.0f} min old (down after {limit['down']:.0f})")
