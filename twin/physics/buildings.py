"""3D buildings (LoD1 footprints + heights) in a local metric frame, for propagation.

Read from the WS2 city model (buildings_lod1.parquet): footprint polygons as
WKB, ``height_m`` above the building's own ground and ``height_sd_m`` (one
sigma). The terrain is treated as flat inside the study radius
(config/physics.yaml ``buildings.terrain``).
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from numpy.typing import NDArray

from twin.physics import config
from twin.scenarios.geometry import EARTH_RADIUS_M

F64 = NDArray[np.float64]
Ring = list[tuple[float, float]]
Polygon = list[Ring]


# --- WKB ------------------------------------------------------------------------------

def parse_wkb(blob: bytes) -> list[Polygon]:
    """Polygon or MultiPolygon WKB (2D, or 3D with Z dropped) as a list of polygons."""
    polys, _ = _read_geometry(memoryview(blob), 0)
    return polys


def _read_geometry(buf: memoryview, pos: int) -> tuple[list[Polygon], int]:
    order = "<" if buf[pos] == 1 else ">"
    (kind,) = struct.unpack_from(order + "I", buf, pos + 1)
    pos += 5
    has_z = kind > 1000 and kind < 2000 or bool(kind & 0x80000000)
    base = kind % 1000 if kind < 0x80000000 else kind & 0xFF
    dims = 3 if has_z else 2
    if base == 3:
        poly, pos = _read_polygon(buf, pos, order, dims)
        return [poly], pos
    if base == 6:
        (n,) = struct.unpack_from(order + "I", buf, pos)
        pos += 4
        out: list[Polygon] = []
        for _ in range(n):
            sub, pos = _read_geometry(buf, pos)
            out.extend(sub)
        return out, pos
    raise ValueError(f"unsupported WKB geometry type {kind}")


def _read_polygon(buf: memoryview, pos: int, order: str, dims: int) -> tuple[Polygon, int]:
    (n_rings,) = struct.unpack_from(order + "I", buf, pos)
    pos += 4
    rings: Polygon = []
    for _ in range(n_rings):
        (n,) = struct.unpack_from(order + "I", buf, pos)
        pos += 4
        values = struct.unpack_from(order + "d" * (n * dims), buf, pos)
        pos += 8 * n * dims
        rings.append([(values[i * dims], values[i * dims + 1]) for i in range(n)])
    return rings, pos


# --- local frame -------------------------------------------------------------------------

def to_local(lon: F64, lat: F64, lon0: float, lat0: float) -> tuple[F64, F64]:
    x = np.radians(lon - lon0) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
    y = np.radians(lat - lat0) * EARTH_RADIUS_M
    return np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)


def from_local(x: F64, y: F64, lon0: float, lat0: float) -> tuple[F64, F64]:
    lon = lon0 + np.degrees(x / (EARTH_RADIUS_M * math.cos(math.radians(lat0))))
    lat = lat0 + np.degrees(y / EARTH_RADIUS_M)
    return np.asarray(lon, dtype=np.float64), np.asarray(lat, dtype=np.float64)


@dataclass
class Buildings:
    ids: list[str]
    heights: F64          # metres above own ground
    height_sd: F64        # one sigma, metres
    edges: F64            # (E, 4): x0, y0, x1, y1 in metres
    edge_building: NDArray[np.int64]
    bounds: F64           # (B, 4): xmin, ymin, xmax, ymax
    lon0: float
    lat0: float
    footprint_m2: F64 = field(default_factory=lambda: np.zeros(0))
    centroids: F64 = field(default_factory=lambda: np.zeros((0, 2)))
    #: Per building: rings in local metres as (array (n, 2), is_outer), for meshing.
    rings: list[list[tuple[F64, bool]]] = field(default_factory=list)
    _grid: dict[tuple[int, int], list[int]] = field(default_factory=dict)
    _cell: float = 50.0

    @classmethod
    def from_rings(cls, ids: Sequence[str], polygons: Sequence[Sequence[Ring]], heights: F64, height_sd: F64,
                   lon0: float, lat0: float, outer: Sequence[Sequence[bool]] | None = None) -> Buildings:
        """``polygons[b]`` lists building b's rings; ``outer[b][k]`` says whether ring k is an outer ring
        (default: only the first ring)."""
        edges: list[F64] = []
        owner: list[NDArray[np.int64]] = []
        bounds = np.zeros((len(ids), 4))
        areas = np.zeros(len(ids))
        cents = np.zeros((len(ids), 2))
        local_rings: list[list[tuple[F64, bool]]] = []
        for b, polys in enumerate(polygons):
            local_rings.append([])
            xs_all: list[F64] = []
            ys_all: list[F64] = []
            for k, ring in enumerate(polys):
                arr = np.asarray(ring, dtype=np.float64)
                if arr.shape[0] < 3:
                    continue
                x, y = to_local(arr[:, 0], arr[:, 1], lon0, lat0)
                is_outer = outer[b][k] if outer is not None else k == 0
                local_rings[b].append((np.stack([x, y], axis=1), bool(is_outer)))
                e = np.stack([x[:-1], y[:-1], x[1:], y[1:]], axis=1)
                edges.append(e)
                owner.append(np.full(e.shape[0], b, dtype=np.int64))
                xs_all.append(x)
                ys_all.append(y)
                ring_area = abs(0.5 * float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1])))
                areas[b] += ring_area if is_outer else -ring_area
            if xs_all:
                xs, ys = np.concatenate(xs_all), np.concatenate(ys_all)
                bounds[b] = (xs.min(), ys.min(), xs.max(), ys.max())
                cents[b] = (xs.mean(), ys.mean())
        city = cls(
            ids=list(ids), heights=np.asarray(heights, dtype=np.float64),
            height_sd=np.asarray(height_sd, dtype=np.float64),
            edges=np.concatenate(edges) if edges else np.zeros((0, 4)),
            edge_building=np.concatenate(owner) if owner else np.zeros(0, dtype=np.int64),
            bounds=bounds, lon0=lon0, lat0=lat0, footprint_m2=np.abs(areas), centroids=cents, rings=local_rings,
        )
        city._index()
        return city

    def __len__(self) -> int:
        return len(self.ids)

    def _index(self) -> None:
        self._grid = {}
        for b, (x0, y0, x1, y1) in enumerate(self.bounds):
            for i in range(int(math.floor(x0 / self._cell)), int(math.floor(x1 / self._cell)) + 1):
                for j in range(int(math.floor(y0 / self._cell)), int(math.floor(y1 / self._cell)) + 1):
                    self._grid.setdefault((i, j), []).append(b)

    # --- queries ---------------------------------------------------------------------

    def crossings(self, tx: F64, rx: F64, chunk: int = 128) -> list[list[tuple[float, int]]]:
        """Walls crossed by each horizontal path tx -> rx[k]: (distance from tx in m, building index)."""
        out: list[list[tuple[float, int]]] = [[] for _ in range(rx.shape[0])]
        if self.edges.shape[0] == 0 or rx.shape[0] == 0:
            return out
        reach = float(np.max(np.hypot(rx[:, 0] - tx[0], rx[:, 1] - tx[1]))) + 1.0
        near = ((np.minimum(self.edges[:, 0], self.edges[:, 2]) <= tx[0] + reach)
                & (np.maximum(self.edges[:, 0], self.edges[:, 2]) >= tx[0] - reach)
                & (np.minimum(self.edges[:, 1], self.edges[:, 3]) <= tx[1] + reach)
                & (np.maximum(self.edges[:, 1], self.edges[:, 3]) >= tx[1] - reach))
        e = self.edges[near]
        owner = self.edge_building[near]
        if e.shape[0] == 0:
            return out
        sx, sy = e[:, 2] - e[:, 0], e[:, 3] - e[:, 1]
        qx, qy = e[:, 0] - tx[0], e[:, 1] - tx[1]
        for start in range(0, rx.shape[0], chunk):
            r = rx[start:start + chunk]
            rx_, ry_ = (r[:, 0] - tx[0])[:, None], (r[:, 1] - tx[1])[:, None]
            denom = rx_ * sy[None, :] - ry_ * sx[None, :]
            with np.errstate(divide="ignore", invalid="ignore"):
                t = (qx[None, :] * sy[None, :] - qy[None, :] * sx[None, :]) / denom
                u = (qx[None, :] * ry_ - qy[None, :] * rx_) / denom
            hit = (np.abs(denom) > 1e-12) & (t > 1e-9) & (t < 1.0 - 1e-9) & (u >= 0.0) & (u <= 1.0)
            length = np.hypot(rx_[:, 0], ry_[:, 0])
            for k, j in zip(*np.nonzero(hit)):
                out[start + int(k)].append((float(t[k, j] * length[k]), int(owner[j])))
        return out

    def candidates(self, x: float, y: float) -> list[int]:
        return self._grid.get((int(math.floor(x / self._cell)), int(math.floor(y / self._cell))), [])

    def building_at(self, points: F64) -> NDArray[np.int64]:
        """Index of the building containing each point, or -1."""
        out = np.full(points.shape[0], -1, dtype=np.int64)
        for k, (x, y) in enumerate(points):
            for b in self.candidates(float(x), float(y)):
                x0, y0, x1, y1 = self.bounds[b]
                if not (x0 <= x <= x1 and y0 <= y <= y1):
                    continue
                e = self.edges[self.edge_building == b]
                cross = ((e[:, 1] > y) != (e[:, 3] > y))
                with np.errstate(divide="ignore", invalid="ignore"):
                    xi = e[:, 0] + (y - e[:, 1]) * (e[:, 2] - e[:, 0]) / (e[:, 3] - e[:, 1])
                if int(np.sum(cross & (x < xi))) % 2 == 1:
                    out[k] = b
                    break
        return out

    def facade_point(self, b: int, toward: F64) -> F64:
        """Point of building ``b``'s outline closest to ``toward`` (x, y), pulled 0.5 m inside."""
        e = self.edges[self.edge_building == b]
        p0, d = e[:, :2], e[:, 2:] - e[:, :2]
        ll = np.maximum(np.sum(d * d, axis=1), 1e-12)
        t = np.clip(np.sum((toward[None, :] - p0) * d, axis=1) / ll, 0.0, 1.0)
        pts = p0 + d * t[:, None]
        k = int(np.argmin(np.hypot(pts[:, 0] - toward[0], pts[:, 1] - toward[1])))
        inward = self.centroids[b] - pts[k]
        norm = float(np.hypot(*inward))
        return np.asarray(pts[k] + (inward / norm * 0.5 if norm > 0.5 else 0.0), dtype=np.float64)


