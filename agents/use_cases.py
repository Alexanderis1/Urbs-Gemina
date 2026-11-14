"""Use-case playbooks: a fixed plan of tool calls per use case, run by code (``config/use_cases.yaml``).

Same pattern as the permit flow: the facts never depend on the model. Code runs the steps in
order, fills each step's arguments from the inputs and from earlier results (a resolved place
gives its point, municipio and a circle around it), skips a step whose inputs are missing and
says why. The model then writes one narrative from those runs, and the verifier checks every
figure before the officer sees it.

Two ways in:
* ``run_use_case``: the interface (or voice) names the use case; one model call writes the text.
* ``UseCaseTool``: the orchestrator can call ``run_use_case`` as a tool in free chat; it gets
  the runs back as one composite envelope (``result.tool_runs``) and writes the answer itself.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from agents.config import ROOT, AgentConfig, load_agent_config
from agents.contract import TwinAnswer
from agents.envelope import flatten_runs, is_ok, make_envelope
from agents.llm import LLM, ModelRefused
from agents.loop import render_for_model
from agents.prompting import PROMPT_DIR, system_prompt
from agents.tools import ToolError, ToolGateway, ToolSpec
from agents.verifier import (Problem, VerifierReport, auto_cite_marked, citation_trace, describe_problems,
                             verify)
from agents.web import quote_untrusted

USE_CASES_PATH = ROOT / "config" / "use_cases.yaml"
WEB_TOOLS = frozenset({"legal_lookup", "find_dataset", "news_search"})
M_PER_DEG_LAT = 111_195.0
CIRCLE_VERTICES = 32
_ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV")
_REF = re.compile(r"\{([a-z_][a-z0-9_]*(?:\.[a-z0-9_]+)?)\}")
#: "{?ref}" as a whole value: optional; the key is left out when the ref is empty (e.g. a param with no default).
_OPTIONAL = re.compile(r"\{\?([a-z_][a-z0-9_]*(?:\.[a-z0-9_]+)?)\}")


class UseCaseError(ValueError):
    """Unknown use case, a tier that may not run it, or a required input missing."""


@dataclass(frozen=True)
class Step:
    id: str
    tool: str
    args: Mapping[str, Any]
    label: str


@dataclass(frozen=True)
class UseCase:
    id: str
    title: Mapping[str, str]
    summary: Mapping[str, str]
    tiers: tuple[str, ...]
    needs: tuple[str, ...]
    prompt: str
    params: Mapping[str, Mapping[str, Any]]
    steps: tuple[Step, ...]
    basis: str

    @property
    def prompt_path(self) -> Path:
        return PROMPT_DIR / "use_cases" / f"{self.prompt}.md"

    def defaults(self) -> dict[str, Any]:
        return {k: v.get("default") for k, v in self.params.items()}


def load_use_cases(path: Path = USE_CASES_PATH) -> dict[str, UseCase]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, UseCase] = {}
    for uid, raw in (doc.get("use_cases") or {}).items():
        steps = tuple(Step(str(s["id"]), str(s["tool"]), dict(s.get("args") or {}), str(s.get("label", s["id"])))
                      for s in raw.get("steps", []))
        out[str(uid)] = UseCase(
            id=str(uid), title=dict(raw.get("title", {})), summary=dict(raw.get("summary", {})),
            tiers=tuple(raw.get("tiers", ["office"])), needs=tuple(raw.get("needs", [])), prompt=str(raw["prompt"]),
            params={str(k): dict(v) for k, v in (raw.get("params") or {}).items()}, steps=steps,
            basis=str(raw.get("basis", "")))
    return out


def default_area(path: Path = USE_CASES_PATH) -> str:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return str((doc.get("defaults") or {}).get("area", "city"))


def area_label(area: Any, language: str = "it") -> str:
    """'municipio:7' -> 'Municipio VII', 'zone:6A' -> 'zona 6A', 'city' -> 'Roma'; polygons -> 'selected area'."""
    if isinstance(area, str):
        kind, _, code = area.partition(":")
        if kind == "municipio" and code.isdigit() and 1 <= int(code) <= len(_ROMAN):
            return f"Municipio {_ROMAN[int(code) - 1]}"
        if kind == "zone" and code:
            return f"{'zona' if language == 'it' else 'zone'} {code}"
        if kind == "city":
            return "Roma" if language == "it" else "Rome"
    return "area selezionata" if language == "it" else "selected area"


def circle_polygon(lon: float, lat: float, radius_m: float, vertices: int = CIRCLE_VERTICES) -> dict[str, Any]:
    """GeoJSON polygon approximating a circle (local equirectangular projection; fine below a few km)."""
    import math

    m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(lat))
    ring = [[round(lon + radius_m * math.cos(2 * math.pi * i / vertices) / m_per_deg_lon, 7),
             round(lat + radius_m * math.sin(2 * math.pi * i / vertices) / M_PER_DEG_LAT, 7)] for i in range(vertices)]
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def _municipio_area(raw: Any) -> str | None:
    """resolve_place gives {"id": "1"} (or a bare id, or a Roman numeral): return 'municipio:<n>'."""
    value = raw.get("id") if isinstance(raw, Mapping) else raw
    text = str(value).strip().upper() if value is not None else ""
    text = text.removeprefix("MUNICIPIO").strip()
    if text.isdigit() and 1 <= int(text) <= 15:
        return f"municipio:{int(text)}"
    if text in _ROMAN:
        return f"municipio:{_ROMAN.index(text) + 1}"
    return None


def _place_context(env: Mapping[str, Any], radius_m: float, rings: Mapping[str, float]) -> dict[str, Any] | None:
    res = env.get("result") or {}
    lon, lat = res.get("lon"), res.get("lat")
    if not is_ok(env) or not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        return None
    ctx: dict[str, Any] = {"lon": float(lon), "lat": float(lat), "point": [float(lon), float(lat)],
                           "circle": circle_polygon(float(lon), float(lat), radius_m)}
    for name, ring_m in rings.items():
        ctx[name] = circle_polygon(float(lon), float(lat), ring_m)
    mun = _municipio_area(res.get("municipio"))
    if mun is not None:
        ctx["municipio"] = mun
    return ctx


class _Missing(LookupError):
    pass


def _lookup(ref: str, ctx: Mapping[str, Any]) -> Any:
    head, _, tail = ref.partition(".")
    if head not in ctx or ctx[head] is None:
        raise _Missing(head)
    value = ctx[head]
    if tail:
        if not isinstance(value, Mapping) or tail not in value or value[tail] is None:
            raise _Missing(ref)
        value = value[tail]
    return value


def fill(template: Any, ctx: Mapping[str, Any]) -> Any:
    """Fill ``{ref}`` placeholders. A value that is exactly one ref keeps the referenced type."""
    if isinstance(template, str):
        whole = _REF.fullmatch(template)
        if whole:
            return _lookup(whole.group(1), ctx)
        return _REF.sub(lambda m: str(_lookup(m.group(1), ctx)), template)
    if isinstance(template, Mapping):
        out: dict[str, Any] = {}
        for k, v in template.items():
            optional = _OPTIONAL.fullmatch(v) if isinstance(v, str) else None
            if optional:
                try:
                    out[k] = _lookup(optional.group(1), ctx)
                except _Missing:
                    pass
                continue
            out[k] = fill(v, ctx)
        return out
    if isinstance(template, list):
        return [fill(v, ctx) for v in template]
    return template


def _skip_reason(missing: str) -> str:
    head = missing.partition(".")[0]
    if head == "place" or "." in missing:
        return f"skipped: needs {missing}, but the place was not found in Rome"
    return f"skipped: needs {missing}"


def _fence(env: dict[str, Any]) -> dict[str, Any]:
    """Copy of a web-tool envelope with every text and title inside the quote fence."""
    shown = json.loads(json.dumps(env, default=str))
    items = (shown.get("result") or {}).get("results", [])
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict):
            for key in ("text", "title"):
                if key in item:
                    item[key] = quote_untrusted(str(item.get("url", "")), str(item.get("retrieved_at", "")), str(item[key]))
    return dict(shown)


def run_steps(uc: UseCase, *, gateway: ToolGateway, area: Any = None, place: str | None = None,
              params: Mapping[str, Any] | None = None, language: str = "it") -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Run the playbook's tool steps. Returns (envelopes, skipped steps with reasons)."""
    if "place" in uc.needs and not (place and place.strip()):
        raise UseCaseError(f"use case '{uc.id}' needs a place (address or place name)")
    if "area" in uc.needs and area in (None, ""):
        area = default_area()
    merged = {**uc.defaults(), **{k: v for k, v in (params or {}).items() if k in uc.params}}
    radius = float(merged.get("radius_m") or 500)
    # Every '<name>_radius_m' param gives a polygon '{<place step>.<name>}' (e.g. district, traffic).
    rings = {k[: -len("_radius_m")]: float(v) for k, v in merged.items()
             if k.endswith("_radius_m") and k != "radius_m" and v}
    ctx: dict[str, Any] = {"params": merged, "area": area, "area_label": area_label(area, language),
                           "place": place.strip() if place else None}
    runs: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for step in uc.steps:
        try:
            args = fill(step.args, ctx)
        except _Missing as missing:
            skipped.append({"step": step.id, "tool": step.tool, "label": step.label, "reason": _skip_reason(str(missing))})
            continue
        if step.tool not in gateway.specs:
            skipped.append({"step": step.id, "tool": step.tool, "label": step.label,
                            "reason": f"skipped: tool {step.tool} is not available on this server"})
            continue
        try:
            env = gateway.call(step.tool, args)
        except (ToolError, OSError, ValueError, KeyError) as error:
            skipped.append({"step": step.id, "tool": step.tool, "label": step.label,
                            "reason": f"failed: {type(error).__name__}: {error}"})
            continue
        env = dict(env)
        env["step"] = step.id
        runs.append(env)
        ctx[step.id] = _place_context(env, radius, rings) if step.tool == "resolve_place" else env.get("result")
    return runs, skipped


