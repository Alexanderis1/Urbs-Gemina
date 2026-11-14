"""Tool specs and gateways. Agents reach tools only through a gateway that returns envelopes.

* ``HttpToolGateway``: ``POST {URBS_TOOL_API_URL}/tools/<name>`` on the WS4 tool API.
* ``LocalWebTools``: the Exa tools of this package, run in-process.
* ``CompositeGateway``: routes each tool name to the gateway that has it.

Schemas come from ``twin/api/schemas/*.json`` (published by WS4). Until they exist, the draft
in ``agents/tool_schemas_draft.json`` is used and the agent says so in its warnings.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from agents.config import ROOT, AgentConfig, load_agent_config
from agents.envelope import make_envelope

API_SCHEMA_DIR = ROOT / "twin" / "api" / "schemas"
DRAFT_SCHEMAS = Path(__file__).resolve().parent / "tool_schemas_draft.json"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    #: Changes stored state (writes, provider switches, queues). Locked after web content in a turn.
    state_changing: bool = False
    #: Output contains web text. Seeing it locks state-changing tools for the rest of the turn.
    untrusted_output: bool = False

    def for_model(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


class ToolGateway(Protocol):
    @property
    def specs(self) -> Mapping[str, ToolSpec]: ...

    def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]: ...


class ToolError(RuntimeError):
    pass


def _spec_from_json(stem: str, doc: Mapping[str, Any]) -> ToolSpec:
    schema = doc.get("input_schema")
    if not isinstance(schema, dict):
        schema = {k: v for k, v in doc.items() if k in ("type", "properties", "required", "additionalProperties")}
    return ToolSpec(
        name=str(doc.get("name", stem)),
        description=str(doc.get("description", "")),
        input_schema=schema or {"type": "object"},
        state_changing=bool(doc.get("x-state-changing", doc.get("state_changing", False))),
        untrusted_output=bool(doc.get("x-untrusted-output", doc.get("untrusted_output", False))),
    )


def load_tool_specs(schema_dir: Path = API_SCHEMA_DIR, draft: Path = DRAFT_SCHEMAS) -> tuple[dict[str, ToolSpec], bool]:
    """Return (specs, is_draft). Published schemas win over the draft, tool by tool."""
    specs: dict[str, ToolSpec] = {}
    for item in json.loads(draft.read_text(encoding="utf-8"))["tools"]:
        spec = _spec_from_json(str(item["name"]), item)
        specs[spec.name] = spec
    published = sorted(schema_dir.glob("*.json")) if schema_dir.is_dir() else []
    for path in published:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(doc, dict):
            spec = _spec_from_json(path.stem, doc)
            draft_spec = specs.get(spec.name)
            if draft_spec and draft_spec.untrusted_output and not spec.untrusted_output:
                spec = ToolSpec(spec.name, spec.description, spec.input_schema, spec.state_changing, True)
            specs[spec.name] = spec
    return specs, not published


class HttpToolGateway:
    """Calls the WS4 tool API. ``role`` is sent so the API enforces citizen/office tiers itself."""

    def __init__(self, specs: Mapping[str, ToolSpec], base_url: str | None = None, role: str = "office",
                 token: str | None = None, config: AgentConfig | None = None) -> None:
        cfg = config or load_agent_config()
        url = base_url or os.environ.get(cfg.tool_api_url_env)
        if not url:
            raise ToolError(f"set {cfg.tool_api_url_env} to the tool API URL")
        self.base_url = url.rstrip("/")
        self.role = role
        self.token = token
        self.timeout_s = cfg.tool_api_timeout_s
        self._specs = dict(specs)

    @property
    def specs(self) -> Mapping[str, ToolSpec]:
        return self._specs

    def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        headers = {"content-type": "application/json", "x-urbs-role": self.role}
        if self.token:
            headers["authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(f"{self.base_url}/tools/{name}", data=json.dumps(dict(arguments)).encode("utf-8"),
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310 (configured API URL)
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ToolError(f"{name} returned HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}") from e
        if not isinstance(body, dict):
            raise ToolError(f"{name} returned a non-object body")
        return body


class LocalWebTools:
    """The Exa tools (legal_lookup, find_dataset, news_search) run in-process."""

    def __init__(self, specs: Mapping[str, ToolSpec], exa: Any = None, config: AgentConfig | None = None) -> None:
        from agents import exa_tools

        cfg = config or load_agent_config()
        fns: dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]] = {
            "legal_lookup": lambda a: exa_tools.legal_lookup(str(a["question"]), exa=exa, config=cfg),
            "find_dataset": lambda a: exa_tools.find_dataset(str(a["need"]), exa=exa, config=cfg),
            "news_search": lambda a: exa_tools.news_search(str(a["query"]), exa=exa, config=cfg),
        }
        self._fns = fns
        self._specs = {n: specs[n] for n in fns if n in specs}

    @property
    def specs(self) -> Mapping[str, ToolSpec]:
        return self._specs

    def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return self._fns[name](arguments)


class CompositeGateway:
    def __init__(self, *gateways: ToolGateway) -> None:
        self._route: dict[str, ToolGateway] = {}
        for g in gateways:  # earlier gateways win
            for n in g.specs:
                self._route.setdefault(n, g)

    @property
    def specs(self) -> Mapping[str, ToolSpec]:
        return {n: g.specs[n] for n, g in self._route.items()}

    def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if name not in self._route:
            raise ToolError(f"unknown tool {name}")
        return self._route[name].call(name, arguments)


def error_envelope(name: str, arguments: Mapping[str, Any], message: str) -> dict[str, Any]:
    return make_envelope(tool=name, inputs=arguments, result={"error": message}, data_kinds={}, sources=[],
                         warnings=[message])
