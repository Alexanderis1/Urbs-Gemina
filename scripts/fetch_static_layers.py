"""Download the static context layers of Rome and record them in the manifest.

Run from the project root:  python scripts/fetch_static_layers.py [layer_key ...]

Each layer is saved as GeoJSON (WGS84) under data/raw/, personal contact
fields are dropped, and data/manifest.json gets the SHA-256, feature count
and fetch time. A layer that fails is recorded as "not_available" and the
script carries on (gate A of the build order).
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twin.providers.open.roma_wfs import fetch_layer  # noqa: E402

#: key -> WFS typeName on Roma Capitale's GeoServer
LAYERS: dict[str, str] = {
    "municipi": "DIPPC:210_RomaCapitale_Municipi",
    "urban_zones": "DIPDIT:ZoneUrbanistiche",
    "rete_ecologica_poly": "DIPAU:ReteEcologicaPoligono",
    "rete_ecologica_line": "DIPAU:ReteEcologicaLinea",
    "cpq_morfologie": "DIPAU:CartaPerLaQualita_Morfologie_Poligono",
    "cpq_preesistenze": "DIPAU:CartaPerLaQualita_Preesistenze_Poligono",
    "cpq_spazi_aperti": "DIPAU:CartaPerLaQualita_Elementi_Spazi_Aperti_Poligono",
    "cpq_edilizia_speciale": "DIPAU:CartaPerLaQualita_Edifici_Edilizia_Speciale",
    "unesco": "SOVR:SitoUnescoPoly",
    "unesco_buffer": "SOVR:buffer_zone",
    "protected_areas": "DIPPC:235_AreeProtette",
    "schools_state": "DIPSCU:mv_portale_rete_statale",
    "nidi": "DIPSCU:mv_portale_nidi_capitolini",
    "infanzia": "DIPSCU:mv_portale_infanzia_capitolina",
    "hospitals": "DIPAMB:Ospedali",
    "sports_municipal": "DIPPC:243_ServiziSportivi",
}

RAW = ROOT / "data" / "raw"
MANIFEST = ROOT / "data" / "manifest.json"


def main(keys: list[str]) -> int:
    unknown = [key for key in keys if key not in LAYERS]
    if unknown:
        print(f"Unknown layer keys: {unknown}. Known: {sorted(LAYERS)}")
        return 2
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    snapshots: dict[str, dict[str, object]] = manifest.setdefault("snapshots", {})
    failures = 0
    for key in keys or list(LAYERS):
        type_name = LAYERS[key]
        entry: dict[str, object] = {
            "source": "roma_geoserver",
            "type_name": type_name,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        try:
            collection = fetch_layer(type_name)
            payload = json.dumps(collection, ensure_ascii=False).encode("utf-8")
            path = RAW / f"{key}.geojson"
            path.write_bytes(payload)
            entry.update(
                status="ok",
                file=str(path.relative_to(ROOT)).replace("\\", "/"),
                features=len(collection.get("features", [])),
                sha256=hashlib.sha256(payload).hexdigest(),
            )
            print(f"ok   {key:24s} {entry['features']} features")
        except Exception as error:  # noqa: BLE001 - any failure marks the layer unavailable
            failures += 1
            entry.update(status="not_available", error=f"{type(error).__name__}: {error}")
            print(f"FAIL {key:24s} {entry['error']}")
        snapshots[key] = entry
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
