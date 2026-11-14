"""Orchestrator: answers a question with tools, then lets the verifier decide if it may be shown.

Flow: loop (model + tools + turn guard) -> verifier -> one rewrite with the verifier's notes ->
verifier -> otherwise "insufficient data". The AI disclosure line is added by code, not by the model.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from agents.config import AgentConfig, load_agent_config
from agents.envelope import flatten_runs
from agents.contract import TwinAnswer, TwinQuestion
from agents.llm import LLM, AnthropicLLM, ModelRefused
from agents.loop import AgentLoop, LoopResult
from agents.prompting import system_prompt
from agents.tools import CompositeGateway, HttpToolGateway, LocalWebTools, ToolGateway, load_tool_specs
from agents.verifier import Problem, VerifierReport, auto_cite_marked, citation_trace, describe_problems, verify

LOG = logging.getLogger("urbs.agents")

DEFAULT_TOOLS = ["run_use_case", "resolve_place", "context_check", "estimate_field", "query_layer", "run_scenario",
                 "sports_facilities", "sport_coverage", "legal_lookup", "find_dataset", "news_search", "data_status"]

PLAIN_PROBLEMS_IT = {
    "uncited_number": "una cifra senza esecuzione di uno strumento o fonte",
    "untraced_number": "una cifra che non corrisponde al risultato dello strumento",
    "unknown_citation": "una citazione a un'esecuzione o fonte che non esiste",
    "missing_range": "una stima senza il suo intervallo",
    "missing_calibration": "una stima senza lo stato di calibrazione",
    "missing_estimate_label": "una stima non indicata come tale",
    "missing_simulated_label": "dati simulati non indicati come tali",
    "decision_language": "una formulazione che trasforma il contesto in una decisione",
    "no_answer": "nessuna risposta entro il limite di strumenti",
    "model_refused": "il modello ha rifiutato la richiesta",
}

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


def plain_problem(p: Problem, language: str = "it", with_figure: bool = True) -> str:
    """Plain wording of a problem in the answer's language, naming the figure when there is one (and asked)."""
    table = PLAIN_PROBLEMS_IT if language == "it" else PLAIN_PROBLEMS
    base = table.get(p.code, p.code)
    m = re.match(r"'([^']+)'", p.message)
    return (f"{base} ('{m.group(1)}')" if with_figure and m and p.code in ("uncited_number", "untraced_number")
            else base)


def _plain(p: Problem) -> str:
    return plain_problem(p, "en")


@dataclass
class Answer:
    text: str
    verified: bool
    problems: list[Problem]
    runs: list[dict[str, Any]]
    blocked_calls: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: Runs the verified answer actually cites; labels (data kinds, SIMULATED) follow these.
    cited_run_ids: list[str] = field(default_factory=list)
    #: Tool trace of citations: {"line", "kind", "ref", "cite_mode": "explicit" | "auto"}.
    citations: list[dict[str, Any]] = field(default_factory=list)
    language: str = "it"

    def _label_runs(self) -> list[dict[str, Any]]:
        if self.verified and self.cited_run_ids:
            index = flatten_runs(self.runs)
            return [index[i] for i in self.cited_run_ids if i in index]
        return self.runs

    @property
    def data_kinds(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for r in self._label_runs():
            out.update({str(k): str(v) for k, v in r.get("data_kinds", {}).items()})
        return out

    @property
    def synthetic(self) -> bool:
        return any(r.get("synthetic") is True for r in self._label_runs())

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
        out = sorted({plain_problem(p, self.language) for p in self.problems}) if not self.verified else []
        for r in self.runs:
            if r.get("status", "ok") != "ok":
                reason = str(r.get("reason") or r.get("status"))
                if reason not in out:
                    out.append(reason)
        return out


def _finalise(text: str, report: VerifierReport, state: LoopResult, language: str, first_message: bool,
              cfg: AgentConfig, tier: str = "office") -> Answer:
    verified = report.ok and bool(text.strip())
    problems = list(report.problems)
    if not text.strip():
        problems.append(Problem("no_answer", "the agent produced no answer"))
    if not verified:
        missing = sorted({plain_problem(p, language) for p in problems})
        text = INSUFFICIENT.get(language, INSUFFICIENT["en"]) + " " + (
            "Problem found: " if language == "en" else "Problema: ") + "; ".join(missing) + "."
    if first_message:
        text = cfg.disclosure_for(tier, language) + "\n\n" + _drop_self_disclosure(text)
    return Answer(text=text, verified=verified, problems=problems, runs=state.runs,
                  blocked_calls=state.blocked_calls, warnings=state.warnings,
                  cited_run_ids=list(report.cited_runs) if verified else [], language=language)


SELF_DISCLOSURE = re.compile(
    r"\b(i am|i'm|sono)\s+(an?\s+|un['’]?\s*|una\s+)?(assistente\s+(di\s+)?|assistant\s+)?"
    r"(ai|ia|intelligenza artificiale|artificial intelligence)\b", re.IGNORECASE)
_SENT = re.compile(r"[^.!?\n]*[.!?]?")


def _drop_self_disclosure(text: str) -> str:
    """Code adds the disclosure line; drop any sentence where the model discloses itself again
    (only sentences without figures, so nothing factual is lost)."""
    out_lines = []
    for line in text.split("\n"):
        kept = [m.group(0) for m in _SENT.finditer(line)
                if m.group(0).strip() and not (SELF_DISCLOSURE.search(m.group(0)) and not re.search(r"\d", m.group(0)))]
        new = "".join(kept).strip()
        if new or not line.strip():
            out_lines.append(new if line.strip() else line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out_lines)).strip()


