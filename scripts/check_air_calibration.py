"""Leave-one-station-out check of the air-quality belief layers on REAL EEA stations in Rome.

    python scripts/check_air_calibration.py [--days 3] [--out docs/air_calibration.md]

For each hour and each station: hide it, predict it from the prior plus the other stations,
and test whether the stated 90% range holds (twin/beliefs/calibration.py).
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from twin.beliefs.calibration import CalibrationRules, leave_one_station_out
from twin.beliefs.config import load_calibration_rules, load_specs
from twin.providers.base import ROME_BBOX
from twin.providers.open.eea import EeaHourlyProvider


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=float, default=3.0)
    p.add_argument("--out", default="docs/air_calibration.md")
    args = p.parse_args()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)
    obs = list(EeaHourlyProvider().fetch(ROME_BBOX, start, end))
    specs = load_specs()
    rules = CalibrationRules.from_config(load_calibration_rules())
    stations = sorted({o.entity_id for o in obs})
    lines = ["# Air-quality uncertainty check on real EEA stations", "",
             f"Window {start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M} UTC, {len(obs)} hourly readings from "
             f"{len(stations)} EEA stations in Rome (unverified up-to-date data). Method: leave one station out, "
             f"predict it from the prior plus the others, check the {rules.interval:.0%} range.", "",
             "| Layer | Status | Held-out predictions | Coverage of 90% range | Spread of z | RMSE | Reason |",
             "|---|---|---|---|---|---|---|"]
    results = {}
    for name in ("air_no2", "air_pm10", "air_pm25"):
        spec = specs[name]
        rep = leave_one_station_out(spec, obs, rules)
        d = rep.as_dict()
        results[name] = d
        cov = "-" if d["coverage"] is None else f"{d['coverage']:.0%}"
        lines.append(f"| {name} | {d['status']} | {d['n_predictions']} | {cov} | {d['z_sd']} | {d['rmse']} | {d['reason']} |")
        print(name, d)
    lines += ["", "```json", json.dumps({"stations": len(stations), "readings": len(obs), "results": results}, indent=2),
              "```", ""]
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
