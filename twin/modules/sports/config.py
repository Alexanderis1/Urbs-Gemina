"""Typed view of config/sports.yaml. All tunable numbers live in that file."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config" / "sports.yaml"


@dataclass(frozen=True)
class MatchingConfig:
    name_similarity_min: float
    max_distance_m: float
    same_kind_distance_m: float
    unlocated_name_similarity_min: float
    name_stopwords: frozenset[str]
    part_of_site_distance_m: float = 0.0
    part_kinds: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ReachConfig:
    walk_minutes: float
    walk_speed_kmh: float
    detour_factor: float


@dataclass(frozen=True)
class WebConfig:
    min_confidence: float
    label_unverified: str
    accessibility_keywords: tuple[str, ...]
    org_email_local_parts: frozenset[str]
    drop_mobile_numbers: bool
    org_name_markers: tuple[str, ...]


@dataclass(frozen=True)
class Discipline:
    id: str
    it: str
    words: tuple[str, ...]


@dataclass(frozen=True)
class SportsConfig:
    pilot_municipio: str
    matching: MatchingConfig
    source_priority: tuple[str, ...]
    reach: ReachConfig
    transit_stop_radius_m: float
    web: WebConfig
    disciplines: dict[str, Discipline]
    desert_min_uncovered_share: float
    desert_min_residents: float
    school_gym_default_disciplines: tuple[str, ...]
    source_fields: dict[str, tuple[str, ...]]
    exclude_osm_unnamed_pools_without_access: bool = True

    def priority(self, source: str) -> int:
        """Lower is more trusted. Unknown sources rank last."""
        try:
            return self.source_priority.index(source)
        except ValueError:
            return len(self.source_priority)


def _strs(values: Any) -> tuple[str, ...]:
    return tuple(str(v) for v in (values or []))


def load_config(path: Path = DEFAULT_PATH) -> SportsConfig:
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    m = raw["matching"]
    r = raw["reach"]
    w = raw["web"]
    d = raw["deserts"]
    disciplines = {
        str(key): Discipline(id=str(key), it=str(val.get("it", key)), words=_strs(val.get("words")))
        for key, val in raw["disciplines"].items()
    }
    defaults = _strs(raw.get("school_gym_default_disciplines"))
    unknown = [x for x in defaults if x not in disciplines]
    if unknown:
        raise ValueError(f"school_gym_default_disciplines has unknown ids: {unknown}")
    fields = raw.get("source_fields", {}).get("common", {})
    return SportsConfig(
        pilot_municipio=str(raw.get("pilot_municipio", "")),
        matching=MatchingConfig(
            name_similarity_min=float(m["name_similarity_min"]),
            max_distance_m=float(m["max_distance_m"]),
            same_kind_distance_m=float(m["same_kind_distance_m"]),
            unlocated_name_similarity_min=float(m["unlocated_name_similarity_min"]),
            name_stopwords=frozenset(_strs(m.get("name_stopwords"))),
            part_of_site_distance_m=float(m.get("part_of_site_distance_m", 0.0)),
            part_kinds=frozenset(_strs(m.get("part_kinds"))),
        ),
        source_priority=_strs(raw["source_priority"]),
        reach=ReachConfig(float(r["walk_minutes"]), float(r["walk_speed_kmh"]), float(r["detour_factor"])),
        transit_stop_radius_m=float(raw["transit"]["stop_radius_m"]),
        web=WebConfig(
            min_confidence=float(w["min_confidence"]),
            label_unverified=str(w["label_unverified"]),
            accessibility_keywords=_strs(w["accessibility_keywords"]),
            org_email_local_parts=frozenset(_strs(w["org_email_local_parts"])),
            drop_mobile_numbers=bool(w["drop_mobile_numbers"]),
            org_name_markers=_strs(w["org_name_markers"]),
        ),
        disciplines=disciplines,
        desert_min_uncovered_share=float(d["min_uncovered_share"]),
        desert_min_residents=float(d["min_residents"]),
        school_gym_default_disciplines=defaults,
        source_fields={str(k): _strs(v) for k, v in fields.items()},
        exclude_osm_unnamed_pools_without_access=bool(
            (raw.get("coverage") or {}).get("exclude_osm_unnamed_pools_without_access", True)),
    )
