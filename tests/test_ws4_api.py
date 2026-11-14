"""WS4: HTTP tool API, role tiers and published schemas."""
import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from twin.api.app import create_app, parse_keys  # noqa: E402
from twin.api.export_schemas import SCHEMA_DIR, build_schemas  # noqa: E402
from twin.api.tools import TOOLS  # noqa: E402
from twin.tools.layers import LayerStore  # noqa: E402
from twin.tools.runtime import ToolRuntime  # noqa: E402
from twin.tools.settings import Settings  # noqa: E402

CONTRACT_TOOLS = {"resolve_place", "context_check", "estimate_field", "query_layer", "run_scenario",
                  "legal_lookup", "find_dataset", "data_status"}
OFFICE = {"Authorization": "Bearer office-key"}


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    settings = Settings.load()
    store = LayerStore(raw_dir=tmp_path)
    store.add("schools_state", {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [12.4830, 41.8960]},
         "properties": {"nome": "Scuola", "codice": "RM123"}}]})
    rt = ToolRuntime(settings=settings, store=store)
    rt.providers = rt._build_providers()
    rt.prg_fetcher = lambda url: {"type": "FeatureCollection", "features": []}  # no live calls in tests
    return TestClient(create_app(rt, api_keys={"office-key": "office", "citizen-key": "citizen"}))


def test_parse_keys_ignores_bad_roles() -> None:
    assert parse_keys("a:office, b:citizen ,c:admin,broken") == {"a": "office", "b": "citizen"}


def test_every_contract_tool_has_an_endpoint(client: TestClient) -> None:
    listed = {tool["name"] for tool in client.get("/tools").json()}
    assert CONTRACT_TOOLS <= listed
    assert client.get("/health").json() == {"status": "ok"}


def test_role_tiers(client: TestClient) -> None:
    assert client.get("/whoami").json() == {"role": "citizen"}
    assert client.get("/whoami", headers={"Authorization": "Bearer wrong"}).json() == {"role": "citizen"}
    assert client.get("/whoami", headers=OFFICE).json() == {"role": "office"}
    body = {"point": [12.4823, 41.8960]}
    office = client.post("/tools/context_check", json=body, headers=OFFICE).json()
    citizen = client.post("/tools/context_check", json=body).json()
    hit_office = office["result"]["groups"]["sensitive_site"]["layers"][0]["hits"][0]
    hit_citizen = citizen["result"]["groups"]["sensitive_site"]["layers"][0]["hits"][0]
    assert "properties" in hit_office and "properties" not in hit_citizen


def test_envelope_over_http(client: TestClient) -> None:
    r = client.post("/tools/resolve_place", json={"text": "41.896, 12.4823"})
    assert r.status_code == 200
    env = r.json()
    assert set(env) == {"run_id", "tool", "status", "inputs", "result", "data_kinds", "sources", "synthetic",
                        "warnings", "cached"}
    assert env["result"]["lat"] == 41.896


def test_strict_inputs_are_rejected(client: TestClient) -> None:
    assert client.post("/tools/resolve_place", json={"text": "Roma", "extra": 1}).status_code == 422
    assert client.post("/tools/context_check", json={"point": [9.19, 45.46]}).status_code == 422


def test_tool_errors_are_400(client: TestClient) -> None:
    r = client.post("/tools/estimate_field", json={"point": [12.48, 41.9], "area": "city"})
    assert r.status_code == 400 and "exactly one" in r.json()["error"]


def test_data_status_without_body(client: TestClient) -> None:
    r = client.post("/tools/data_status")
    assert r.status_code == 200 and r.json()["tool"] == "data_status"


def test_tools_of_other_streams_answer_not_available_until_wired(client: TestClient) -> None:
    r = client.post("/tools/legal_lookup", json={"question": "limite di attenzione campi elettromagnetici"})
    assert r.status_code == 200
    env = r.json()
    assert env["tool"] == "legal_lookup" and env["status"] in ("ok", "not_available")
    if env["status"] == "not_available":  # WS7 not merged, or no EXA_API_KEY
        assert env["reason"]


