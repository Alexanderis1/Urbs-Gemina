"""Read provider settings from config/provider_settings.yaml and config/emf_params.yaml.

Assumptions in config are written either as a bare value or as
``{value: ..., basis: "..."}``. The helpers here unwrap both forms so code never
hard-codes a number that belongs in config.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"

Section = Mapping[str, Any]


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be a mapping")
    return raw


@dataclass(frozen=True)
class Settings:
    """All settings a provider may need, plus the repository root for relative paths."""

    providers: dict[str, Any] = field(default_factory=dict)
    emf: dict[str, Any] = field(default_factory=dict)
    root: Path = ROOT

    @classmethod
    def load(cls, config_dir: Path = CONFIG_DIR, root: Path | None = None) -> "Settings":
        return cls(
            providers=_load_yaml(config_dir / "provider_settings.yaml"),
            emf=_load_yaml(config_dir / "emf_params.yaml"),
            root=root if root is not None else config_dir.parent,
        )

    def section(self, *keys: str) -> Section:
        node: Any = self.providers
        for key in keys:
            node = node.get(key, {}) if isinstance(node, dict) else {}
        return node if isinstance(node, dict) else {}

    def path(self, relative: str | None) -> Path | None:
        if not relative:
            return None
        candidate = Path(relative)
        return candidate if candidate.is_absolute() else self.root / candidate

    @property
    def simulator_version(self) -> str:
        return str(self.section("simulators").get("version", "sim-unversioned"))


def value(node: Any, default: Any = None) -> Any:
    """Unwrap ``{value: x, basis: ...}`` into ``x``; return bare values unchanged."""
    if node is None:
        return default
    if isinstance(node, dict):
        return node.get("value", default)
    return node


def number(section: Section, key: str, default: float) -> float:
    return float(value(section.get(key), default))


def integer(section: Section, key: str, default: int) -> int:
    return int(value(section.get(key), default))


def text(section: Section, key: str, default: str) -> str:
    return str(value(section.get(key), default))
