"""Terrain helpers: ground level under a building and terrain-RGB encoding for the viewer."""
from __future__ import annotations

from typing import Optional

import numpy as np
import numpy.typing as npt


def ground_from_samples(
    samples: npt.NDArray[np.floating], *, percentile: float, nodata: Optional[float]
) -> Optional[float]:
    """Low percentile of the valid DEM samples around a building.

    The Copernicus DEM is a surface model, so samples that hit roofs or trees are high;
    a low percentile approximates bare ground.
    """
    values = np.asarray(samples, dtype="float64")
    mask = np.isfinite(values)
    if nodata is not None:
        mask &= values != nodata
    if not mask.any():
        return None
    return float(np.percentile(values[mask], percentile))


def encode_terrarium(elev: npt.NDArray[np.floating]) -> npt.NDArray[np.uint8]:
    """Terrarium encoding used by MapLibre raster-dem: h = R*256 + G + B/256 - 32768."""
    v = np.asarray(elev, dtype="float64") + 32768.0
    r = np.floor(v / 256.0)
    g = np.floor(v - r * 256.0)
    b = np.round((v - r * 256.0 - g) * 256.0)
    carry = b >= 256
    b[carry] = 0
    g[carry] += 1
    out = np.stack([r, g, b], axis=-1)
    clipped: npt.NDArray[np.uint8] = np.clip(out, 0, 255).astype(np.uint8)
    return clipped


def decode_terrarium(rgb: npt.NDArray[np.uint8]) -> npt.NDArray[np.float64]:
    a = rgb.astype("float64")
    h: npt.NDArray[np.float64] = a[..., 0] * 256.0 + a[..., 1] + a[..., 2] / 256.0 - 32768.0
    return h
