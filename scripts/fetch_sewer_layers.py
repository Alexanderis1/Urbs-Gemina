"""Sewer layers for the rain flood scenario (WS6), written to the shared processed folder.

* ``sewer_outfalls.geojson``: ACEA ATO2 outfall points on the Tiber basin (SIITevere open data portal,
  Città Metropolitana di Roma, CC BY 4.0). Kept fields: id, name, comune, receiving water, function.
  The portal is not reachable from the cloud sandbox; run this where it is (e.g. a Modal function).

Usage: python scripts/fetch_sewer_layers.py [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any, Mapping

OUTFALLS_URL = ("https://dati-siitevere.cittametropolitanaroma.it/dataset/75a84f9f-eb83-4c3c-9ead-e9d7db847f20/"
                "resource/297997a0-e8e9-48e4-bce1-0a2952535ecb/download/punti_scarico_tevere.geojson")
DEFAULT_OUT = Path("/mnt/project-files/data/processed")
FIELDS = {"IDGIS": "id", "DENOM": "name", "LOCALITA": "comune", "D_CORPO_RI": "receiving", "FUNZIONE": "function"}


def outfalls_geojson(raw: Mapping[str, Any]) -> dict[str, Any]:
    """WGS84 points (from the X_GEO / Y_GEO fields) with the kept properties only."""
    features = []
    for f in raw.get("features", []):
        p = f.get("properties") or {}
        if p.get("X_GEO") is None or p.get("Y_GEO") is None:
            continue
        features.append({"type": "Feature",
                         "geometry": {"type": "Point", "coordinates": [float(p["X_GEO"]), float(p["Y_GEO"])]},
                         "properties": {new: p.get(old) for old, new in FIELDS.items()}})
    return {"type": "FeatureCollection", "features": features}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--from-file", type=Path, help="convert an already downloaded GeoJSON")
    args = parser.parse_args(argv)
    if args.from_file:
        raw = json.loads(args.from_file.read_text(encoding="utf-8"))
    else:
        with urllib.request.urlopen(OUTFALLS_URL, timeout=120) as resp:  # noqa: S310 - fixed public URL
            raw = json.loads(resp.read().decode("utf-8"))
    out = args.out / "sewer_outfalls.geojson"
    out.write_text(json.dumps(outfalls_geojson(raw), ensure_ascii=False), encoding="utf-8")
    print(f"sewer_outfalls: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
