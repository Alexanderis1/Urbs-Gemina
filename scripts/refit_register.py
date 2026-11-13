"""Compare antenna-register models on held-out Cartoradio cells (register v1 vs v2 steps).

    python scripts/refit_register.py [--bbox lon0 lat0 lon1 lat1] [--out docs/register_refit.md]

Prints and writes only aggregate errors (no Cartoradio values: the grid is runtime-only).
"""
from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from twin.physics.buildings import to_local
from twin.providers.base import ROME_BBOX
from twin.providers.estimated import refit
from twin.providers.estimated.register import EstimatedRegisterProvider, obs_to_cell
from twin.providers.restricted.cartoradio import CartoradioGridProvider


def site_heights(lons: np.ndarray[Any, Any], lats: np.ndarray[Any, Any]) -> tuple[np.ndarray[Any, Any], int]:
    """Mast height per site from the LiDAR-corrected roof of the building it stands on (else a tower)."""
    import pyarrow.parquet as pq  # type: ignore[import-untyped]

    from twin.physics.buildings import buildings_path, parse_wkb
    from twin.scenarios.geometry import contains

    heights = np.full(lons.size, refit.tower_height_m())
    path = buildings_path()
    if path is None:
        return heights, 0
    t = pq.read_table(path, columns=["height_m", "bbox"])
    bb = t.column("bbox").combine_chunks()
    x0, y0 = bb.field("xmin").to_numpy(), bb.field("ymin").to_numpy()
    x1, y1 = bb.field("xmax").to_numpy(), bb.field("ymax").to_numpy()
    h = t.column("height_m").to_numpy()
    cand: dict[int, list[int]] = {}
    for k, (lon, lat) in enumerate(zip(lons, lats)):
        hit = np.nonzero((x0 <= lon) & (x1 >= lon) & (y0 <= lat) & (y1 >= lat))[0]
        if hit.size:
            cand[k] = hit.tolist()
    rows = sorted({r for v in cand.values() for r in v})
    geoms = pq.read_table(path, columns=["geometry"]).column("geometry").take(rows).to_pylist() if rows else []
    geom_of = dict(zip(rows, geoms))
    on_roof = 0
    for k, hits in cand.items():
        for r in hits:
            polys = parse_wkb(bytes(geom_of[r]))
            if any(contains({"type": "Polygon", "coordinates": poly}, float(lons[k]), float(lats[k])) for poly in polys):
                heights[k] = refit.mast_height(float(h[r]), True)
                on_roof += 1
                break
    return heights, on_roof


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bbox", type=float, nargs=4, default=list(ROME_BBOX))
    p.add_argument("--out", default="docs/register_refit.md")
    p.add_argument("--radius", type=float, default=500.0)
    args = p.parse_args()
    bbox = tuple(args.bbox)
    t0 = time.time()
    now = datetime.now(timezone.utc)
    cells = [obs_to_cell(o) for o in CartoradioGridProvider().fetch(bbox, now, now)]
    v1 = EstimatedRegisterProvider(area=bbox)
    sites = v1.sites()
    print(f"{len(cells)} cells, {len(sites)} sites, v1 fit error {v1.fit_error_db:.2f} dB ({time.time() - t0:.0f} s)")
    lon0, lat0 = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    cx, cy = to_local(np.array([c.lon for c in cells]), np.array([c.lat for c in cells]), lon0, lat0)
    slon, slat = np.array([s.lon for s in sites]), np.array([s.lat for s in sites])
    sx, sy = to_local(slon, slat, lon0, lat0)
    e = np.array([c.value for c in cells])
    cap = 15.0
    keep = e > 0
    prob = refit.Problem(np.column_stack([sx, sy]), np.full(sx.size, 21.5), cx[keep], cy[keep],
                         e[keep] ** 2, e[keep] >= cap)
    lidar_h, on_roof = site_heights(slon, slat)
    print(f"LiDAR roofs under {on_roof}/{len(sites)} sites ({time.time() - t0:.0f} s)")
    base = refit.Model(exponent=2.0, receptor_m=1.5, tilt_deg=float(refit._cfg("tilt_deg")))
    exps = [float(x) for x in refit._cfg("exponents")]
    seed = int(refit._cfg("seed"))
    share = float(refit._cfg("holdout_share"))
    rows = []

    def run(name: str, problem: refit.Problem, exponents: list[float], azimuth: bool) -> refit.FitResult:
        r = refit.select_exponent(problem, exponents, 4.0, args.radius, seed, share, base, azimuth)
        rows.append({"model": name, "exponent": r.model.exponent, "train_db": round(r.train_median_abs_db, 2),
                     "holdout_db": round(r.holdout_median_abs_db, 2), "holdout_cells": r.n_holdout})
        print(rows[-1], f"({time.time() - t0:.0f} s)")
        return r

    run("v1-like: free space (n=2), orientation-averaged sectors, 20 m height", prob, [2.0], False)
    run("+ fitted path-loss exponent", prob, exps, False)
    best = run("+ sector directions (azimuth search)", prob, exps, True)
    with_h = replace(prob, heights=lidar_h)
    final = run("+ mast heights from LiDAR roofs", with_h, [best.model.exponent], True)
    report = {"cells": len(cells), "sites": len(sites), "v1_reported_fit_error_db": round(v1.fit_error_db, 2),
              "sites_on_lidar_roofs": on_roof, "rows": rows,
              "azimuth_offsets_histogram": np.histogram(final.offsets_deg, bins=np.arange(0, 130, 10))[0].tolist()}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Antenna register refit: hold-out comparison", "",
             f"Run {now:%Y-%m-%d %H:%M} UTC on {len(cells)} Cartoradio cells (100 m) and {len(sites)} estimated sites, "
             f"one cell in five held out (seed {seed}). Error = median |model - Cartoradio| in dB on cells below "
             "the 15 V/m cap. Only aggregates are reported: Cartoradio values are runtime-only.", "",
             "| Model | Exponent | Fit error (dB) | Hold-out error (dB) |", "|---|---|---|---|"]
    lines += [f"| {r['model']} | {r['exponent']} | {r['train_db']} | {r['holdout_db']} |" for r in rows]
    lines += ["", f"v1 register (free space, isotropic) reported {v1.fit_error_db:.2f} dB on its own fit cells.",
              f"Mast heights from LiDAR roofs for {on_roof} of {len(sites)} sites; the rest use a "
              f"{refit.tower_height_m():g} m tower.", "", "```json", json.dumps(report, indent=2), "```", ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({time.time() - t0:.0f} s); hold-out {rows[0]['holdout_db']} -> {rows[-1]['holdout_db']} dB")
    _ = math


if __name__ == "__main__":
    main()