@dataclass
class UseCaseReport:
    use_case: str
    text: str
    verified: bool
    problems: list[Problem]
    runs: list[dict[str, Any]]
    skipped: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    cited_run_ids: list[str] = field(default_factory=list)

    @property
    def missing(self) -> list[str]:
        out = [f"{s['label']}: {s['reason']}" for s in self.skipped]
        for r in self.runs:
            if r.get("status", "ok") != "ok":
                out.append(f"{r.get('tool')}: {r.get('reason') or r.get('status')}")
        if not self.verified:
            from agents.orchestrator import PLAIN_PROBLEMS

            out += sorted({PLAIN_PROBLEMS.get(p.code, p.code) for p in self.problems})
        return out


def _runs_block(uc: UseCase, runs: Sequence[Mapping[str, Any]], skipped: Sequence[Mapping[str, str]],
                untrusted: set[str]) -> str:
    labels = {s.id: s.label for s in uc.steps}
    parts = []
    for r in runs:
        parts.append(f"step: {r.get('step')} ({labels.get(str(r.get('step')), r.get('tool'))})\nrun_id: {r['run_id']}\ntool: {r['tool']}\n"
                     f"{render_for_model(dict(r), r['tool'] in untrusted)}")
    for s in skipped:
        parts.append(f"step: {s['step']} ({s['label']})\nNOT RUN ({s['reason']})")
    return "\n\n".join(parts)


