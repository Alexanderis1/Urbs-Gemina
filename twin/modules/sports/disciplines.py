"""Map free text and OSM tags to the canonical discipline ids of config/sports.yaml."""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Mapping

from twin.modules.sports.config import SportsConfig

#: OSM leisure=* values that imply a discipline on their own.
OSM_LEISURE_DISCIPLINE = {"swimming_pool": "swimming", "fitness_centre": "fitness", "ice_rink": "skating",
                          "golf_course": "golf", "horse_riding": "equestrian"}


def fold(text: str) -> str:
    """Lowercase, strip accents, collapse spaces."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.lower()).strip()


def disciplines_from_text(text: str | None, config: SportsConfig) -> set[str]:
    if not text:
        return set()
    folded = fold(text)
    return {d.id for d in config.disciplines.values() if any(fold(w) in folded for w in d.words)}


def discipline_id(value: str, config: SportsConfig) -> str | None:
    """Canonical id for one discipline word, or None if it is not in the vocabulary."""
    folded = fold(value).replace(" ", "_")
    if folded in config.disciplines:
        return folded
    exact = {d.id for d in config.disciplines.values() if fold(value) in (fold(w) for w in d.words)}
    if len(exact) == 1:
        return exact.pop()
    found = disciplines_from_text(value, config)
    return min(found) if len(found) == 1 else None


def disciplines_from_osm(tags: Mapping[str, str], config: SportsConfig) -> set[str]:
    out: set[str] = set()
    for value in (tags.get("sport") or "").split(";"):
        value = fold(value)
        if not value:
            continue
        for d in config.disciplines.values():
            if value in (fold(w).replace(" ", "_") for w in d.words) or value == d.id:
                out.add(d.id)
    leisure = tags.get("leisure", "")
    if leisure in OSM_LEISURE_DISCIPLINE:
        out.add(OSM_LEISURE_DISCIPLINE[leisure])
    return out


def known(ids: Iterable[str], config: SportsConfig) -> set[str]:
    return {i for i in ids if i in config.disciplines}