def test_run_scenario_refuses_or_reports(client: TestClient) -> None:
    pytest.importorskip("twin.scenarios.engine")
    heavy = client.post("/tools/run_scenario", json={"kind": "road_closure", "area": "city",
                                                     "change": {"close": {"street": "Via del Corso"}}})
    assert heavy.status_code == 200 and heavy.json()["status"] == "refused"
    assert client.post("/tools/run_scenario", json={"kind": "nope", "area": "city"}).status_code == 400


def test_permit_report_markdown(client: TestClient) -> None:
    r = client.post("/reports/permit.md", json={"point": [12.4823, 41.8960]}, headers=OFFICE)
    assert r.status_code == 200 and r.text.startswith("# Permit context report")


def test_published_schemas_are_up_to_date() -> None:
    expected = build_schemas()
    for filename, content in expected.items():
        path = SCHEMA_DIR / filename
        assert path.exists(), f"run: python -m twin.api.export_schemas ({filename} missing)"
        assert json.loads(path.read_text(encoding="utf-8")) == content, f"{filename} is stale"
    assert {f"{name}.json" for name in TOOLS} | {"envelope.json"} == set(expected)


def _walk(schema: Any) -> list[dict[str, Any]]:
    found = []
    if isinstance(schema, dict):
        if schema.get("type") == "object" and "properties" in schema:
            found.append(schema)
        for value in schema.values():
            found += _walk(value)
    elif isinstance(schema, list):
        for value in schema:
            found += _walk(value)
    return found


def test_input_schemas_are_strict() -> None:
    for name, content in build_schemas().items():
        if name == "envelope.json":
            continue
        for obj in _walk(content["input_schema"]):
            assert obj.get("additionalProperties") is False, name


def test_sports_tools_are_mounted_and_honest_when_missing(client: TestClient) -> None:
    listed = {tool["name"] for tool in client.get("/tools").json()}
    assert {"sports_facilities", "sport_coverage"} <= listed
    r = client.post("/tools/sports_facilities", json={"area": "municipio:1", "discipline": "swimming"})
    assert r.status_code == 200 and r.json()["status"] == "not_available"  # module or built layer missing here
    r = client.post("/tools/sport_coverage", json={"discipline": "swimming", "max_minutes": 90})
    assert r.status_code == 422


def test_census_sections_are_read_from_processed(tmp_path: Path) -> None:
    from twin.api.tools import _census
    from twin.tools.settings import Paths

    settings = Settings.load()
    rt = ToolRuntime(settings=Settings(**{**settings.__dict__,
                                          "paths": Paths(root=tmp_path, config=settings.paths.config, data=tmp_path)}),
                     store=LayerStore(raw_dir=tmp_path))
    assert _census(rt) is None
    (tmp_path / "processed").mkdir()
    ring = [[12.48, 41.89], [12.49, 41.89], [12.49, 41.90], [12.48, 41.89]]
    (tmp_path / "processed" / "census_sections.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
         "properties": {"sez_id": "1", "residents": 120, "children_0_14": 15, "municipio": "1", "zone": "1A"}}]}))
    census = _census(rt)
    assert census is not None and len(census.features) == 1 and census.sha256


def test_voice_and_ask_routes_exist_and_never_trust_the_body_for_the_tier(client: TestClient) -> None:
    r = client.post("/voice/ask_twin", json={"question": "Com'e il traffico?"})
    if r.status_code == 501:  # WS9 not installed in this build
        assert "voice" in r.json()["error"]
    else:
        assert r.status_code == 401  # no ElevenLabs secret header
    assert client.post("/ask", json={"question": "x", "tier": "office"}).status_code == 422


def test_in_process_gateway_uses_the_given_tier(tmp_path: Path) -> None:
    from twin.api.orchestrator import InProcessGateway

    rt = ToolRuntime(settings=Settings.load(), store=LayerStore(raw_dir=tmp_path))
    gw = InProcessGateway(rt, "citizen", {"resolve_place": object(), "news_search": object()})
    assert set(gw.specs) == {"resolve_place"}
    env = gw.call("resolve_place", {"text": "41.896, 12.4823"})
    assert env["status"] == "ok"
    bad = gw.call("resolve_place", {"text": "x", "tier": "office"})
    assert bad["status"] == "refused" and "invalid arguments" in bad["reason"]


