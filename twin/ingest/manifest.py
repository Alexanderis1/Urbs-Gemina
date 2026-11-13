"""Write snapshot records into data/manifest.json without touching anything else."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def record_snapshots(manifest_path: Path, entries: Mapping[str, Mapping[str, Any]]) -> None:
    """Set ``snapshots[key]`` for each entry. Sources and other snapshots stay as they are.

    The file is re-read right before writing because other streams also append to it.
    """
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshots: dict[str, Any] = manifest.setdefault("snapshots", {})
    for key, entry in entries.items():
        snapshots[key] = dict(entry)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
