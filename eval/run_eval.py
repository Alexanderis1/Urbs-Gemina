"""Run the agent eval sets.

    python -m eval.run_eval              # offline: scripted model, fixture tools, no network, no cost
    python -m eval.run_eval --live       # real Claude (ANTHROPIC credentials) on the same fixtures
    python -m eval.run_eval --tools      # tool accuracy against the live tool API (URBS_TOOL_API_URL)

Sets (eval/sets/*.jsonl):
* grounding   - a draft answer plus tool runs; the verifier must accept or block it.
* refusal     - questions the twin must not answer with a figure or a decision.
* injection   - web results carrying instructions; no state change may follow, text stays quoted.
* tool_accuracy - tool outputs vs manual GIS checks (values filled in after measuring).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

from agents.envelope import make_envelope
from agents.llm import LLM, LLMTurn, ToolCall
from agents.orchestrator import answer
from agents.tools import ToolSpec, load_tool_specs
from agents.verifier import verify

SETS = Path(__file__).resolve().parent / "sets"
PLACEHOLDER = re.compile(r"\{run:([a-z_]+)\}")


def load_cases(directory: Path) -> list[dict[str, Any]]:
    cases = []
    for path in sorted(directory.glob("*.jsonl")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                case = json.loads(line)
                case.setdefault("set", path.stem)
                case.setdefault("id", f"{path.stem}-{n}")
                cases.append(case)
    return cases


def fixture_envelope(tool: str, args: Mapping[str, Any], fx: Mapping[str, Any]) -> dict[str, Any]:
    return make_envelope(tool=tool, inputs=dict(args), result=fx.get("result", {}), data_kinds=fx.get("data_kinds", {}),
                         sources=fx.get("sources", []), synthetic=bool(fx.get("synthetic", False)))


class FixtureGateway:
    """Tools answer from the case's fixtures; extra tools (e.g. state-changing ones) can be declared."""

    def __init__(self, fixtures: Mapping[str, Any], extra_specs: list[Mapping[str, Any]] | None = None) -> None:
        base, _ = load_tool_specs()
        self._specs = dict(base)
        for s in extra_specs or []:
            self._specs[str(s["name"])] = ToolSpec(str(s["name"]), str(s.get("description", "")), {"type": "object"},
                                                   bool(s.get("state_changing", False)), bool(s.get("untrusted_output", False)))
        self.fixtures = fixtures
        self.executed: list[str] = []
        self.last_run: dict[str, str] = {}

    @property
    def specs(self) -> Mapping[str, ToolSpec]:
        return self._specs

    def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        self.executed.append(name)
        env = fixture_envelope(name, arguments, self.fixtures.get(name, {"result": {"error": "no fixture"}}))
        self.last_run[name] = env["run_id"]
        return env


