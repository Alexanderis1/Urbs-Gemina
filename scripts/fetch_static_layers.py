"""Download the static context layers of Rome and record them in the manifest.

Run from the project root:  python scripts/fetch_static_layers.py [layer_key ...]

The layer list lives in config/ingest.yaml. Each layer is downloaded in WGS84,
personal contact fields are dropped, and the result is written as GeoParquet
(plus GeoJSON) under data/processed/. data/manifest.json gets the SHA-256 of the
download and of each file, the feature count, the real/estimated/simulated label
and the fetch time. A layer that fails is recorded as "not_available" and the
script carries on (gate A of the build order).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twin.ingest.catalog import load_catalog  # noqa: E402
from twin.ingest.http import urllib_fetch  # noqa: E402
from twin.ingest.static import run  # noqa: E402


def main(keys: list[str]) -> int:
    catalog = load_catalog(ROOT / "config" / "ingest.yaml")
    return run(keys, catalog, urllib_fetch, ROOT / "data" / "processed", ROOT / "data" / "manifest.json", root=ROOT)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
