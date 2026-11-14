"""Minimal client for the Exa Agent API (POST /agent/runs, then poll GET /agent/runs/{id}).

Shared by the sports scout and enrichment agents. The key is read from the
EXA_API_KEY environment variable and never written anywhere.
API reference: https://exa.ai/docs/reference/agent-api/create-a-run
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any

EXA_AGENT_URL = "https://api.exa.ai/agent/runs"


def _call(method: str, url: str, body: dict[str, Any] | None = None, timeout_s: float = 60.0) -> dict[str, Any]:
    key = os.environ.get("EXA_API_KEY")
    if not key:
        raise RuntimeError("EXA_API_KEY is not set")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"x-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310 (fixed https host)
        result: dict[str, Any] = json.load(response)
    return result


def run_agent(query: str, output_schema: dict[str, Any], system_prompt: str, effort: str = "low",
              data: list[dict[str, Any]] | None = None, poll_s: float = 10.0,
              max_wait_s: float = 1800.0) -> dict[str, Any]:
    """Start a run and wait for it. Returns the whole run object (``output.structured`` holds the JSON)."""
    body: dict[str, Any] = {"query": query, "systemPrompt": system_prompt, "effort": effort,
                            "outputSchema": output_schema}
    if data:
        body["input"] = {"data": data}
    run = _call("POST", EXA_AGENT_URL, body)
    waited = 0.0
    while run.get("status") in ("queued", "running", "pending", None) and waited < max_wait_s:
        time.sleep(poll_s)
        waited += poll_s
        run = _call("GET", f"{EXA_AGENT_URL}/{run['id']}")
    if run.get("status") != "completed":
        raise RuntimeError(f"Exa run {run.get('id')} ended with status {run.get('status')}: {run.get('error')}")
    return run


def structured(run: dict[str, Any]) -> dict[str, Any]:
    output = run.get("output") or {}
    value = output.get("structured")
    return value if isinstance(value, dict) else {}