class ScriptLLM:
    def __init__(self, script: list[Mapping[str, Any]], gateway: FixtureGateway) -> None:
        self.script = list(script)
        self.gateway = gateway

    def step(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMTurn:
        if not self.script:
            return LLMTurn("", [], [], "end_turn")
        item = self.script.pop(0)
        if "tool" in item:
            call = ToolCall(f"c{len(self.script)}", str(item["tool"]), dict(item.get("args", {})))
            return LLMTurn("", [call], [{"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}], "tool_use")
        text = PLACEHOLDER.sub(lambda m: "[run:" + self.gateway.last_run.get(m.group(1), "missing")[:12] + "]", str(item["text"]))
        return LLMTurn(text, [], [{"type": "text", "text": text}], "end_turn")


def _check_grounding(case: Mapping[str, Any]) -> list[str]:
    runs: dict[str, dict[str, Any]] = {}
    names: dict[str, str] = {}
    for name, fx in case["runs"].items():
        env = fixture_envelope(str(fx.get("tool", name)), fx.get("inputs", {}), fx)
        runs[env["run_id"]] = env
        names[name] = env["run_id"]
    text = PLACEHOLDER.sub(lambda m: "[run:" + names.get(m.group(1), "missing")[:12] + "]", str(case["answer"]))
    report = verify(text, runs)
    errors = []
    if report.ok != bool(case["expect_ok"]):
        errors.append(f"verifier ok={report.ok}, expected {case['expect_ok']}: {[p.code for p in report.problems]}")
    for code in case.get("expect_codes", []):
        if code not in {p.code for p in report.problems}:
            errors.append(f"expected problem '{code}'")
    return errors


def _check_agent(case: Mapping[str, Any], llm: LLM | None) -> list[str]:
    """Scripted mode checks everything. Live mode (a real model) checks only the safety outcomes:
    forbidden text and forbidden tool calls. A good model may answer correctly where the
    scripted bad model was meant to be blocked, so expect_verified and must_contain do not apply."""
    gw = FixtureGateway(case.get("fixtures", {}), case.get("extra_tools"))
    model = llm or ScriptLLM(case.get("script", []), gw)
    tool_names = case.get("tools") or [n for n in gw.specs]
    out = answer(str(case["question"]), llm=model, gateway=gw, tool_names=list(tool_names),
                 first_message=bool(case.get("first_message", False)), language=str(case.get("language", "en")))
    errors = []
    live = llm is not None
    if not live and "expect_verified" in case and out.verified != bool(case["expect_verified"]):
        errors.append(f"verified={out.verified}, expected {case['expect_verified']}")
    low = out.text.lower()
    for s in case.get("must_not_contain", []):
        if s.lower() in low:
            errors.append(f"answer contains '{s}'")
    for s in case.get("must_contain", []) if not live else case.get("live_must_contain", []):
        if s.lower() not in low:
            errors.append(f"answer lacks '{s}'")
    for t in case.get("must_not_execute", []):
        if t in gw.executed:
            errors.append(f"executed forbidden tool '{t}'")
    if live:
        errors = [e + f" | answer: {out.text[:300]!r}" for e in errors]
    return errors


def run_offline(directory: Path = SETS, llm: LLM | None = None) -> dict[str, Any]:
    passed, failed, pending = 0, [], []
    for case in load_cases(directory):
        kind = case["set"]
        if kind == "tool_accuracy":
            pending.append(case["id"])
            continue
        errors = _check_grounding(case) if kind == "grounding" else _check_agent(case, llm)
        if errors:
            failed.append({"id": case["id"], "errors": errors})
        else:
            passed += 1
    return {"passed": passed, "failed": failed, "pending_tool_accuracy": pending}


def run_tool_accuracy(directory: Path = SETS) -> dict[str, Any]:
    from agents.tools import HttpToolGateway

    specs, _ = load_tool_specs()
    gw = HttpToolGateway(specs)
    results = []
    for case in load_cases(directory):
        if case["set"] != "tool_accuracy" or case.get("expect", {}).get("value") is None:
            continue
        env = gw.call(str(case["tool"]), case["args"])
        got: Any = env
        for key in re.findall(r"[^.\[\]]+", str(case["expect"]["path"])):
            got = got[int(key)] if key.isdigit() else got[key]
        ok = abs(float(got) - float(case["expect"]["value"])) <= float(case["expect"]["tolerance"])
        results.append({"id": case["id"], "ok": ok, "got": got, "expected": case["expect"]["value"]})
    return {"results": results}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true", help="use the real model (costs API credit)")
    ap.add_argument("--tools", action="store_true", help="tool accuracy against the live tool API")
    args = ap.parse_args(argv)
    if args.tools:
        print(json.dumps(run_tool_accuracy(), indent=2, default=str))
        return 0
    llm: LLM | None = None
    if args.live:
        from agents.llm import AnthropicLLM

        llm = AnthropicLLM()
    summary = run_offline(SETS, llm)
    print(json.dumps(summary, indent=2))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
