"""Load config/agents.yaml and the thresholds the agents need (read-only)."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


@dataclass(frozen=True)
class ExaConfig:
    api_key_env: str
    endpoint: str
    num_results: int
    max_characters: int
    legal_domains: list[str]
    dataset_domains: list[str]
    news_domains: list[str]


@dataclass(frozen=True)
class Monitor:
    id: str
    query: str
    kind: str = "news"


@dataclass(frozen=True)
class VerifierConfig:
    banned_phrases: list[str]
    exempt_patterns: list[str]
    calibration_words: list[str]
    abbreviations: list[str]
    generic_name_words: list[str]
    non_measure_keys: list[str]
    estimate_words: list[str]
    simulated_words: list[str]


@dataclass(frozen=True)
class AgentConfig:
    models: dict[str, str]
    effort: str
    max_tokens: int
    max_tool_rounds: int
    verifier_retries: int
    tool_api_url_env: str
    claude_key_envs: list[str]
    claude_base_url: str
    tool_api_timeout_s: float
    disclosure: dict[str, str]
    simulated_note: dict[str, str]
    exa: ExaConfig
    monitors: list[Monitor]
    verifier: VerifierConfig
    injection_patterns: list[str]
    context_radius_m: float
    permit_legal_questions: list[str]
    circle_vertices: int
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def disclosure_for(self, tier: str, language: str) -> str:
        """AI disclosure for the first answer: officers get 'the official decides', residents get
        'information only; in an emergency call 112' (config/agents.yaml disclosure.citizen_*)."""
        d = self.raw.get("disclosure") or {}
        if tier == "citizen" and d.get(f"citizen_{language}"):
            return str(d[f"citizen_{language}"])
        return self.disclosure.get(language, self.disclosure["en"])

    @property
    def model_view_max_items(self) -> int:
        return int((self.raw.get("model_view") or {}).get("max_list_items", 25))


def _read(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    return data


@lru_cache(maxsize=4)
def load_agent_config(config_dir: Path = CONFIG_DIR) -> AgentConfig:
    raw = _read(config_dir / "agents.yaml")
    thresholds = _read(config_dir / "thresholds.yaml")
    m = raw["models"]
    exa = raw["exa"]
    v = raw["verifier"]
    return AgentConfig(
        models={k: str(m[k]) for k in ("orchestrator", "permit", "scenario", "voice")},
        effort=str(m["effort"]),
        max_tokens=int(m["max_tokens"]),
        max_tool_rounds=int(raw["loop"]["max_tool_rounds"]),
        verifier_retries=int(raw["loop"]["verifier_retries"]),
        tool_api_url_env=str(raw["tool_api"]["base_url_env"]),
        claude_key_envs=[str(x) for x in raw["claude_api"]["api_key_envs"]],
        claude_base_url=str(raw["claude_api"]["base_url"]),
        tool_api_timeout_s=float(raw["tool_api"]["timeout_s"]),
        disclosure={k: str(raw["disclosure"][k]) for k in ("en", "it")},
        simulated_note={k: str(raw["disclosure"][f"simulated_note_{k}"]) for k in ("en", "it")},
        exa=ExaConfig(
            api_key_env=str(exa["api_key_env"]),
            endpoint=str(exa["endpoint"]),
            num_results=int(exa["num_results"]),
            max_characters=int(exa["max_characters"]),
            legal_domains=[str(d) for d in exa["legal_domains"]],
            dataset_domains=[str(d) for d in exa["dataset_domains"]],
            news_domains=[str(d) for d in exa["news_domains"]],
        ),
        monitors=[Monitor(id=str(x["id"]), query=str(x["query"]), kind=str(x.get("kind", "news"))) for x in raw["monitors"]],
        verifier=VerifierConfig(
            banned_phrases=[str(x) for x in v["banned_phrases"]],
            exempt_patterns=[str(x) for x in v["exempt_patterns"]],
            calibration_words=[str(x) for x in v["calibration_words"]],
            abbreviations=[str(x) for x in v["abbreviations"]],
            generic_name_words=[str(x) for x in v["generic_name_words"]],
            non_measure_keys=[str(x) for x in v["non_measure_keys"]],
            estimate_words=[str(x) for x in v["estimate_words"]],
            simulated_words=[str(x) for x in v["simulated_words"]],
        ),
        injection_patterns=[str(x) for x in raw["injection"]["patterns"]],
        context_radius_m=float(thresholds["antenna_context"]["radius_m"]),
        permit_legal_questions=[str(q) for q in raw["permit"]["legal_questions"]],
        circle_vertices=int(raw["permit"]["circle_vertices"]),
        raw=raw,
    )
