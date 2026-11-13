"""Static context layers as downloaded by WS1 (``data/raw/<key>.geojson``).

The store loads a layer the first time it is asked for, keeps its SHA-256
(from the manifest when recorded there, otherwise computed from the file) and
a bounding box per feature so spatial queries can skip far-away features.
A missing layer is ``None``: tools report it as "not available".
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from twin.providers.base import BBox
from twin.tools.envelope import Source, utc_now

Feature = dict[str, Any]
FeatureCollection = dict[str, Any]


def iter_positions(coords: Any) -> Iterator[Sequence[float]]:
    """Every [lon, lat] position in a GeoJSON coordinates array, at any depth."""
    if isinstance(coords, (list, tuple)) and coords and isinstance(coords[0], (int, float)):
        yield coords
        return
    for item in coords or []:
        yield from iter_positions(item)


def geometry_bbox(geometry: Mapping[str, Any]) -> BBox | None:
    lons: list[float] = []
    lats: list[float] = []
    for position in iter_positions(geometry.get("coordinates")):
        lons.append(float(position[0]))
        lats.append(float(position[1]))
    if not lons:
        return None
    return min(lons), min(lats), max(lons), max(lats)


def bboxes_intersect(a: BBox, b: BBox) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


@dataclass
class LayerSnapshot:
    key: str
    features: list[Feature]
    bboxes: list[BBox | None]
    sha256: str
    retrieved_at: str
    source_id: str
    url: str | None = None

    @classmethod
    def from_collection(cls, key: str, collection: Mapping[str, Any], sha256: str | None = None,
                        retrieved_at: str | None = None, source_id: str | None = None,
                        url: str | None = None) -> "LayerSnapshot":
        features = [f for f in collection.get("features", []) if f.get("geometry")]
        digest = sha256 or hashlib.sha256(
            json.dumps(collection, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        return cls(
            key=key,
            features=features,
            bboxes=[geometry_bbox(f["geometry"]) for f in features],
            sha256=digest,
            retrieved_at=retrieved_at or utc_now(),
            source_id=source_id or key,
            url=url,
        )

    def near(self, bbox: BBox) -> list[Feature]:
        """Features whose bounding box touches ``bbox``."""
        return [f for f, b in zip(self.features, self.bboxes) if b is not None and bboxes_intersect(b, bbox)]

    def source(self) -> Source:
        return Source(id=f"layer:{self.key}", retrieved_at=self.retrieved_at, url=self.url, sha256=self.sha256)


@dataclass
class LayerStore:
    raw_dir: Path
    manifest_path: Path | None = None
    #: Searched after ``raw_dir``: cleaned layers WS1 writes to ``data/processed`` (e.g. urban_zones).
    processed_dir: Path | None = None
    _cache: dict[str, LayerSnapshot | None] = field(default_factory=dict)

    def add(self, key: str, collection: Mapping[str, Any], **meta: Any) -> LayerSnapshot:
        """Put a layer in memory (tests, or layers produced at runtime)."""
        snapshot = LayerSnapshot.from_collection(key, collection, **meta)
        self._cache[key] = snapshot
        return snapshot

    def get(self, key: str) -> LayerSnapshot | None:
        if key not in self._cache:
            self._cache[key] = self._load(key)
        return self._cache[key]

    def _manifest(self) -> dict[str, Any]:
        if self.manifest_path is None or not self.manifest_path.exists():
            return {}
        data: dict[str, Any] = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return data

    def _load(self, key: str) -> LayerSnapshot | None:
        candidates = [self.raw_dir / f"{key}.geojson"]
        if self.processed_dir is not None:
            candidates.append(self.processed_dir / f"{key}.geojson")
        path = next((c for c in candidates if c.exists()), None)
        if path is None:
            return None
        payload = path.read_bytes()
        manifest = self._manifest()
        entry: dict[str, Any] = manifest.get("snapshots", {}).get(key, {})
        source_meta: dict[str, Any] = manifest.get("sources", {}).get(entry.get("source", ""), {})
        return LayerSnapshot.from_collection(
            key,
            json.loads(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            retrieved_at=str(entry.get("fetched_at") or utc_now()),
            source_id=str(entry.get("source") or key),
            url=source_meta.get("endpoint"),
        )


def first_property(properties: Mapping[str, Any], candidates: Sequence[str]) -> Any:
    for name in candidates:
        found = properties.get(name)
        if found not in (None, ""):
            return found
    return None
