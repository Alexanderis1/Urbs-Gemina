"""Independent check of the heatwave model on Regione Lazio's official thermometers in Rome.

    python scripts/check_heat_lazio.py [--out docs/heat_check_lazio.md]

The heatwave model (scenario engine, config/scenarios.yaml -> heatwave.coefficients) was fitted on 17
ASTI rooftop stations in summers 2019-2020. This script tests it on a DIFFERENT network and years:
the Civil Protection thermometers of scripts/fetch_lazio_gauges.py, every June-August from 2018 to 2026.

For each summer day with enough stations, each station's daily minimum (and maximum) is compared with
the average of all stations that day (its anomaly). The model's anomaly comes from Copernicus 2018
sealing and tree cover, as in the scenario engine: district sealing over the 2.2 km forecast scale plus
the local difference of the 100 m cell. Scores: "no model" (every station equals the average), the model
with the coefficients fitted on ASTI (out of sample here), and the same form re-fitted on these stations,
scored on each station left out in turn.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

GAUGES = Path("/mnt/project-files/data/processed/lazio_gauges/temperature_daily.csv")
RASTERS = Path("/mnt/project-files/data/processed")
#: Scenario-engine night coefficients (°C for 0 -> 100 %), fitted on ASTI 2019-2020 (WS6, 14 Nov 2026).
NIGHT = {"impervious_city": 2.9, "impervious": 0.6, "trees": 1.2}
DAY = {"impervious_city": 0.0, "impervious": 0.0, "trees": 0.3}
CELL_M, DISTRICT_M = 100.0, 2200.0
MIN_STATIONS = 8
HOT_MEAN_TMAX = 32.0


def raster_means(name: str, pts: list[tuple[float, float]], size_m: float) -> np.ndarray:
    import rasterio  # type: ignore[import-untyped]
    from rasterio.warp import transform  # type: ignore[import-untyped]
    from rasterio.windows import from_bounds  # type: ignore[import-untyped]

    out = np.full(len(pts), np.nan)
    with rasterio.open(RASTERS / name) as src:
        xs, ys = transform("EPSG:4326", src.crs, [p[0] for p in pts], [p[1] for p in pts])
        for i, (x, y) in enumerate(zip(xs, ys)):
            h = size_m / 2
            a = src.read(1, window=from_bounds(x - h, y - h, x + h, y + h, src.transform), boundless=True,
                         fill_value=255).astype(float)
            a[(a > 100) | (a < 0)] = np.nan
            out[i] = float(np.nanmean(a)) / 100.0
    return out


def features(imp_cell: np.ndarray, imp_dist: np.ndarray, tree_cell: np.ndarray, tree_dist: np.ndarray) -> np.ndarray:
    """Columns: impervious_city, impervious (local difference), trees (local difference, cooling)."""
    return np.column_stack([imp_dist, imp_cell - imp_dist, -(tree_cell - tree_dist)])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="docs/heat_check_lazio.md")
    p.add_argument("--json", default="docs/heat_check_lazio.json")
    args = p.parse_args()
    series: dict[str, dict[str, tuple[float | None, float | None]]] = defaultdict(dict)
    pos: dict[str, tuple[float, float]] = {}
    with GAUGES.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["day"][5:7] not in ("06", "07", "08"):
                continue
            pos[r["station"]] = (float(r["lon"]), float(r["lat"]))
            series[r["station"]][r["day"]] = (float(r["t_min"]) if r["t_min"] else None,
                                             float(r["t_max"]) if r["t_max"] else None)
    names = sorted(pos)
    pts = [pos[n] for n in names]
    imp_c, imp_d = raster_means("imperviousness_2018.tif", pts, CELL_M), raster_means("imperviousness_2018.tif", pts, DISTRICT_M)
    tr_c, tr_d = raster_means("tree_cover_2018.tif", pts, CELL_M), raster_means("tree_cover_2018.tif", pts, DISTRICT_M)
    feat = features(imp_c, imp_d, tr_c, tr_d)

    results: dict[str, object] = {"stations": {n: {"lon": pos[n][0], "lat": pos[n][1], "sealing_100m": round(float(imp_c[i]), 3),
                                                   "sealing_2200m": round(float(imp_d[i]), 3)} for i, n in enumerate(names)}}
    days = sorted({d for s in series.values() for d in s})
    for which, col, coefs in (("night_minimum", 0, NIGHT), ("day_maximum", 1, DAY)):
        for subset in ("all_summer_days", "hot_days"):
            day_groups: list[tuple[np.ndarray, np.ndarray]] = []
            for d in days:
                have = [(i, series[n][d]) for i, n in enumerate(names) if d in series[n]]
                vals = [(i, v[col]) for i, v in have if v[col] is not None]
                tmax = [v[1] for _, v in have if v[1] is not None]
                if len(vals) < MIN_STATIONS or not tmax:
                    continue
                if subset == "hot_days" and float(np.mean(tmax)) < HOT_MEAN_TMAX:
                    continue
                idx = np.array([i for i, _ in vals])
                obs = np.array([v for _, v in vals], dtype=float)
                day_groups.append((idx, obs - obs.mean()))
            if not day_groups:
                continue
            w = np.array([coefs["impervious_city"], coefs["impervious"], coefs["trees"]])

            def rmse(weights: np.ndarray | None, groups: list[tuple[np.ndarray, np.ndarray]], only: int | None = None) -> float:
                err: list[float] = []
                for idx, anom in groups:
                    pred = np.zeros(len(idx)) if weights is None else feat[idx] @ weights
                    pred = pred - pred.mean()
                    e = anom - pred
                    err.extend(e if only is None else e[idx == only])
                return float(np.sqrt(np.mean(np.square(err)))) if err else float("nan")

            def fit(groups: list[tuple[np.ndarray, np.ndarray]], skip: int | None) -> np.ndarray:
                xs, ys = [], []
                for idx, anom in groups:
                    keep = idx != skip if skip is not None else np.ones(len(idx), bool)
                    if keep.sum() < 3:
                        continue
                    f = feat[idx[keep]]
                    a = anom[keep] - anom[keep].mean()
                    xs.append(f - f.mean(axis=0))
                    ys.append(a)
                coef, *_ = np.linalg.lstsq(np.vstack(xs), np.concatenate(ys), rcond=None)
                return np.asarray(coef)

            # Leave-one-station-out: fit without station k, score station k (its anomaly vs the others).
            loso_err: list[float] = []
            for k in range(len(names)):
                c = fit(day_groups, k)
                for idx, anom in day_groups:
                    if k in idx:
                        pred = feat[idx] @ c
                        pred = pred - pred.mean()
                        loso_err.append(float((anom - pred)[idx == k][0]))
            full = fit(day_groups, None)
            results[f"{which}/{subset}"] = {
                "days": len(day_groups),
                "rmse_no_model": round(rmse(None, day_groups), 3),
                "rmse_engine_coefficients": round(rmse(w, day_groups), 3),
                "rmse_refit_left_out": round(float(np.sqrt(np.mean(np.square(loso_err)))), 3),
                "refit_coefficients": {"impervious_city": round(float(full[0]), 2), "impervious": round(float(full[1]), 2),
                                       "trees": round(float(full[2]), 2)},
                "engine_coefficients": coefs,
            }
            print(which, subset, results[f"{which}/{subset}"])
    Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
    Path(args.out).write_text(report(results, names), encoding="utf-8")
    print(f"wrote {args.out}")


def report(results: dict[str, object], names: list[str]) -> str:
    lines = ["# Heatwave model checked on Regione Lazio thermometers", "",
             f"Independent data: {len(names)} Civil Protection thermometers in Rome (Regione Lazio open data, CC BY 4.0), "
             "daily minimum and maximum, June-August 2018-2026 (some months missing on the portal). The model was fitted "
             "on 17 ASTI rooftop stations in 2019-2020, so this is a test on another network and other years.", "",
             "| Quantity | Days | No model | Engine coefficients (fitted on ASTI) | Re-fitted here, station left out |",
             "|---|---|---|---|---|"]
    for key, r in results.items():
        if key == "stations" or not isinstance(r, dict):
            continue
        lines.append(f"| {key.replace('/', ', ').replace('_', ' ')} | {r['days']} | {r['rmse_no_model']} °C | "
                     f"{r['rmse_engine_coefficients']} °C | {r['rmse_refit_left_out']} °C |")
    lines += ["", "Re-fitted coefficients (°C from 0 to 100 %):", ""]
    for key, r in results.items():
        if key != "stations" and isinstance(r, dict):
            lines.append(f"- {key}: {r['refit_coefficients']} (engine: {r['engine_coefficients']})")
    lines += ["", "Stations and their sealing (100 m cell, 2.2 km district):", ""]
    stations = results["stations"]
    assert isinstance(stations, dict)
    for n, s in stations.items():
        lines.append(f"- {n}: {s['sealing_100m']:.0%} / {s['sealing_2200m']:.0%}")
    lines += ["", "Positions: Roma Capitale Civil Protection plan (2018), Tab. 8. Stations differ in height above sea "
              "level (up to about 130 m at Monte Mario), which the model does not use.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