def _check(text: str, by_id: Mapping[str, Mapping[str, Any]], cfg: AgentConfig, question: str,
           language: str) -> tuple[str, VerifierReport, list[int]]:
    text, auto_lines = auto_cite_marked(text, by_id, cfg, question=question)
    report = verify(text, by_id, cfg, question=question)
    if report.problems and all(p.code == "missing_simulated_label" for p in report.problems):
        text = text.rstrip() + "\n\n" + cfg.simulated_note.get(language, cfg.simulated_note["en"])
        report = verify(text, by_id, cfg, question=question)
    return text, report, auto_lines


#: Problems that concern one figure on one line: that line can be withheld. Anything else (decision wording,
#: a missing estimate label...) blocks the whole note.
_LINE_LOCAL = frozenset({"uncited_number", "untraced_number", "unknown_citation", "mismatched_entity"})


def _withhold_lines(text: str, report: VerifierReport, by_id: Mapping[str, Mapping[str, Any]], cfg: AgentConfig,
                    question: str, language: str) -> tuple[str, VerifierReport, list[int], int]:
    """Last resort after the rewrite: drop only the lines whose figure cannot be traced, then verify again.

    The officer is told how many lines were withheld. The note is kept only if what remains passes the
    verifier and still holds at least one line that is not a heading."""
    if not report.problems or any(p.code not in _LINE_LOCAL for p in report.problems):
        return text, report, [], 0
    bad = [p.sentence.strip() for p in report.problems if p.sentence.strip()]
    lines = text.split("\n")
    kept = [ln for ln in lines if not any(b and (b in ln or ln.strip() and ln.strip() in b) for b in bad)]
    withheld = len(lines) - len(kept)
    body = [ln for ln in kept if ln.strip() and not ln.lstrip().startswith("#")
            and not re.fullmatch(r"\s*\*\*[^*]+\*\*\s*", ln)]
    if not withheld or not body:
        return text, report, [], 0
    new_text, new_report, auto_lines = _check("\n".join(kept), by_id, cfg, question, language)
    if not new_report.ok:
        return text, report, [], 0
    return new_text, new_report, auto_lines, withheld