def _label_simulated(state: LoopResult, runs: dict[str, dict[str, Any]], cfg: AgentConfig, question: str,
                     language: str) -> VerifierReport:
    """Verify; if the only gap is a missing SIMULATED label, add the fixed note by code and re-verify."""
    report = verify(state.text, runs, cfg, question=question)
    if report.problems and all(p.code == "missing_simulated_label" for p in report.problems):
        state.text = state.text.rstrip() + "\n\n" + cfg.simulated_note.get(language, cfg.simulated_note["en"])
        report = verify(state.text, runs, cfg, question=question)
    return report


def answer(question: str, *, llm: LLM, gateway: ToolGateway, tool_names: list[str] | None = None,
           first_message: bool = False, language: str = "it", tier: str = "office", agent: str = "orchestrator",
           config: AgentConfig | None = None) -> Answer:
    cfg = config or load_agent_config()
    loop = AgentLoop(llm=llm, gateway=gateway, system=system_prompt(agent, language, tier),
                     tool_names=tool_names or DEFAULT_TOOLS, max_tool_rounds=cfg.max_tool_rounds)
    try:
        state = loop.run(question)
        runs = flatten_runs(state.runs)
        state.text, auto_lines = auto_cite_marked(state.text, runs, cfg, question=question)
        report = _label_simulated(state, runs, cfg, question, language)
        attempts = 0
        while (not report.ok) and state.text.strip() and attempts < cfg.verifier_retries:
            attempts += 1
            state = loop.resume(state, "VERIFIER: your draft was blocked. Fix these problems using only the tool "
                                       "outputs above, or answer 'insufficient data'. Write the corrected answer only: do not mention "
                                       "this correction or talk about run ids.\n" + describe_problems(report))
            runs = flatten_runs(state.runs)
            state.text, auto_lines = auto_cite_marked(state.text, runs, cfg, question=question)
            report = _label_simulated(state, runs, cfg, question, language)
    except ModelRefused:
        state = LoopResult(text="", runs=[], messages=[])
        auto_lines = []
        report = VerifierReport(problems=[Problem("model_refused", "the model declined the request")])
    if not report.ok:
        # Codes and flagged figures only: no draft text in logs (guardrail 11, privacy).
        LOG.warning("verifier blocked answer: %s", "; ".join(f"{p.code} {p.message}" for p in report.problems))
    out = _finalise(state.text, report, state, language, first_message, cfg, tier)
    if out.verified:
        out.citations = citation_trace(state.text, flatten_runs(state.runs), auto_lines)
    return out


def _first_message(question: TwinQuestion) -> bool:
    """The AI disclosure goes on the first chat answer. Voice agents say it in their own first message."""
    return question.conversation_id is None and question.channel != "voice"


