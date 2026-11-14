"""Download Overture Maps road segments (and their connectors) for Roma Capitale.

    python scripts/fetch_overture_roads.py [--release 2026-10-21.0]

Output: data/raw/overture/segments.parquet (git-ignored). Licence: ODbL (OpenStreetMap-derived).
Used by scripts/build_walk_graph.py for real walking distances.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

BBOX = (12.234, 41.655, 12.856, 42.141)


def main() -> None:
    import pyarrow.dataset as ds  # type: ignore[import-untyped]
    import pyarrow.fs as pafs  # type: ignore[import-untyped]
    import pyarrow.parquet as pq  # type: ignore[import-untyped]

    p = argparse.ArgumentParser()
    p.add_argument("--release", default="2026-10-21.0")
    p.add_argument("--out", default="data/raw/overture/segments.parquet")
    args = p.parse_args()
    s3 = pafs.S3FileSystem(anonymous=True, region="us-west-2")
    path = f"overturemaps-us-west-2/release/{args.release}/theme=transportation/type=segment"
    data = ds.dataset(path, filesystem=s3, format="parquet")
    x0, y0, x1, y1 = BBOX
    flt = ((ds.field("bbox", "xmax") >= x0) & (ds.field("bbox", "xmin") <= x1)
           & (ds.field("bbox", "ymax") >= y0) & (ds.field("bbox", "ymin") <= y1))
    t = time.time()
    table = data.to_table(columns=["id", "geometry", "subtype", "class", "connectors", "bbox"], filter=flt)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out)
    print(f"{table.num_rows} segments -> {out} in {time.time() - t:.0f} s (Overture {args.release}, ODbL)")


if __name__ == "__main__":
    main()
