"""Sewers for the rain flood scenario: capacity from Rome's design rules, routing, outfalls and the river.

Rome's pipe map is not open, so each terrain cell gets the sewer that the
city's own design rules (Comune di Roma, 2000) would give the basin draining
through it: design rain from the Rome curve over the basin's concentration
time, times the basin's runoff coefficient and area, times an efficiency
for real-world conditions. Rain caught by street drains is routed downhill
along the terrain; where the flow is more than the pipe holds, the excess
comes back up (surcharge) and pools at the surface. ACEA outfalls on the
Tiber and Aniene stop working when the river rises over them, and the basins
behind them keep only part of their capacity.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import numpy.typing as npt

from twin.scenarios import config, hydro, layers
from twin.scenarios.terrain import BoolArray, FloatArray, Grid, IntArray, to_utm


def _cfg() -> dict[str, Any]:
    section: dict[str, Any] = config.load("scenarios.yaml")["rain_flood"]
    return section


def _v(key: str) -> Any:
    return config.value(_cfg(), key)


def concentration_time_h(area_km2: FloatArray) -> FloatArray:
    rain = _v("sewer_design_rain")
    length = _v("sewer_flow_length")
    length_km = float(length["coefficient_km"]) * np.power(np.maximum(area_km2, 1e-6), float(length["exponent"]))
    tc = length_km * 1000.0 / (float(rain["pipe_speed_m_s"]) * 3600.0) + float(rain["inlet_time_h"])
    out: FloatArray = np.maximum(tc, float(rain["min_tc_h"]))
    return out


def design_intensity_mm_h(area_km2: FloatArray) -> FloatArray:
    """Rain intensity (mm/h) a Rome sewer draining ``area_km2`` is designed for (over its concentration time)."""
    rain = _v("sewer_design_rain")
    a_km2 = np.asarray(area_km2, dtype=np.float64)
    t = concentration_time_h(a_km2)
    short, long_, areal = rain["short"], rain["long"], rain["areal"]
    a = np.where(t <= float(short["max_h"]), float(short["a"]), float(long_["a"]))
    n = np.where(t <= float(short["max_h"]), float(short["n"]), float(long_["n"]))
    a = a * (1.0 + float(areal["a1"]) * a_km2 + float(areal["a2"]) * a_km2 ** 2)
    n = n + float(areal["n1"]) * a_km2
    out: FloatArray = a * np.power(t, n) / t
    return out


def route(receiver: IntArray, order: IntArray, sink: BoolArray, captured: FloatArray,
          capacity: FloatArray) -> tuple[FloatArray, FloatArray]:
    """Route caught water (members x cells, m3) down the receivers, capped by pipe capacity.

    Returns the surcharge per cell (water that cannot enter or stay in the pipe there) and the volume
    leaving at each sink cell (members x number of sinks, in the order of ``np.flatnonzero(sink)``).
    Cells are processed in generations (all upstream cells before their receiver) so the members are
    vectorised.
    """
    n = receiver.size
    rec = receiver.tolist()
    gen = [0] * n
    for i in reversed(order.tolist()):  # upstream first
        j = rec[i]
        if j != i and gen[j] < gen[i] + 1:
            gen[j] = gen[i] + 1
    gen_arr = np.asarray(gen)
    by_gen = np.argsort(gen_arr, kind="stable")
    bounds = np.searchsorted(gen_arr[by_gen], np.arange(gen_arr.max() + 2))
    flow = np.array(captured, dtype=np.float64, copy=True)
    surcharge = np.zeros_like(flow)
    passes = (receiver != np.arange(n)) & ~sink
    for g in range(len(bounds) - 1):
        idx = by_gen[bounds[g]:bounds[g + 1]]
        if idx.size == 0:
            continue
        pipe = idx[~sink[idx]]
        if pipe.size:
            over = flow[:, pipe] - capacity[:, pipe]
            np.maximum(over, 0.0, out=over)
            surcharge[:, pipe] += over
            flow[:, pipe] -= over
        down = idx[passes[idx]]
        if down.size:
            np.add.at(flow.T, receiver[down], flow[:, down].T)
    sinks = np.flatnonzero(sink)
    discharged: FloatArray = flow[:, sinks]
    return surcharge, discharged


@dataclass
class Network:
    receiver: IntArray
    order: IntArray
    sink: BoolArray
    sink_of: IntArray  # flat index of the sink each cell drains to
    upstream_km2: FloatArray
    runoff_coefficient: FloatArray  # design runoff coefficient of the basin upstream
    intensity_mm_h: FloatArray  # design intensity per cell


def network(grid: Grid, sealed: FloatArray, channels: BoolArray) -> Network:
    """Pipes follow the filled terrain (they pass under hollows) and end in streams or at the grid edge."""
    _, receiver, order = hydro.priority_flood(grid.z)
    flat_valid = ~np.isnan(grid.z.ravel())
    n = receiver.size
    sink = channels.ravel() | (receiver == np.arange(n)) | ~flat_valid
    rec = receiver.copy()
    rec[sink] = np.flatnonzero(sink)
    sink_of = hydro.terminal(rec)
    area = [grid.cell_area] * n
    sealed_area = (np.nan_to_num(sealed.ravel()) * grid.cell_area).tolist()
    r = rec.tolist()
    for i in reversed(order.tolist()):
        j = r[i]
        if j != i:
            area[j] += area[i]
            sealed_area[j] += sealed_area[i]
    area_m2 = np.asarray(area)
    coeff = np.maximum(np.asarray(sealed_area) / area_m2, float(_v("sewer_min_runoff_coefficient")))
    km2 = area_m2 / 1e6
    return Network(rec, order, sink, sink_of, km2, coeff, design_intensity_mm_h(km2))


@dataclass
class Outfall:
    name: str
    receiving: str
    lon: float
    lat: float


def load_outfalls(river: str | None) -> list[Outfall] | None:
    """Outfalls straight into ``river`` (all when None); None when the layer is not loaded."""
    path = layers.find(str(_v("outfalls_file")))
    if path is None:
        return None
    names = [s.casefold() for s in (_v("outfall_rivers").get(river, []) if river else [])]
    out: list[Outfall] = []
    for f in layers.read(path).get("features", []):
        g, p = f.get("geometry") or {}, f.get("properties") or {}
        if g.get("type") != "Point":
            continue
        receiving = str(p.get("receiving") or "")
        if river and receiving.casefold() not in names:
            continue
        out.append(Outfall(str(p.get("name") or p.get("id") or ""), receiving,
                           float(g["coordinates"][0]), float(g["coordinates"][1])))
    return out


def outfall_sinks(grid: Grid, net: Network, outfalls: Sequence[Outfall]) -> IntArray:
    """For each sink cell, the outfall it discharges through (-1 when none is within reach)."""
    sinks = np.flatnonzero(net.sink)
    out = np.full(sinks.size, -1, dtype=np.int64)
    if not outfalls or sinks.size == 0:
        return out
    from scipy.spatial import cKDTree  # type: ignore[import-untyped]

    ox, oy = to_utm([o.lon for o in outfalls], [o.lat for o in outfalls])
    rows, cols = np.divmod(sinks, grid.shape[1])
    sx = grid.x0 + (cols + 0.5) * grid.cell
    sy = grid.y0 - (rows + 0.5) * grid.cell
    dist, idx = cKDTree(np.column_stack([ox, oy])).query(np.column_stack([sx, sy]))
    reach = float(_v("outfall_reach_m"))
    out = np.where(np.asarray(dist) <= reach, np.asarray(idx, dtype=np.int64), -1)
    return out


def outfall_taper(grid: Grid, outfalls: Sequence[Outfall], normal_level_m: float) -> FloatArray:
    """Share of the gauge's rise felt at each outfall: lowest terrain near it over the gauge's ordinary level."""
    if normal_level_m <= 0:
        return np.ones(len(outfalls))
    rows, cols = grid.rowcol([o.lon for o in outfalls], [o.lat for o in outfalls])
    out = np.ones(len(outfalls))
    for k, (r, c) in enumerate(zip(rows.tolist(), cols.tolist())):
        if r < 0:
            continue
        window = grid.z[max(r - 1, 0):r + 2, max(c - 1, 0):c + 2]
        low = float(np.nanmin(window)) if np.isfinite(window).any() else normal_level_m
        out[k] = min(max(low / normal_level_m, 0.0), 1.0)
    return out


def blocked_outfalls(rises: npt.NDArray[np.float64], taper: FloatArray,
                     rng: np.random.Generator) -> npt.NDArray[np.bool_]:
    """members x outfalls: the river at the outfall is above its mouth."""
    height = _cfg()["outfall_height_m"]
    members = rises.size
    mouth = float(height["value"]) * np.exp(rng.normal(0.0, float(height["sigma_ln"]), (members, taper.size)))
    out: npt.NDArray[np.bool_] = rises[:, None] * taper[None, :] > mouth
    return out


def capacity_factor(net: Network, sink_outfall: IntArray, blocked: npt.NDArray[np.bool_]) -> FloatArray:
    """members x cells: 1, or the residual share for basins whose outfall is under water."""
    members = blocked.shape[0]
    residual = float(_v("blocked_outfall_residual"))
    sinks = np.flatnonzero(net.sink)
    position = np.full(net.receiver.size, -1, dtype=np.int64)
    position[sinks] = np.arange(sinks.size)
    cell_outfall = sink_outfall[position[net.sink_of]] if sinks.size else np.full(net.receiver.size, -1)
    factor = np.ones((members, net.receiver.size))
    has = cell_outfall >= 0
    if has.any() and blocked.size:
        factor[:, has] = np.where(blocked[:, cell_outfall[has]], residual, 1.0)
    return factor


def summary(outfalls: Sequence[Outfall], blocked: npt.NDArray[np.bool_], served: Sequence[int],
            limit: int = 20) -> list[dict[str, Any]]:
    """Outfalls that can block, most likely first."""
    rows: list[dict[str, Any]] = []
    for k in served:
        p = float(blocked[:, k].mean()) if blocked.size else 0.0
        if p > 0:
            o = outfalls[k]
            rows.append({"name": o.name, "receiving": o.receiving, "lon": round(o.lon, 6), "lat": round(o.lat, 6),
                         "probability_blocked": round(p, 3)})
    rows.sort(key=lambda r: -float(r["probability_blocked"]))
    return rows[:limit]


def efficiency(members: int, rng: np.random.Generator) -> FloatArray:
    eff: Mapping[str, Any] = _cfg()["sewer_efficiency"]
    out: FloatArray = float(eff["value"]) * np.exp(rng.normal(0.0, float(eff["sigma_ln"]), members))
    return out


def rain_capacity_m3(net: Network, cell_area: float, duration_h: float) -> FloatArray:
    """Design pipe volume (m3) over the storm at each cell, before efficiency and outfall factors."""
    out: FloatArray = (net.intensity_mm_h / 1000.0 * duration_h * net.runoff_coefficient
                       * net.upstream_km2 * 1e6)
    return out


def inlet_rate_mm_h(cell_area_m2: float) -> float:
    """Rate street drains take before the water joins the pipes: the design rain of a one-cell basin."""
    return float(design_intensity_mm_h(np.asarray([cell_area_m2 / 1e6]))[0])
