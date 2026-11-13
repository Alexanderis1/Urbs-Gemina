"""Gate E demo: the road-speed layer updates, shows uncertainty and decays when the feed pauses.

Run: ``python -m twin.beliefs.demo --out data/processed/beliefs_demo``

Feeds the simulated loop stations (``sim_loops``) into the whole-city road-speed
layer from ``start`` to ``pause``, then stops the feed and lets the layer relax
until ``end``. Writes one JSON file per snapshot with per-cell mean, sd and
staleness, plus a short summary. Everything is SIMULATED and labelled so.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from twin.beliefs.api import query
from twin.beliefs.config import grid_resolution, load_specs
from twin.beliefs.grid import cell_center, cells_in_bbox
from twin.beliefs.layer import BeliefLayer, assimilate, prior_layer
from twin.providers.base import ROME_BBOX
from twin.providers.simulated.loops import SimLoopsProvider


def summary(layer: BeliefLayer, label: str) -> dict[str, Any]:
    sd = np.sqrt(layer.variance)
    fresh = int(np.sum(~np.isnan(layer.updated_at) & (layer.as_of.timestamp() - layer.updated_at <= 900)))
    return {
        "label": label,
        "as_of": layer.as_of.isoformat(),
        "cells": len(layer.cells),
        "observations_so_far": layer.n_observations,
        "mean_kmh": {"min": round(float(layer.mean.min()), 1), "median": round(float(np.median(layer.mean)), 1), "max": round(float(layer.mean.max()), 1)},
        "sd_kmh": {"min": round(float(sd.min()), 2), "median": round(float(np.median(sd)), 2), "max": round(float(sd.max()), 2)},
        "cells_updated_in_last_15_min": fresh,
    }


def run(start: datetime, pause: datetime, end: datetime, out: Path | None = None) -> list[dict[str, Any]]:
    spec = load_specs()["road_speed"]
    cells = cells_in_bbox(ROME_BBOX, grid_resolution())
    provider = SimLoopsProvider()
    layer = prior_layer(spec, cells, start)
    snapshots: list[tuple[str, BeliefLayer]] = [("prior only", layer)]
    t = start
    step = timedelta(minutes=30)
    while t < pause:
        nxt = min(t + step, pause)
        layer = assimilate(layer, provider.fetch(ROME_BBOX, t + timedelta(seconds=1) if t > start else t, nxt), until=nxt)
        t = nxt
    snapshots.append(("feed live", layer))
    for hours in (0.5, 2.0):
        snapshots.append((f"feed paused {hours:g} h", layer.at(pause + timedelta(hours=hours))))
    if end > pause:
        snapshots.append(("end", layer.at(end)))

    results = []
    for label, snap in snapshots:
        s = summary(snap, label)
        results.append(s)
        if out is not None:
            out.mkdir(parents=True, exist_ok=True)
            slug = label.replace(" ", "_").replace(".", "")
            payload = query(snap, [])  # metadata only
            payload["result"]["cells"] = [
                [c, round(float(snap.mean[i]), 2), round(float(np.sqrt(snap.variance[i])), 2)]
                for i, c in enumerate(snap.cells)
            ]
            payload["result"]["cell_columns"] = ["cell", "mean", "sd"]
            payload["summary"] = s
            (out / f"{slug}.json").write_text(json.dumps(payload), encoding="utf-8")
    if out is not None:
        centres = {c: [round(v, 5) for v in cell_center(c)] for c in cells}
        (out / "cell_centres.json").write_text(json.dumps(centres), encoding="utf-8")
        (out / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", default="2026-11-13")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    day = datetime.fromisoformat(args.day).replace(tzinfo=timezone.utc)
    start, pause = day + timedelta(hours=5), day + timedelta(hours=8)
    for s in run(start, pause, pause + timedelta(hours=3), args.out):
        print(json.dumps(s))


if __name__ == "__main__":
    main()