def run_use_case(use_case: str, *, llm: LLM, gateway: ToolGateway, area: Any = None, place: str | None = None,
                 params: Mapping[str, Any] | None = None, language: str = "it", tier: str = "office",
                 question: str = "", config: AgentConfig | None = None) -> UseCaseReport:
    """Run the steps, then one model call (plus one rewrite if the verifier blocks it)."""
    cfg = config or load_agent_config()
    cases = load_use_cases()
    uc = cases.get(use_case)
    if uc is None:
        raise UseCaseError(f"unknown use case '{use_case}'. Known: {', '.join(sorted(cases))}")
    if tier not in uc.tiers:
        raise UseCaseError(f"use case '{use_case}' is not available to the {tier} tier")
    runs, skipped = run_steps(uc, gateway=gateway, area=area, place=place, params=params, language=language)
    warnings = [str(w) for r in runs for w in r.get("warnings", [])]
    by_id = flatten_runs(runs)
    if not any(is_ok(r) for r in runs):
        from agents.orchestrator import INSUFFICIENT

        reasons = "; ".join([str(r.get("reason", r.get("status"))) for r in runs] + [s["reason"] for s in skipped])
        text = INSUFFICIENT.get(language, INSUFFICIENT["en"]) + (f" {reasons}." if reasons else "")
        return UseCaseReport(use_case, text, False, [Problem("no_answer", "no tool step returned data")], runs, skipped, warnings)

    untrusted = {n for n, s in gateway.specs.items() if s.untrusted_output} | set(WEB_TOOLS)
    ask = question.strip() or uc.title.get(language, uc.title.get("en", uc.id))
    inputs = {"area": area_label(area, language) if area is not None else None, "place": place,
              "params": {**uc.defaults(), **dict(params or {})}}
    prompt = (f"Use case: {uc.title.get('en', uc.id)}\nOfficer's request: {ask}\n"
              f"Inputs: {json.dumps(inputs, ensure_ascii=False, default=str)}\n\n"
              f"Tool outputs (each step, in order):\n\n{_runs_block(uc, runs, skipped, untrusted)}\n\n"
              "Write the answer now.")
    system = system_prompt(f"use_cases/{uc.prompt}", language, tier)
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    auto_lines: list[int] = []
    try:
        turn = llm.step(system, messages, [])
        text, report, auto_lines = _check(turn.text, by_id, cfg, ask, language)
        for _ in range(cfg.verifier_retries):
            if report.ok and text.strip():
                break
            messages += [{"role": "assistant", "content": turn.assistant_content},
                         {"role": "user", "content": "VERIFIER: your draft was blocked. Fix these problems using only the "
                                                     "tool outputs above, or say 'insufficient data'. Write the corrected answer "
                                                     "only.\n" + describe_problems(report)}]
            turn = llm.step(system, messages, [])
            text, report, auto_lines = _check(turn.text, by_id, cfg, ask, language)
    except ModelRefused:
        text, report = "", VerifierReport(problems=[Problem("model_refused", "the model declined the request")])

    withheld = 0
    if not report.ok and text.strip():
        text, report, auto_lines, withheld = _withhold_lines(text, report, by_id, cfg, ask, language)
    if withheld:
        warnings.append(f"{withheld} line(s) withheld: a figure could not be traced to a tool run")
        skipped.append({"step": "narrative", "tool": "verifier", "label": "note",
                        "reason": f"{withheld} line(s) withheld because a figure could not be traced to a tool run"})

    if report.ok and text.strip():
        from agents.orchestrator import _drop_self_disclosure

        text = _drop_self_disclosure(text)  # code adds the AI disclosure line once, at the start of a conversation
        return UseCaseReport(use_case, text, True, [], runs, skipped, warnings,
                             citations=citation_trace(text, by_id, auto_lines), cited_run_ids=list(report.cited_runs))
    from agents.orchestrator import INSUFFICIENT, PLAIN_PROBLEMS

    problems = list(report.problems) or [Problem("no_answer", "the agent produced no answer")]
    missing = sorted({PLAIN_PROBLEMS.get(p.code, p.code) for p in problems})
    fallback = (INSUFFICIENT.get(language, INSUFFICIENT["en"]) + " "
                + ("Problem found: " if language == "en" else "Problema: ") + "; ".join(missing) + ".")
    return UseCaseReport(use_case, fallback, False, problems, runs, skipped, warnings)


