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
    assert r.json()["status"] == "not_available" and r.json()["reason"]  # not wired, or no EXA_API_KEY here


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
