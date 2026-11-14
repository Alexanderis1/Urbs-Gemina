"""Walking network of Rome from Overture Maps road segments (ODbL), and network distances.

Replaces the straight-line x detour-factor reach: a resident is covered when the
shortest walk along real streets, footways, steps and squares to a facility is
within the walking budget. Points are snapped to the nearest graph node and the
snap distance is walked too. Motorways, trunk roads and rail are not walkable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

from twin.physics.buildings import parse_wkb, to_local
from twin.scenarios.geometry import EARTH_RADIUS_M

F64 = NDArray[np.float64]
NOT_WALKABLE = frozenset({"motorway", "trunk"})
LON0, LAT0 = 12.4964, 41.9028  # local frame origin (Rome centre)


def _wkb_line(blob: bytes) -> list[tuple[float, float]]:
    import struct

    order = "<" if blob[0] == 1 else ">"
    (kind,) = struct.unpack_from(order + "I", blob, 1)
    base = kind % 1000 if kind < 0x80000000 else kind & 0xFF
    dims = 3 if (1000 < kind < 2000 or kind & 0x80000000) else 2
    if base != 2:
        polys = parse_wkb(blob)  # not a line: use the outline
        return [p for ring in polys[0] for p in ring] if polys else []
    (n,) = struct.unpack_from(order + "I", blob, 5)
    vals = struct.unpack_from(order + "d" * (n * dims), blob, 9)
    return [(vals[i * dims], vals[i * dims + 1]) for i in range(n)]


def _haversine(lon: F64, lat: F64) -> F64:
    p = np.radians(lat)
    dp, dl = np.diff(p), np.radians(np.diff(lon))
    a = np.sin(dp / 2) ** 2 + np.cos(p[:-1]) * np.cos(p[1:]) * np.sin(dl / 2) ** 2
    return np.asarray(2 * EARTH_RADIUS_M * np.arcsin(np.minimum(1.0, np.sqrt(a))), dtype=np.float64)


@dataclass
class WalkGraph:
    node_lon: F64
    node_lat: F64
    edge_u: NDArray[np.int64]
    edge_v: NDArray[np.int64]
    edge_m: F64

    @property
    def node_count(self) -> int:
        return int(self.node_lon.size)

    @property
    def edge_count(self) -> int:
        return int(self.edge_u.size)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            np.savez_compressed(fh, node_lon=self.node_lon, node_lat=self.node_lat, edge_u=self.edge_u,
                                edge_v=self.edge_v, edge_m=self.edge_m.astype(np.float32))

    @classmethod
    def load(cls, path: Path) -> WalkGraph:
        z = np.load(path)
        return cls(z["node_lon"], z["node_lat"], z["edge_u"].astype(np.int64), z["edge_v"].astype(np.int64),
                   z["edge_m"].astype(np.float64))

    def matrix(self) -> Any:
        from scipy.sparse import coo_matrix  # type: ignore[import-untyped]

        n = self.node_count
        return coo_matrix((self.edge_m, (self.edge_u, self.edge_v)), shape=(n, n)).tocsr()


def graph_from_segments(rows: Iterable[Mapping[str, Any]]) -> WalkGraph:
    """Overture transportation segments (geometry WKB, subtype, class, connectors) -> walking graph."""
    ids: dict[str, int] = {}
    lons: list[float] = []
    lats: list[float] = []
    us: list[int] = []
    vs: list[int] = []
    ms: list[float] = []
    for row in rows:
        if row.get("subtype") != "road" or row.get("class") in NOT_WALKABLE:
            continue
        conns = sorted(row.get("connectors") or [], key=lambda c: float(c["at"]))
        if len(conns) < 2:
            continue
        pts = np.asarray(_wkb_line(bytes(row["geometry"])), dtype=np.float64)
        if pts.shape[0] < 2:
            continue
        seg = _haversine(pts[:, 0], pts[:, 1])
        cum = np.concatenate([[0.0], np.cumsum(seg)])
        total = float(cum[-1])
        if total <= 0:
            continue
        prev = None
        for c in conns:
            at = min(max(float(c["at"]), 0.0), 1.0)
            cid = str(c["connector_id"])
            if cid not in ids:
                ids[cid] = len(lons)
                lons.append(float(np.interp(at * total, cum, pts[:, 0])))
                lats.append(float(np.interp(at * total, cum, pts[:, 1])))
            node = ids[cid]
            if prev is not None and prev[0] != node:
                length = (at - prev[1]) * total
                us.extend([prev[0], node])
                vs.extend([node, prev[0]])
                ms.extend([length, length])
            prev = (node, at)
    edges = WalkGraph(np.asarray(lons), np.asarray(lats), np.asarray(us, dtype=np.int64),
                      np.asarray(vs, dtype=np.int64), np.maximum(np.asarray(ms, dtype=np.float64), 0.01))
    # one undirected edge counted once in edge_count
    keep = edges.edge_u < edges.edge_v
    return WalkGraph(edges.node_lon, edges.node_lat, edges.edge_u[keep], edges.edge_v[keep], edges.edge_m[keep])


def _snap(graph: WalkGraph, points: Sequence[tuple[float, float]]) -> tuple[NDArray[np.int64], F64]:
    from scipy.spatial import cKDTree  # type: ignore[import-untyped]

    nx, ny = to_local(graph.node_lon, graph.node_lat, LON0, LAT0)
    tree = cKDTree(np.column_stack([nx, ny]))
    px, py = to_local(np.array([p[0] for p in points], dtype=np.float64),
                      np.array([p[1] for p in points], dtype=np.float64), LON0, LAT0)
    dist, idx = tree.query(np.column_stack([px, py]))
    return np.asarray(idx, dtype=np.int64), np.asarray(dist, dtype=np.float64)


def nearest_facility_m(graph: WalkGraph, facilities: Sequence[tuple[float, float]],
                       people: Sequence[tuple[float, float]], max_snap_m: float = 300.0,
                       limit_m: float = math.inf) -> F64:
    """Walking distance from each person to the nearest facility (inf if none, or too far from any street)."""
    from scipy.sparse.csgraph import dijkstra  # type: ignore[import-untyped]

    out = np.full(len(people), np.inf)
    if not facilities or not people or graph.node_count == 0:
        return out
    f_node, f_snap = _snap(graph, facilities)
    p_node, p_snap = _snap(graph, people)
    ok_f = f_snap <= max_snap_m
    if not ok_f.any():
        return out
    # Multi-source Dijkstra; the facility's own snap walk is added with a virtual source node.
    n = graph.node_count
    from scipy.sparse import coo_matrix, vstack, hstack

    base = graph.matrix()
    sym = base + base.T
    src = coo_matrix((f_snap[ok_f] + 0.01, (np.zeros(int(ok_f.sum()), dtype=np.int64), f_node[ok_f])), shape=(1, n))
    big = vstack([hstack([coo_matrix((1, 1)), src]), hstack([coo_matrix((n, 1)), sym])]).tocsr()
    dist = dijkstra(big, directed=True, indices=0, limit=limit_m)[1:]
    reach = dist[p_node] + p_snap
    out = np.where(p_snap <= max_snap_m, reach, np.inf)
    return np.asarray(out, dtype=np.float64)


def default_paths() -> list[Path]:
    root = Path(__file__).resolve().parents[3]
    return [root / "data" / "model" / "walk_graph.npz", Path("/mnt/project-files/model/walk_graph.npz")]


def load_default() -> WalkGraph | None:
    for path in default_paths():
        if path.exists():
            return WalkGraph.load(path)
    return None
