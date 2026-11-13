"""Permit-context agent (Challenge 02): fixed tool sequence, then a verified narrative.

The tool calls are made by code in a fixed order, so the facts never depend on the model.
The model only writes the narrative, and the verifier checks it against those runs.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

from agents.config import AgentConfig, load_agent_config
from agents.llm import LLM, ModelRefused
from agents.loop import render_for_model
from agents.orchestrator import INSUFFICIENT, PLAIN_PROBLEMS
from agents.prompting import system_prompt
from agents.tools import ToolError, ToolGateway
from agents.verifier import Problem, VerifierReport, describe_problems, verify

M_PER_DEG_LAT = 111_195.0
CONTEXT_SENTENCE = "Distance to these sites is context for the officer, not a prohibition."


@dataclass
class PermitReport:
    address: str
    text: str
    verified: bool
    problems: list[Problem]
    runs: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)


def circle_polygon(lon: float, lat: float, radius_m: float, vertices: int) -> dict[str, Any]:
    """GeoJSON polygon approximating a circle (local equirectangular projection; fine at 300 m)."""
    m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(lat))
    ring = []
    for i in range(vertices):
        a = 2 * math.pi * i / vertices
        ring.append([round(lon + radius_m * math.cos(a) / m_per_deg_lon, 7), round(lat + radius_m * math.sin(a) / M_PER_DEG_LAT, 7)])
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def _runs_block(runs: list[dict[str, Any]], untrusted: set[str]) -> str:
    parts = []
    for r in runs:
        parts.append(f"run_id: {r['run_id']}\ntool: {r['tool']}\n{render_for_model(r, r['tool'] in untrusted)}")
    return "\n\n".join(parts)


def permit_context(address: str, *, llm: LLM, gateway: ToolGateway, language: str = "en",
                   config: AgentConfig | None = None) -> PermitReport:
    cfg = config or load_agent_config()
    runs: list[dict[str, Any]] = []
    warnings: list[str] = []

    def call(name: str, args: dict[str, Any]) -> dict[str, Any] | None:
        try:
            env = gateway.call(name, args)
        except (ToolError, OSError, ValueError, KeyError) as e:
            warnings.append(f"{name} failed: {e}")
            return None
        runs.append(env)
        warnings.extend(str(w) for w in env.get("warnings", []))
        return env

    place = call("resolve_place", {"text": address})
    res = place["result"] if place else {}
    lon, lat = res.get("lon"), res.get("lat")
    if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        msg = INSUFFICIENT.get(language, INSUFFICIENT["en"]) + " The address could not be located."
        return PermitReport(address, msg, False, [Problem("no_answer", "address not resolved")], runs, warnings)

    radius = cfg.context_radius_m
    call("context_check", {"point": [lon, lat], "radius_m": radius})
    call("estimate_field", {"area": circle_polygon(float(lon), float(lat), radius, cfg.circle_vertices)})
    for q in cfg.permit_legal_questions:
        call("legal_lookup", {"question": q})

    untrusted = {n for n, s in gateway.specs.items() if s.untrusted_output} | {"legal_lookup"}
    prompt = (f"Address: {address}\n\nTool outputs:\n\n{_runs_block(runs, untrusted)}\n\n"
              f"Write the narrative now. Use the fixed sentence: \"{CONTEXT_SENTENCE}\"")
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    by_id = {r["run_id"]: r for r in runs}
    system = system_prompt("permit", language, "office")
    try:
        turn = llm.step(system, messages, [])
        text = turn.text
        report = verify(text, by_id, cfg)
        for _ in range(cfg.verifier_retries):
            if report.ok:
                break
            messages += [{"role": "assistant", "content": turn.assistant_content},
                         {"role": "user", "content": "VERIFIER: your draft was blocked. Fix:\n" + describe_problems(report)}]
            turn = llm.step(system, messages, [])
            text = turn.text
            report = verify(text, by_id, cfg)
    except ModelRefused:
        text, report = "", VerifierReport(problems=[Problem("model_refused", "the model declined the request")])

    if report.ok and text.strip():
        return PermitReport(address, text, True, [], runs, warnings)
    missing = sorted({PLAIN_PROBLEMS.get(p.code, p.code) for p in report.problems}) or ["no narrative"]
    fallback = (INSUFFICIENT.get(language, INSUFFICIENT["en"]) + " The tool results below are complete and cited; "
                "the written summary was withheld because of: " + "; ".join(missing) + ".")
    return PermitReport(address, fallback, False, report.problems, runs, warnings)


def report_json(report: PermitReport) -> str:
    """Machine-readable handoff for the WS4 report builder and the WS8 Permit check screen."""
    return json.dumps({"address": report.address, "narrative": report.text, "verified": report.verified,
                       "run_ids": [r["run_id"] for r in report.runs], "runs": report.runs,
                       "warnings": report.warnings}, ensure_ascii=False, indent=2)
