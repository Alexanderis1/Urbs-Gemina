"""Data freshness: is each feed of the belief layers live, late or down right now?"""
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from twin.beliefs.freshness import feed_freshness
from twin.providers.base import BBox, Observation, ProviderInfo, ProviderNotConfigured

NOW = datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc)


class Feed:
    def __init__(self, layer: str, ages_min: list[float], synthetic: bool = False,
                 feed_time: datetime | None = None, fail: Exception | None = None) -> None:
        self.layer, self.ages, self.synthetic, self.fail = layer, ages_min, synthetic, fail
        if feed_time is not None:
            self.last_feed_time = feed_time

    def describe(self) -> ProviderInfo:
        return ProviderInfo(id=f"{self.layer}_p", kind="open", layer=self.layer, licence="x",
                            cadence="x", synthetic=self.synthetic)

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterable[Observation]:
        if self.fail is not None:
            raise self.fail
        for i, age in enumerate(self.ages):
            t = NOW - timedelta(minutes=age)
            if start <= t <= end:
                yield Observation(f"{self.layer}{i}", "X", 12.5, 41.9, t, {"v": 1.0}, {"v": 1.0}, f"{self.layer}_p", self.synthetic)


def by_feed(out: dict[str, Any]) -> dict[str, Any]:
    return {row["feed"]: row for row in out["result"]["feeds"]}


def test_live_late_down_and_missing() -> None:
    providers = {
        "air_quality": Feed("air_quality", [70, 130]),         # late 180 -> live
        "traffic_flow": Feed("traffic_flow", [30], synthetic=True),  # late 15, down 60 -> late
        "rain": Feed("rain", []),                               # nothing in the window -> down
    }
    rows = by_feed(feed_freshness(providers, NOW))
    assert rows["air_quality"]["status"] == "live"
    assert rows["air_quality"]["age_minutes"] == 70
    assert rows["air_quality"]["readings"] == 2
    assert "air_no2" in rows["air_quality"]["used_by"]
    assert rows["traffic_flow"]["status"] == "late"
    assert rows["traffic_flow"]["synthetic"] is True
    assert rows["rain"]["status"] == "down"
    assert rows["transit"]["status"] == "not_connected"
    assert rows["emf_baseline"]["status"] in {"static", "not_connected"}


def test_frozen_snapshot_feed_uses_its_own_clock() -> None:
    # A snapshot feed can stamp readings 'now' while the upstream file is old (buses frozen since 13 Nov).
    frozen = NOW - timedelta(hours=14)
    rows = by_feed(feed_freshness({"transit": Feed("transit", [1], feed_time=frozen)}, NOW))
    assert rows["transit"]["status"] == "down"
    assert rows["transit"]["age_minutes"] == 14 * 60


def test_errors_and_missing_access_are_reported_not_raised() -> None:
    providers = {
        "rain": Feed("rain", [], fail=ProviderNotConfigured("needs a key")),
        "micromobility": Feed("micromobility", [], fail=TimeoutError("slow")),
        "emf_baseline": Feed("emf_baseline", []),
    }
    out = feed_freshness(providers, NOW)
    rows = by_feed(out)
    assert rows["rain"]["status"] == "needs_access" and "key" in rows["rain"]["reason"]
    assert rows["micromobility"]["status"] == "down" and "TimeoutError" in rows["micromobility"]["reason"]
    assert rows["emf_baseline"]["status"] == "static"
    assert out["result"]["summary"]["down"] >= 1
    assert out["status"] == "ok"


def test_snapshot_stamped_just_after_now_counts_as_live() -> None:
    rows = by_feed(feed_freshness({"micromobility": Feed("micromobility", [-2])}, NOW))
    assert rows["micromobility"]["status"] == "live"
    assert rows["micromobility"]["age_minutes"] == 0
