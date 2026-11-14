"""Minimal HTTP helpers shared by the open providers (standard library only).

Providers take these as injectable callables so tests can replace the network.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Mapping

#: Generic client name: no personal or project contact details are sent.
USER_AGENT = "urbs-gemina-twin/0.1"

#: Transient network failures (reset, timeout, DNS blip) are retried; HTTP error answers are not.
RETRIES = 3
RETRY_PAUSE_S = 1.0


def _open(request: urllib.request.Request, timeout_s: float) -> bytes:
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310 (hosts from config)
                data: bytes = response.read()
            return data
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if attempt == RETRIES - 1:
                raise
            time.sleep(RETRY_PAUSE_S * (attempt + 1))
    raise AssertionError("unreachable")


def get_bytes(url: str, headers: Mapping[str, str] | None = None, timeout_s: float = 60.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    return _open(request, timeout_s)


def get_json(url: str, headers: Mapping[str, str] | None = None, timeout_s: float = 60.0) -> Any:
    return json.loads(get_bytes(url, headers, timeout_s).decode("utf-8-sig"))


def post_json(url: str, body: Mapping[str, Any], headers: Mapping[str, str] | None = None,
              timeout_s: float = 60.0) -> bytes:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    return _open(request, timeout_s)


# --- shared cache with back-off (free services that rate-limit, e.g. Open-Meteo) ---------

class RateLimited(RuntimeError):
    """The host asked us to slow down and no cached copy is available."""


#: url -> (fetched_at, body), shared by every provider in the process.
_CACHE: dict[str, tuple[float, bytes]] = {}
#: host -> time until which no request is sent (after a 429 or 503).
_BLOCKED: dict[str, float] = {}
_LOCK = threading.Lock()
#: Pause after a 429 without Retry-After.
DEFAULT_BACKOFF_S = 120.0


def clear_cache() -> None:
    with _LOCK:
        _CACHE.clear()
        _BLOCKED.clear()


class CachedFetcher:
    """``fetch(url)`` with a per-process cache of ``ttl_s`` seconds.

    When the host answers 429/503, the last copy is served (even if stale) and the host
    is left alone until Retry-After (or ``DEFAULT_BACKOFF_S``) has passed.
    """

    def __init__(self, fetch: Callable[[str], bytes], ttl_s: float,
                 now: Callable[[], float] = time.time) -> None:
        self._fetch = fetch
        self._ttl = ttl_s
        self._now = now

    def __call__(self, url: str) -> bytes:
        host = urllib.parse.urlsplit(url).netloc
        now = self._now()
        with _LOCK:
            cached = _CACHE.get(url)
            blocked_until = _BLOCKED.get(host, 0.0)
        if cached is not None and now - cached[0] < self._ttl:
            return cached[1]
        if now < blocked_until:
            if cached is not None:
                return cached[1]
            raise RateLimited(f"{host} asked to slow down; retrying after {blocked_until - now:.0f} s")
        try:
            body = self._fetch(url)
        except urllib.error.HTTPError as error:
            if error.code in (429, 503):
                pause = _retry_after(error) or DEFAULT_BACKOFF_S
                with _LOCK:
                    _BLOCKED[host] = now + pause
                if cached is not None:
                    return cached[1]
            raise
        with _LOCK:
            _CACHE[url] = (now, body)
        return body


def _retry_after(error: urllib.error.HTTPError) -> float | None:
    value = error.headers.get("Retry-After") if error.headers else None
    try:
        return float(value) if value else None
    except ValueError:
        return None
