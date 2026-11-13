"""The one place where ingest talks to the network, so tests can replace it."""
from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from typing import Callable

USER_AGENT = "urbs-gemina-ingest/0.1 (open digital twin research prototype)"


@dataclass(frozen=True)
class HttpRequest:
    url: str
    #: POST body; None means GET.
    body: bytes | None = None
    content_type: str | None = None
    timeout_s: float = 120.0


#: Takes a request, returns the response body, raises on any failure.
Fetch = Callable[[HttpRequest], bytes]


def urllib_fetch(request: HttpRequest) -> bytes:
    """Default fetcher. Uses the system proxy and CA settings from the environment."""
    headers = {"User-Agent": USER_AGENT}
    if request.content_type:
        headers["Content-Type"] = request.content_type
    method = "POST" if request.body is not None else "GET"
    req = urllib.request.Request(request.url, data=request.body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=request.timeout_s) as response:  # noqa: S310 (hosts come from config)
        body: bytes = response.read()
    return body
