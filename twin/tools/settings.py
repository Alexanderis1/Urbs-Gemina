"""Where the tools find their config and data, and small YAML helpers.

Paths default to the repository layout and can be moved with environment
variables (used by the hosted deployment):

- ``URBS_ROOT``: project root (default: two levels above this file)
- ``URBS_CONFIG_DIR``: config folder (default: ``<root>/config``)
- ``URBS_DATA_DIR``: data folder holding ``raw/`` and ``manifest.json`` (default: ``<root>/data``)
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml


#: Config files whose content changes tool results.
CONFIG_FILES = ("thresholds.yaml", "emf_params.yaml", "areas.yaml", "scenarios.yaml", "beliefs.yaml",
                "providers.yaml", "tools.yaml", "context_layers.yaml", "places.yaml")


def _root() -> Path:
    return Path(os.environ.get("URBS_ROOT", Path(__file__).resolve().parents[2]))


@dataclass(frozen=True)
class Paths:
    root: Path
    config: Path
    data: Path

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def manifest(self) -> Path:
        return self.data / "manifest.json"


def default_paths() -> Paths:
    root = _root()
    config = Path(os.environ.get("URBS_CONFIG_DIR", root / "config"))
    data = Path(os.environ.get("URBS_DATA_DIR", root / "data"))
    return Paths(root=root, config=config, data=data)


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a mapping")
    return raw


def value(entry: Any) -> Any:
    """Config numbers are written either bare or as ``{value: ..., basis: ...}``."""
    if isinstance(entry, Mapping) and "value" in entry:
        return entry["value"]
    return entry


@dataclass(frozen=True)
class Settings:
    """All config files the tools read, loaded once."""

    paths: Paths
    thresholds: dict[str, Any] = field(default_factory=dict)
    areas: dict[str, Any] = field(default_factory=dict)
    context_layers: dict[str, Any] = field(default_factory=dict)
    tools: dict[str, Any] = field(default_factory=dict)
    places: dict[str, Any] = field(default_factory=dict)
    providers: dict[str, str] = field(default_factory=dict)
    emf_params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, paths: Paths | None = None) -> "Settings":
        paths = paths or default_paths()
        providers = load_yaml(paths.config / "providers.yaml")
        return cls(
            paths=paths,
            thresholds=load_yaml(paths.config / "thresholds.yaml"),
            areas=load_yaml(paths.config / "areas.yaml"),
            context_layers=load_yaml(paths.config / "context_layers.yaml"),
            tools=load_yaml(paths.config / "tools.yaml"),
            places=load_yaml(paths.config / "places.yaml"),
            providers={str(k): str(v) for k, v in providers.items()},
            emf_params=load_yaml(paths.config / "emf_params.yaml"),
        )

    def config_hashes(self) -> dict[str, str]:
        """SHA-256 of every config file that can change a tool result (enters the run id)."""
        out: dict[str, str] = {}
        for name in CONFIG_FILES:
            path = self.paths.config / name
            if path.exists():
                out[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return out

    def tool(self, *keys: str) -> Any:
        """Nested lookup in tools.yaml, unwrapping ``{value: ...}`` entries."""
        node: Any = self.tools
        for key in keys:
            node = node[key]
        return value(node)


@lru_cache(maxsize=1)
def default_settings() -> Settings:
    return Settings.load()
