"""Multiple knife-edge diffraction, ITU-R P.526-15.

J(v) = 6.9 + 20 log10( sqrt((v - 0.1)^2 + 1) + v - 0.1 )  for v > -0.78, else 0   (eq. 31)
v    = h * sqrt( 2 d / (lambda d1 d2) )                                           (eq. 26)

Deygout (sec. 4.5.1): the edge with the largest v is the principal edge; the
two sub-paths (transmitter -> principal edge, principal edge -> receiver) each
add the loss of their own largest-v edge. Everything is vectorised over Monte
Carlo samples: edge heights have shape (edges, samples).
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

F64 = NDArray[np.float64]
NU_MIN = -0.78


def knife_edge_db(nu: F64) -> F64:
    out = 6.9 + 20.0 * np.log10(np.sqrt((nu - 0.1) ** 2 + 1.0) + nu - 0.1)
    return np.asarray(np.where(nu > NU_MIN, out, 0.0), dtype=np.float64)


def _nu(d: F64, h: F64, mask: NDArray[np.bool_], a_d: F64, a_z: F64, b_d: F64, b_z: F64,
        lam: float) -> F64:
    """v of every edge for the sub-path a -> b (endpoints per sample); -inf outside ``mask``."""
    span = np.maximum(b_d - a_d, 1e-6)[None, :]
    d1 = np.maximum(d[:, None] - a_d[None, :], 1e-6)
    d2 = np.maximum(b_d[None, :] - d[:, None], 1e-6)
    los = a_z[None, :] + (b_z - a_z)[None, :] * d1 / span
    nu = (h - los) * np.sqrt(2.0 * span / (lam * d1 * d2))
    return np.asarray(np.where(mask, nu, -np.inf), dtype=np.float64)


def deygout_db(d: F64, h: F64, z_tx: float | F64, z_rx: float | F64, total_d: float, lam: float,
               max_edges: int = 3) -> F64:
    """Diffraction loss in dB per sample.

    ``d``: edge distances from the transmitter (edges,); ``h``: edge heights (edges, samples);
    ``z_tx``/``z_rx``: end heights (scalar or per sample); ``total_d``: horizontal path length.
    """
    n_samples = h.shape[1]
    loss = np.zeros(n_samples)
    if d.size == 0:
        return loss
    a_d = np.zeros(n_samples)
    b_d = np.full(n_samples, float(total_d))
    a_z = np.broadcast_to(np.asarray(z_tx, dtype=np.float64), (n_samples,)).astype(np.float64)
    b_z = np.broadcast_to(np.asarray(z_rx, dtype=np.float64), (n_samples,)).astype(np.float64)
    inside = (d[:, None] > 0.0) & (d[:, None] < total_d)
    inside = np.broadcast_to(inside, h.shape)
    nu = _nu(d, h, inside, a_d, a_z, b_d, b_z, lam)
    p = np.argmax(nu, axis=0)
    cols = np.arange(n_samples)
    nu_p = nu[p, cols]
    has_p = np.isfinite(nu_p) & (nu_p > NU_MIN)
    loss += np.where(has_p, knife_edge_db(np.where(np.isfinite(nu_p), nu_p, NU_MIN)), 0.0)
    if max_edges < 2:
        return loss
    p_d, p_z = d[p], h[p, cols]
    for left in (True, False):
        mask = inside & ((d[:, None] < p_d[None, :]) if left else (d[:, None] > p_d[None, :]))
        if left:
            sub = _nu(d, h, mask, a_d, a_z, p_d, p_z, lam)
        else:
            sub = _nu(d, h, mask, p_d, p_z, b_d, b_z, lam)
        s = sub.max(axis=0)
        ok = has_p & np.isfinite(s) & (s > NU_MIN)
        loss += np.where(ok, knife_edge_db(np.where(np.isfinite(s), s, NU_MIN)), 0.0)
    return loss
