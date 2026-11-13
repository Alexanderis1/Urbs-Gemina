"""The one place where ingest talks to the network, so tests can replace it."""
from __future__ import annotations

import ssl
import urllib.error
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
    try:
        with urllib.request.urlopen(req, timeout=request.timeout_s) as response:  # noqa: S310 (hosts come from config)
            body: bytes = response.read()
        return body
    except urllib.error.URLError as error:
        if "HANDSHAKE_FAILURE" not in str(error.reason):
            raise
    # Some public-sector servers (e.g. dati.salute.gov.it) only offer ciphers that OpenSSL 3
    # rejects at its default security level. Retry once at level 1; certificates and host
    # names are still verified.
    context = ssl.create_default_context()
    context.set_ciphers("DEFAULT:@SECLEVEL=1")
    with urllib.request.urlopen(req, timeout=request.timeout_s, context=context) as response:  # noqa: S310
        legacy_body: bytes = response.read()
    return legacy_body
