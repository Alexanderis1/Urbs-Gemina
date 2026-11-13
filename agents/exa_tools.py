"""``legal_lookup`` and ``find_dataset``: Exa search restricted to official domains.

Defence in depth: the domain list is sent to Exa (``includeDomains``) *and* every result is
re-checked here, so a result from any other host is dropped with a warning.
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from agents.config import AgentConfig, load_agent_config
from agents.envelope import make_envelope, sha256_of
from agents.web import host_allowed, scan_for_injection


@dataclass(frozen=True)
class ExaResult:
    url: str
    title: str
    text: str
    published: str | None = None


class ExaSearch(Protocol):
    def search(self, query: str, include_domains: list[str], num_results: int) -> list[ExaResult]: ...


class ExaNotConfigured(RuntimeError):
    """No Exa API key in the environment."""


class HttpExaClient:
    """Minimal client for Exa's search endpoint (stdlib only, honours HTTPS_PROXY)."""

    def __init__(self, config: AgentConfig | None = None, api_key: str | None = None, timeout_s: float = 30.0) -> None:
        cfg = config or load_agent_config()
        self.endpoint = cfg.exa.endpoint
        self.max_characters = cfg.exa.max_characters
        key = api_key or os.environ.get(cfg.exa.api_key_env)
        if not key:
            raise ExaNotConfigured(f"set {cfg.exa.api_key_env} to use Exa")
        self.api_key = key
        self.timeout_s = timeout_s

    def search(self, query: str, include_domains: list[str], num_results: int) -> list[ExaResult]:
        body = {
            "query": query,
            "numResults": num_results,
            "includeDomains": include_domains,
            "contents": {"text": {"maxCharacters": self.max_characters}},
        }
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"x-api-key": self.api_key, "content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310 (fixed https endpoint)
            payload = json.loads(resp.read().decode("utf-8"))
        out = []
        for r in payload.get("results", []):
            out.append(ExaResult(url=str(r.get("url", "")), title=str(r.get("title") or ""),
                                 text=str(r.get("text") or ""), published=r.get("publishedDate")))
        return out


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _search_envelope(tool: str, inputs: dict[str, Any], query: str, domains: list[str], exa: ExaSearch,
                     cfg: AgentConfig, layer: str) -> dict[str, Any]:
    retrieved_at = _now()
    raw = exa.search(query, include_domains=list(domains), num_results=cfg.exa.num_results)
    warnings: list[str] = []
    kept: list[dict[str, Any]] = []
    for r in raw:
        if not host_allowed(r.url, domains):
            warnings.append(f"dropped result outside the allowed domains: {r.url}")
            continue
        text = r.text[: cfg.exa.max_characters]
        suspected = scan_for_injection(r.title + "\n" + text, cfg.injection_patterns)
        if suspected:
            warnings.append(f"possible prompt injection in {r.url}; quoted as data only")
        kept.append({"url": r.url, "title": r.title, "published": r.published, "text": text,
                     "retrieved_at": retrieved_at, "injection_suspected": suspected, "trust": "untrusted_web"})
    if not kept:
        warnings.append("no result from an allowed domain: answer 'insufficient data' for this point")
    snapshot = sha256_of([{k: v for k, v in i.items() if k != "retrieved_at"} for i in kept])
    return make_envelope(
        tool=tool,
        inputs=inputs,
        result={"results": kept, "allowed_domains": list(domains)},
        data_kinds={layer: "real"},
        sources=[{"id": "exa", "url": i["url"], "retrieved_at": retrieved_at} for i in kept],
        synthetic=False,
        warnings=warnings,
        snapshot_hashes=[snapshot, sha256_of(sorted(domains))],
    )


def legal_lookup(question: str, *, exa: ExaSearch | None = None, config: AgentConfig | None = None) -> dict[str, Any]:
    """Search Italian/EU official legal sources. Returns URLs with retrieval time, never a verdict."""
    cfg = config or load_agent_config()
    client = exa or HttpExaClient(cfg)
    return _search_envelope("legal_lookup", {"question": question}, question, cfg.exa.legal_domains, client, cfg, "legal_text")


def find_dataset(need: str, *, exa: ExaSearch | None = None, config: AgentConfig | None = None) -> dict[str, Any]:
    """Dataset scout on official open-data portals. Licence, format and cadence are read by the
    officer from the quoted page; the scout does not invent them."""
    cfg = config or load_agent_config()
    client = exa or HttpExaClient(cfg)
    query = f"open data dataset {need}"
    return _search_envelope("find_dataset", {"need": need}, query, cfg.exa.dataset_domains, client, cfg, "dataset_catalogue")


def news_search(query: str, *, exa: ExaSearch | None = None, config: AgentConfig | None = None) -> dict[str, Any]:
    """News 'text sensor' for disruptions (roadworks, strikes, demonstrations). Unverified."""
    cfg = config or load_agent_config()
    client = exa or HttpExaClient(cfg)
    return _search_envelope("news_search", {"query": query}, query, cfg.exa.news_domains, client, cfg, "disruption_news")
