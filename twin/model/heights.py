"""Pick one height per building from an ordered list of sources.

Pure Python, no geospatial dependencies, so the rule is easy to test and audit.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping, Optional

import yaml

DataKind = Literal["real", "estimated", "simulated"]
KNOWN_SOURCES = ("osm_tag", "gba", "raster", "floors", "default")


@dataclass(frozen=True)
class HeightConfig:
    priority: tuple[str, ...]
    data_kinds: dict[str, DataKind]
    licences: dict[str, str]
    metres_per_floor: float
    default_m: float
    clamp: tuple[float, float]
    raster_path: Optional[str] = None
    raster_statistic: str = "median"
    raster_min_valid: float = 1.0
    gba_path: Optional[str] = None
    method: str = "priority"
    fusion_reference: str = "osm_tag"
    fusion_reference_sd: float = 1.5
    fusion_prior: tuple[float, float] = (9.0, 8.0)
    fusion_min_pairs: int = 200
    fusion_conflict_chi2: float = 9.0
    #: Urban Atlas class code -> (low m, high m, height used). Empty when the raster holds metres.
    raster_classes: dict[int, tuple[float, float, float]] = field(default_factory=dict)

    @property
    def non_commercial(self) -> frozenset[str]:
        """Sources whose licence forbids commercial use (CC BY-NC and similar)."""
        return frozenset(k for k, v in self.licences.items() if "NC" in v.upper().replace("-", " ").split())


@dataclass(frozen=True)
class ResolvedHeight:
    height_m: float
    source: str
    data_kind: DataKind
    licence: str


def height_config_from_dict(heights: Mapping[str, Any]) -> HeightConfig:
    priority = tuple(str(s) for s in heights["priority"])
    unknown = [s for s in priority if s not in KNOWN_SOURCES]
    if unknown:
        raise ValueError(f"unknown height sources in priority: {unknown}")
    if not priority or priority[-1] != "default":
        raise ValueError("height priority must end with 'default'")
    sources: Mapping[str, Any] = heights.get("sources", {})
    kinds: dict[str, DataKind] = {}
    licences: dict[str, str] = {}
    for name in priority:
        licences[name] = str(sources.get(name, {}).get("licence", "not stated"))
        kind = str(sources.get(name, {}).get("data_kind", "estimated"))
        if kind not in ("real", "estimated", "simulated"):
            raise ValueError(f"bad data_kind for {name}: {kind}")
        kinds[name] = kind  # type: ignore[assignment]
    raster = sources.get("raster", {})
    lo, hi = heights.get("clamp_m", [2.0, 160.0])
    method = str(heights.get("method", "priority"))
    if method not in ("priority", "fusion"):
        raise ValueError(f"unknown height method {method}")
    fu = heights.get("fusion", {}) or {}
    prior = fu.get("prior", {}) or {}
    return HeightConfig(
        priority=priority,
        data_kinds=kinds,
        licences=licences,
        metres_per_floor=float(sources.get("floors", {}).get("metres_per_floor", 3.2)),
        default_m=float(sources.get("default", {}).get("metres", 9.0)),
        clamp=(float(lo), float(hi)),
        method=method,
        fusion_reference=str(fu.get("reference", "osm_tag")),
        fusion_reference_sd=float(fu.get("reference_sd_m", 1.5)),
        fusion_prior=(float(prior.get("mean_m", 9.0)), float(prior.get("sd_m", 8.0))),
        fusion_min_pairs=int(fu.get("min_pairs", 200)),
        fusion_conflict_chi2=float(fu.get("conflict_chi2", 9.0)),
        raster_path=raster.get("path"),
        raster_statistic=str(raster.get("statistic", "median")),
        raster_min_valid=float(raster.get("min_valid", 1.0)),
        gba_path=sources.get("gba", {}).get("path"),
        raster_classes={
            int(k): (float(v[0]), float(v[1]), float(v[2])) for k, v in (raster.get("classes") or {}).items()
        },
    )


def load_height_config(path: Path) -> HeightConfig:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return height_config_from_dict(data["heights"])


def _usable(value: Optional[float]) -> bool:
    return value is not None and math.isfinite(value) and value > 0.0


def resolve_height(candidates: Mapping[str, Optional[float]], cfg: HeightConfig) -> ResolvedHeight:
    """First source in ``cfg.priority`` with a positive finite value wins (metres)."""
    lo, hi = cfg.clamp
    for name in cfg.priority:
        value = cfg.default_m if name == "default" else candidates.get(name)
        if value is not None and _usable(float(value)):
            return ResolvedHeight(
                min(max(float(value), lo), hi), name, cfg.data_kinds[name], cfg.licences[name]
            )
    raise AssertionError("unreachable: priority ends with default")