def to_twin_answer(rep: UseCaseReport, *, disclosure: str | None = None) -> TwinAnswer:
    from agents.orchestrator import Answer, map_actions
    from agents.orchestrator import to_twin_answer as base

    answer = Answer(text=(disclosure + "\n\n" + rep.text) if disclosure else rep.text, verified=rep.verified,
                    problems=rep.problems, runs=rep.runs, warnings=rep.warnings, cited_run_ids=rep.cited_run_ids,
                    citations=rep.citations)
    out = base(answer)
    return replace(out, missing=tuple(dict.fromkeys(rep.missing)), map_actions=map_actions(rep.runs))


def use_case_tool_spec(tier: str) -> ToolSpec:
    cases = {k: v for k, v in load_use_cases().items() if tier in v.tiers}
    lines = [f"- {k} (needs {' and '.join(v.needs)}): {v.summary.get('en', '')}" for k, v in cases.items()]
    return ToolSpec(
        name="run_use_case",
        description=("Run a ready-made playbook: a fixed set of tool calls for a common request, returned together. "
                     "Prefer it over many single calls when the request matches one:\n" + "\n".join(lines)),
        input_schema={
            "type": "object",
            "properties": {
                "use_case": {"type": "string", "enum": sorted(cases)},
                "area": {"type": "string", "description": "'city', 'municipio:<1-15>' or 'zone:<CODE>' (for use cases that need an area)"},
                "place": {"type": "string", "description": "Address or place name in Rome (for use cases that need a place)"},
                "params": {"type": "object", "description": "Optional settings, e.g. {\"attendees\": 30000} or {\"discipline\": \"nuoto\"}"},
            },
            "required": ["use_case"],
        },
        untrusted_output=True,
    )


class UseCaseTool:
    """``run_use_case`` as a local tool for the orchestrator loop (no model call inside)."""

    def __init__(self, gateway: ToolGateway, tier: str = "office", language: str = "it") -> None:
        self._gateway = gateway
        self._tier = tier
        self._language = language
        self._specs = {"run_use_case": use_case_tool_spec(tier)}

    @property
    def specs(self) -> Mapping[str, ToolSpec]:
        return self._specs

    def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        uid = str(arguments.get("use_case", ""))
        uc = load_use_cases().get(uid)
        if uc is None or self._tier not in uc.tiers:
            raise ToolError(f"use case '{uid}' is not available")
        params = arguments.get("params") if isinstance(arguments.get("params"), Mapping) else {}
        try:
            runs, skipped = run_steps(uc, gateway=self._gateway, area=arguments.get("area"),
                                      place=arguments.get("place"), params=params, language=self._language)
        except UseCaseError as error:
            raise ToolError(str(error)) from error
        untrusted = {n for n, s in self._gateway.specs.items() if s.untrusted_output} | set(WEB_TOOLS)
        shown = [_fence(r) if r["tool"] in untrusted else r for r in runs]
        kinds: dict[str, str] = {}
        sources: list[dict[str, Any]] = []
        for r in runs:
            kinds.update({str(k): str(v) for k, v in (r.get("data_kinds") or {}).items()})
            sources += [dict(s) for s in r.get("sources", []) if dict(s) not in sources]
        result = {"use_case": uid, "title": uc.title.get("en", uid), "tool_runs": shown, "skipped": skipped,
                  "steps": [{"id": s.id, "label": s.label} for s in uc.steps]}
        return make_envelope(tool="run_use_case", inputs=dict(arguments), result=result, data_kinds=kinds,
                             sources=sources, synthetic=any(r.get("synthetic") is True for r in runs),
                             warnings=[f"{s['label']}: {s['reason']}" for s in skipped],
                             snapshot_hashes=[str(r["run_id"]) for r in runs])
