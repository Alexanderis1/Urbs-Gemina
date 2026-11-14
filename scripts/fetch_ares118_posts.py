"""Locate the ARES 118 ambulance posts inside Rome and write them as a point layer.

The posts and their addresses come from ARES 118's public list of posts ("Elenco postazioni", Allegato 1a,
https://ares118.it/media/foto-articoli/2664/varie/elenco_postazioni.pdf). Each address is placed with
Roma Capitale's street-number service (GeoromaCiviciLocator WFS): the official house number closest
to the listed one on that street. Posts outside the city limits are not covered by that service and
are left out. No personal data: these are public service buildings.

Usage: python scripts/fetch_ares118_posts.py [--out /mnt/project-files/data/processed/ares118_posts.geojson]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

WFS = ("https://geoportale.comune.roma.it/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature"
       "&typeNames=DIPCUL:GeoromaCiviciLocator&outputFormat=application/json"
       "&propertyName=TOPONIMO,NUMERO_CIVICO,MUNICIPIO,GEOMETRIA&count=2000&CQL_FILTER=")
SOURCE = "ARES 118, Elenco postazioni (Allegato 1a), ares118.it"

# (post name, macro-area, street pattern for the city's street list, house number) as listed by ARES 118
POSTS: list[tuple[str, str, str, int]] = [
    ("San Giovanni / Addolorata", "Roma Centro", "STEFANO ROTONDO", 5),
    ("Circonvallazione Appia", "Roma Centro", "CIRCONVALLAZIONE APPIA", 92),
    ("Treviso / Eastman", "Roma Centro", "VIA TREVISO", 46),
    ("Vittor Pisani", "Roma Centro", "VIA VITTOR PISANI", 19),
    ("Nuovo Regina Margherita", "Roma Centro", "VIA EMILIO MOROSINI", 30),
    ("CTO", "Roma Centro", "NEMESIO", 21),
    ("Montagnola", "Roma Centro", "VIA BENEDETTO CROCE", 50),
    ("San Camillo", "Roma Centro", "CIRCONVALLAZIONE GIANICOLENSE", 77),
    ("Ponte Galeria", "Roma Ovest", "VIA SENORBI", 4),
    ("Aurelia Hospital", "Roma Ovest", "VIA AURELIA", 860),
    ("Acilia", "Roma Sud", "VILLA DI CILONE", 4),
    ("Spinaceto", "Roma Sud", "VIA RAFFAELE AVERSA", 165),
    ("Sant'Eugenio", "Roma Sud", "VIA ACHILLE CAMPANILE", 67),
    ("Grassi (Ostia)", "Roma Sud", "VIA GIANCARLO PASSERONI", 28),
    ("Cinecitta", "Roma Est", "PIAZZA DI CINECITTA", 11),
    ("Pispole", "Roma Est", "VIA DELLE PISPOLE", 2),
    ("Tor Bella Monaca", "Roma Est", "VIA FERNANDO CONTI", 1),
    ("Romanina", "Roma Est", "VIA DEL PONTE DELLE SETTE MIGLIA", 97),
    ("Prenestino", "Roma Est", "PIAZZALE PRENESTINO", 52),
    ("Monte Rocchetta (Marcigliana)", "Roma Nord", "VIA MONTE ROCCHETTA", 1),
    ("Settecamini", "Roma Nord", "VIA RUBELLIA", 4),
    ("Lunghezza", "Roma Nord", "VIA DEL CASALONE", 26),
    ("La Rustica", "Roma Nord", "VIA ACHILLE VERTUNNI", 124),
    ("Cassia", "Roma Nord", "VIA TOMBA DI NERONE", 9),
    ("Cesano", "Roma Nord", "VIA ORREA", 25),
    ("Briziarelli", "Roma Nord", "VIA PIO BRIZIARELLI", 19),
]


def locate(pattern: str, number: int) -> tuple[float, float, str, int] | None:
    """(lon, lat, street, number) of the official house number nearest the listed one."""
    cql = "TOPONIMO LIKE '%" + pattern.replace("'", "''") + "%'"
    with urllib.request.urlopen(WFS + urllib.parse.quote(cql), timeout=300) as resp:  # noqa: S310 - public WFS
        feats: list[dict[str, Any]] = json.load(resp)["features"]
    feats = [f for f in feats if f.get("geometry") and f["properties"].get("NUMERO_CIVICO") is not None]
    if not feats:
        return None
    # shortest street name first (the exact street rather than a longer one that contains it), then number
    best = min(feats, key=lambda f: (len(f["properties"]["TOPONIMO"]), abs(int(f["properties"]["NUMERO_CIVICO"]) - number)))
    lon, lat = best["geometry"]["coordinates"][:2]
    return float(lon), float(lat), str(best["properties"]["TOPONIMO"]), int(best["properties"]["NUMERO_CIVICO"])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    p.add_argument("--out", type=Path, default=Path("/mnt/project-files/data/processed/ares118_posts.geojson"))
    args = p.parse_args(argv)
    feats: list[dict[str, Any]] = []
    for name, macro, pattern, number in POSTS:
        hit = locate(pattern, number)
        if hit is None:
            print(f"not found: {name} ({pattern} {number})", file=sys.stderr)
            continue
        lon, lat, street, civic = hit
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                      "properties": {"name": name, "macroarea": macro, "address": f"{street} {civic}",
                                     "listed_number": number, "source": SOURCE, "kind": "real"}})
        print(f"{name:28s} {street} {civic} ({lon:.5f}, {lat:.5f})")
    args.out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"{len(feats)} of {len(POSTS)} posts written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
