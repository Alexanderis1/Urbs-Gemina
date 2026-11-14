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


def _travel_minutes(starts: list[dict[str, Any]], cx: np.ndarray, cy: np.ndarray, cfg: dict[str, Any]) -> np.ndarray:
    from scipy.spatial import cKDTree  # type: ignore[import-untyped]

    hx, hy = to_utm([f["geometry"]["coordinates"][0] for f in starts], [f["geometry"]["coordinates"][1] for f in starts])
    dist, _ = cKDTree(np.column_stack([hx, hy])).query(np.column_stack([cx, cy]))
    speed = float(cfg["urban_speed_cap_kmh"]["value"]) / 3.6 * float(cfg["speed_factor"]["value"])
    minutes: np.ndarray = np.asarray(dist) * float(cfg["off_network_detour"]["value"]) / speed / 60
    return minutes


def busy_post_response(starts: list[dict[str, Any]], cx: np.ndarray, cy: np.ndarray, residents: np.ndarray,
                       cfg: dict[str, Any], pre_min: float, busy: float) -> float:
    """P75 response when each post is busy with probability `busy`: the first free post (in distance order) goes."""
    from scipy.spatial import cKDTree

    hx, hy = to_utm([f["geometry"]["coordinates"][0] for f in starts], [f["geometry"]["coordinates"][1] for f in starts])
    k = len(starts)
    dist, _ = cKDTree(np.column_stack([hx, hy])).query(np.column_stack([cx, cy]), k=k)
    speed = float(cfg["urban_speed_cap_kmh"]["value"]) / 3.6 * float(cfg["speed_factor"]["value"])
    minutes = np.asarray(dist) * float(cfg["off_network_detour"]["value"]) / speed / 60 + pre_min
    p = (1 - busy) * busy ** np.arange(k)  # chance that the j-th nearest post is the first free one
    p[-1] += 1 - p.sum()
    vals = minutes.ravel()
    w = (residents[:, None] * p[None, :]).ravel()
    return weighted_quantiles(vals, w, (0.75,))["p75"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "eval/scenarios/access_validation.json"))
    args = parser.parse_args()
    cfg = config.load("scenarios.yaml")["emergency_access"]
    census_path = layers.find("census_sections.geojson")
    if census_path is None:
        sys.exit("census_sections.geojson is needed (scripts/fetch_static_layers.py)")
    sections = [f for f in layers.read(census_path)["features"] if f.get("geometry")]
    cents = [centroid(f["geometry"]) for f in sections]
    residents = np.asarray([float((f.get("properties") or {}).get("residents") or 0) for f in sections])
    ux, uy = to_utm([c[0] for c in cents], [c[1] for c in cents])
    cx, cy = np.asarray(ux), np.asarray(uy)
    pre = cfg["pre_travel_min"]["value"]["ambulance"]
    observed = cfg["observed_response"]["value"]
    out: dict[str, Any] = {
        "method": "nearest start point, straight line x detour at the emergency speed, residents-weighted; "
                  "response = call handling and dispatch (median) + travel",
        "sections": len(sections), "residents": int(residents.sum()),
        "pre_travel_median_min": pre["median"],
        "observed_alarm_to_target_p75_min": observed["lazio_p75_min"], "observed_source": observed["source"],
        "starts": {},
    }
    for label, file_name in (("ares118_posts", "ares118_posts.geojson"),
                             ("emergency_hospitals", "emergency_hospitals.geojson")):
        path = layers.find(file_name)
        if path is None:
            continue
        starts = layers.read(path)["features"]
        travel = weighted_quantiles(_travel_minutes(starts, cx, cy, cfg), residents, (0.5, 0.75, 0.95))
        response = {k: round(v + float(pre["median"]), 1) for k, v in travel.items()}
        out["starts"][label] = {"count": len(starts), "model_travel_min": travel, "model_response_min": response,
                                "gap_p75_min": round(float(observed["lazio_p75_min"]) - response["p75"], 1)}
        if label == "ares118_posts":
            out["starts"][label]["p75_response_if_posts_busy"] = {
                f"{round(b * 100)}%": busy_post_response(starts, cx, cy, residents, cfg, float(pre["median"]), b)
                for b in (0.3, 0.5, 0.7, 0.8, 0.9)}
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
