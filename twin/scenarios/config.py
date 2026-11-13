"""Read the config files the scenario engine depends on."""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"

#: Config files whose content changes scenario results; their hashes enter the run id.
RESULT_CONFIGS = ("scenarios.yaml", "thresholds.yaml", "emf_params.yaml", "areas.yaml")


@lru_cache(maxsize=None)
def load(name: str) -> dict[str, Any]:
    raw = yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"config/{name} must be a mapping")
    return raw


def value(section: dict[str, Any], key: str) -> Any:
    """Read ``key`` from a section where entries are either plain or ``{value:, basis:}``."""
    entry = section[key]
    return entry["value"] if isinstance(entry, dict) and "value" in entry else entry


@lru_cache(maxsize=None)
def config_hashes() -> dict[str, str]:
    return {f"config/{name}": hashlib.sha256((CONFIG_DIR / name).read_bytes()).hexdigest()
            for name in RESULT_CONFIGS}
