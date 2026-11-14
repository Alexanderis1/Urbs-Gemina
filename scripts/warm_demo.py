"""Wake the live twin about 10 minutes before a demo, so the first click on stage is fast.

Usage (office key from the environment, never on the command line):

    URBS_OFFICE_KEY=... python scripts/warm_demo.py [--url https://...modal.run]

What it does, in order:
1. GET /health wakes one API container (scale-to-zero: the first call starts it).
2. Office calls that fill the in-memory caches: antenna register fit, belief layers
   (air, temperature), feed status, the citizen layers.
3. One cheap scenario (river_flood +3 m on Municipio I) wakes the scenarios worker.
4. One use case through /ask (Claude), which also warms the orchestrator.

Long calls answer 202 + /jobs/<id>; the script polls them. Containers keep running for
the scale-down window after the last call (API 300 s, worker 120 s), so start about
10 minutes before the demo and click something every few minutes, or run it again.
Everything still scales to zero afterwards: nothing is left always on.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_URL = "https://anzellinialessandroangelo--urbs-gemina-tools-api.us-east.modal.run"
MUNICIPIO = "municipio:1"
POINT = [12.4823, 41.896]  # Piazza Venezia

#: (label, method, path, body). Office tier: no rate limit, full detail.
CALLS: list[tuple[str, str, str, dict[str, Any] | None]] = [
    ("wake the API", "GET", "/health", None),
    ("antenna register", "POST", "/tools/query_layer", {"layer": "antenna_register", "area": "city"}),
    ("air NO2 map", "POST", "/tools/query_layer", {"layer": "air_no2", "area": MUNICIPIO}),
    ("air temperature map", "POST", "/tools/query_layer", {"layer": "air_temperature", "area": MUNICIPIO}),
    ("feed status", "POST", "/tools/feed_status", {}),
    ("air near me", "POST", "/tools/air_here", {"point": POINT}),
    ("transport notices", "POST", "/tools/transport_now", {}),
    ("schools to check", "POST", "/tools/schools_to_check", {"area": MUNICIPIO}),
    ("wake the scenario worker", "POST", "/tools/run_scenario",
     {"kind": "river_flood", "area": MUNICIPIO, "change": {"rise_m": 3}}),
    ("one use case (Claude)", "POST", "/ask",
     {"question": "Briefing del municipio", "use_case": "municipio_briefing", "area": MUNICIPIO, "language": "it"}),
]


def _request(url: str, method: str, key: str, body: dict[str, Any] | None, timeout_s: float) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:  # noqa: S310 - our own API
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, error.read()[:200].decode(errors="replace")


def call(base: str, key: str, method: str, path: str, body: dict[str, Any] | None,
         max_wait_s: float = 900.0) -> tuple[str, float]:
    start = time.time()
    code, out = _request(base + path, method, key, body, timeout_s=170)
    while code == 202 and isinstance(out, dict) and time.time() - start < max_wait_s:
        time.sleep(4)
        code, out = _request(f"{base}/jobs/{out.get('job_id')}", "GET", key, None, timeout_s=60)
        if code == 200 and isinstance(out, dict) and out.get("status") == "running":
            code, out = 202, {"job_id": out.get("job_id")}
    status = out.get("status", "") if isinstance(out, dict) else ""
    return f"HTTP {code} {status}".strip(), time.time() - start


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=os.environ.get("URBS_API_URL", DEFAULT_URL))
    parser.add_argument("--skip-claude", action="store_true", help="do not run the /ask use case")
    args = parser.parse_args(argv)
    key = os.environ.get("URBS_OFFICE_KEY", "")
    if not key:
        print("Set URBS_OFFICE_KEY (the office key of the tool API).", file=sys.stderr)
        return 2
    failed = 0
    for label, method, path, body in CALLS:
        if args.skip_claude and path == "/ask":
            continue
        result, seconds = call(args.url.rstrip("/"), key, method, path, body)
        ok = result.startswith("HTTP 200")
        failed += 0 if ok else 1
        print(f"{'ok ' if ok else 'ERR'} {label:<26} {result:<20} {seconds:6.1f} s", flush=True)
    print("Warm. Containers stay up about 5 minutes after the last call." if not failed
          else f"{failed} call(s) failed; run again in a minute (a container may still be starting).")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
