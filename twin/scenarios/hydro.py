"""Terrain hydrology on a ``Grid``: depressions, flow routing, height above the river.

Pure NumPy plus one priority-queue pass (Barnes et al. 2014 priority-flood).
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass

import numpy as np

from twin.scenarios.terrain import BoolArray, FloatArray, IntArray

_OFFSETS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def priority_flood(z: FloatArray) -> tuple[FloatArray, IntArray, IntArray]:
    """Priority-flood (Barnes et al. 2014).

    Returns the depression-filled surface, each cell's receiver (the cell it was
    reached from, so flow always finds the grid edge, also across flats) and the
    order cells were reached in (outlets first).
    """
    rows, cols = z.shape
    flat = np.where(np.isnan(z), -1e9, z).ravel().tolist()
    n = rows * cols
    closed = [False] * n
    receiver = list(range(n))
    order: list[int] = []
    heap: list[tuple[float, int, int]] = []
    edge = np.zeros((rows, cols), dtype=bool)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
    edge |= np.isnan(z)
    counter = 0
    for i in np.flatnonzero(edge.ravel()).tolist():
        closed[i] = True
        heap.append((flat[i], counter, i))
        counter += 1
    heapq.heapify(heap)
    push, pop = heapq.heappush, heapq.heappop
    while heap:
        h, _, i = pop(heap)
        order.append(i)
        r, c = divmod(i, cols)
        for dr, dc in _OFFSETS:
            rr, cc = r + dr, c + dc
            if 0 <= rr < rows and 0 <= cc < cols:
                j = rr * cols + cc
                if closed[j]:
                    continue
                closed[j] = True
                receiver[j] = i
                if flat[j] < h:
                    flat[j] = h
                counter += 1
                push(heap, (flat[j], counter, j))
    out = np.asarray(flat, dtype=np.float64).reshape(rows, cols)
    out[np.isnan(z)] = np.nan
    return out, np.asarray(receiver, dtype=np.int64), np.asarray(order, dtype=np.int64)


def fill_depressions(z: FloatArray) -> FloatArray:
    """Lowest surface without pits that drains to the grid edge or to no-data."""
    return priority_flood(z)[0]


def steepest_descent(z: FloatArray, cell: float) -> IntArray:
    """D8 receiver (flat index) of each cell; a cell with no lower neighbour is its own receiver."""
    rows, cols = z.shape
    padded = np.pad(np.where(np.isnan(z), np.inf, z), 1, constant_values=np.inf)
    best = np.zeros((rows, cols))
    target = np.arange(rows * cols, dtype=np.int64).reshape(rows, cols)
    rr, cc = np.mgrid[0:rows, 0:cols]
    for dr, dc in _OFFSETS:
        neighbour = padded[1 + dr:1 + dr + rows, 1 + dc:1 + dc + cols]
        slope = (z - neighbour) / (cell * (1.4142135623730951 if dr and dc else 1.0))
        better = np.isfinite(slope) & (slope > best)
        best = np.where(better, slope, best)
        target = np.where(better, (rr + dr) * cols + (cc + dc), target)
    out: IntArray = target.ravel()
    return out


def terminal(receiver: IntArray) -> IntArray:
    """Where each cell's flow path ends (pointer jumping, log2 of the longest path)."""
    end = receiver.copy()
    for _ in range(64):
        nxt = end[end]
        if np.array_equal(nxt, end):
            break
        end = nxt
    return end


@dataclass(frozen=True)
class Depressions:
    label: IntArray  # 0 = not in a depression, 1..n otherwise
    count: int
    spill: FloatArray  # filled surface: the spill level of each depression cell


def depressions(z: FloatArray, min_depth_m: float) -> Depressions:
    from scipy import ndimage  # type: ignore[import-untyped]

    filled = fill_depressions(z)
    depth = filled - z
    mask = np.nan_to_num(depth, nan=0.0) > min_depth_m
    # grow each core to all cells under the same spill level, so shallow rims belong to it
    mask = ndimage.binary_dilation(mask, iterations=1) & (np.nan_to_num(depth, nan=0.0) > 0.0) | mask
    label, count = ndimage.label(mask, structure=np.ones((3, 3)))
    return Depressions(np.asarray(label, dtype=np.int64), int(count), filled)


def height_above_river(z: FloatArray, river: BoolArray) -> tuple[FloatArray, IntArray]:
    """HAND (Euclidean variant): height above the nearest river cell, and that cell's flat index."""
    from scipy import ndimage

    if not river.any():
        raise ValueError("no river cell inside the grid")
    _, (ri, ci) = ndimage.distance_transform_edt(~river, return_indices=True)
    nearest = np.asarray(ri, dtype=np.int64) * z.shape[1] + np.asarray(ci, dtype=np.int64)
    hand = z - z.ravel()[nearest].reshape(z.shape)
    return hand, nearest


def connected_to(mask: BoolArray, seeds: BoolArray) -> BoolArray:
    """Cells of ``mask`` in a component (8-connected) that contains a seed cell."""
    from scipy import ndimage

    label, _ = ndimage.label(mask, structure=np.ones((3, 3)))
    keep = np.unique(label[seeds & mask])
    keep = keep[keep > 0]
    out: BoolArray = np.isin(label, keep)
    return out


def flow_accumulation(z: FloatArray, cell: float) -> FloatArray:
    """Upstream area (m2), routing along the priority-flood receivers (drains flats and pits)."""
    _, receiver, order = priority_flood(z)
    acc = [cell * cell] * receiver.size
    rec = receiver.tolist()
    for i in reversed(order.tolist()):
        j = rec[i]
        if j != i:
            acc[j] += acc[i]
    out = np.asarray(acc, dtype=np.float64).reshape(z.shape)
    out[np.isnan(z)] = np.nan
    return out
