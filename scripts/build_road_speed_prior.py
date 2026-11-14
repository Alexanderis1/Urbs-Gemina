"""Per-cell free-flow speed for the road speed layer's starting map (road_speed).

    python scripts/build_road_speed_prior.py [--out /mnt/project-files/model/road_free_flow_kmh.csv]

Input (real, open): Overture Maps transportation segments (ODbL), data/raw/overture/segments.parquet.
For every H3 cell of the city grid: metres of each motor road class within ``radius_m`` of the
centre, then the length-weighted free-flow speed from the per-class speeds in config/beliefs.yaml
(road_speed.prior_field.covariate). Cells without motor roads are left out (they keep the city profile).
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from twin.beliefs import landuse
from twin.beliefs.grid import cell_center, cells_in_bbox

SEGMENTS = Path("data/raw/overture/segments.parquet")


def _value(node: Any) -> Any:
    return node["value"] if isinstance(node, dict) and "value" in node else node


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="/mnt/project-files/model/road_free_flow_kmh.csv")
    args = p.parse_args()

    import pyarrow.parquet as pq  # type: ignore[import-untyped]
    import shapely  # type: ignore[import-untyped]

    cov = yaml.safe_load(Path("config/beliefs.yaml").read_text(encoding="utf-8"))["layers"]["road_speed"]["prior_field"]["covariate"]
    speeds = {str(k): float(v) for k, v in _value(cov["free_flow_kmh_by_class"]).items()}
    radius = float(_value(cov["radius_m"]))

    table = pq.read_table(SEGMENTS, columns=["geometry", "class"])
    classes = table.column("class").to_pylist()
    keep = [i for i, c in enumerate(classes) if c in speeds]
    lines = landuse.project_lines([table.column("geometry")[i].as_py() for i in keep])
    line_class = np.array([classes[i] for i in keep])
    tree = shapely.STRtree(lines)

    areas = yaml.safe_load(Path("config/areas.yaml").read_text(encoding="utf-8"))
    cells = cells_in_bbox(tuple(areas["city"]["bbox"]), int(areas["grid"]["city_resolution"]))
    centres = [cell_center(c) for c in cells]
    xs, ys = landuse._to_m([c[0] for c in centres], [c[1] for c in centres])

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    values: list[float] = []
    with out.open("w", encoding="utf-8") as f:
        f.write("cell,value\n")
        for cell, x, y in zip(cells, xs, ys):
            circle = shapely.buffer(shapely.Point(x, y), radius, quad_segs=16)
            idx = tree.query(circle)
            if not len(idx):
                continue
            lengths = shapely.length(shapely.intersection(lines[idx], circle))
            by_class: dict[str, float] = defaultdict(float)
            for k, m in zip(idx, lengths):
                by_class[str(line_class[k])] += float(m)
            v = landuse.free_flow_speed(dict(by_class), speeds)
            if v is not None:
                f.write(f"{cell},{v:.1f}\n")
                values.append(v)
    arr = np.array(values)
    print(f"{len(values)} of {len(cells)} cells -> {out}; free-flow km/h: median {np.median(arr):.0f}, "
          f"P5 {np.percentile(arr, 5):.0f}, P95 {np.percentile(arr, 95):.0f}")


if __name__ == "__main__":
    main()
