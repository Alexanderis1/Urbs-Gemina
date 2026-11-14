"""Offline street lookup: find street names in a notice's text and place it on the map.

The table (data/processed/street_names.csv) is built from the OSM extract by
scripts/build_street_index.py. No outside geocoder sees the text.
"""
from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PREFIXES = ("via", "viale", "piazza", "piazzale", "largo", "lungotevere", "circonvallazione", "corso", "vicolo",
            "ponte", "galleria", "piazzetta", "salita", "clivo", "borgo", "vicolo", "lungotevere", "rampa", "scalinata")
_LINKS = {"di", "del", "della", "dei", "delle", "degli", "dello", "d", "de", "da", "san", "santa", "santo", "s"}
_STOP = {"e", "nel", "nella", "tratto", "compreso", "tra", "fra", "all", "altezza", "la", "il", "linea", "da", "fino",
         "a", "in", "per", "dalle", "ore", "direzione", "verso", "dopo", "prima", "con", "angolo"}


def normalise(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", folded).split())


def streets_in_text(text: str) -> list[str]:
    """Normalised street names in reading order: a prefix word followed by the name's words."""
    found: list[str] = []
    for chunk in re.split(r"[,.:;()\n]", text):
        found += _streets_in_chunk(normalise(chunk).split())
    return found


def _streets_in_chunk(words: list[str]) -> list[str]:
    found: list[str] = []
    i = 0
    while i < len(words):
        if words[i] in PREFIXES:
            name = [words[i]]
            j = i + 1
            while j < len(words) and len(name) < 7:
                w = words[j]
                if w in _STOP and not (w in _LINKS and j + 1 < len(words) and words[j + 1] not in _STOP):
                    break
                if w in PREFIXES:
                    break
                name.append(w)
                j += 1
            if len(name) > 1:
                found.append(" ".join(name))
            i = j
        else:
            i += 1
    return found


@dataclass(frozen=True)
class StreetIndex:
    table: dict[str, tuple[str, float, float]]
    #: (prefix, last word) -> keys, for short forms ("via Gregorovius" = "via Ferdinando Gregorovius")
    short: dict[tuple[str, str], list[str]]

    @classmethod
    def load(cls, path: Path) -> "StreetIndex":
        table: dict[str, tuple[str, float, float]] = {}
        short: dict[tuple[str, str], list[str]] = {}
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                table[row["key"]] = (row["name"], float(row["lon"]), float(row["lat"]))
                words = row["key"].split()
                if len(words) > 2:
                    short.setdefault((words[0], words[-1]), []).append(row["key"])
        return cls(table, short)

    def _hit(self, key: str) -> tuple[str, float, float] | None:
        hit = self.table.get(key)
        if hit is not None:
            return hit
        words = key.split()
        keys = self.short.get((words[0], words[-1]), []) if len(words) == 2 else []
        return self.table[keys[0]] if len(keys) == 1 else None

    def locate(self, text: str) -> dict[str, Any] | None:
        """The first street of the text found in the table (shortening the name word by word)."""
        for candidate in streets_in_text(text):
            words = candidate.split()
            while len(words) > 1:
                hit = self._hit(" ".join(words))
                if hit is not None:
                    return {"name": hit[0], "lon": hit[1], "lat": hit[2]}
                words = words[:-1]
        return None
