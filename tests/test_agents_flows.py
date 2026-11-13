"""WS7: permit-context flow, scenario slot check, data steward and eval sets."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from agents.envelope import make_envelope
from agents.exa_tools import ExaResult
from agents.llm import LLMTurn
from agents.permit import permit_context
from agents.scenario import missing_slots
from agents.steward import InMemoryProposalQueue, propose, scan
from agents.tools import ToolSpec
from eval.run_eval import run_offline


class RecordingGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.specs = {n: ToolSpec(n, n, {"type": "object"}) for n in ["resolve_place", "context_check", "estimate_field", "legal_lookup"]}

    def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append((name, dict(arguments)))
        results: dict[str, dict[str, Any]] = {
            "resolve_place": {"lon": 12.4823, "lat": 41.896, "municipio": "1", "urban_zone": "1a"},
            "context_check": {"count": 1, "sites": [{"layer": "schools", "distance_m": 182.4}]},
            "estimate_field": {"p5": 0.8, "p50": 1.4, "p95": 2.6, "calibration": "uncalibrated"},
            "legal_lookup": {"results": [{"url": "https://www.normattiva.it/a", "text": "15 V/m"}]},
        }
        return make_envelope(tool=name, inputs=dict(arguments), result=results[name], data_kinds={name: "real"},
                             sources=[{"id": name, "retrieved_at": "2026-11-13T10:00:00Z"}])


class EchoLLM:
    """Writes a narrative that cites the runs it was given."""

    def step(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMTurn:
        prompt = str(messages[0]["content"])
        ids = [line.split("run_id: ")[1][:12] for line in prompt.splitlines() if line.startswith("run_id: ")]
        text = (f"One school lies 182 m from the site [run:{ids[1]}]; this is context, not a ban. "
                f"Estimate, not a measurement: median 1.4 V/m, range 0.8 to 2.6 V/m, uncalibrated [run:{ids[2]}].")
        return LLMTurn(text=text, tool_calls=[], assistant_content=[{"type": "text", "text": text}], stop_reason="end_turn")


def test_permit_flow_runs_tools_in_order_with_config_radius() -> None:
    gw = RecordingGateway()
    report = permit_context("Via del Corso 1", llm=EchoLLM(), gateway=gw)
    names = [c[0] for c in gw.calls]
    assert names[:3] == ["resolve_place", "context_check", "estimate_field"]
    assert "legal_lookup" in names
    assert gw.calls[1][1]["radius_m"] == 300  # from config/thresholds.yaml
    assert report.verified, report.problems
    assert all(r["run_id"] for r in report.runs)


def test_scenario_asks_before_running() -> None:
    assert missing_slots({"kind": "antenna_add"}) == ["area", "change"]
    assert missing_slots({"kind": "antenna_add", "area": "municipio:1", "change": {"lon": 12.5}}) == []


class FakeExa:
    def search(self, query: str, include_domains: list[str], num_results: int) -> list[ExaResult]:
        return [ExaResult(url="https://romamobilita.it/news/1", title=f"Chiusura {query}", text="Via X chiusa", published="2026-11-13")]


def test_steward_scans_then_proposes_only_on_human_request() -> None:
    queue = InMemoryProposalQueue()
    items = scan(exa=FakeExa())
    assert items and all(i["status"] == "unverified" for i in items)
    assert queue.items == []  # scanning never writes
    p = propose(items[0], requested_by="officer", queue=queue)
    assert p["status"] == "pending_approval"
    assert queue.items == [p]


def test_eval_sets_pass_offline() -> None:
    summary = run_offline(Path("eval/sets"))
    assert summary["failed"] == [], summary["failed"]
    assert summary["passed"] >= 10


class ReportGateway(RecordingGateway):
    """A tool API that has WS4's permit_report tool (deterministic markdown + inner runs)."""

    def __init__(self) -> None:
        super().__init__()
        self.specs["permit_report"] = ToolSpec("permit_report", "report", {"type": "object"})

    def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if name != "permit_report":
            return super().call(name, arguments)
        self.calls.append((name, dict(arguments)))
        inner = [super(ReportGateway, self).call(n, {"x": 1}) for n in ("resolve_place", "context_check", "estimate_field")]
        self.calls = [c for c in self.calls if c[1] != {"x": 1}]
        return make_envelope(tool=name, inputs=dict(arguments), result={"markdown": "# Report\n| school | 182.4 m |", "tool_runs": inner},
                             data_kinds={"schools": "real"}, sources=[])


def test_permit_flow_uses_permit_report_when_available() -> None:
    gw = ReportGateway()
    report = permit_context("Via del Corso 1", llm=EchoLLM(), gateway=gw)
    names = [c[0] for c in gw.calls]
    assert names[0] == "permit_report" and "resolve_place" not in names
    assert gw.calls[0][1]["radius_m"] == 300
    assert "legal_lookup" in names
    assert report.markdown.startswith("# Report")
    assert report.verified, report.problems  # summary cites the inner runs of the report
