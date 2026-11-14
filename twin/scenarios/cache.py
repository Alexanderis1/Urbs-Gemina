"""Result cache keyed by run id: precomputed runs make the demo instant."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def get(cache_dir: Path, run_id: str) -> dict[str, Any] | None:
    path = cache_dir / f"{run_id}.json"
    if not path.exists():
        return None
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else None


def put(cache_dir: Path, run_id: str, envelope: dict[str, Any]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache_dir / f"{run_id}.json.tmp"
    tmp.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
    tmp.replace(cache_dir / f"{run_id}.json")
