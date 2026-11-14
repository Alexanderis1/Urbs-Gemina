"""Compare the emergency access model's travel times with official 118 response times.

The road-graph model needs an OpenStreetMap network per area; for a citywide check this script uses the
model's own off-network rule (straight-line distance x detour factor at the emergency speed) from the
nearest emergency hospital to every census section, weighted by residents. The reference is the
national LEA indicator D09Z (alarm-to-target time, 75th percentile) for Lazio, stored in
config/scenarios.yaml (emergency_access.observed_response).

Usage: python scripts/validate_access.py [--out eval/scenarios/access_validation.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twin.scenarios import config, layers  # noqa: E402
from twin.scenarios.geometry import centroid  # noqa: E402
from twin.scenarios.terrain import to_utm  # noqa: E402


def weighted_quantiles(values: np.ndarray, weights: np.ndarray, qs: tuple[float, ...]) -> dict[str, float]:
    order = np.argsort(values)
    cum = np.cumsum(weights[order])
    return {f"p{round(q * 100)}": round(float(values[order][np.searchsorted(cum, q * cum[-1])]), 1) for q in qs}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "eval/scenarios/access_validation.json"))
    args = parser.parse_args()
    cfg = config.load("scenarios.yaml")["emergency_access"]
    hosp_path, census_path = layers.find("emergency_hospitals.geojson"), layers.find("census_sections.geojson")
    if hosp_path is None or census_path is None:
        sys.exit("emergency_hospitals.geojson and census_sections.geojson are needed (scripts/fetch_static_layers.py)")
    hospitals = layers.read(hosp_path)["features"]
    hx, hy = to_utm([f["geometry"]["coordinates"][0] for f in hospitals],
                    [f["geometry"]["coordinates"][1] for f in hospitals])
    sections = [f for f in layers.read(census_path)["features"] if f.get("geometry")]
    cents = [centroid(f["geometry"]) for f in sections]
    residents = np.asarray([float((f.get("properties") or {}).get("residents") or 0) for f in sections])
    cx, cy = to_utm([c[0] for c in cents], [c[1] for c in cents])
    from scipy.spatial import cKDTree  # type: ignore[import-untyped]

    dist, _ = cKDTree(np.column_stack([hx, hy])).query(np.column_stack([cx, cy]))
    speed = float(cfg["urban_speed_cap_kmh"]["value"]) / 3.6 * float(cfg["speed_factor"]["value"])
    minutes = np.asarray(dist) * float(cfg["off_network_detour"]["value"]) / speed / 60
    observed = cfg["observed_response"]["value"]
    model = weighted_quantiles(minutes, residents, (0.5, 0.75, 0.95))
    out: dict[str, Any] = {
        "method": "nearest emergency hospital, straight line x detour at the emergency speed, residents-weighted",
        "hospitals": len(hospitals), "sections": len(sections), "residents": int(residents.sum()),
        "model_travel_min": model,
        "observed_alarm_to_target_p75_min": observed["lazio_p75_min"],
        "observed_source": observed["source"],
        "gap_p75_min": round(float(observed["lazio_p75_min"]) - model["p75"], 1),
    }
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
