"""Learn the air-quality layers' settings from 2026 history of REAL EEA stations in Rome.

    python scripts/fit_air_fusion.py [--split 2026-09-01] [--out docs/air_fusion_fit.md]

Inputs (both open): EEA up-to-date station files (NO2 and O3 hourly, PM10 and PM2.5 daily means)
and the CAMS European forecast at each station from the Open-Meteo air-quality archive.
Steps (twin/beliefs/learn.py), fitted on data BEFORE ``--split`` only:
  1. CAMS bias:   station = offset + scale * CAMS
  2. covariance:  spread, reach and local part of what CAMS still misses (maximum likelihood)
  3. memory:      how fast that error fades (relax_tau_hours)
Then a leave-one-station-out check AFTER ``--split`` (data the fit never saw) compares the
old settings with the learned ones. Writes the report and prints the values for config/beliefs.yaml.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from twin.beliefs import learn
from twin.beliefs.calibration import CalibrationRules, leave_one_station_out
from twin.beliefs.config import FieldSpec, LayerSpec, load_calibration_rules, load_specs
from twin.beliefs.grid import local_xy_km
from twin.providers import http
from twin.providers.base import ROME_BBOX, Observation
from twin.providers.open.eea import EeaHourlyProvider

CAMS_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
CAMS_VAR = {"no2": "nitrogen_dioxide", "pm10": "pm10", "pm25": "pm2_5", "o3": "ozone"}
LAYER = {"no2": "air_no2", "pm10": "air_pm10", "pm25": "air_pm25", "o3": "air_o3"}
#: Averaging period of the EEA values (hours): NO2 is hourly, PM10/PM2.5 are daily means in Rome.
PERIOD_H = {"no2": 1, "pm10": 24, "pm25": 24, "o3": 1}
LAGS_H = {"no2": [1.0, 2.0, 3.0, 6.0], "pm10": [24.0, 48.0], "pm25": [24.0, 48.0], "o3": [1.0, 2.0, 3.0, 6.0]}
MAX_GROUPS = 1500
#: Land-use regression for NO2: motor road length within this radius. 100 m is the ESCAPE traffic
#: buffer and close to the size of an H3 res-9 cell; on 13 Rome stations it explains r = 0.85 of the
#: stations' lasting offsets (scripts/fit_air_fusion.py, 14 Nov 2026).
LUR_RADIUS_M = 100.0
#: Pollutants that get the road term. Tried on O3 (14 Nov 2026): the slope is negative as expected
#: (traffic NO consumes ozone, -0.4 ug/m3 per 100 m of road) but the 9 ozone stations' lasting offsets
#: do not follow road length, and the held-out error got worse (RMSE 12.5 -> 12.9, coverage 87% -> 84%).
LUR_KEYS = ("no2",)
SEGMENTS = Path("data/raw/overture/segments.parquet")
COVARIATE_OUT = Path("/mnt/project-files/model/no2_lur_covariates.csv")  # moments used for the likelihood fit (NO2 has ~7,000 hours; a random sample is enough)


def cams_history(stations: dict[str, tuple[float, float]], start: datetime, end: datetime) -> dict[str, dict[str, Any]]:
    ids = sorted(stations)
    url = (f"{CAMS_URL}?latitude={','.join(str(stations[i][1]) for i in ids)}"
           f"&longitude={','.join(str(stations[i][0]) for i in ids)}"
           f"&hourly={','.join(CAMS_VAR.values())}&start_date={start:%Y-%m-%d}&end_date={end:%Y-%m-%d}"
           f"&timezone=GMT&domains=cams_europe")
    answer = json.loads(http.get_bytes(url, timeout_s=180.0).decode("utf-8"))
    if isinstance(answer, dict):
        answer = [answer]
    out: dict[str, dict[str, Any]] = {}
    for sid, a in zip(ids, answer):
        hourly = a["hourly"]
        index = {datetime.fromisoformat(t).replace(tzinfo=timezone.utc): k for k, t in enumerate(hourly["time"])}
        out[sid] = {"index": index, **{k: hourly[v] for k, v in CAMS_VAR.items()}}
    return out


def cams_mean(cams: dict[str, Any], key: str, end: datetime, hours: int) -> float | None:
    vals = []
    for h in range(hours):
        k = cams["index"].get(end - timedelta(hours=h + 1))
        if k is not None and cams[key][k] is not None:
            vals.append(float(cams[key][k]))
    return float(np.mean(vals)) if len(vals) >= 0.75 * hours else None


def _motor_lines() -> Any:
    import pyarrow.parquet as pq  # type: ignore[import-untyped]

    from twin.beliefs import landuse

    if not SEGMENTS.exists():
        raise SystemExit(f"{SEGMENTS} missing: run scripts/fetch_overture_roads.py first")
    t = pq.read_table(SEGMENTS, columns=["geometry", "class"])
    keep = [i for i, c in enumerate(t.column("class").to_pylist()) if c in landuse.MOTOR_CLASSES]
    geoms = t.column("geometry").to_pylist()
    return landuse.project_lines([geoms[i] for i in keep])


def station_covariate(stations: dict[str, tuple[float, float]]) -> dict[str, float]:
    from twin.beliefs import landuse

    ids = sorted(stations)
    vals = landuse.road_length_within(_motor_lines(), [stations[i][0] for i in ids], [stations[i][1] for i in ids],
                                      LUR_RADIUS_M)
    return {sid: float(v) for sid, v in zip(ids, vals)}


def write_cell_covariates() -> None:
    """Road length around every H3 cell centre of the city grid (config/areas.yaml), for the live layer."""
    import yaml

    from twin.beliefs import landuse
    from twin.beliefs.grid import cell_center, cells_in_bbox

    areas = yaml.safe_load(Path("config/areas.yaml").read_text(encoding="utf-8"))
    cells = cells_in_bbox(tuple(areas["city"]["bbox"]), int(areas["grid"]["city_resolution"]))
    centres = [cell_center(c) for c in cells]
    vals = landuse.road_length_within(_motor_lines(), [c[0] for c in centres], [c[1] for c in centres], LUR_RADIUS_M)
    COVARIATE_OUT.parent.mkdir(parents=True, exist_ok=True)
    with COVARIATE_OUT.open("w", encoding="utf-8") as f:
        f.write("cell,value\n")
        for c, v in zip(cells, vals):
            f.write(f"{c},{v:.1f}\n")
    print(f"{len(cells)} cells -> {COVARIATE_OUT}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--split", default="2026-09-01")
    p.add_argument("--out", default="docs/air_fusion_fit.md")
    p.add_argument("--json", default="docs/air_fusion_fit.json")
    p.add_argument("--no-land-use", dest="land_use", action="store_false", help="fit NO2 without the road term")
    p.add_argument("--covariates", action="store_true", help="also write the per-cell road table for the whole city")
    p.add_argument("--only", nargs="+", choices=sorted(LAYER), help="fit these pollutants and keep the others' saved results")
    args = p.parse_args()
    split = datetime.fromisoformat(args.split).replace(tzinfo=timezone.utc)
    end = datetime.now(timezone.utc)
    start = datetime(end.year, 1, 1, tzinfo=timezone.utc)
    obs = list(EeaHourlyProvider().fetch(ROME_BBOX, start, end))
    stations = {o.entity_id: (o.lon, o.lat) for o in obs}
    cams = cams_history(stations, start, end)
    specs = load_specs()
    rules = CalibrationRules.from_config(load_calibration_rules())
    random.seed(20261114)

    covariate = station_covariate(stations) if args.land_use else None
    if args.covariates:
        write_cell_covariates()

    results: dict[str, Any] = {}
    if args.only and Path(args.json).exists():
        results = json.loads(Path(args.json).read_text(encoding="utf-8")).get("results", {})
    for key, layer_name in LAYER.items():
        if args.only and key not in args.only:
            continue
        spec = specs[layer_name]
        pairs: list[tuple[Observation, float]] = []
        for o in obs:
            if key in o.values:
                c = cams_mean(cams[o.entity_id], key, o.observed_at, PERIOD_H[key])
                if c is not None:
                    pairs.append((o, c))
        train = [(o, c) for o, c in pairs if o.observed_at < split]
        test = [(o, c) for o, c in pairs if o.observed_at >= split]
        bias = learn.fit_bias([o.values[key] for o, _ in train], [c for _, c in train])
        # Land-use term (LUR_KEYS): station = a + b * CAMS + g * (road length - mean at stations).
        lur = covariate if key in LUR_KEYS else None
        center = float(np.mean(list(lur.values()))) if lur else 0.0

        def coefs(rows: list[tuple[Observation, float]]) -> Any:
            cols = [np.ones(len(rows)), np.array([c for _, c in rows])]
            if lur:
                cols.append(np.array([lur[o.entity_id] - center for o, _ in rows]))
            return np.linalg.lstsq(np.column_stack(cols), np.array([o.values[key] for o, _ in rows]), rcond=None)[0]

        def model(o: Observation, c: float, k: Any) -> float:
            return float(k[0] + k[1] * c + (k[2] * (lur[o.entity_id] - center) if lur else 0.0))

        full = coefs(train)
        if lur:
            bias = learn.BiasFit(offset=float(full[0]), scale=float(full[1]), n=len(train), residual_sd=float(
                np.std([o.values[key] - model(o, c, full) for o, c in train])))

        by_time: dict[datetime, list[tuple[Observation, float]]] = defaultdict(list)
        for o, c in train:
            by_time[o.observed_at].append((o, c))
        moments = [g for g in by_time.values() if len(g) >= 5]
        if len(moments) > MAX_GROUPS:
            moments = random.sample(moments, MAX_GROUPS)
        groups = [learn.SpatialGroup(
            xy=np.array(local_xy_km([(o.lon, o.lat) for o, _ in g]), dtype=np.float64),
            residual=np.array([o.values[key] - model(o, c, full) for o, c in g]),
        ) for g in moments]
        fitted = learn.fit_covariance(groups)
        # The fitted local part also holds the stations' own measurement error, which the layer
        # adds separately from each reading's sigma: take it out so it is not counted twice.
        meas_var = float(np.mean([o.sigma.get(key, 0.0) ** 2 for o, _ in train]))
        cov = replace(fitted, nugget_sd=math.sqrt(max(fitted.nugget_sd**2 - meas_var, 0.0)))
        series: dict[str, dict[datetime, float]] = defaultdict(dict)
        for o, c in train:
            series[o.entity_id][o.observed_at] = o.values[key] - model(o, c, full)
        memory = learn.fit_persistence(series, LAGS_H[key])
        tau = min(memory.tau_hours, 168.0)

        test_obs = [o for o, _ in test]
        old = leave_one_station_out(spec, test_obs, rules)  # a new layer: its starting (unlearned) settings
        raw_cams = {(o.entity_id, o.observed_at): c for o, c in test}
        cams_sd = float(np.median([max(1.0, 0.5 * c) for _, c in test]))  # the live layer's CAMS sigma (50%)
        cams_only = leave_one_station_out(spec, test_obs, rules, prior_means=raw_cams, prior_sd=cams_sd)
        field = spec.prior_field or FieldSpec(source="air_quality_model", entity_types=("AirQualityForecast",),
                                              value_key=key, method="idw")
        learned_spec: LayerSpec = replace(
            spec, correlation_length_km=cov.length_km, relax_tau_hours=tau, spatial_share=cov.spatial_share,
            prior_field=replace(field, offset=bias.offset, scale=bias.scale, sd=cov.total_sd))
        # Held-out check: a station's starting value never uses a land-use slope fitted on itself.
        per_station = ({sid: coefs([(o, c) for o, c in train if o.entity_id != sid]) for sid in lur}
                       if lur else {})
        corrected = {(o.entity_id, o.observed_at): model(o, c, per_station.get(o.entity_id, full)) for o, c in test}
        new = leave_one_station_out(learned_spec, test_obs, rules, prior_means=corrected, prior_sd=cov.total_sd)
        if lur:
            y = {sid: float(np.mean([o.values[key] - (full[0] + full[1] * c) for o, c in train if o.entity_id == sid]))
                 for sid in lur}
            loo = [y[sid] - float(per_station[sid][2] * (lur[sid] - center)) for sid in lur]
            land_use = {"covariate": f"motor road length within {LUR_RADIUS_M:.0f} m", "slope_per_m": round(float(full[2]), 5),
                        "center_m": round(center, 1), "station_offsets_sd": round(float(np.std(list(y.values()))), 2),
                        "station_offsets_sd_left_out": round(float(np.sqrt(np.mean(np.square(loo)))), 2),
                        "stations": {sid[-7:]: {"road_m": round(lur[sid], 1), "offset": round(y[sid], 2)} for sid in lur}}
        else:
            land_use = None

        results[layer_name] = {
            "train_readings": len(train), "test_readings": len(test), "stations": len(series),
            "bias": {"offset": round(bias.offset, 2), "scale": round(bias.scale, 3), "residual_sd": round(bias.residual_sd, 2),
                     "mean_obs": round(float(np.mean([o.values[key] for o, _ in train])), 2),
                     "mean_cams": round(float(np.mean([c for _, c in train])), 2)},
            "covariance": {"sd": round(cov.sd, 2), "length_km": round(cov.length_km, 2), "nugget_sd": round(cov.nugget_sd, 2),
                           "total_sd": round(cov.total_sd, 2), "spatial_share": round(cov.spatial_share, 3),
                           "fitted_local_sd_with_measurement": round(fitted.nugget_sd, 2),
                           "measurement_sd": round(math.sqrt(meas_var), 2),
                           "moments": cov.n_groups},
            "memory": {"tau_hours": round(tau, 1), "lag_correlations": [[lag, round(r, 3)] for lag, r in memory.correlations]},
            "check_old_settings": old.as_dict(),
            "check_cams_uncorrected": cams_only.as_dict(),
            "check_learned": new.as_dict(),
            "land_use": land_use,
        }
        print(layer_name, json.dumps(results[layer_name]))

    Path(args.json).write_text(json.dumps({"split": args.split, "window": [f"{start:%Y-%m-%d}", f"{end:%Y-%m-%d %H:%M}"],
                                           "results": results}, indent=2), encoding="utf-8")
    Path(args.out).write_text(report(results, args.split, start, end, rules), encoding="utf-8")
    print(f"wrote {args.out} and {args.json}")


def _fmt(d: dict[str, Any]) -> str:
    cov = "-" if d["coverage"] is None else f"{d['coverage']:.0%}"
    return f"{d['status']} | {cov} | {d['z_sd']} | {d['rmse']}"


def report(results: dict[str, Any], split: str, start: datetime, end: datetime, rules: CalibrationRules) -> str:
    lines = ["# Air-quality fusion learned from real data", "",
             f"Data: EEA up-to-date station files for Rome, {start:%d %b %Y} to {end:%d %b %Y %H:%M} UTC, and the CAMS "
             "European forecast at each station (Open-Meteo archive). NO2 and O3 are hourly; PM10 and PM2.5 are daily means.",
             f"Settings are fitted on readings before {split} and checked on readings after it (never seen by the fit), "
             f"by hiding one station at a time and testing the {rules.interval:.0%} range.", "",
             "## What was learned", "",
             "| Layer | CAMS bias: station = a + b x CAMS | CAMS error left (sd) | shared part sd | reach L | local part sd (minus station error) | memory tau |",
             "|---|---|---|---|---|---|---|"]
    for name, r in results.items():
        b, c, m = r["bias"], r["covariance"], r["memory"]
        lines.append(f"| {name} | {b['offset']} + {b['scale']} x CAMS (station mean {b['mean_obs']}, CAMS mean {b['mean_cams']}) "
                     f"| {c['total_sd']} | {c['sd']} | {c['length_km']} km | {c['nugget_sd']} ({c['fitted_local_sd_with_measurement']} - {c['measurement_sd']}) | {m['tau_hours']} h |")
    lines += ["", "## Honesty check on held-out months", "",
              "| Layer | Settings | Status | Coverage of 90% range | Spread of z (1 = honest) | RMSE |", "|---|---|---|---|---|---|"]
    for name, r in results.items():
        lines.append(f"| {name} | no map, one city-wide value | {_fmt(r['check_old_settings'])} |")
        lines.append(f"| {name} | CAMS as is, 50% sigma | {_fmt(r['check_cams_uncorrected'])} |")
        lines.append(f"| {name} | **learned** | {_fmt(r['check_learned'])} |")
    for name, r in results.items():
        lu = r.get("land_use")
        if lu:
            lines += ["", f"## Land-use term for {name}", "",
                      f"Covariate: {lu['covariate']} (Overture roads). Slope {lu['slope_per_m'] * 100:.2f} ug/m3 per 100 m of road, "
                      f"centred on the station mean ({lu['center_m']} m). The stations' lasting differences from the corrected "
                      f"CAMS have a spread of {lu['station_offsets_sd']} ug/m3; predicting each station from a slope fitted on the "
                      f"others leaves {lu['station_offsets_sd_left_out']} ug/m3.", "",
                      "| Station | Road within 100 m (m) | Lasting offset (ug/m3) |", "|---|---|---|"]
            lines += [f"| {sid} | {v['road_m']} | {v['offset']} |" for sid, v in lu["stations"].items()]
    lines += ["", "Before this upgrade the live NO2 layer had a held-out RMSE of 12.8 ug/m3 (fixed guesses: reach 3 km, "
              "memory 3 h, no bias correction; first run of this script on 14 Nov 2026).", "",
              "## How to read this", "",
              "- CAMS is a 10 km regional model, so it misses part of the city's own pollution; the bias fit corrects that on average.",
              "- The shared part of the error spreads over the reach L; the local part (a station by a busy road) stays in its own cell.",
              "- A long reach for PM means CAMS is wrong by about the same amount everywhere in the city on a given day.",
              "- Memory tau is how long a reading keeps informing the map when the station goes silent.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