class TwinOrchestrator:
    """Implements shared interface 7 (``ask``) for chat and voice."""

    def __init__(self, *, llm: LLM | None = None, gateway: ToolGateway | None = None, model_role: str = "orchestrator",
                 config: AgentConfig | None = None) -> None:
        self.cfg = config or load_agent_config()
        self.llm = llm
        self.gateway = gateway
        self.model_role = model_role

    def _base_gateway(self, tier: str) -> ToolGateway:
        if self.gateway is not None:
            return self.gateway
        specs, _ = load_tool_specs()
        return CompositeGateway(LocalWebTools(specs, config=self.cfg), HttpToolGateway(specs, role=tier, config=self.cfg))

    def _gateway_for(self, tier: str, language: str = "it") -> ToolGateway:
        """Base tools plus ``run_use_case`` (playbooks run by code, see agents/use_cases.py)."""
        from agents.use_cases import UseCaseTool

        base = self._base_gateway(tier)
        return CompositeGateway(base, UseCaseTool(base, tier=tier, language=language))

    def ask(self, question: TwinQuestion) -> TwinAnswer:
        from dataclasses import replace

        from agents.language import answer_language

        question = replace(question, language=answer_language(question))  # Italian unless they wrote in English
        role = "voice" if question.channel == "voice" else self.model_role
        llm = self.llm or AnthropicLLM(role=role, config=self.cfg)
        use_case = question.use_case or ("municipio_briefing" if question.mode == "briefing" else None)
        if use_case:
            return self._run_use_case(use_case, question, llm)
        prompt = question.question
        if question.area:
            prompt += f"\n\nOperating area chosen in the interface: {question.area}"
        if question.mode == "briefing":
            prompt = f"Morning briefing requested. {prompt}"
        result = answer(prompt, llm=llm, gateway=self._gateway_for(question.tier, question.language),
                        language=question.language, tier=question.tier,
                        first_message=_first_message(question), config=self.cfg)
        return to_twin_answer(result)

    def _run_use_case(self, use_case: str, question: TwinQuestion, llm: LLM) -> TwinAnswer:
        """A named playbook: code runs the tool plan, the model writes one verified narrative."""
        from agents.use_cases import UseCaseError, load_use_cases, run_use_case
        from agents.use_cases import to_twin_answer as use_case_answer

        params = dict(question.params)
        uc = load_use_cases().get(use_case)
        place = params.pop("place", None)
        if place is None and uc is not None and "place" in uc.needs:
            place = question.question  # the question text names the place ("Via del Corso 1")
        disclosure = self.cfg.disclosure_for(question.tier, question.language) if _first_message(question) else None
        try:
            rep = run_use_case(use_case, llm=llm, gateway=self._base_gateway(question.tier), area=question.area,
                               place=str(place) if place is not None else None, params=params,
                               language=question.language, tier=question.tier, question=question.question, config=self.cfg)
        except UseCaseError as error:
            text = INSUFFICIENT.get(question.language, INSUFFICIENT["en"]) + f" {error}."
            return TwinAnswer(text=(disclosure + "\n\n" + text) if disclosure else text, verified=False, run_ids=(),
                              sources=(), data_kinds={}, synthetic=False, missing=(str(error),))
        return use_case_answer(rep, disclosure=disclosure)


def to_twin_answer(a: Answer) -> TwinAnswer:
    return TwinAnswer(text=a.text, verified=a.verified, run_ids=tuple(str(r["run_id"]) for r in a.runs),
                      sources=tuple(a.sources), data_kinds=a.data_kinds, synthetic=a.synthetic,
                      missing=tuple(a.missing), map_actions=map_actions(a.runs), citations=tuple(a.citations))


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
            mun = res.get("municipio")
            mun_id = mun.get("id") if isinstance(mun, dict) else mun
            if isinstance(mun_id, (str, int)) and str(mun_id).strip().isdigit():
                actions.append({"tool": "show_area", "args": {"area": f"municipio:{int(str(mun_id).strip())}"}})
        if r.get("tool") == "context_check":
            inp = r.get("inputs", {})
            pt = inp.get("point")
            radius = inp.get("radius_m")
            if isinstance(pt, list) and len(pt) == 2 and isinstance(radius, (int, float)):
                actions.append({"tool": "show_radius", "args": {"lon": pt[0], "lat": pt[1], "radius_m": radius, "run_id": r["run_id"]}})
    return tuple(actions)