# --- loading -----------------------------------------------------------------------------

@dataclass(frozen=True)
class _CityTable:
    """The few columns the field engine needs, for the whole city, held in memory."""

    ids: list[str]
    heights: NDArray[np.float64]
    height_sd: NDArray[np.float64]
    geometry: list[bytes]
    xmin: NDArray[np.float64]
    ymin: NDArray[np.float64]
    xmax: NDArray[np.float64]
    ymax: NDArray[np.float64]


@lru_cache(maxsize=2)
def _city_table(path: str) -> _CityTable:
    """Read the city model once per process. The file is one 100 MB row group on a network
    folder, so a filtered read still scans all of it (about 10 s); after this, a window is a
    numpy bounding-box test (milliseconds)."""
    import pyarrow.parquet as pq  # type: ignore[import-untyped]

    t = pq.read_table(path, columns=["id", "height_m", "height_sd_m", "geometry", "bbox"])
    bbox = t.column("bbox").combine_chunks()

    def col(name: str) -> NDArray[np.float64]:
        return np.asarray(t.column(name).to_numpy(zero_copy_only=False), dtype=np.float64)

    def part(name: str) -> NDArray[np.float64]:
        return np.asarray(bbox.field(name).to_numpy(zero_copy_only=False), dtype=np.float64)

    return _CityTable(ids=[str(x) for x in t.column("id").to_pylist()], heights=col("height_m"),
                      height_sd=col("height_sd_m"), geometry=t.column("geometry").to_pylist(),
                      xmin=part("xmin"), ymin=part("ymin"), xmax=part("xmax"), ymax=part("ymax"))


