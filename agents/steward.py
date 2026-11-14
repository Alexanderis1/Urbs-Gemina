"""Data steward: Exa monitors for news and new datasets, and ingest proposals for human approval.

Two separate steps, by design (guardrail 9):
1. ``scan`` reads the web and returns unverified items. It writes nothing.
2. ``propose`` is called later, by an officer's action in the UI, and queues a proposal with
   status ``pending_approval``. Nothing is ingested until an administrator approves it.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from agents.config import AgentConfig, load_agent_config
from agents.envelope import sha256_of
from agents.exa_tools import ExaSearch, find_dataset, news_search


class ProposalQueue(Protocol):
    def add(self, proposal: dict[str, Any]) -> None: ...


class InMemoryProposalQueue:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(self, proposal: dict[str, Any]) -> None:
        self.items.append(proposal)


class JsonlProposalQueue:
    """Append-only file queue (e.g. a git-ignored path under data/)."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def add(self, proposal: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(proposal, ensure_ascii=False) + "\n")


def scan(*, exa: ExaSearch | None = None, config: AgentConfig | None = None) -> list[dict[str, Any]]:
    cfg = config or load_agent_config()
    items: list[dict[str, Any]] = []
    for mon in cfg.monitors:
        env = (find_dataset(mon.query, exa=exa, config=cfg) if mon.kind == "dataset"
               else news_search(mon.query, exa=exa, config=cfg))
        for r in env["result"]["results"]:
            items.append({
                "id": sha256_of({"monitor": mon.id, "url": r["url"]})[:16],
                "monitor": mon.id,
                "kind": mon.kind,
                "title": r["title"],
                "url": r["url"],
                "published": r["published"],
                "retrieved_at": r["retrieved_at"],
                "excerpt": r["text"][:500],
                "injection_suspected": r["injection_suspected"],
                "run_id": env["run_id"],
                "data_kind": "real",
                "status": "unverified",
                "label": "from the web, unverified",
            })
    return items


def propose(item: Mapping[str, Any], *, requested_by: str, queue: ProposalQueue, note: str = "") -> dict[str, Any]:
    """Queue an ingest proposal. ``requested_by`` is a role or officer id, never a model."""
    proposal = {
        "proposal_id": sha256_of({"item": item.get("id"), "by": requested_by})[:16],
        "item": dict(item),
        "requested_by": requested_by,
        "note": note,
        "status": "pending_approval",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    queue.add(proposal)
    return proposal
