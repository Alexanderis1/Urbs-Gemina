"""When did a building appear? Compare its roof in each historical photo with today's.

Normalised cross-correlation (NCC) of the grey-level pixels inside the footprint: the same
roof correlates strongly across years, a field or a building site does not. The first year
from which the roof matches gives the construction period ("2005-2011").
Old photos are misaligned by a few metres and tall roofs lean, so this is an estimate (C=55).
"""
from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import numpy.typing as npt
from scipy import ndimage

Array = npt.NDArray[np.float64]


def ncc_per_label(a: npt.NDArray[np.floating], b: npt.NDArray[np.floating], labels: npt.NDArray[np.integer], *,
                  n: int) -> Array:
    """NCC between images ``a`` and ``b`` over each label's pixels (1..n). NaN for empty or flat labels."""
    idx = np.arange(1, n + 1)
    x = np.asarray(a, dtype="float64")
    y = np.asarray(b, dtype="float64")
    cnt = ndimage.sum_labels(np.ones_like(x), labels, idx)
    sx, sy = ndimage.sum_labels(x, labels, idx), ndimage.sum_labels(y, labels, idx)
    sxx, syy = ndimage.sum_labels(x * x, labels, idx), ndimage.sum_labels(y * y, labels, idx)
    sxy = ndimage.sum_labels(x * y, labels, idx)
    safe = np.where(cnt > 0, cnt, 1.0)
    cov = sxy - sx * sy / safe
    vx = sxx - sx * sx / safe
    vy = syy - sy * sy / safe
    den = np.sqrt(np.maximum(vx, 0) * np.maximum(vy, 0))
    ok = (cnt >= 4) & (den > 1e-9)
    return np.where(ok, cov / np.where(ok, den, 1.0), np.nan)


def appearance_period(
    ncc_by_year: Mapping[int, Array], years: Sequence[int], *, latest_year: int, threshold: float
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.object_]]:
    """First year from which the roof matches today's, and a readable period label.

    Returns (first_year, label): first_year = -1 when unknown; the earliest year means "before" it.
    A building that matches in no historical year appeared after the last one.
    """
    ys = sorted(years)
    n = len(next(iter(ncc_by_year.values())))
    first = np.full(n, -1, dtype=np.int64)
    label = np.empty(n, dtype=object)
    for i in range(n):
        known = [(y, float(ncc_by_year[y][i])) for y in ys if np.isfinite(ncc_by_year[y][i])]
        if not known:
            label[i] = "unknown"
            continue
        # The earliest photo from which most later photos also match today's roof
        # (one badly lit or leaning photo must not reset the history).
        start = None
        for j in range(len(known)):
            later = [v >= threshold for _, v in known[j:]]
            if later[0] and sum(later) >= 0.6 * len(later):
                start = j
                break
        if start is None:
            first[i] = latest_year
            label[i] = f"{known[-1][0]}-{latest_year}"
        elif start == 0:
            first[i] = known[0][0]
            label[i] = f"before {known[0][0]}"
        else:
            first[i] = known[start][0]
            label[i] = f"{known[start - 1][0]}-{known[start][0]}"
    return first, label


def align_shift(moving: npt.NDArray[np.floating], fixed: npt.NDArray[np.floating], *, max_shift: int) -> tuple[int, int]:
    """Integer (dy, dx) such that ``moving`` ~= roll(``fixed``, (dy, dx)), by phase correlation."""
    a = np.asarray(fixed, dtype="float64")
    b = np.asarray(moving, dtype="float64")
    a = a - a.mean()
    b = b - b.mean()
    fa, fb = np.fft.fft2(a), np.fft.fft2(b)
    cross = fb * np.conj(fa)
    cross /= np.maximum(np.abs(cross), 1e-12)
    corr = np.real(np.fft.ifft2(cross))
    h, w = corr.shape
    best, best_v = (0, 0), -np.inf
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            v = corr[dy % h, dx % w]
            if v > best_v:
                best, best_v = (dy, dx), v
    return best
