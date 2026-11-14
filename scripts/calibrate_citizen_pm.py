"""Calibrate Rome's Sensor.Community PM sensors (SDS011) against the official EEA stations.

    python scripts/calibrate_citizen_pm.py [--days 90] [--out docs/citizen_pm_calibration.md]

Low-cost optical sensors read too high in humid air: water makes particles swell. The standard
correction (kappa-Koehler growth, Di Antonio et al. 2018, Sensors 18:2790; Crilley et al. 2018, AMT
11:709) is

    raw = s * reference * (1 + c * RH / (100 - RH))

with ``s`` the sensor's dry scale and ``c`` the hygroscopic growth term, RH in percent (capped, the
formula diverges near 100 %). The reference is the daily mean of the EEA stations in Rome that day:
the learned PM layers show that PM varies city-wide day to day and very little street to street
(docs/air_fusion_fit.md: 99 % of the PM10 error is shared over > 50 km), so the station mean is a fair
reference anywhere in the city.

Fitted on daily means (archive.sensor.community, ODbL; humidity from the DHT22/BME280 on the same
node), scored by leaving one sensor out. Prints the values for config/provider_settings.yaml.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from twin.providers import http
from twin.providers.base import ROME_BBOX
from twin.providers.open.eea import EeaHourlyProvider

ARCHIVE = "https://archive.sensor.community"
LIVE_24H = "https://data.sensor.community/static/v2/data.24h.json"
HUMIDITY_TYPES = ("dht22", "bme280", "htu21d")
KEYS = {"P1": "pm10", "P2": "pm25"}


def rome_nodes() -> list[dict[str, Any]]:
    """PM sensors in Rome with the humidity sensor of the same node, from the public 24 h feed."""
    rows = json.loads(http.get_bytes(LIVE_24H, timeout_s=180.0).decode("utf-8"))
    lo_lon, lo_lat, hi_lon, hi_lat = ROME_BBOX
    by_loc: dict[int, dict[str, Any]] = defaultdict(dict)
    for r in rows:
        loc = r.get("location") or {}
        try:
            lon, lat = float(loc["longitude"]), float(loc["latitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (lo_lon <= lon <= hi_lon and lo_lat <= lat <= hi_lat) or str(loc.get("indoor", "0")) == "1":
            continue
        kind = str(r["sensor"]["sensor_type"]["name"]).lower()
        node = by_loc[int(loc["id"])]
        node.update(lon=lon, lat=lat)
        if kind == "sds011":
            node["pm"] = int(r["sensor"]["id"])
        elif kind in HUMIDITY_TYPES:
            node["rh"] = (kind, int(r["sensor"]["id"]))
    return [n for n in by_loc.values() if "pm" in n]


def day_means(text: str, columns: tuple[str, ...]) -> dict[str, float]:
    sums: dict[str, list[float]] = defaultdict(list)
    for row in csv.DictReader(io.StringIO(text), delimiter=";"):
        for c in columns:
            try:
                v = float(row.get(c) or "nan")
            except ValueError:
                continue
            if math.isfinite(v) and 0.0 <= v < 999.0:
                sums[c].append(v)
    # A day counts when the sensor reported for most of it (5-min cadence: 288 rows).
    return {c: float(np.mean(v)) for c, v in sums.items() if len(v) >= 150}


def fetch(url: str) -> str:
    try:
        return http.get_bytes(url, timeout_s=60.0).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - a missing day is normal (sensor offline)
        return ""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--rh-cap", type=float, default=95.0)
    p.add_argument("--out", default="docs/citizen_pm_calibration.md")
    p.add_argument("--json", default="docs/citizen_pm_calibration.json")
    p.add_argument("--report-only", action="store_true")
    args = p.parse_args()
    if args.report_only:
        Path(args.out).write_text(report(json.loads(Path(args.json).read_text(encoding="utf-8"))), encoding="utf-8")
        return

    end = datetime.now(timezone.utc)
    obs = list(EeaHourlyProvider().fetch(ROME_BBOX, end - timedelta(days=args.days + 3), end))
    ref: dict[str, dict[date, list[float]]] = {"pm10": defaultdict(list), "pm25": defaultdict(list)}
    for o in obs:
        for key in ("pm10", "pm25"):
            if key in o.values:
                # Daily means are stamped at the end of the local day: shift back to the day they describe.
                ref[key][(o.observed_at - timedelta(hours=1)).date()].append(o.values[key])
    ref_day = {k: {d: float(np.mean(v)) for d, v in days.items() if len(v) >= 5} for k, days in ref.items()}
    last = max(ref_day["pm10"])
    days = [last - timedelta(days=i) for i in range(args.days)]

    nodes = rome_nodes()
    jobs: list[tuple[int, date, str, str]] = []
    for i, n in enumerate(nodes):
        for d in days:
            jobs.append((i, d, "pm", f"{ARCHIVE}/{d}/{d}_sds011_sensor_{n['pm']}.csv"))
            if "rh" in n:
                kind, sid = n["rh"]
                jobs.append((i, d, "rh", f"{ARCHIVE}/{d}/{d}_{kind}_sensor_{sid}.csv"))
    with ThreadPoolExecutor(max_workers=8) as pool:
        texts = list(pool.map(lambda j: fetch(j[3]), jobs))
    daily: dict[tuple[int, date], dict[str, float]] = defaultdict(dict)
    for (i, d, kind, _), text in zip(jobs, texts):
        if text:
            cols = ("P1", "P2") if kind == "pm" else ("humidity",)
            daily[(i, d)].update(day_means(text, cols))

    results: dict[str, Any] = {"nodes": len(nodes), "days": args.days, "rh_cap": args.rh_cap,
                               "window": [str(days[-1]), str(days[0])]}
    for raw_key, key in KEYS.items():
        rows = [(i, d, v[raw_key], min(v["humidity"], args.rh_cap), ref_day[key][d])
                for (i, d), v in daily.items() if raw_key in v and "humidity" in v and d in ref_day[key]
                and ref_day[key][d] > 1.0 and v[raw_key] > 0.5]
        if len(rows) < 30:
            results[key] = {"status": "not enough co-located days", "n": len(rows)}
            continue
        sensor = np.array([r[0] for r in rows])
        raw = np.array([r[2] for r in rows])
        rh = np.array([r[3] for r in rows])
        reference = np.array([r[4] for r in rows])
        growth = rh / (100.0 - rh)

        def fit(mask: np.ndarray) -> tuple[float, float]:
            # log(raw/ref) = log s + log(1 + c g): one-dimensional search over c, s in closed form.
            best = (math.inf, 1.0, 0.0)
            for c in np.linspace(0.0, 1.5, 301):
                resid = np.log(raw[mask] / reference[mask]) - np.log1p(c * growth[mask])
                log_s = float(np.mean(resid))
                sse = float(np.sum((resid - log_s) ** 2))
                if sse < best[0]:
                    best = (sse, math.exp(log_s), float(c))
            return best[1], best[2]

        def corrected(s: float, c: float, mask: np.ndarray) -> np.ndarray:
            out: np.ndarray = raw[mask] / (s * (1.0 + c * growth[mask]))
            return out

        s_all, c_all = fit(np.ones(len(rows), bool))
        loo_raw, loo_cor, loo_rel = [], [], []
        for k in np.unique(sensor):
            test = sensor == k
            if (~test).sum() < 20:
                continue
            s_k, c_k = fit(~test)
            loo_raw.extend(raw[test] - reference[test])
            cor = corrected(s_k, c_k, test)
            loo_cor.extend(cor - reference[test])
            loo_rel.extend(np.log(cor / reference[test]))
        rel_sd = float(np.std(loo_rel)) if loo_rel else float("nan")
        results[key] = {
            "n_days": len(rows), "sensors": int(len(np.unique(sensor))),
            "scale": round(s_all, 3), "growth_c": round(c_all, 3),
            "raw_bias": round(float(np.mean(raw - reference)), 2),
            "rmse_raw_left_out": round(float(np.sqrt(np.mean(np.square(loo_raw)))), 2) if loo_raw else None,
            "rmse_corrected_left_out": round(float(np.sqrt(np.mean(np.square(loo_cor)))), 2) if loo_cor else None,
            "bias_corrected_left_out": round(float(np.mean(loo_cor)), 2) if loo_cor else None,
            "relative_sigma_daily": round(math.expm1(rel_sd), 3) if loo_rel else None,
            "mean_reference": round(float(np.mean(reference)), 2), "mean_rh": round(float(np.mean(rh)), 1),
        }
        print(key, results[key])
    Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
    Path(args.out).write_text(report(results), encoding="utf-8")
    print(f"wrote {args.out}")


def report(r: dict[str, Any]) -> str:
    lines = ["# Citizen PM sensors calibrated against official stations", "",
             f"{r['nodes']} Sensor.Community nodes in Rome, daily means {r['window'][0]} to {r['window'][1]} "
             "(archive.sensor.community, ODbL). Reference: mean of the EEA stations in Rome that day. "
             f"Model: raw = s x reference x (1 + c x RH/(100 - RH)), RH capped at {r['rh_cap']:.0f} %. "
             "Scores leave one sensor out.", "",
             "| Pollutant | Sensor-days | Sensors | Dry scale s | Growth c | Raw error (RMSE) | Corrected error (RMSE) | Corrected bias | Relative error |",
             "|---|---|---|---|---|---|---|---|---|"]
    for key in ("pm10", "pm25"):
        x = r.get(key, {})
        if "scale" not in x:
            lines.append(f"| {key} | {x.get('n', 0)} | - | - | - | - | - | - | {x.get('status', '')} |")
            continue
        lines.append(f"| {key} | {x['n_days']} | {x['sensors']} | {x['scale']} | {x['growth_c']} | {x['rmse_raw_left_out']} | "
                     f"{x['rmse_corrected_left_out']} | {x['bias_corrected_left_out']} | {x['relative_sigma_daily']:.0%} |")
    lines += ["", "How it is used: the live provider (twin/providers/open/sensor_community.py) divides every reading by "
              "the dry scale s and gives it the relative error above, doubled at humidity >= 80 %. The humidity "
              "growth term is not applied when it comes out near zero, as it does on daily means. Rescaling removes "
              "the bias (sensors read about half the official level), which matters most in the map because a bias "
              "is shared by all citizen sensors while their noise averages out; the error per reading stays large, "
              "so the stations still dominate the PM layers.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
