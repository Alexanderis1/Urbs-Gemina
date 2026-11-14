"""Regione Lazio Civil Protection gauges: daily rain and daily min/max temperature. Real, open (CC BY 4.0).

Source: dati.lazio.it datasets ``serie-storica-dato-pluviometrico`` and
``serie-storica-dato-termometrico`` (Agenzia Regionale di Protezione Civile, monthly CSV files
from September 2018). The files name stations but give no coordinates, and the official station
register on the portal is broken, so positions come from the Roma Capitale Civil Protection plan
(Fascicolo 1, Dec 2018, Tab. 8 "Lista dei sistemi di monitoraggio"), saved in
``seed_data/lazio_gauges_rome.csv``. Files are published months late, so these are history
for checking models, not a live feed.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Iterator

SEED = Path(__file__).parent / "seed_data" / "lazio_gauges_rome.csv"
CKAN = "https://dati.lazio.it/api/3/action/package_show?id="
DATASETS = {"rain": "serie-storica-dato-pluviometrico", "temperature": "serie-storica-dato-termometrico"}
LICENCE = "CC BY 4.0, Regione Lazio - Agenzia Regionale di Protezione Civile"


@dataclass(frozen=True)
class Gauge:
    name: str
    lon: float
    lat: float
    rain: bool
    temperature: bool


@dataclass(frozen=True)
class DailyRain:
    station: str
    day: date
    mm: float


@dataclass(frozen=True)
class DailyTemperature:
    station: str
    day: date
    t_min: float | None
    t_max: float | None


def norm(name: str) -> str:
    """Station names differ in accents, dots, spaces and case between files: compare a plain key."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "", plain)


def load_gauges(path: Path = SEED) -> dict[str, Gauge]:
    out: dict[str, Gauge] = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[norm(row["name"])] = Gauge(row["name"], float(row["lon"]), float(row["lat"]),
                                           row["rain"] == "1", row["temperature"] == "1")
    return out


def _number(text: str) -> float | None:
    text = text.strip().replace(",", ".")
    if not text or text in {"-", "ND", "nd", "n.d."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _day(text: str) -> date | None:
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", text)
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def _rows(text: str) -> Iterator[list[str]]:
    reader = csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=";")
    next(reader, None)  # header
    for row in reader:
        if len(row) >= 3:
            yield row


def parse_rain(text: str) -> Iterator[DailyRain]:
    for row in _rows(text):
        day, mm = _day(row[1]), _number(row[2])
        if day is not None and mm is not None and 0.0 <= mm < 1000.0:
            yield DailyRain(row[0].strip(), day, mm)


def parse_temperature(text: str) -> Iterator[DailyTemperature]:
    for row in _rows(text):
        day = _day(row[1])
        t_min = _number(row[2])
        t_max = _number(row[3]) if len(row) > 3 else None
        if t_min is not None and not -30.0 < t_min < 50.0:
            t_min = None
        if t_max is not None and not -30.0 < t_max < 50.0:
            t_max = None
        if day is not None and (t_min is not None or t_max is not None):
            yield DailyTemperature(row[0].strip(), day, t_min, t_max)


def in_rome(records: Iterable[DailyRain | DailyTemperature], gauges: dict[str, Gauge]) -> list[DailyRain | DailyTemperature]:
    return [r for r in records if norm(r.station) in gauges]
