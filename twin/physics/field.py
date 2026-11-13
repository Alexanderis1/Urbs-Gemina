"""Electric field of antenna sites with buildings, antenna patterns and Monte Carlo uncertainty.

For every transmitter sector and receptor:

  E = sqrt(30 * EIRP * G(phi, theta)) / r * 10^(-(L_diff + L_BEL - err) / 20)

* G: 3GPP TR 38.901 sector pattern (twin.physics.pattern), with azimuth and tilt.
* r: 3D distance; horizontal distance clamped to 1 m.
* L_diff: Deygout multiple knife-edge diffraction over the building walls
  crossed by the path (ITU-R P.526), building heights from the city model,
  combined in power with a diffuse multipath component (config ``multipath``).
* L_BEL: building entry loss for indoor receptors (ITU-R P.2109).
* err: model error, normal in dB, larger when the path is obstructed.

Sectors add as powers. Uncertainty is propagated by Monte Carlo: each draw
samples building heights (height_sd_m), EIRP, unknown azimuths and tilts,
entry loss and model error. The result is a (receptors, samples) array, from
which percentiles and exceedance probabilities are read directly.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from twin.physics import bel, config, diffraction, pattern
from twin.physics.buildings import Buildings

F64 = NDArray[np.float64]
C_MHZ_M = 299.792458  # speed of light, in m * MHz


def free_space_v_per_m(eirp_w: float, distance_m: float) -> float:
    return math.sqrt(30.0 * eirp_w) / max(distance_m, 1.0)


@dataclass(frozen=True)
class Sector:
    eirp_w: float
    azimuth_deg: float | None = None   # compass bearing of the main beam; None = unknown
    tilt_deg: float | None = None      # downtilt; None = unknown (sampled from config range)


@dataclass(frozen=True)
class Transmitter:
    x: float
    y: float
    height_m: float                    # antenna centre above ground
    frequency_mhz: float
    sectors: tuple[Sector, ...] | None = None
    #: When ``sectors`` is None: EIRP per sector of a standard tri-sector site with unknown azimuth.
    unknown_sector_eirp_w: float = 0.0
    eirp_sigma_db: float = 0.0


@dataclass(frozen=True)
class Receptor:
    x: float
    y: float
    height_m: float
    indoor: bool = False
    building: int = -1                 # building index for indoor receptors (-1: detect)


@dataclass
class FieldResult:
    samples: F64                       # (receptors, draws) in V/m
    obstructed_share: F64              # (receptors,) share of draws with diffraction loss > 0
    #: "building_aware" (CPU knife-edge engine), "raytrace" (Sionna RT maps) or "open_ground"
    model: str = "building_aware"


@dataclass
class FieldEngine:
    buildings: Buildings | None
    samples: int = field(default_factory=lambda: int(config.value("monte_carlo", "samples")))
    seed: int = field(default_factory=lambda: int(config.value("monte_carlo", "seed")))
    los_sigma_db: float = field(default_factory=lambda: float(config.value("model_error", "los_sigma_db")))
    nlos_sigma_db: float = field(default_factory=lambda: float(config.value("model_error", "nlos_sigma_db")))
    building_type: str | None = None
    diffuse_loss_db: float = field(default_factory=lambda: float(config.value("multipath", "diffuse_loss_db")))

    def field_samples(self, txs: list[Transmitter], receptors: list[Receptor]) -> F64:
        return self.evaluate(txs, receptors).samples

    def evaluate(self, txs: list[Transmitter], receptors: list[Receptor]) -> FieldResult:
        s = self.samples
        # Independent streams, so adding buildings does not change the antenna or entry-loss draws.
        rng_h, rng_bel, rng = (np.random.default_rng(c) for c in np.random.SeedSequence(self.seed).spawn(3))
        r = len(receptors)
        power = np.zeros((r, s))
        obstructed = np.zeros(r)
        if r == 0:
            return FieldResult(np.zeros((0, s)), obstructed)
        city = self.buildings
        heights: F64 | None = None
        if city is not None and len(city):
            z = rng_h.standard_normal((len(city), s))
            heights = np.maximum(city.heights[:, None] + city.height_sd[:, None] * z, 0.0)
        rx_xy = np.array([[p.x, p.y] for p in receptors], dtype=np.float64)
        rx_h = np.array([p.height_m for p in receptors], dtype=np.float64)
        own = np.array([p.building for p in receptors], dtype=np.int64)
        if city is not None and len(city):
            need = np.array([p.indoor and p.building < 0 for p in receptors])
            if need.any():
                own[need] = city.building_at(rx_xy[need])
        indoor = np.array([p.indoor for p in receptors])
        bel_z = rng_bel.standard_normal((r, s))
        tilt_lo, tilt_hi = (float(v) for v in config.value("antenna_pattern", "tilt_deg_when_unknown"))
        az_sd = float(config.value("antenna_pattern", "azimuth_sd_deg_when_given"))
        n_unknown = int(config.value("antenna_pattern", "sectors_when_unknown"))

        for tx in txs:
            lam = C_MHZ_M / tx.frequency_mhz
            eirp_factor = 10.0 ** (rng.normal(0.0, tx.eirp_sigma_db, s) / 10.0) if tx.eirp_sigma_db > 0 else np.ones(s)
            if tx.sectors is None:
                offset = rng.uniform(0.0, 360.0, s)
                sectors = [(tx.unknown_sector_eirp_w, (offset + k * 360.0 / n_unknown) % 360.0,
                            rng.uniform(tilt_lo, tilt_hi, s)) for k in range(n_unknown)]
            else:
                sectors = []
                for sec in tx.sectors:
                    az = (rng.uniform(0.0, 360.0, s) if sec.azimuth_deg is None
                          else sec.azimuth_deg + rng.normal(0.0, az_sd, s))
                    tilt = rng.uniform(tilt_lo, tilt_hi, s) if sec.tilt_deg is None else np.full(s, sec.tilt_deg)
                    sectors.append((sec.eirp_w, az, tilt))
            err_z = rng.standard_normal((r, s))

            dx, dy = rx_xy[:, 0] - tx.x, rx_xy[:, 1] - tx.y
            horiz = np.maximum(np.hypot(dx, dy), 1.0)
            dz = tx.height_m - rx_h
            dist3 = np.hypot(horiz, dz)
            bearing = np.degrees(np.arctan2(dx, dy)) % 360.0
            elev = np.degrees(np.arctan2(dz, horiz))

            eirp_eff = np.zeros((r, s))
            for eirp, az, tilt in sectors:
                g = pattern.gain_db_array(bearing[:, None] - az[None, :], elev[:, None], tilt[None, :])
                eirp_eff += eirp * 10.0 ** (g / 10.0)
            e2 = 30.0 * eirp_eff * eirp_factor[None, :] / (dist3 ** 2)[:, None]

            loss = np.zeros((r, s))
            if city is not None and heights is not None:
                tx_xy = np.array([tx.x, tx.y])
                host = int(city.building_at(tx_xy[None, :])[0])
                walls = city.crossings(tx_xy, rx_xy)
                for k, hits in enumerate(walls):
                    keep = [(d, b) for d, b in hits if b != own[k]]
                    if not keep:
                        continue
                    d = np.array([d for d, _ in keep])
                    b = np.array([b for _, b in keep])
                    h = heights[b]
                    if host >= 0:
                        # The mast stands on its host roof: that roof stays below the antenna.
                        h = np.where((b == host)[:, None], np.minimum(h, tx.height_m - 0.5), h)
                    loss[k] = diffraction.deygout_db(d, h, tx.height_m, float(rx_h[k]), float(horiz[k]), lam,
                                                     int(config.value("diffraction", "max_edges")))
            obstructed += np.mean(loss > 0.0, axis=1) / len(txs)
            # Diffuse multipath (reflections) added in power: a soft floor under deep shadows.
            loss = np.where(loss > 0.0,
                            -10.0 * np.log10(10.0 ** (-loss / 10.0) + 10.0 ** (-self.diffuse_loss_db / 10.0)), 0.0)
            sigma = np.where(loss > 0.0, self.nlos_sigma_db, self.los_sigma_db)
            total_db = -loss + sigma * err_z
            if indoor.any():
                f_ghz = tx.frequency_mhz / 1000.0
                bel_db = bel.loss_db_from_z(f_ghz, np.broadcast_to(elev[:, None], (r, s)).copy(), bel_z,
                                            self.building_type)
                total_db -= np.where(indoor[:, None], bel_db, 0.0)
            power += e2 * 10.0 ** (total_db / 10.0)
        return FieldResult(np.sqrt(power), obstructed)


def summarise(samples: F64, thresholds: dict[str, float]) -> list[dict[str, float]]:
    """P5 / P50 / P95 and the share of draws above each threshold, per receptor."""
    if samples.shape[0] == 0:
        return []
    p5, p50, p95 = np.percentile(samples, [5, 50, 95], axis=1)
    out = []
    for k in range(samples.shape[0]):
        row = {"p5": round(float(p5[k]), 4), "p50": round(float(p50[k]), 4), "p95": round(float(p95[k]), 4)}
        for name, value in thresholds.items():
            row[f"p_exceed_{name}"] = round(float(np.mean(samples[k] > value)), 4)
        out.append(row)
    return out
