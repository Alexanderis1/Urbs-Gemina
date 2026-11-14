"""Simple in-memory rate limit for the expensive endpoints (Claude questions, scenario runs).

Callers with an office key are never limited. Callers without one (the public app, or
anyone who finds the URL) get a per-client and a global budget per sliding window, so a
leaked URL cannot run up the Claude or Modal bill. Limits live in config/tools.yaml
(api.rate_limits). State is per container: a few containers at most, so the real cap is
at most a few times the configured one.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Callable, Mapping


class RateLimiter:
    def __init__(self, limits: Mapping[str, Mapping[str, Any]], now: Callable[[], float] = time.monotonic) -> None:
        self._limits = {k: dict(v) for k, v in limits.items() if isinstance(v, Mapping)}
        self._now = now
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, bucket: str, client: str, role: str) -> float | None:
        """``None`` when the call may go ahead (and counts it), else the seconds to wait."""
        limit = self._limits.get(bucket)
        if limit is None or role == "office":
            return None
        window = float(limit.get("window_s", 600))
        now = self._now()
        with self._lock:
            mine = self._window((bucket, client), now, window)
            everyone = self._window((bucket, "*"), now, window)
            for hits, cap in ((mine, int(limit.get("per_client", 10))), (everyone, int(limit.get("global", 100)))):
                if len(hits) >= cap:
                    return max(1.0, hits[0] + window - now)
            mine.append(now)
            everyone.append(now)
        return None

    def _window(self, key: tuple[str, str], now: float, window: float) -> deque[float]:
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - window:
            hits.popleft()
        return hits