def test_scenario_data_prefers_ws6_live_baseline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """With WS6's baselines.live_data present, the real Cartoradio grid replaces our point baseline."""
    import sys
    import types

    from twin.api import tools as api_tools

    data_mod = types.ModuleType("twin.scenarios.data")
    data_mod.ScenarioData = lambda **kw: ("ours", kw)  # type: ignore[attr-defined]
    data_mod.FieldSample = lambda v, s: (v, s)  # type: ignore[attr-defined]
    calls: list[tuple[Any, ...]] = []
    live = types.ModuleType("twin.scenarios.baselines")

    def live_data(kind: str, area: Any, change: Any, **overrides: Any) -> Any:
        calls.append((kind, area, change, overrides))
        return ("live", overrides)

    live.live_data = live_data  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "twin.scenarios.data", data_mod)
    monkeypatch.setitem(sys.modules, "twin.scenarios.baselines", live)
    rt = ToolRuntime(settings=Settings.load(), store=LayerStore(tmp_path, tmp_path / "m.json"))
    out = api_tools._scenario_data(rt, "antenna", None, {"site": {"lon": 12.48, "lat": 41.89}})
    assert out[0] == "live"
    assert "baseline_field" not in calls[0][3] and "area_lookup" in calls[0][3]

    def broken(*args: Any, **kw: Any) -> Any:
        raise RuntimeError("cartoradio down")

    live.live_data = broken  # type: ignore[attr-defined]
    assert api_tools._scenario_data(rt, "antenna", None, {})[0] == "ours"


