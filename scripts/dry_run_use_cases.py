"""Dry run of every use-case playbook against the local tool API: real tools, no model, no Exa.

    python scripts/dry_run_use_cases.py [--only heat_plan_elderly] [--out report.json]

Checks that each step's arguments are accepted by the tool API and shows which steps return data,
which are not available (and why) and which are skipped. Web tools (news_search, legal_lookup)
answer with a stub, so the run costs nothing. Live feeds are called if the network allows.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.envelope import make_envelope  # noqa: E402
from agents.tools import ToolSpec, load_tool_specs  # noqa: E402
from agents.use_cases import load_use_cases, run_steps  # noqa: E402

EXAMPLES: dict[str, dict[str, Any]] = {
    "municipio_briefing": {"area": "municipio:1"},
    "civil_protection_alert": {"area": "municipio:11"},
    "heat_plan_elderly": {"area": "municipio:5"},
    "site_risk_check": {"place": "Ospedale Sandro Pertini"},
    "event_planning": {"place": "Circo Massimo", "params": {"attendees": 60000}},
    "antenna_permit": {"place": "Piazza Venezia"},
    "sport_deserts": {"area": "municipio:7"},
    "citizen_area_info": {"place": "Colosseo"},
}


class LocalApiGateway:
    """Calls the FastAPI app in-process; web tools are stubbed."""

    def __init__(self) -> None:
        from fastapi.testclient import TestClient

        from twin.api.app import create_app

        self.client = TestClient(create_app(api_keys={"dry": "office"}))
        specs, _ = load_tool_specs()
        self._specs = {**specs, **{n: ToolSpec(n, n, {"type": "object"}) for n in ("sports_facilities", "sport_coverage")}}

    @property
    def specs(self) -> Mapping[str, ToolSpec]:
        return self._specs

    def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if name in ("news_search", "legal_lookup", "find_dataset"):
            return make_envelope(tool=name, inputs=dict(arguments), result={"results": []}, data_kinds={}, sources=[],
                                 warnings=["dry run: web search stubbed"])
        r = self.client.post(f"/tools/{name}", json=dict(arguments), headers={"authorization": "Bearer dry"})
        body: dict[str, Any] = r.json()
        if r.status_code != 200:
            return make_envelope(tool=name, inputs=dict(arguments), result={}, data_kinds={}, sources=[],
                                 status="not_available", reason=f"HTTP {r.status_code}: {json.dumps(body)[:300]}")
        return body


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--out")
    a = ap.parse_args()
    gw = LocalApiGateway()
    report: dict[str, Any] = {}
    for uid, uc in load_use_cases().items():
        if a.only and uid != a.only:
            continue
        ex = EXAMPLES[uid]
        t0 = time.time()
        runs, skipped = run_steps(uc, gateway=gw, area=ex.get("area"), place=ex.get("place"), params=ex.get("params"))
        rows = [{"step": r.get("step"), "tool": r["tool"], "status": r.get("status", "ok"),
                 "reason": str(r.get("reason", ""))[:200], "result_keys": sorted((r.get("result") or {}).keys())[:12]}
                for r in runs]
        report[uid] = {"seconds": round(time.time() - t0, 1), "runs": rows, "skipped": skipped}
        print(f"\n== {uid} ({report[uid]['seconds']} s)")
        for row in rows:
            print(f"  {row['step']:<12} {row['tool']:<16} {row['status']:<14} {row['reason'] or row['result_keys']}")
        for s in skipped:
            print(f"  {s['step']:<12} {s['tool']:<16} SKIPPED        {s['reason']}")
    if a.out:
        Path(a.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
