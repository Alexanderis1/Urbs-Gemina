import hashlib
import json

import pytest
from datetime import datetime, timezone
from pathlib import Path

from twin.ingest.catalog import load_catalog
from twin.ingest.http import HttpRequest
from twin.ingest.live import latest_snapshot, pull_feed

ROOT = Path(__file__).resolve().parents[1]
CATALOG = load_catalog(ROOT / "config" / "ingest.yaml")
NOW = datetime(2026, 11, 13, 20, 0, 5, tzinfo=timezone.utc)


def test_snapshot_is_stored_with_its_hash(tmp_path: Path) -> None:
    body = b"\x0a\x03gtfs-rt-bytes"
    record = pull_feed(CATALOG.live_feeds["gtfs_rt_vehicle_positions"], lambda r: body, tmp_path, NOW)
    digest = hashlib.sha256(body).hexdigest()
    assert record["sha256"] == digest and record["bytes"] == len(body)
    assert record["data_kind"] == "real" and record["synthetic"] is False
    path = tmp_path / record["path"]
    assert path.read_bytes() == body
    assert path.name == f"20261113T200005Z_{digest[:12]}.pb"
    index = (tmp_path / "gtfs_rt_vehicle_positions" / "index.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(index[-1]) == record
    assert latest_snapshot(tmp_path, "gtfs_rt_vehicle_positions") == record


def test_unchanged_feed_is_logged_but_not_stored_twice(tmp_path: Path) -> None:
    feed = CATALOG.live_feeds["bird_gbfs_vehicles"]
    first = pull_feed(feed, lambda r: b"{}", tmp_path, NOW)
    second = pull_feed(feed, lambda r: b"{}", tmp_path, NOW.replace(minute=5))
    assert second["unchanged"] is True and second["path"] == first["path"]
    assert len(list((tmp_path / "bird_gbfs_vehicles").glob("*.json"))) == 1


def test_eea_pull_posts_a_time_window(tmp_path: Path) -> None:
    seen: list[HttpRequest] = []

    def fetch(request: HttpRequest) -> bytes:
        seen.append(request)
        return b"PK\x03\x04zip"

    pull_feed(CATALOG.live_feeds["eea_no2_hourly"], fetch, tmp_path, NOW)
    body = json.loads(seen[0].body or b"")
    assert seen[0].content_type == "application/json"
    assert body["cities"] == ["Roma"] and body["dateTimeEnd"] == "2026-11-13T20:00:05Z"
    assert body["dateTimeStart"] == "2026-11-11T20:00:05Z" and "lookback_hours" not in body


def test_radar_pull_follows_the_presigned_link(tmp_path: Path) -> None:
    def fetch(request: HttpRequest) -> bytes:
        if "findLastProductByType" in request.url:
            return json.dumps({"lastProducts": [{"productType": "VMI", "time": 1794597600000}]}).encode()
        if request.url.endswith("/downloadProduct"):
            assert json.loads(request.body or b"") == {"productType": "VMI", "productDate": 1794597600000}
            return json.dumps({"url": "https://s3.example/VMI/x.tif?sig=1"}).encode()
        assert request.url == "https://s3.example/VMI/x.tif?sig=1"
        return b"II*\x00tiff"

    record = pull_feed(CATALOG.live_feeds["dpc_radar_vmi"], fetch, tmp_path, NOW)
    assert record["product_time"] == "2026-11-13T19:20:00Z"
    assert "sig=" not in record["url"]  # presigned query string is not logged


def test_fetch_retries_once_with_older_ciphers_on_handshake_failure(monkeypatch: "pytest.MonkeyPatch") -> None:
    import ssl
    import urllib.error
    import urllib.request

    from twin.ingest import http

    contexts: list[object] = []

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"ok"

    def fake_urlopen(req: object, timeout: float, context: object = None) -> Response:
        contexts.append(context)
        if context is None:
            raise urllib.error.URLError(ssl.SSLError(1, "[SSL: SSLV3_ALERT_HANDSHAKE_FAILURE] handshake failure"))
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert http.urllib_fetch(http.HttpRequest("https://old-server.example/x.csv")) == b"ok"
    assert contexts[0] is None and isinstance(contexts[1], ssl.SSLContext)
    assert contexts[1].verify_mode == ssl.CERT_REQUIRED  # certificates are still checked
