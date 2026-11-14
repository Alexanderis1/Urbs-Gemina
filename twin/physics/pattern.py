"""Sector antenna element pattern, 3GPP TR 38.901 Table 7.3-1.

A_H(phi)   = -min(12 (phi / phi_3dB)^2, A_max)
A_V(theta) = -min(12 ((theta - tilt) / theta_3dB)^2, SLA_V)
A          = -min(-(A_H + A_V), A_max)

``theta`` is the angle below the horizon (positive downwards), like the tilt.
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from twin.physics import config

def _p(key: str) -> float:
    return float(config.value("antenna_pattern", key))


def wrap_deg(angle: NDArray[np.float64]) -> NDArray[np.float64]:
    """Angle folded into [-180, 180)."""
    return np.asarray((angle + 180.0) % 360.0 - 180.0, dtype=np.float64)


def gain_db_array(azimuth_off_deg: NDArray[np.float64], elevation_down_deg: NDArray[np.float64],
                  tilt_deg: NDArray[np.float64] | float) -> NDArray[np.float64]:
    a_max, sla = _p("front_to_back_db"), _p("side_lobe_vertical_db")
    h3, v3 = _p("horizontal_beamwidth_deg"), _p("vertical_beamwidth_deg")
    a_h = -np.minimum(12.0 * (wrap_deg(azimuth_off_deg) / h3) ** 2, a_max)
    a_v = -np.minimum(12.0 * ((elevation_down_deg - tilt_deg) / v3) ** 2, sla)
    return np.asarray(-np.minimum(-(a_h + a_v), a_max), dtype=np.float64)


def gain_db(azimuth_off_deg: float, elevation_down_deg: float, tilt_deg: float) -> float:
    """Gain relative to boresight in dB (0 on the main beam, never below -A_max)."""
    return float(gain_db_array(np.array([azimuth_off_deg], dtype=np.float64),
                               np.array([elevation_down_deg], dtype=np.float64), tilt_deg)[0])
