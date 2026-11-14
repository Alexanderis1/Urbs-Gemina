"""Flash-flood watch: where heavy rain is falling now on ground that floods.

Combines the rain belief layer (radar + forecast) with two static real layers:
the ISPRA/PGRA flood-hazard zones (P1 low, P2 medium, P3 high) and OSM road
underpasses, which are where Rome's streets flood first in a cloudburst.
A cell is listed when it has a hazard zone or an underpass and the chance of
rain above ``heavy_rain_mm_h`` is at least the watch level. This says where to
look, not that flooding will happen. Settings: ``flood_watch`` in config/beliefs.yaml.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import NormalDist
from typing import Any, Mapping, Sequence

import h3  # type: ignore[import-untyped]
import yaml

from twin.beliefs.api import snapshot_hash
from twin.beliefs.config import CONFIG_DIR
from twin.beliefs.grid import cell_of
from twin.beliefs.layer import BeliefLayer

HAZARD_RANK = {"P1": 1, "P2": 2, "P3": 3}


def flood_settings(config_dir: Path = CONFIG_DIR) -> dict[str, Any]:
    raw = yaml.safe_load((config_dir / "beliefs.yaml").read_text(encoding="utf-8"))["flood_watch"]
    if not isinstance(raw, dict):
        raise ValueError("flood_watch must be a mapping")
    return raw


def hazard_per_cell(path: Path, cells: Sequence[str]) -> dict[str, str]:
    """Worst flood-hazard class touching each cell."""
    wanted = set(cells)
    res = int(h3.get_resolution(cells[0]))
    out: dict[str, str] = {}
    for feature in json.loads(path.read_text(encoding="utf-8"))["features"]:
        cls = str(feature["properties"].get("hazard"))
        if cls not in HAZARD_RANK:
            continue
        shape = h3.geo_to_h3shape(feature["geometry"])
        for cell in h3.h3shape_to_cells_experimental(shape, res, contain="overlap"):
            c = str(cell)
            if c in wanted and HAZARD_RANK[cls] > HAZARD_RANK.get(out.get(c, ""), 0):
                out[c] = cls
    return out


def underpasses_per_cell(path: Path, cells: Sequence[str]) -> dict[str, int]:
    """Road underpass segments per cell (by the segment's middle vertex)."""
    wanted = set(cells)
    res = int(h3.get_resolution(cells[0]))
    out: dict[str, int] = {}
    for feature in json.loads(path.read_text(encoding="utf-8"))["features"]:
        geometry = feature["geometry"]
        if geometry["type"] != "LineString":
            continue
        coords = geometry["coordinates"]
        lon, lat = coords[len(coords) // 2]
        c = cell_of(lon, lat, res)
        if c in wanted:
            out[c] = out.get(c, 0) + 1
    return out


def flood_watch(rain: BeliefLayer, hazard: Mapping[str, str], underpasses: Mapping[str, int]) -> dict[str, Any]:
    settings = flood_settings()
    heavy = float(settings["heavy_rain_mm_h"])
    watch = float(settings["watch_probability"])
    warning = float(settings["warning_probability"])
    rows: list[dict[str, Any]] = []
    for cell in sorted(set(hazard) | set(underpasses)):
        i = rain.index.get(cell)
        if i is None:
            continue
        mean = float(rain.mean[i])
        sd = float(rain.variance[i]) ** 0.5
        p = 1.0 - NormalDist(mean, sd).cdf(heavy) if sd > 0 else float(mean > heavy)
        if p < watch:
            continue
        rows.append({
            "cell": cell,
            "level": "warning" if p >= warning else "watch",
            "p_heavy_rain": round(p, 3),
            "rain_mm_h": {"mean": round(mean, 2), "sd": round(sd, 2)},
            "hazard": hazard.get(cell),
            "underpasses": underpasses.get(cell, 0),
        })
    rows.sort(key=lambda r: (-r["p_heavy_rain"], -HAZARD_RANK.get(r["hazard"] or "", 0), -r["underpasses"]))
    warnings = [
        "this is where heavy rain meets flood-prone ground or underpasses: a place to watch, not a forecast of flooding",
        "drainage, blocked drains and river levels are not modelled",
    ]
    if rain.n_observations == 0:
        warnings.append("no radar readings in the window: rain is the forecast only")
    return {
        "status": "ok",
        "reason": None,
        "inputs": {"layer": rain.spec.name, "as_of": rain.as_of.isoformat()},
        "result": {
            "heavy_rain_mm_h": heavy,
            "levels": {"watch": watch, "warning": warning},
            "cells": rows,
        },
        "data_kinds": {rain.spec.name: "simulated" if rain.synthetic else "estimated",
                       "flood_hazard": "real", "underpasses": "real"},
        "sources": [{"id": s, "retrieved_at": rain.as_of.isoformat()} for s in rain.sources]
        + [{"id": "ispra_pgra_mosaic_v5", "retrieved_at": None}, {"id": "osm_road_underpasses", "retrieved_at": None}],
        "synthetic": rain.synthetic,
        "warnings": warnings,
        "snapshot_hash": snapshot_hash(rain),
    }
