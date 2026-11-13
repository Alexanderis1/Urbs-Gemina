"""Deterministic entity matching: one record per real facility.

Rule (thresholds in config/sports.yaml, ``matching``):
  - two located records are the same facility when their names are similar
    (>= name_similarity_min) and they are within max_distance_m, or when they
    are of the same kind and within same_kind_distance_m;
  - records from the same source are never merged (each official record is
    its own facility, even when two sit side by side);
  - pairs are linked greedily, best score first, so the result does not depend
    on input order;
  - a record without coordinates joins the best located facility of the same
    municipio with a near-exact name, otherwise it stays alone and is reported.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Iterable

from twin.modules.sports.config import SportsConfig
from twin.modules.sports.disciplines import fold
from twin.modules.sports.geo import GridIndex
from twin.modules.sports.model import (
    NOT_KNOWN, SOURCE_STATUS, STANDARD_FIELDS, Candidate, Facility, FieldValue,
)

_PUNCT = str.maketrans({c: " " for c in ".,;:'\"()[]/\\-_&+!?#*"})


def normalize_name(name: str, stopwords: Iterable[str]) -> tuple[str, ...]:
    stop = set(stopwords)
    tokens = fold(name).translate(_PUNCT).split()
    return tuple(t for t in tokens if t not in stop)


def name_similarity(a: str, b: str, stopwords: Iterable[str]) -> float:
    """1.0 for the same name once generic words are removed; 0.0 when one is empty."""
    stop = frozenset(stopwords)
    ta, tb = normalize_name(a, stop), normalize_name(b, stop)
    if not ta or not tb:
        return 0.0
    sa, sb = set(ta), set(tb)
    jaccard = len(sa & sb) / len(sa | sb)
    ratio = SequenceMatcher(None, " ".join(sorted(sa)), " ".join(sorted(sb))).ratio()
    return round(max(jaccard, ratio), 4)


@dataclass(frozen=True)
class Link:
    a: str
    b: str
    reason: str
    distance_m: float | None
    similarity: float

    def to_dict(self) -> dict[str, Any]:
        return {"a": self.a, "b": self.b, "reason": self.reason, "distance_m": self.distance_m,
                "similarity": self.similarity}


@dataclass
class MatchReport:
    links: list[Link] = field(default_factory=list)
    unlocated: list[str] = field(default_factory=list)
    candidates: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"candidates": self.candidates, "links": [lk.to_dict() for lk in self.links],
                "unlocated": self.unlocated}


class _Clusters:
    def __init__(self, cands: list[Candidate]) -> None:
        self.parent = list(range(len(cands)))
        self.sources: list[set[str]] = [{c.source} for c in cands]

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def try_union(self, i: int, j: int) -> bool:
        ri, rj = self.find(i), self.find(j)
        if ri == rj or self.sources[ri] & self.sources[rj]:
            return False
        if rj < ri:
            ri, rj = rj, ri
        self.parent[rj] = ri
        self.sources[ri] |= self.sources[rj]
        return True


def _sort_key(c: Candidate) -> tuple[str, str]:
    return c.source, c.record_id


def build_facilities(candidates: list[Candidate], config: SportsConfig) -> tuple[list[Facility], MatchReport]:
    cfg = config.matching
    cands = sorted(candidates, key=_sort_key)
    report = MatchReport(candidates=len(cands))
    clusters = _Clusters(cands)

    index: GridIndex[int] = GridIndex(cfg.max_distance_m)
    for i, c in enumerate(cands):
        if c.lon is not None and c.lat is not None:
            index.add(c.lon, c.lat, i)

    pairs: list[tuple[float, float, str, str, int, int, str]] = []
    for i, c in enumerate(cands):
        if c.lon is None or c.lat is None:
            continue
        for d, j in index.near(c.lon, c.lat, cfg.max_distance_m):
            if j <= i or cands[j].source == c.source:
                continue
            sim = name_similarity(c.name, cands[j].name, cfg.name_stopwords)
            if sim >= cfg.name_similarity_min:
                reason = "similar_name_nearby"
            elif d <= cfg.same_kind_distance_m and c.kind == cands[j].kind:
                reason = "same_kind_very_close"
            else:
                continue
            pairs.append((-sim, round(d, 3), c.key, cands[j].key, i, j, reason))
    pairs.sort()
    for neg_sim, d, ka, kb, i, j, reason in pairs:
        if clusters.try_union(i, j):
            report.links.append(Link(ka, kb, reason, round(d, 1), -neg_sim))

    # Records without coordinates: near-exact name in the same municipio.
    for i, c in enumerate(cands):
        if c.located:
            continue
        best: tuple[float, int] | None = None
        for j, other in enumerate(cands):
            if not other.located or other.municipio is None or other.municipio != c.municipio:
                continue
            sim = name_similarity(c.name, other.name, cfg.name_stopwords)
            if sim >= cfg.unlocated_name_similarity_min and (best is None or sim > best[0]):
                best = (sim, j)
        if best is not None and clusters.try_union(best[1], i):
            report.links.append(Link(cands[best[1]].key, c.key, "same_name_same_municipio", None, best[0]))
        else:
            report.unlocated.append(c.key)

    groups: dict[int, list[Candidate]] = {}
    for i, c in enumerate(cands):
        groups.setdefault(clusters.find(i), []).append(c)
    facilities = [merge_cluster(members, config) for members in groups.values()]
    facilities.sort(key=lambda f: f.facility_id)
    return facilities, report


def facility_id_for(anchor: Candidate) -> str:
    return "sf_" + hashlib.sha256(anchor.key.encode("utf-8")).hexdigest()[:12]


def _field(value: Any, c: Candidate, config: SportsConfig) -> FieldValue:
    status = SOURCE_STATUS.get(c.source, "web_unverified")
    label = config.web.label_unverified if status == "web_unverified" else None
    return FieldValue(value=value, status=status, provenance=(c.provenance(),), label=label)


def merge_cluster(members: list[Candidate], config: SportsConfig) -> Facility:
    """Most trusted source wins each field; disciplines are the union, each with its sources."""
    ranked = sorted(members, key=lambda c: (config.priority(c.source), c.source, c.record_id))
    anchor = ranked[0]
    located = next((c for c in ranked if c.located), None)

    fields: dict[str, FieldValue] = {name: NOT_KNOWN for name in STANDARD_FIELDS}
    extra: dict[str, FieldValue] = {}
    for c in reversed(ranked):  # least trusted first, so trusted sources overwrite
        values: dict[str, Any] = {"name": c.name or None, "kind": c.kind, "address": c.address,
                                  "municipio": c.municipio}
        for key, value in c.attributes.items():
            if key in STANDARD_FIELDS:
                values[key] = value
            elif key == "website":
                values["contact"] = {"website": value}
            else:
                extra[key] = _field(value, c, config)
        for key, value in values.items():
            if value not in (None, "", {}):
                fields[key] = _field(value, c, config)

    disciplines: dict[str, FieldValue] = {}
    for d in sorted({d for c in ranked for d in c.disciplines}):
        sources = [c for c in ranked if d in c.disciplines]
        best = sources[0]
        disciplines[d] = FieldValue(
            value=True, status=SOURCE_STATUS.get(best.source, "web_unverified"),
            provenance=tuple(c.provenance() for c in sources),
            label=config.web.label_unverified if SOURCE_STATUS.get(best.source) == "web_unverified" else None,
        )
    return Facility(
        facility_id=facility_id_for(anchor),
        lon=located.lon if located else None,
        lat=located.lat if located else None,
        fields=fields, disciplines=disciplines,
        members=tuple(c.key for c in ranked),
        synthetic=any(c.synthetic for c in members),
        extra=extra,
    )

