"""Typed view of config/model.yaml."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from twin.model.heights import HeightConfig, height_config_from_dict


@dataclass(frozen=True)
class FootprintConfig:
    release: str
    drop_underground: bool
    min_area_m2: float


@dataclass(frozen=True)
class TerrainConfig:
    ring_m: float
    percentile: float


@dataclass(frozen=True)
class TileConfig:
    layer: str
    min_zoom: int
    max_zoom: int


@dataclass(frozen=True)
class ValidationConfig:
    references: tuple[str, ...]
    within_m: float


@dataclass(frozen=True)
class ModelConfig:
    footprints: FootprintConfig
    heights: HeightConfig
    terrain: TerrainConfig
    validation: ValidationConfig
    tiles: TileConfig


def model_config_from_dict(data: dict[str, Any]) -> ModelConfig:
    fp, te, va, ti = data["footprints"], data["terrain"], data["validation"], data["tiles"]
    return ModelConfig(
        footprints=FootprintConfig(str(fp["release"]), bool(fp["drop_underground"]), float(fp["min_area_m2"])),
        heights=height_config_from_dict(data["heights"]),
        terrain=TerrainConfig(float(te["ring_m"]), float(te["percentile"])),
        validation=ValidationConfig(tuple(str(r) for r in va["references"]), float(va["within_m"])),
        tiles=TileConfig(str(ti["layer"]), int(ti["min_zoom"]), int(ti["max_zoom"])),
    )


def load_model_config(path: Path) -> ModelConfig:
    with open(path, encoding="utf-8") as fh:
        return model_config_from_dict(yaml.safe_load(fh))
