"""Minimal HTTP helpers shared by the open providers (standard library only).

Providers take these as injectable callables so tests can replace the network.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any, Mapping

#: Generic client name: no personal or project contact details are sent.
USER_AGENT = "urbs-gemina-twin/0.1"


def get_bytes(url: str, headers: Mapping[str, str] | None = None, timeout_s: float = 60.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310 (https hosts from config)
        data: bytes = response.read()
    return data


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
    with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310
        data: bytes = response.read()
    return data
