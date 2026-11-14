"""Build Rome's walking network from Overture road segments (run scripts/fetch_overture_roads.py first).

    python scripts/build_walk_graph.py [--out /mnt/project-files/model/walk_graph.npz]
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from twin.modules.sports.network import graph_from_segments


def main() -> None:
    import pyarrow.parquet as pq  # type: ignore[import-untyped]

    p = argparse.ArgumentParser()
    p.add_argument("--segments", default="data/raw/overture/segments.parquet")
    p.add_argument("--out", default="data/model/walk_graph.npz")
    args = p.parse_args()
    t = time.time()
    rows = pq.read_table(args.segments, columns=["geometry", "subtype", "class", "connectors"]).to_pylist()
    g = graph_from_segments(rows)
    g.save(Path(args.out))
    km = float(g.edge_m.sum()) / 1000.0
    print(f"{g.node_count} nodes, {g.edge_count} edges, {km:.0f} km of walkable ways -> {args.out} ({time.time() - t:.0f} s)")


if __name__ == "__main__":
    main()
