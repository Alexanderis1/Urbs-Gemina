"""Orchestrator: answers a question with tools, then lets the verifier decide if it may be shown.

Flow: loop (model + tools + turn guard) -> verifier -> one rewrite with the verifier's notes ->
verifier -> otherwise "insufficient data". The AI disclosure line is added by code, not by the model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.config import AgentConfig, load_agent_config
from agents.contract import TwinAnswer, TwinQuestion
from agents.llm import LLM, AnthropicLLM, ModelRefused
from agents.loop import AgentLoop, LoopResult
from agents.prompting import system_prompt
from agents.tools import CompositeGateway, HttpToolGateway, LocalWebTools, ToolGateway, load_tool_specs
from agents.verifier import Problem, VerifierReport, describe_problems, verify

DEFAULT_TOOLS = ["resolve_place", "context_check", "estimate_field", "query_layer", "run_scenario",
                 "legal_lookup", "find_dataset", "data_status"]

PLAIN_PROBLEMS = {
    "uncited_number": "a figure without a tool run or source",
    "untraced_number": "a figure that does not match the tool output",
    "unknown_citation": "a citation to a run or source that does not exist",
    "missing_range": "an estimate without its range",
    "missing_calibration": "an estimate without its calibration status",
    "missing_estimate_label": "an estimate not labelled as such",
    "missing_simulated_label": "simulated data not labelled as such",
    "decision_language": "wording that turns context into a decision",
    "no_answer": "no answer within the tool budget",
    "model_refused": "the model declined the request",
}

INSUFFICIENT = {
    "en": "Insufficient data: I cannot back every figure with a tool run or an official source, so I am not giving one.",
    "it": "Dati insufficienti: non posso documentare ogni cifra con un'esecuzione di uno strumento o una fonte ufficiale, quindi non ne fornisco.",
}


@dataclass
class Answer:
    text: str
    verified: bool
    problems: list[Problem]
    runs: list[dict[str, Any]]
    blocked_calls: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def data_kinds(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for r in self.runs:
            out.update({str(k): str(v) for k, v in r.get("data_kinds", {}).items()})
        return out

    @property
    def synthetic(self) -> bool:
        return any(r.get("synthetic") is True for r in self.runs)

    @property
    def sources(self) -> list[str]:
        seen: list[str] = []
        for r in self.runs:
            for s in r.get("sources", []):
                ref = str(s.get("url") or s.get("id") or "")
                if ref and ref not in seen:
                    seen.append(ref)
        return seen

    @property
    def missing(self) -> list[str]:
        """Plain-language gaps: verifier problems plus every tool result that was not available or refused."""
        out = sorted({PLAIN_PROBLEMS.get(p.code, p.code) for p in self.problems}) if not self.verified else []
        for r in self.runs:
            if r.get("status", "ok") != "ok":
                reason = str(r.get("reason") or r.get("status"))
                if reason not in out:
                    out.append(reason)
        return out


def _finalise(text: str, report: VerifierReport, state: LoopResult, language: str, first_message: bool,
              cfg: AgentConfig) -> Answer:
    verified = report.ok and bool(text.strip())
    problems = list(report.problems)
    if not text.strip():
        problems.append(Problem("no_answer", "the agent produced no answer"))
    if not verified:
        missing = sorted({PLAIN_PROBLEMS.get(p.code, p.code) for p in problems})
        text = INSUFFICIENT.get(language, INSUFFICIENT["en"]) + " " + (
            "Problem found: " if language == "en" else "Problema: ") + "; ".join(missing) + "."
    if first_message:
        text = cfg.disclosure.get(language, cfg.disclosure["en"]) + "\n\n" + text
    return Answer(text=text, verified=verified, problems=problems, runs=state.runs,
                  blocked_calls=state.blocked_calls, warnings=state.warnings)


def answer(question: str, *, llm: LLM, gateway: ToolGateway, tool_names: list[str] | None = None,
           first_message: bool = False, language: str = "en", tier: str = "office", agent: str = "orchestrator",
           config: AgentConfig | None = None) -> Answer:
    cfg = config or load_agent_config()
    loop = AgentLoop(llm=llm, gateway=gateway, system=system_prompt(agent, language, tier),
                     tool_names=tool_names or DEFAULT_TOOLS, max_tool_rounds=cfg.max_tool_rounds)
    try:
        state = loop.run(question)
        runs = {r["run_id"]: r for r in state.runs}
        report = verify(state.text, runs, cfg)
        attempts = 0
        while (not report.ok) and state.text.strip() and attempts < cfg.verifier_retries:
            attempts += 1
            state = loop.resume(state, "VERIFIER: your draft was blocked. Fix these problems using only the tool "
                                       "outputs above, or answer 'insufficient data':\n" + describe_problems(report))
            runs = {r["run_id"]: r for r in state.runs}
            report = verify(state.text, runs, cfg)
    except ModelRefused:
        state = LoopResult(text="", runs=[], messages=[])
        report = VerifierReport(problems=[Problem("model_refused", "the model declined the request")])
    return _finalise(state.text, report, state, language, first_message, cfg)


class TwinOrchestrator:
    """Implements shared interface 7 (``ask``) for chat and voice."""

    def __init__(self, *, llm: LLM | None = None, gateway: ToolGateway | None = None, model_role: str = "orchestrator",
                 config: AgentConfig | None = None) -> None:
        self.cfg = config or load_agent_config()
        self.llm = llm
        self.gateway = gateway
        self.model_role = model_role

    def _gateway_for(self, tier: str) -> ToolGateway:
        if self.gateway is not None:
            return self.gateway
        specs, _ = load_tool_specs()
        return CompositeGateway(LocalWebTools(specs, config=self.cfg), HttpToolGateway(specs, role=tier, config=self.cfg))

    def ask(self, question: TwinQuestion) -> TwinAnswer:
        role = "voice" if question.channel == "voice" else self.model_role
        llm = self.llm or AnthropicLLM(role=role, config=self.cfg)
        prompt = question.question
        if question.area:
            prompt += f"\n\nOperating area chosen in the interface: {question.area}"
        if question.mode == "briefing":
            prompt = f"Morning briefing requested. {prompt}"
        result = answer(prompt, llm=llm, gateway=self._gateway_for(question.tier), language=question.language,
                        tier=question.tier, first_message=question.conversation_id is None, config=self.cfg)
        return to_twin_answer(result)


def to_twin_answer(a: Answer) -> TwinAnswer:
    return TwinAnswer(text=a.text, verified=a.verified, run_ids=tuple(str(r["run_id"]) for r in a.runs),
                      sources=tuple(a.sources), data_kinds=a.data_kinds, synthetic=a.synthetic,
                      missing=tuple(a.missing), map_actions=map_actions(a.runs))


def map_actions(runs: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Map moves derived by code from tool outputs (client tools in voice/client_tools.json)."""
    actions: list[dict[str, Any]] = []
    point: tuple[float, float] | None = None
    for r in runs:
        if r.get("status", "ok") != "ok":
            continue
        res = r.get("result", {})
        if r.get("tool") == "resolve_place" and isinstance(res.get("lon"), (int, float)) and isinstance(res.get("lat"), (int, float)):
            point = (float(res["lon"]), float(res["lat"]))
            actions.append({"tool": "fly_to", "args": {"lon": point[0], "lat": point[1], "zoom": 16}})
            if res.get("municipio"):
                actions.append({"tool": "show_area", "args": {"area": f"municipio:{res['municipio']}"}})
        if r.get("tool") == "context_check":
            inp = r.get("inputs", {})
            pt = inp.get("point")
            radius = inp.get("radius_m")
            if isinstance(pt, list) and len(pt) == 2 and isinstance(radius, (int, float)):
                actions.append({"tool": "show_radius", "args": {"lon": pt[0], "lat": pt[1], "radius_m": radius, "run_id": r["run_id"]}})
    return tuple(actions)
