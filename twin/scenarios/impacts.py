"""Who and what lies in a hazard footprint: residents (census) and sensitive sites. Aggregates only."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from twin.scenarios import config, layers
from twin.scenarios.data import ScenarioData
from twin.scenarios.exposure import load_census
from twin.scenarios.terrain import BoolArray, FloatArray, Grid, rasterize_index

COUNTS = ("residents", "children_0_14")


def _file(key: str) -> str:
    return str(config.value(config.load("scenarios.yaml")["impacts"], key))


def residents(grid: Grid, data: ScenarioData, footprints: Mapping[str, BoolArray]) -> dict[str, Any] | None:
    """Residents and children living in each footprint, sharing a section's people by its flooded share."""
    census = load_census(data)
    if census is None:
        return None
    features = [f for f in census.get("features", []) if f.get("geometry")]
    index = rasterize_index(grid, [f["geometry"] for f in features])
    inside = index >= 0
    n = len(features)
    cells = np.bincount(index[inside], minlength=n).astype(np.float64)
    counts = {c: np.asarray([float((f.get("properties") or {}).get(c) or 0) for f in features]) for c in COUNTS}
    out: dict[str, Any] = {}
    for name, mask in footprints.items():
        hit = np.bincount(index[inside & mask], minlength=n).astype(np.float64)
        share = np.divide(hit, cells, out=np.zeros(n), where=cells > 0)
        out[name] = {c: int(round(float((share * counts[c]).sum()))) for c in COUNTS}
        out[name]["sections_touched"] = int((hit > 0).sum())
    return out


def sensitive_sites(grid: Grid, probability: FloatArray, min_probability: float,
                    limit: int = 200) -> dict[str, Any] | None:
    """Sensitive sites whose cell has at least ``min_probability`` of being hit."""
    path = layers.find(_file("sensitive_sites_file"))
    if path is None:
        return None
    feats = [f for f in layers.read(path).get("features", [])
             if (f.get("geometry") or {}).get("type") == "Point"]
    if not feats:
        return {"count": 0, "by_category": {}, "sites": []}
    lons = [float(f["geometry"]["coordinates"][0]) for f in feats]
    lats = [float(f["geometry"]["coordinates"][1]) for f in feats]
    p = grid.sample(probability, lons, lats, missing=0.0)
    hits = [(float(p[i]), feats[i]) for i in np.flatnonzero(p >= min_probability).tolist()]
    hits.sort(key=lambda h: -h[0])
    by_category: dict[str, int] = {}
    for _, f in hits:
        cat = str((f.get("properties") or {}).get("category", "other"))
        by_category[cat] = by_category.get(cat, 0) + 1
    rows: list[dict[str, Any]] = []
    for prob, f in hits[:limit]:
        props = f.get("properties") or {}
        rows.append({"name": props.get("name"), "category": props.get("category"), "subtype": props.get("subtype"),
                     "lon": round(float(f["geometry"]["coordinates"][0]), 6),
                     "lat": round(float(f["geometry"]["coordinates"][1]), 6), "probability": round(prob, 3)})
    return {"count": len(hits), "by_category": by_category, "sites": rows}


def quantiles(values: Sequence[float]) -> dict[str, float]:
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return {"p5": 0.0, "p50": 0.0, "p95": 0.0}
    p5, p50, p95 = np.percentile(arr, [5, 50, 95])
    return {"p5": round(float(p5), 3), "p50": round(float(p50), 3), "p95": round(float(p95), 3)}
