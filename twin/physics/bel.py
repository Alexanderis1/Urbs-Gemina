"""Building entry loss, ITU-R P.2109-2 eq. (1)-(5).

L_BEL(P) = 10 log10(10^(0.1 A) + 10^(0.1 B) + 10^(0.1 C))
A = F^-1(P) s1 + m1,   B = F^-1(P) s2 + m2
m1 = L_h + L_e,  L_h = r + s log f + t (log f)^2,  L_e = 0.212 |theta|
m2 = w + x log f,  s1 = u + v log f,  s2 = y + z log f      (f in GHz)

``P`` is the probability that the loss is not exceeded.
"""
from __future__ import annotations

from statistics import NormalDist

import numpy as np
from numpy.typing import NDArray

from twin.physics import config


def _coeffs(building_type: str) -> dict[str, float]:
    section = config.load()["building_entry_loss"]
    if building_type not in section or building_type in ("basis", "building_type"):
        raise ValueError(f"unknown building type {building_type!r}")
    return {k: float(v) for k, v in section[building_type].items()}


def default_type() -> str:
    return str(config.value("building_entry_loss", "building_type"))


def loss_db_from_z(f_ghz: float, elevation_deg: NDArray[np.float64], z: NDArray[np.float64],
                   building_type: str | None = None) -> NDArray[np.float64]:
    """Loss for standard-normal draws ``z`` (= F^-1(P)); vectorised."""
    c = _coeffs(building_type or default_type())
    lf = np.log10(f_ghz)
    m1 = c["r"] + c["s"] * lf + c["t"] * lf * lf + 0.212 * np.abs(elevation_deg)
    m2 = c["w"] + c["x"] * lf
    s1 = c["u"] + c["v"] * lf
    s2 = c["y"] + c["z"] * lf
    a = z * s1 + m1
    b = z * s2 + m2
    return np.asarray(10.0 * np.log10(10 ** (0.1 * a) + 10 ** (0.1 * b) + 10 ** (0.1 * c["C"])), dtype=np.float64)


def loss_db(f_ghz: float, elevation_deg: float, probability: float, building_type: str | None = None) -> float:
    z = NormalDist().inv_cdf(probability)
    return float(loss_db_from_z(f_ghz, np.array([elevation_deg]), np.array([z]), building_type)[0])
