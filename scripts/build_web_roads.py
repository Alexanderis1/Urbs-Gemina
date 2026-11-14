"""Main roads of Rome as one small file for the web app, so traffic can be drawn along the streets.

    python scripts/build_web_roads.py [--out web/public/roads-rome.json]

Input (real, open): Overture Maps transportation segments (ODbL), read from the public bucket for the
release in config/model.yaml and the city box in config/areas.yaml. Kept: motor roads of the classes
below. Output: {"classes": [...], "roads": [[class index, [lon, lat, lon, lat, ...]], ...]}, coordinates
rounded to 5 decimals (about 1 m), shapes simplified.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import yaml

BUCKET = "overturemaps-us-west-2"
# Basis: the road classes that carry through traffic; smaller streets would triple the file for little gain at city zoom.
CLASSES = ["motorway", "trunk", "primary", "secondary", "tertiary"]
# Basis: 4 m is below the width of one lane, so the simplified line stays on the carriageway.
SIMPLIFY_M = 4.0


def fetch_segments(bbox: tuple[float, float, float, float], release: str) -> Any:
    import pyarrow.compute as pc  # type: ignore[import-untyped]
    import pyarrow.dataset as ds  # type: ignore[import-untyped]
    import pyarrow.fs as pafs  # type: ignore[import-untyped]

    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    kwargs: dict[str, Any] = {"anonymous": True, "region": "us-west-2"}
    if proxy:
        kwargs["proxy_options"] = proxy
    fs = pafs.S3FileSystem(**kwargs)
    dataset = ds.dataset(f"{BUCKET}/release/{release}/theme=transportation/type=segment/", filesystem=fs, format="parquet")
    xmin, ymin, xmax, ymax = bbox
    def f(name: str) -> Any:
        return pc.field("bbox", name)

    inside = (f("xmin") < xmax) & (f("xmax") > xmin) & (f("ymin") < ymax) & (f("ymax") > ymin)
    wanted = inside & (pc.field("subtype") == "road") & pc.field("class").isin(CLASSES)
    return dataset.to_table(columns=["geometry", "class"], filter=wanted)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="web/public/roads-rome.json")
    args = p.parse_args()

    import shapely  # type: ignore[import-untyped]

    release = str(yaml.safe_load(Path("config/model.yaml").read_text(encoding="utf-8"))["footprints"]["release"])
    bbox = tuple(float(v) for v in yaml.safe_load(Path("config/areas.yaml").read_text(encoding="utf-8"))["city"]["bbox"])
    table = fetch_segments(bbox, release)  # type: ignore[arg-type]
    classes = table.column("class").to_pylist()
    lines = shapely.from_wkb([g.as_py() for g in table.column("geometry")])
    lines = shapely.simplify(lines, SIMPLIFY_M / 111_320.0, preserve_topology=False)
    box = shapely.box(*bbox)
    roads: list[list[Any]] = []
    for line, cls in zip(lines, classes):
        if line is None or line.is_empty or not line.intersects(box):
            continue
        parts = line.geoms if line.geom_type == "MultiLineString" else [line]
        for part in parts:
            flat = [round(float(v), 5) for xy in part.coords for v in xy[:2]]
            if len(flat) >= 4:
                roads.append([CLASSES.index(cls), flat])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"classes": CLASSES, "source": f"Overture Maps {release} (ODbL)", "roads": roads}, separators=(",", ":")), encoding="utf-8")
    print(f"{len(roads)} roads, {out.stat().st_size / 1e6:.1f} MB -> {out}")


if __name__ == "__main__":
    main()
