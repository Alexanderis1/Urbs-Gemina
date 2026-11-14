"""Crowds view: real activity signals side by side, and where they agree.

No single open source counts people in Rome. Each signal below sees a different
slice, so they are shown next to each other with their own margins instead of
being merged into one invented number:

- ``wifi_sessions``: people on the City's free Wi-Fi per hotspot and hour (a lower bound, a day late);
- ``activity``: parked shared e-scooters per cell (a weak proxy);
- ``transit_supply``: buses and trams the timetable places in the cell (planned supply);
- ``residents``: ISTAT 2021 census residents per cell (static, for context, not in the vote).

A cell is flagged ``busy`` when at least ``min_agree`` signals are above their
own city-wide percentile. Agreement of independent signals is the information
extracted here; settings live in the ``crowds`` block of config/beliefs.yaml.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml

from twin.beliefs.api import build_layer, snapshot_hash
from twin.beliefs.config import CONFIG_DIR, load_specs
from twin.beliefs.grid import cell_of
from twin.beliefs.layer import BeliefLayer
from twin.providers.base import Provider, ProviderNotConfigured

#: What each signal is, for the data_kinds label (real = measured, estimated = model/timetable).
SIGNAL_KINDS = {"wifi_sessions": "real", "activity": "real", "transit_supply": "estimated"}


def crowds_settings(config_dir: Path = CONFIG_DIR) -> dict[str, Any]:
    raw = yaml.safe_load((config_dir / "beliefs.yaml").read_text(encoding="utf-8"))["crowds"]
    if not isinstance(raw, dict):
        raise ValueError("crowds settings must be a mapping")
    return raw


def census_per_cell(path: Path, cells: Sequence[str], ages_path: Path | None = None) -> dict[str, dict[str, Any]]:
    """ISTAT 2021 census per cell: residents, children aged 0-14 and municipio.

    Each section goes to the cell holding its centre (sections are small in the
    city, so this is close to an area split). The municipio is the one with the
    most residents in the cell.
    """
    wanted = set(cells)
    resolution = _resolution(cells)
    ages: dict[str, tuple[int, int]] = {}
    if ages_path is not None:
        with ages_path.open(encoding="utf-8") as fh:
            for rec in csv.DictReader(fh):
                ages[rec["sez_id"]] = (int(rec["elderly_65_plus"] or 0), int(rec["elderly_75_plus"] or 0))
    out: dict[str, dict[str, Any]] = {}
    by_mun: dict[str, dict[str, int]] = {}
    for feature in json.loads(path.read_text(encoding="utf-8"))["features"]:
        props = feature["properties"]
        geometry = feature["geometry"]
        ring = geometry["coordinates"][0] if geometry["type"] == "Polygon" else geometry["coordinates"][0][0]
        pts = ring[:-1] if ring[0] == ring[-1] else ring
        cell = cell_of(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts), resolution)
        if cell not in wanted:
            continue
        residents = int(props.get("residents") or 0)
        row = out.setdefault(cell, {"residents": 0, "children_0_14": 0, "municipio": None})
        row["residents"] += residents
        row["children_0_14"] += int(props.get("children_0_14") or 0)
        if ages_path is not None:
            e65, e75 = ages.get(str(props.get("sez_id")), (0, 0))
            row["elderly_65_plus"] = row.get("elderly_65_plus", 0) + e65
            row["elderly_75_plus"] = row.get("elderly_75_plus", 0) + e75
        mun = str(props.get("municipio")) if props.get("municipio") is not None else None
        if mun is not None:
            counts = by_mun.setdefault(cell, {})
            counts[mun] = counts.get(mun, 0) + residents
    for cell, counts in by_mun.items():
        out[cell]["municipio"] = max(counts, key=lambda m: counts[m])
    return out


def points_per_cell(path: Path, cells: Sequence[str]) -> dict[str, int]:
    """Count point features (e.g. care homes) per cell."""
    wanted = set(cells)
    resolution = _resolution(cells)
    out: dict[str, int] = {}
    for feature in json.loads(path.read_text(encoding="utf-8"))["features"]:
        if feature["geometry"]["type"] != "Point":
            continue
        lon, lat = feature["geometry"]["coordinates"][:2]
        cell = cell_of(lon, lat, resolution)
        if cell in wanted:
            out[cell] = out.get(cell, 0) + 1
    return out


def residents_per_cell(path: Path, cells: Sequence[str]) -> dict[str, int]:
    """Census residents per cell (see ``census_per_cell``)."""
    return {cell: int(row["residents"]) for cell, row in census_per_cell(path, cells).items()}


def crowds(
    cells: Sequence[str],
    start: datetime,
    end: datetime,
    providers: Mapping[str, Provider],
    residents_path: Path | None = None,
) -> dict[str, Any]:
    settings = crowds_settings()
    specs = load_specs()
    names = [str(n) for n in settings["signals"]]
    layers: dict[str, BeliefLayer] = {}
    data_kinds: dict[str, str] = {}
    warnings: list[str] = []
    for name in names:
        spec = specs[name]
        feeds = [(providers[s.layer], s) for s in spec.sources if s.layer in providers]
        if not feeds:
            data_kinds[name] = "not_available"
            warnings.append(f"{name}: no source connected ({', '.join(spec.source_layers)})")
            continue
        try:
            layers[name] = build_layer(name, cells, [p for p, _ in feeds], start, end, spec=spec,
                                       sources=[s for _, s in feeds])
        except ProviderNotConfigured as exc:
            data_kinds[name] = "not_available"
            warnings.append(f"{name}: {exc}")
            continue
        data_kinds[name] = "simulated" if layers[name].synthetic else SIGNAL_KINDS.get(name, "estimated")
        warnings.extend(spec.caveats)

    residents: dict[str, int] = {}
    if residents_path is not None and residents_path.exists():
        residents = residents_per_cell(residents_path, cells)
        data_kinds["residents"] = "real"
        warnings.append("residents are the ISTAT 2021 census: where people live, not where they are now")
    else:
        data_kinds["residents"] = "not_available"

    # Per signal: cells that carry a reading, and the city-wide threshold among them.
    percentile = float(settings["busy_percentile"])
    min_agree = int(settings["min_agree"])
    observed: dict[str, np.ndarray] = {}
    thresholds: dict[str, float] = {}
    for name, layer in layers.items():
        has = ~np.isnan(layer.updated_at)
        observed[name] = has
        thresholds[name] = float(np.percentile(layer.mean[has], percentile)) if has.any() else math.inf

    rows = []
    for cell in cells:
        signals: dict[str, dict[str, Any]] = {}
        agree = 0
        for name, layer in layers.items():
            i = layer.index[cell]
            if not observed[name][i]:
                continue
            mean = float(layer.mean[i])
            above = mean > thresholds[name] and mean > 0.0
            agree += int(above)
            signals[name] = {
                "mean": round(mean, 2),
                "sd": round(math.sqrt(float(layer.variance[i])), 2),
                "unit": layer.spec.unit,
                "above_city_p": above,
            }
        if cell in residents:
            signals["residents"] = {"mean": residents[cell], "sd": 0.0, "unit": "people", "above_city_p": None}
        if signals:
            rows.append({"cell": cell, "signals": signals, "agree": agree, "busy": agree >= min_agree})

    return {
        "status": "ok",
        "reason": None,
        "inputs": {"view": "crowds", "start": start.isoformat(), "end": end.isoformat(), "cells": len(cells)},
        "result": {
            "rule": f"busy = at least {min_agree} of {len(layers)} live signals above their city-wide p{percentile:g}",
            "thresholds": {k: (None if math.isinf(v) else round(v, 2)) for k, v in thresholds.items()},
            "cells": rows,
        },
        "data_kinds": data_kinds,
        "sources": [{"id": s, "retrieved_at": end.isoformat()} for s in sorted({s for layer in layers.values() for s in layer.sources})],
        "synthetic": any(layer.synthetic for layer in layers.values()),
        "warnings": warnings,
        "snapshot_hash": hashlib.sha256("|".join(snapshot_hash(layer) for layer in layers.values()).encode()).hexdigest(),
    }


def _resolution(cells: Sequence[str]) -> int:
    import h3  # type: ignore[import-untyped]

    return int(h3.get_resolution(cells[0]))
