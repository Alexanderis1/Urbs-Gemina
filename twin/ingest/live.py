"""Pull live public feeds and keep each pull as a hashed snapshot.

Each pull writes the raw bytes to ``data/snapshots/<feed>/<UTC time>_<sha12>.<ext>``
and appends one JSON line to ``data/snapshots/<feed>/index.jsonl``. If the bytes did
not change since the last pull, only the index line is added (``unchanged: true``).

Parsing is not done here: the WS3 providers read these snapshot files. The snapshot
SHA-256 is what tools put into their ``run_id``.

Usage::

    python -m twin.ingest.live                      # pull every feed once
    python -m twin.ingest.live gtfs_rt_vehicle_positions --every 60 --count 10

Any scheduler (Modal cron, a Lovable scheduled job calling the API, or a workstation
cron) only needs to run this command.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from twin.ingest.catalog import FeedSpec, load_catalog
from twin.ingest.http import Fetch, HttpRequest, urllib_fetch

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOTS = ROOT / "data" / "snapshots"

Record = dict[str, Any]


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _strip_query(url: str) -> str:
    """Drop query strings (presigned signatures) before a URL is logged."""
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _download(feed: FeedSpec, fetch: Fetch, now: datetime) -> tuple[bytes, str, Record]:
    """Return (bytes, url to log, extra fields for the record)."""
    if feed.method == "get":
        return fetch(HttpRequest(feed.url, timeout_s=60.0)), feed.url, {}

    if feed.method == "eea_parquet_zip":
        request = dict(feed.request)
        lookback = float(request.pop("lookback_hours", 48))
        request["dateTimeStart"] = _iso(now - timedelta(hours=lookback))
        request["dateTimeEnd"] = _iso(now)
        body = json.dumps(request).encode("utf-8")
        data = fetch(HttpRequest(feed.url, body=body, content_type="application/json", timeout_s=180.0))
        return data, feed.url, {"window": [request["dateTimeStart"], request["dateTimeEnd"]]}

    if feed.method == "dpc_radar":
        product = feed.product_type or "VMI"
        latest = json.loads(fetch(HttpRequest(f"{feed.url}/findLastProductByType?type={product}", timeout_s=30.0)))
        product_ms = int(latest["lastProducts"][0]["time"])
        link_body = json.dumps({"productType": product, "productDate": product_ms}).encode("utf-8")
        link = json.loads(fetch(HttpRequest(f"{feed.url}/downloadProduct", body=link_body,
                                            content_type="application/json", timeout_s=30.0)))
        data = fetch(HttpRequest(str(link["url"]), timeout_s=120.0))
        product_time = datetime.fromtimestamp(product_ms / 1000, tz=timezone.utc)
        return data, _strip_query(str(link["url"])), {"product_type": product, "product_time": _iso(product_time)}

    raise ValueError(f"unknown feed method {feed.method}")


def latest_snapshot(out_root: Path, feed_key: str) -> Record | None:
    index = out_root / feed_key / "index.jsonl"
    if not index.exists():
        return None
    lines = [line for line in index.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return None
    record: Record = json.loads(lines[-1])
    return record


def pull_feed(feed: FeedSpec, fetch: Fetch, out_root: Path, now: datetime | None = None) -> Record:
    moment = now or datetime.now(timezone.utc)
    data, url, extra = _download(feed, fetch, moment)
    digest = hashlib.sha256(data).hexdigest()
    folder = out_root / feed.key
    folder.mkdir(parents=True, exist_ok=True)

    previous = latest_snapshot(out_root, feed.key)
    unchanged = previous is not None and previous.get("sha256") == digest
    if unchanged and previous is not None:
        relative = str(previous["path"])
    else:
        stamp = moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = folder / f"{stamp}_{digest[:12]}.{feed.extension}"
        path.write_bytes(data)
        relative = path.relative_to(out_root).as_posix()

    record: Record = {
        "feed": feed.key,
        "source": feed.source,
        "data_kind": feed.data_kind,
        "synthetic": feed.data_kind == "simulated",
        "retrieved_at": _iso(moment),
        "url": url,
        "sha256": digest,
        "bytes": len(data),
        "path": relative,
        "unchanged": unchanged,
        **extra,
    }
    with (folder / "index.jsonl").open("a", encoding="utf-8") as index:
        index.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("feeds", nargs="*", help="feed keys from config/ingest.yaml (default: all)")
    parser.add_argument("--every", type=float, default=0.0, help="seconds between rounds (0 = one round)")
    parser.add_argument("--count", type=int, default=1, help="number of rounds when --every is set")
    parser.add_argument("--out", type=Path, default=SNAPSHOTS)
    args = parser.parse_args(argv)

    catalog = load_catalog(ROOT / "config" / "ingest.yaml")
    keys = args.feeds or list(catalog.live_feeds)
    unknown = [key for key in keys if key not in catalog.live_feeds]
    if unknown:
        print(f"Unknown feeds: {unknown}. Known: {sorted(catalog.live_feeds)}")
        return 2

    failures = 0
    rounds = args.count if args.every > 0 else 1
    for round_number in range(rounds):
        for key in keys:
            try:
                record = pull_feed(catalog.live_feeds[key], urllib_fetch, args.out)
                state = "same" if record["unchanged"] else "new "
                print(f"{state} {key:28s} {record['bytes']:>9} B  {record['sha256'][:12]}")
            except Exception as error:  # noqa: BLE001 - one feed failing must not stop the others
                failures += 1
                print(f"FAIL {key:28s} {type(error).__name__}: {error}", file=sys.stderr)
        if round_number + 1 < rounds:
            time.sleep(args.every)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
