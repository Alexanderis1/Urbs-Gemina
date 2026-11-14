"""Build data/processed/street_names.csv: one point per named street of Rome, from the OSM extract.

Run from the project root:
    python scripts/build_street_index.py <lazio-latest.osm.pbf>

Used to place transport notices that name a street ("Chiusura di via Cavour") on the map, offline
(no outside geocoder sees the text). For each street name the point is the middle of its longest
mapped piece inside Rome's bounding box: homonyms in far-apart localities keep the main one (C=60).
Licence of the output: ODbL (OpenStreetMap contributors).
"""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twin.providers.base import ROME_BBOX  # noqa: E402
from twin.tools.street_names import normalise  # noqa: E402

OUT = ROOT / "data" / "processed" / "street_names.csv"


def main(pbf: str) -> int:
    import osmium

    best: dict[str, tuple[float, str, float, float, float]] = {}   # key -> (piece length, name, lon, lat, total)

    class Streets(osmium.SimpleHandler):
        def way(self, w: object) -> None:
            tags = w.tags  # type: ignore[attr-defined]
            name = tags.get("name")
            if not name or "highway" not in tags:
                return
            try:
                pts = [(n.lon, n.lat) for n in w.nodes]  # type: ignore[attr-defined]
            except osmium.InvalidLocationError:
                return
            mid = pts[len(pts) // 2]
            if not (ROME_BBOX[0] <= mid[0] <= ROME_BBOX[2] and ROME_BBOX[1] <= mid[1] <= ROME_BBOX[3]):
                return
            length = sum(math.hypot((b[0] - a[0]) * 83_000, (b[1] - a[1]) * 111_000) for a, b in zip(pts, pts[1:]))
            key = normalise(name)
            old = best.get(key)
            total = (old[4] if old else 0.0) + length
            if old is None or length > old[0]:
                best[key] = (length, name, mid[0], mid[1], total)
            else:
                best[key] = (*old[:4], total)

    Streets().apply_file(pbf, locations=True, idx="flex_mem")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(["key", "name", "lon", "lat", "length_m"])
        for key, (_, name, lon, lat, total) in sorted(best.items()):
            out.writerow([key, name, round(lon, 6), round(lat, 6), round(total)])
    print(f"{len(best)} street names -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
