"""Find WS1's cleaned GeoJSON layers and turn them into inputs (boundaries, census)."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from twin.scenarios import config
from twin.scenarios.area import AreaNotAvailable


def search_dirs() -> list[Path]:
    dirs = config.value(config.load("scenarios.yaml")["layers"], "search_dirs")
    return [Path(d) if Path(d).is_absolute() else config.ROOT / d for d in dirs]


def find(file_name: str) -> Path | None:
    for directory in search_dirs():
        path = directory / file_name
        if path.exists():
            return path
    return None


@lru_cache(maxsize=16)
def _read(path: str, mtime: float, size: int) -> dict[str, Any]:
    loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} is not a GeoJSON FeatureCollection")
    return loaded


@lru_cache(maxsize=16)
def _hash(path: str, mtime: float, size: int) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return _read(str(path), stat.st_mtime, stat.st_size)


def file_hash(path: Path) -> str:
    stat = path.stat()
    return _hash(str(path), stat.st_mtime, stat.st_size)


def default_area_lookup(area_id: str) -> Mapping[str, Any]:
    """Boundary of "municipio:N" or "zone:CODE" from WS1's layers."""
    kind, _, key = area_id.partition(":")
    section = config.load("scenarios.yaml")["layers"].get({"municipio": "municipi", "zone": "zones"}.get(kind, ""))
    if section is None:
        raise AreaNotAvailable(f"No boundary layer for area '{area_id}'")
    path = find(str(section["file"]))
    if path is None:
        raise AreaNotAvailable(f"Boundary layer {section['file']} for area '{area_id}' is not available yet")
    prop = str(section["id_property"])
    for feature in read(path).get("features", []):
        if str((feature.get("properties") or {}).get(prop, "")).upper() == key.upper() and feature.get("geometry"):
            return dict(feature["geometry"])
    raise ValueError(f"Area '{area_id}' does not exist in {section['file']}")


def snapshots(names: list[str]) -> dict[str, str]:
    """Hashes of the layer files a run reads, for the run id."""
    out: dict[str, str] = {}
    for name in names:
        path = find(name)
        out[f"layer/{name}"] = file_hash(path) if path is not None else "missing"
    return out
