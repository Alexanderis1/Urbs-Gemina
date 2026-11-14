"""Read config/physics.yaml (entries are plain values or ``{value:, basis:}``)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from twin.scenarios import config as _scen

ROOT = _scen.ROOT


@lru_cache(maxsize=None)
def load() -> dict[str, Any]:
    return _scen.load("physics.yaml")


def value(section: str, key: str) -> Any:
    return _scen.value(load()[section], key)


def search_paths(section: str) -> list[Path]:
    dirs = value(section, "search_dirs")
    name = str(value(section, "file"))
    return [(Path(d) if Path(d).is_absolute() else ROOT / d) / name for d in dirs]


def frequency_mhz(band: str | None) -> float:
    table = load()["frequency_mhz_by_band"]["value"]
    if band is not None and str(band) in table:
        return float(table[str(band)])
    return float(load()["default_frequency_mhz"]["value"])