def buildings_path() -> Path | None:
    for path in config.search_paths("buildings"):
        if path.exists():
            return path
    return None


def load_window(lon0: float, lat0: float, radius_m: float, path: Path | None = None) -> Buildings | None:
    """Buildings whose bounding box meets the square of side 2*radius around (lon0, lat0)."""
    path = path or buildings_path()
    if path is None:
        return None
    dlat = math.degrees(radius_m / EARTH_RADIUS_M)
    dlon = dlat / math.cos(math.radians(lat0))
    city = _city_table(str(path))
    hit = np.flatnonzero((city.xmax >= lon0 - dlon) & (city.xmin <= lon0 + dlon)
                         & (city.ymax >= lat0 - dlat) & (city.ymin <= lat0 + dlat))
    rows: dict[str, Any] = {"id": [city.ids[i] for i in hit], "height_m": city.heights[hit],
                            "height_sd_m": city.height_sd[hit], "geometry": [city.geometry[i] for i in hit]}
    polys = [parse_wkb(bytes(g)) for g in rows["geometry"]]
    keep = [i for i, p in enumerate(polys) if p]
    heights = np.nan_to_num(np.array([float(rows["height_m"][i]) for i in keep]), nan=0.0)
    sd = np.nan_to_num(np.array([float(rows["height_sd_m"][i]) for i in keep]), nan=0.0)
    flat: list[list[Ring]] = []
    flags: list[list[bool]] = []
    for i in keep:
        # A MultiPolygon becomes one building with several outer rings.
        flat.append([ring for poly in polys[i] for ring in poly])
        flags.append([k == 0 for poly in polys[i] for k in range(len(poly))])
    return Buildings.from_rings([str(rows["id"][i]) for i in keep], flat, heights, sd, lon0, lat0, flags)
