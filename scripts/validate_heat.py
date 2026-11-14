"""Check the heatwave model against 17 real Rome weather stations (ASTI-Network, summers 2019-2020).

Data: Cecilia et al., "Database of ASTI-Network Rome weather stations", Zenodo 19454855, CC BY 4.0
(hourly air temperature; rooftop stations of the Meteo Lazio network and the LIFE-ASTI project).
Download the zip from https://zenodo.org/records/19454855 and pass the unzipped folder.

For every summer day, each station's daily maximum and minimum is compared with the average of all
stations that day (its anomaly). The model's anomaly at a station comes from sealed ground and tree
cover (Copernicus 2018 rasters) with the coefficients in config/scenarios.yaml. Three readings are
scored: "two_scale" (as built: district sealing over the 2.2 km forecast scale plus the local
difference), "local_only" (local differences only) and "absolute_100m". Each is also re-fitted and
scored on stations left out one at a time; "no model" means every station equals the average.

Usage: python scripts/validate_heat.py ASTI_DIR [--out eval/scenarios/heat_validation.json]
       [--daily-out /mnt/project-files/data/processed/asti_stations_daily.csv]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twin.scenarios import config, layers  # noqa: E402

MIN_HOURS = 20       # a day counts when the station has at least this many valid hours
MIN_STATIONS = 10    # and at least this many stations reported that day
HOT_DAY_MEAN_TMAX = 32.0  # "hot days": the station average of the daily maximum reaches this


def stations(meta: Path) -> list[dict[str, Any]]:
    with meta.open(encoding="utf-8") as fh:
        return [{"id": r["ID"], "lon": float(r["LON"]), "lat": float(r["LAT"]), "alt": float(r["ALT"]),
                 "imp1400": float(r["IMP1400"]) / 100.0} for r in csv.DictReader(fh)]


def daily(path: Path) -> dict[str, tuple[float, float]]:
    """CET date -> (Tmax, Tmin) from hourly means."""
    by_day: dict[str, list[float]] = defaultdict(list)
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                t = float(r["T"])
            except (TypeError, ValueError):
                continue
            if np.isfinite(t):
                d, m, y = r["Time_CET"].split(" ")[0].split("/")
                by_day[f"{y}-{m}-{d}"].append(t)
    return {day: (max(v), min(v)) for day, v in by_day.items() if len(v) >= MIN_HOURS}


def raster_means(file_name: str, pts: list[dict[str, Any]], sizes_m: tuple[float, ...]) -> np.ndarray:
    """Mean of a 0-100 % raster in squares of each size centred on each station (share 0-1)."""
    import rasterio  # type: ignore[import-untyped]
    from rasterio.warp import transform  # type: ignore[import-untyped]
    from rasterio.windows import from_bounds  # type: ignore[import-untyped]

    path = layers.find(file_name)
    if path is None:
        sys.exit(f"{file_name} not found (scripts/fetch_static_layers.py / fetch_heat_layers.py)")
    out = np.full((len(pts), len(sizes_m)), np.nan)
    with rasterio.open(path) as src:
        xs, ys = transform("EPSG:4326", src.crs, [p["lon"] for p in pts], [p["lat"] for p in pts])
        for i, (x, y) in enumerate(zip(xs, ys)):
            for j, size in enumerate(sizes_m):
                h = size / 2
                win = from_bounds(x - h, y - h, x + h, y + h, src.transform)
                a = src.read(1, window=win, boundless=True, fill_value=src.nodata or 255).astype(float)
                a[(a > 100) | (a < 0)] = np.nan
                out[i, j] = float(np.nanmean(a)) / 100.0
    return out


def loso(x: np.ndarray, y: np.ndarray) -> tuple[list[float], float, float]:
    """Least-squares fit with intercept; (coefficients, in-sample RMSE, leave-one-station-out RMSE)."""
    a = np.column_stack([np.ones(len(y)), x])
    coef = np.linalg.lstsq(a, y, rcond=None)[0]
    rmse = float(np.sqrt(np.mean((a @ coef - y) ** 2)))
    errs = []
    for k in range(len(y)):
        keep = np.arange(len(y)) != k
        c = np.linalg.lstsq(a[keep], y[keep], rcond=None)[0]
        errs.append(float(a[k] @ c - y[k]))
    return [round(float(v), 3) for v in coef[1:]], round(rmse, 3), round(float(np.sqrt(np.mean(np.square(errs)))), 3)


def centred_rmse(pred: np.ndarray, obs: np.ndarray) -> float:
    return round(float(np.sqrt(np.mean(((pred - pred.mean()) - (obs - obs.mean())) ** 2))), 3)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("asti_dir", type=Path)
    p.add_argument("--out", type=Path, default=ROOT / "eval" / "scenarios" / "heat_validation.json")
    p.add_argument("--daily-out", type=Path, default=None)
    args = p.parse_args(argv)
    cfg = config.load("scenarios.yaml")["heatwave"]
    coef = config.value(cfg, "coefficients")
    nb = float(config.value(cfg, "forecast_scale_m"))
    cell = float(config.value(cfg, "cell_m"))

    st = stations(args.asti_dir / "metadata.csv")
    series = {s["id"]: daily(args.asti_dir / "hourly_data" / f"HOURLY_{s['id']}.csv") for s in st}
    imp = raster_means(str(config.value(cfg, "impervious_file")), st, (cell, nb))
    trees = raster_means(str(config.value(cfg, "tree_cover_file")), st, (cell, nb))

    days = sorted({d for v in series.values() for d in v})
    anomalies: dict[str, dict[str, list[float]]] = {"tmax": defaultdict(list), "tmin": defaultdict(list),
                                                     "tmax_hot": defaultdict(list), "tmin_hot": defaultdict(list)}
    used_days = {"all": 0, "hot": 0}
    for day in days:
        have = {s["id"]: series[s["id"]][day] for s in st if day in series[s["id"]]}
        if len(have) < MIN_STATIONS:
            continue
        mx = np.mean([v[0] for v in have.values()])
        mn = np.mean([v[1] for v in have.values()])
        hot = mx >= HOT_DAY_MEAN_TMAX
        used_days["all"] += 1
        used_days["hot"] += int(hot)
        for sid, (tx, tn) in have.items():
            anomalies["tmax"][sid].append(tx - mx)
            anomalies["tmin"][sid].append(tn - mn)
            if hot:
                anomalies["tmax_hot"][sid].append(tx - mx)
                anomalies["tmin_hot"][sid].append(tn - mn)

    if args.daily_out:
        with args.daily_out.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["station", "lon", "lat", "alt_m", "date", "tmax_c", "tmin_c"])
            for s in st:
                for day, (tx, tn) in sorted(series[s["id"]].items()):
                    w.writerow([s["id"], s["lon"], s["lat"], s["alt"], day, round(tx, 2), round(tn, 2)])

    ids = [s["id"] for s in st]
    alt = np.array([s["alt"] for s in st])
    # model readings: name -> list of (feature, coefficient key in config); trees enter with a minus sign
    readings = {
        "two_scale": [(imp[:, 0] - imp[:, 1], "impervious"), (imp[:, 1], "impervious_city"),
                      (-(trees[:, 0] - trees[:, 1]), "trees")],
        "local_only": [(imp[:, 0] - imp[:, 1], "impervious"), (-(trees[:, 0] - trees[:, 1]), "trees")],
        "absolute_100m": [(imp[:, 0], "impervious"), (-trees[:, 0], "trees")],
    }
    report: dict[str, Any] = {
        "source": "ASTI-Network, Zenodo 19454855 (CC BY 4.0), 17 rooftop stations, JJA 2019-2020",
        "days_used": used_days, "hot_day_rule": f"station average Tmax >= {HOT_DAY_MEAN_TMAX} C",
        "stations": [{"id": sid, "alt_m": float(a), "impervious_100m": round(float(imp[k, 0]), 3),
                      "impervious_2200m": round(float(imp[k, 1]), 3), "trees_100m": round(float(trees[k, 0]), 3),
                      "trees_2200m": round(float(trees[k, 1]), 3)} for k, (sid, a) in enumerate(zip(ids, alt))],
        "results": {},
    }
    for key, phase in (("tmax", "day"), ("tmin", "night"), ("tmax_hot", "day"), ("tmin_hot", "night")):
        ok = [k for k, sid in enumerate(ids) if len(anomalies[key][sid]) >= 10]
        obs = np.array([np.mean(anomalies[key][ids[k]]) for k in ok])
        spread = float(np.mean([np.std(anomalies[key][ids[k]]) for k in ok]))
        row: dict[str, Any] = {"stations": len(ok), "observed_range_c": [round(float(obs.min()), 2),
                                                                        round(float(obs.max()), 2)],
                               "day_to_day_sd_c": round(spread, 2),
                               "no_model_rmse_c": centred_rmse(np.zeros(len(ok)), obs)}
        for name, terms in readings.items():
            pred = sum(float(coef[phase].get(c, [0.0])[0]) * f[ok] for f, c in terms)
            x = np.column_stack([f[ok] for f, _ in terms])
            fit_coef, fit_rmse, fit_loso = loso(x, obs)
            row[name] = {"config_rmse_c": centred_rmse(np.asarray(pred), obs),
                         "refit": {**{c: v for (_, c), v in zip(terms, fit_coef)}, "rmse_c": fit_rmse,
                                   "leave_one_out_rmse_c": fit_loso}}
        report["results"][key] = row
    args.out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report["results"], indent=1))
    print("days", used_days)
    return 0


if __name__ == "__main__":
    sys.exit(main())
