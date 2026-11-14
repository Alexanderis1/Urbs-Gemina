"""Shared cache + back-off for rate-limited free services (Open-Meteo answered 429 under load)."""
from __future__ import annotations

import io
import urllib.error

import pytest

from twin.providers import http


def _http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = {"Retry-After": retry_after} if retry_after else {}
    return urllib.error.HTTPError("https://api.example/x", code, "err", headers, io.BytesIO(b""))  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    http.clear_cache()


def test_second_call_within_ttl_uses_cache() -> None:
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return b"ok"

    clock = [1000.0]
    get = http.CachedFetcher(fetch, ttl_s=1800, now=lambda: clock[0])
    assert get("https://api.example/a") == b"ok"
    clock[0] += 600
    assert get("https://api.example/a") == b"ok"
    assert len(calls) == 1
    clock[0] += 1300  # past the TTL
    get("https://api.example/a")
    assert len(calls) == 2


def test_rate_limit_serves_stale_copy_and_backs_off() -> None:
    clock = [0.0]
    answers: list[object] = [b"v1", _http_error(429, "120")]
    calls = {"n": 0}

    def fetch(url: str) -> bytes:
        calls["n"] += 1
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a  # type: ignore[return-value]

    get = http.CachedFetcher(fetch, ttl_s=60, now=lambda: clock[0])
    assert get("https://api.example/a") == b"v1"
    clock[0] = 100  # stale
    assert get("https://api.example/a") == b"v1"  # 429 -> stale copy
    clock[0] = 150  # within Retry-After: no new request to the host
    assert get("https://api.example/a") == b"v1"
    assert calls["n"] == 2


def test_rate_limit_without_copy_raises_quickly_during_back_off() -> None:
    clock = [0.0]
    calls = {"n": 0}

    def fetch(url: str) -> bytes:
        calls["n"] += 1
        raise _http_error(429)

    get = http.CachedFetcher(fetch, ttl_s=60, now=lambda: clock[0])
    with pytest.raises(urllib.error.HTTPError):
        get("https://api.example/a")
    with pytest.raises(http.RateLimited):
        get("https://api.example/b")  # same host, still backing off
    assert calls["n"] == 1
