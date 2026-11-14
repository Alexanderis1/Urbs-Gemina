"""Ground motion per building from Persistent Scatterer InSAR (Sentinel-1, Regione Lazio).

Each radar geometry measures motion along its line of sight (LOS). With an ascending and a
descending track over the same building, the vertical and east-west components can be separated
(north-south motion is assumed negligible: the radar is almost blind to it).
"""
from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

Array = npt.NDArray[np.float64]
Vec3 = tuple[float, float, float]


def los_unit_vector(*, incidence_deg: float, heading_deg: float) -> Vec3:
    """Unit vector from the ground to a right-looking satellite, as (east, north, up)."""
    th = math.radians(incidence_deg)
    al = math.radians(heading_deg)
    return (-math.sin(th) * math.cos(al), math.sin(th) * math.sin(al), math.cos(th))


def decompose(v_asc: Array, v_desc: Array, asc: Vec3, desc: Vec3) -> tuple[Array, Array]:
    """Solve LOS = e*east + u*up for both tracks; returns (up, east) in the input units."""
    a = np.array([[asc[0], asc[2]], [desc[0], desc[2]]])
    inv = np.linalg.inv(a)
    up = inv[1, 0] * v_asc + inv[1, 1] * v_desc
    east = inv[0, 0] * v_asc + inv[0, 1] * v_desc
    return np.asarray(up, dtype="float64"), np.asarray(east, dtype="float64")
