"""Drop personal fields (names, phones, e-mails) before anything is stored.

The patterns live in config/ingest.yaml (privacy.drop_field_patterns).
"""
from __future__ import annotations

import copy
import re
from typing import Any, Iterable, Sequence

FeatureCollection = dict[str, Any]


def is_personal_field(name: str, patterns: Sequence[str]) -> bool:
    lowered = name.lower()
    return any(re.search(pattern, lowered) for pattern in patterns)


def personal_columns(columns: Iterable[str], patterns: Sequence[str],
                     extra_fields: Iterable[str] = ()) -> list[str]:
    """Names among ``columns`` to drop: pattern matches plus the explicitly named ones."""
    extra = {field.lower() for field in extra_fields}
    return sorted(c for c in columns if c.lower() in extra or is_personal_field(c, patterns))


def strip_personal_fields(collection: FeatureCollection, patterns: Sequence[str],
                          extra_fields: Iterable[str] = ()) -> tuple[FeatureCollection, list[str]]:
    """Return a cleaned copy of a GeoJSON FeatureCollection and the sorted dropped field names."""
    extra = list(extra_fields)
    cleaned = copy.deepcopy(collection)
    dropped: set[str] = set()
    for feature in cleaned.get("features", []):
        properties: dict[str, Any] = feature.get("properties") or {}
        remove = personal_columns(properties, patterns, extra)
        dropped.update(remove)
        feature["properties"] = {k: v for k, v in properties.items() if k not in remove}
    return cleaned, sorted(dropped)