def test_unexpected_error_is_json_500_with_cors(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from twin.api import tools as api_tools

    def boom(rt: Any) -> dict[str, Any]:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(api_tools, "data_status", boom)
    r = client.post("/tools/data_status", json={}, headers={"Origin": "https://example.lovable.app"})
    assert r.status_code == 500
    assert r.json()["error"].startswith("RuntimeError")
    assert r.headers.get("access-control-allow-origin") == "*"


def test_scenario_bad_change_is_refused_with_reason(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    engine = types.ModuleType("twin.scenarios.engine")
    engine.kinds = lambda: {"antenna": "x"}  # type: ignore[attr-defined]

    def run(kind: str, area: Any, change: Any, data: Any = None) -> Any:
        raise ValueError("antenna change needs a 'site' with lon, lat, height_m")

    engine.run = run  # type: ignore[attr-defined]
    area_mod = types.ModuleType("twin.scenarios.area")
    area_mod.AreaTooLarge = type("AreaTooLarge", (Exception,), {})  # type: ignore[attr-defined]
    area_mod.AreaNotAvailable = type("AreaNotAvailable", (Exception,), {})  # type: ignore[attr-defined]
    data_mod = types.ModuleType("twin.scenarios.data")
    data_mod.ScenarioData = lambda **kw: kw  # type: ignore[attr-defined]
    data_mod.FieldSample = lambda v, s: (v, s)  # type: ignore[attr-defined]
    for mod in (engine, area_mod, data_mod):
        monkeypatch.setitem(sys.modules, mod.__name__, mod)
    r = client.post("/tools/run_scenario", json={"kind": "antenna", "area": "city", "change": {}})
    assert r.status_code == 200
    assert r.json()["status"] == "refused" and "site" in r.json()["reason"]


def test_ask_serialises_citations(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import sys
    import types
    from dataclasses import dataclass, field

    from twin.api import app as app_mod

    @dataclass(frozen=True)
    class TwinQuestion:
        question: str
        tier: str
        language: str = "it"
        area: Any = None
        mode: str = "question"
        conversation_id: Any = None
        channel: str = "chat"
        use_case: Any = None
        params: Any = None

    @dataclass(frozen=True)
    class TwinAnswer:
        text: str
        verified: bool
        citations: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    contract = types.ModuleType("agents.contract")
    contract.TwinQuestion = TwinQuestion  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "agents.contract", contract)

    class FakeOrchestrator:
        def __init__(self, runtime: Any) -> None:
            pass

        def ask(self, question: Any) -> TwinAnswer:
            return TwinAnswer("ok", True, ({"line": 1, "kind": "run", "ref": "abc", "cite_mode": "auto"},))

    monkeypatch.setattr(app_mod, "TierOrchestrator", FakeOrchestrator)
    rt = ToolRuntime(settings=Settings.load(), store=LayerStore(raw_dir=tmp_path))
    body = TestClient(create_app(rt, api_keys={})).post("/ask", json={"question": "ciao"}).json()
    assert body["citations"] == [{"line": 1, "kind": "run", "ref": "abc", "cite_mode": "auto"}]


def test_envelope_accepts_hypothetical_scenario_inputs() -> None:
    """What-if inputs (a 3 m river rise, a 38 °C day) are labelled 'hypothetical' by WS6."""
    from twin.api.models import EnvelopeOut

    env = EnvelopeOut(run_id="x", tool="run_scenario", status="ok", inputs={}, result={},
                      data_kinds={"river_level": "hypothetical", "terrain": "estimated"},
                      sources=[], synthetic=False, warnings=[])
    assert env.data_kinds["river_level"] == "hypothetical"


def test_envelope_accepts_file_sources_without_retrieval_time() -> None:
    """Static scenario inputs (e.g. the Copernicus tree-cover file) cite a file, not a fetch time."""
    from twin.api.models import EnvelopeOut

    env = EnvelopeOut(run_id="x", tool="run_scenario", status="ok", inputs={}, result={}, data_kinds={},
                      sources=[{"id": "copernicus_hrl_tree_cover", "file": "tree_cover_2018.tif"}],
                      synthetic=False, warnings=[])
    assert env.sources[0].retrieved_at is None


def test_scenario_sources_without_retrieval_time_still_validate(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """WS6 cites static files as {"id", "file"}: the API adds the read time instead of failing with HTTP 500."""
    import sys
    import types

    engine = types.ModuleType("twin.scenarios.engine")
    engine.kinds = lambda: {"heatwave": "x"}  # type: ignore[attr-defined]

    def run(kind: str, area: Any, change: Any, data: Any = None) -> Any:
        return {"run_id": "a" * 64, "tool": "run_scenario", "inputs": {}, "result": {"status": "ok"},
                "data_kinds": {"tree_cover": "real"}, "sources": [{"id": "copernicus_hrl_tree_cover", "file": "tree_cover_2018.tif"}],
                "synthetic": False, "warnings": [], "status": "ok", "cached": False}

    engine.run = run  # type: ignore[attr-defined]
    area_mod = types.ModuleType("twin.scenarios.area")
    area_mod.AreaTooLarge = type("AreaTooLarge", (Exception,), {})  # type: ignore[attr-defined]
    area_mod.AreaNotAvailable = type("AreaNotAvailable", (Exception,), {})  # type: ignore[attr-defined]
    data_mod = types.ModuleType("twin.scenarios.data")
    data_mod.ScenarioData = lambda **kw: kw  # type: ignore[attr-defined]
    data_mod.FieldSample = lambda v, s: (v, s)  # type: ignore[attr-defined]
    for mod in (engine, area_mod, data_mod):
        monkeypatch.setitem(sys.modules, mod.__name__, mod)
    r = client.post("/tools/run_scenario", json={"kind": "heatwave", "area": "municipio:1", "change": {}})
    assert r.status_code == 200, r.text
    src = r.json()["sources"][0]
    assert src["id"] == "copernicus_hrl_tree_cover" and src["retrieved_at"]


def test_use_cases_are_listed_per_tier(client: TestClient) -> None:
    office = client.get("/use_cases", headers=OFFICE).json()
    citizen = client.get("/use_cases").json()
    ids = {u["id"] for u in office}
    assert {"heat_plan_elderly", "civil_protection_alert", "site_risk_check"} <= ids
    assert {u["id"] for u in citizen} < ids and "event_planning" not in {u["id"] for u in citizen}
    heat = next(u for u in office if u["id"] == "heat_plan_elderly")
    assert heat["needs"] == ["area"] and heat["title"]["it"] and "cover_added_pct" in heat["params"]


def test_ask_passes_use_case_and_params(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    from agents.contract import TwinAnswer
    from twin.api import app as app_mod

    seen: list[Any] = []

    class FakeOrchestrator:
        def __init__(self, runtime: Any) -> None:
            pass

        def ask(self, question: Any) -> TwinAnswer:
            seen.append(question)
            return TwinAnswer("ok", True, (), (), {}, False)

    monkeypatch.setattr(app_mod, "TierOrchestrator", FakeOrchestrator)
    from twin.tools.runtime import ToolRuntime
    from twin.tools.settings import Settings
    from twin.tools.layers import LayerStore

    rt = ToolRuntime(settings=Settings.load(), store=LayerStore(raw_dir=Path("/nonexistent")))
    c = TestClient(create_app(rt, api_keys={"office-key": "office"}))
    r = c.post("/ask", headers=OFFICE, json={"question": "Circo Massimo", "use_case": "event_planning",
                                             "params": {"attendees": 60000}})
    assert r.status_code == 200, r.text
    assert seen[0].use_case == "event_planning" and seen[0].params == {"attendees": 60000}


def test_hypothetical_scenario_inputs_are_labelled_not_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """A what-if input from the officer (WS6 kind 'hypothetical') must not crash the response model."""
    import sys
    import types

    engine = types.ModuleType("twin.scenarios.engine")
    engine.kinds = lambda: {"heatwave": "x"}  # type: ignore[attr-defined]

    def run(kind: str, area: Any, change: Any, data: Any = None) -> Any:
        return {"run_id": "b" * 64, "tool": "run_scenario", "inputs": {}, "result": {"status": "ok"},
                "data_kinds": {"temperature": "hypothetical", "census": "real"}, "sources": [],
                "synthetic": False, "warnings": [], "status": "ok", "cached": False}

    engine.run = run  # type: ignore[attr-defined]
    area_mod = types.ModuleType("twin.scenarios.area")
    area_mod.AreaTooLarge = type("AreaTooLarge", (Exception,), {})  # type: ignore[attr-defined]
    area_mod.AreaNotAvailable = type("AreaNotAvailable", (Exception,), {})  # type: ignore[attr-defined]
    data_mod = types.ModuleType("twin.scenarios.data")
    data_mod.ScenarioData = lambda **kw: kw  # type: ignore[attr-defined]
    data_mod.FieldSample = lambda v, s: (v, s)  # type: ignore[attr-defined]
    for mod in (engine, area_mod, data_mod):
        monkeypatch.setitem(sys.modules, mod.__name__, mod)
    r = client.post("/tools/run_scenario", json={"kind": "heatwave", "area": "municipio:1", "change": {"tmax_c": 38}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["data_kinds"] == {"temperature": "estimated", "census": "real"}
    assert any("temperature" in w and "hypothetical" in w for w in body["warnings"])


def test_population_tools_are_registered(client: TestClient) -> None:
    names = {t["name"] for t in client.get("/tools").json()}
    assert {"crowds", "exposure", "site_values", "check_sensors"} <= names
    r = client.post("/tools/exposure", json={"layer": "emf", "area": "city", "threshold": "no2_hourly_limit"})
    assert r.status_code == 400  # threshold of another layer


def test_thin_evenly_spreads_over_the_whole_list() -> None:
    from twin.tools.query_layer import thin_evenly

    items = list(range(10_000))
    kept = thin_evenly(items, 5)
    assert kept == [0, 2500, 5000, 7499, 9999]
    assert thin_evenly(items[:3], 5) == [0, 1, 2]
    assert len(thin_evenly(items, 5000)) == 5000
    assert thin_evenly(items, 5000)[-1] == 9999
