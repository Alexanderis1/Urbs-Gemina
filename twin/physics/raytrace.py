"""Sionna RT ray tracing of antenna sites over the LoD1 city model (reflections, diffraction, scattering).

Pipeline:
1. ``twin.physics.scene.write_scene`` turns the buildings around a site into meshes.
2. :func:`solve` (needs ``sionna-rt``; runs on a Modal GPU, see deploy/modal_raytrace.py,
   or locally on CPU through Dr.Jit's LLVM backend) computes radio maps of path gain
   on horizontal planes at several heights. A site with unknown azimuth is traced
   as 12 single-sector transmitters, one every 30 degrees, so any tri-sector
   orientation is the sum of three maps (:func:`tri_sector_combinations`).
3. :func:`sample_field` turns path gain into electric field with Monte Carlo
   uncertainty (orientation offset, EIRP, model error, building entry loss).

Field from path gain (isotropic receiver, pattern peak normalised to 0 dB):
E^2 = 30 * EIRP * PG * (4 pi / lambda)^2, which is 30 EIRP / d^2 in free space.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

from twin.physics import bel, config

F64 = NDArray[np.float64]
C_MHZ_M = 299.792458


def field_from_path_gain(path_gain: F64, eirp_w: float | F64, frequency_mhz: float) -> F64:
    lam = C_MHZ_M / frequency_mhz
    return np.asarray(np.sqrt(30.0 * eirp_w * path_gain) * (4.0 * math.pi / lam), dtype=np.float64)


def tri_sector_combinations(single: F64) -> F64:
    """(12, ...) single-sector maps at yaw 0, 30, ..., 330 -> (4, ...) tri-sector maps at offsets 0..90."""
    n = single.shape[0]
    if n % 3:
        raise ValueError("the number of yaws must be a multiple of 3")
    step = n // 3
    return np.asarray(np.stack([single[k] + single[k + step] + single[k + 2 * step] for k in range(step)]),
                      dtype=np.float64)


def yaw_deg(bearing_deg: float) -> float:
    """Sionna yaw (counter-clockwise from +x = east) of a compass bearing (clockwise from north)."""
    return (90.0 - bearing_deg) % 360.0


# --- the GPU / LLVM part -------------------------------------------------------------------

def _register_pattern() -> str:
    """Our 3GPP sector pattern (config antenna_pattern), peak 0 dB, registered in Sionna once."""
    import drjit as dr  # type: ignore[import-not-found,unused-ignore]
    import mitsuba as mi  # type: ignore[import-not-found,unused-ignore]
    import sionna.rt as rt  # type: ignore[import-not-found,unused-ignore]

    name = "urbs_sector"
    h3 = math.radians(float(config.value("antenna_pattern", "horizontal_beamwidth_deg")))
    v3 = math.radians(float(config.value("antenna_pattern", "vertical_beamwidth_deg")))
    a_max = float(config.value("antenna_pattern", "front_to_back_db"))
    sla = float(config.value("antenna_pattern", "side_lobe_vertical_db"))

    def v_pattern(theta: Any, phi: Any) -> Any:
        phi = phi + dr.pi
        phi -= dr.floor(phi / (2.0 * dr.pi)) * 2.0 * dr.pi
        phi -= dr.pi
        a_v = -dr.minimum(12.0 * ((theta - dr.pi / 2.0) / v3) ** 2, sla)
        a_h = -dr.minimum(12.0 * (phi / h3) ** 2, a_max)
        a_db = -dr.minimum(-(a_v + a_h), a_max)
        return mi.Complex2f(dr.sqrt(dr.power(10.0, a_db / 10.0)), 0)

    def factory(*, polarization: str, polarization_model: str = "tr38901_2") -> Any:
        return rt.PolarizedAntennaPattern(v_pattern=v_pattern, polarization=polarization,
                                          polarization_model=polarization_model)

    try:
        rt.register_antenna_pattern(name, factory)
    except Exception:  # already registered in this process
        pass
    return name


def solve(scene_xml: str, params: Mapping[str, Any]) -> dict[str, Any]:
    """Run Sionna RT. ``params``: frequency_mhz, transmitters [{x, y, z, yaw_deg, tilt_deg}],
    center [x, y], size_m, cell_m, heights_m, samples_per_tx, max_depth. Returns numpy arrays."""
    import mitsuba as mi
    import sionna.rt as rt

    pattern_name = _register_pattern()
    scene = rt.load_scene(scene_xml)
    scene.frequency = float(params["frequency_mhz"]) * 1e6
    scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern=pattern_name, polarization="V")
    scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    for k, t in enumerate(params["transmitters"]):
        scene.add(rt.Transmitter(
            name=f"tx{k}", position=mi.Point3f(float(t["x"]), float(t["y"]), float(t["z"])),
            orientation=mi.Point3f(math.radians(float(t["yaw_deg"])), math.radians(float(t["tilt_deg"])), 0.0),
            power_dbm=30.0))
    solver = rt.RadioMapSolver()
    cx, cy = (float(v) for v in params["center"])
    size, cell = float(params["size_m"]), float(params["cell_m"])
    maps = []
    centers = None
    for h in params["heights_m"]:
        rm = solver(scene, center=mi.Point3f(cx, cy, float(h)), orientation=mi.Point3f(0.0, 0.0, 0.0),
                    size=mi.Point2f(size, size), cell_size=mi.Point2f(cell, cell),
                    samples_per_tx=int(params["samples_per_tx"]), max_depth=int(params["max_depth"]),
                    los=True, specular_reflection=True, diffuse_reflection=True, refraction=False,
                    diffraction=True, edge_diffraction=True)
        maps.append(np.asarray(rm.path_gain.numpy(), dtype=np.float64))
        if centers is None:
            centers = np.asarray(rm.cell_centers.numpy(), dtype=np.float64)[..., :2]
    return {"path_gain": np.stack(maps), "cell_centers": centers,
            "heights_m": np.asarray(params["heights_m"], dtype=np.float64)}


# --- results ------------------------------------------------------------------------------------

@dataclass
class RadioMaps:
    """Path gain per height, transmitter and cell, in the scene's local frame."""

    path_gain: F64          # (heights, tx, ny, nx)
    cell_centers: F64       # (ny, nx, 2) local metres
    heights_m: F64
    meta: dict[str, Any]

    def to_bytes(self) -> bytes:
        buf = io.BytesIO()
        np.savez_compressed(buf, path_gain=self.path_gain, cell_centers=self.cell_centers,
                            heights_m=self.heights_m, meta=np.array(json.dumps(self.meta)))
        return buf.getvalue()

    @classmethod
    def from_bytes(cls, blob: bytes) -> RadioMaps:
        z = np.load(io.BytesIO(blob), allow_pickle=False)
        return cls(z["path_gain"], z["cell_centers"], z["heights_m"], json.loads(str(z["meta"])))


def site_key(site: Mapping[str, Any], radius_m: float = 300.0) -> str:
    """Cache key of a site's ray-traced maps: geometry, frequency, sectors, radius and the raytrace settings."""
    keep = {k: site.get(k) for k in ("lon", "lat", "height_m", "band", "frequency_mhz", "sectors")}
    raw = json.dumps({"site": keep, "radius_m": float(radius_m), "raytrace": config.load()["raytrace"],
                      "pattern": config.load()["antenna_pattern"]}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def cache_dirs() -> list[Path]:
    return [config.ROOT / "data" / "cache" / "raytrace", Path("/mnt/project-files/raytrace")]


def load_cached(site: Mapping[str, Any], radius_m: float = 300.0) -> RadioMaps | None:
    key = site_key(site, radius_m)
    for d in cache_dirs():
        path = d / f"{key}.npz"
        if path.exists():
            return RadioMaps.from_bytes(path.read_bytes())
    return None


def save_cached(site: Mapping[str, Any], maps: RadioMaps, radius_m: float = 300.0) -> list[Path]:
    written = []
    for d in cache_dirs():
        try:
            d.mkdir(parents=True, exist_ok=True)
            path = d / f"{site_key(site, radius_m)}.npz"
            path.write_bytes(maps.to_bytes())
            written.append(path)
        except OSError:
            continue
    return written


def _facade_fill(layer: F64) -> F64:
    """Cells with no rays (inside buildings) take the value of the nearest lit cell (the facade)."""
    from scipy import ndimage  # type: ignore[import-untyped]

    lit = layer > 0
    if lit.all() or not lit.any():
        return layer
    _, (iy, ix) = ndimage.distance_transform_edt(~lit, return_indices=True)
    return np.asarray(layer[iy, ix], dtype=np.float64)


def sample_field(maps: RadioMaps, eirp_w: Sequence[float], frequency_mhz: float, points_xy: F64,
                 receptor_h: F64, indoor: NDArray[np.bool_], samples: int, seed: int,
                 eirp_sigma_db: float, unknown_azimuth: bool) -> tuple[F64, F64]:
    """(field draws (points, samples) in V/m, share of points served only through the facade fill)."""
    rng = np.random.default_rng(seed)
    pg = maps.path_gain  # (H, T, ny, nx)
    if unknown_azimuth:
        per_h = np.stack([tri_sector_combinations(pg[h]) for h in range(pg.shape[0])])  # (H, 4, ny, nx)
        eirp = np.full(per_h.shape[1], float(eirp_w[0]))
    else:
        per_h = (pg * np.asarray(eirp_w, dtype=np.float64)[None, :, None, None]).sum(axis=1, keepdims=True)
        eirp = np.ones(1)
    filled = np.stack([[_facade_fill(per_h[h, k]) for k in range(per_h.shape[1])] for h in range(per_h.shape[0])])
    lit_any = per_h.max(axis=1) > 0  # (H, ny, nx)
    centers = maps.cell_centers
    x0, y0 = centers[0, 0]
    cell = float(maps.meta.get("cell_m", centers[0, 1, 0] - centers[0, 0, 0]))
    ny, nx = centers.shape[:2]
    ix = np.clip(np.round((points_xy[:, 0] - x0) / cell).astype(int), 0, nx - 1)
    iy = np.clip(np.round((points_xy[:, 1] - y0) / cell).astype(int), 0, ny - 1)
    hi = np.array([int(np.argmin(np.abs(maps.heights_m - h))) for h in receptor_h])
    choice = rng.integers(0, per_h.shape[1], samples)
    pg_pts = filled[hi[:, None], choice[None, :], iy[:, None], ix[:, None]]  # (P, S)
    eirp_draw = eirp[choice] * 10.0 ** (rng.normal(0.0, eirp_sigma_db, samples) / 10.0)
    e = field_from_path_gain(pg_pts, eirp_draw[None, :], frequency_mhz)
    err = rng.normal(0.0, float(config.value("raytrace", "model_error_sigma_db")), e.shape)
    loss = np.zeros(e.shape)
    if indoor.any():
        loss = np.where(indoor[:, None], bel.loss_db_from_z(frequency_mhz / 1000.0, np.zeros(e.shape),
                                                            rng.standard_normal(e.shape)), 0.0)
    e = e * 10.0 ** ((err - loss) / 20.0)
    facade_only = ~lit_any[hi, iy, ix]
    return np.asarray(e, dtype=np.float64), facade_only.astype(np.float64)


# --- preparing and running a site ---------------------------------------------------------------

def transmitters_for(site: Mapping[str, Any]) -> tuple[list[dict[str, float]], bool]:
    """Sionna transmitters of a site (local frame, site at the origin) and whether azimuth is unknown."""
    z = float(site["height_m"])
    if site.get("sectors"):
        tilt0 = float(config.value("raytrace", "tilt_deg_when_unknown"))
        txs = []
        for s in site["sectors"]:
            if s.get("azimuth_deg") is None:
                raise ValueError("ray tracing needs every declared sector's azimuth_deg (or no sectors at all)")
            txs.append({"x": 0.0, "y": 0.0, "z": z, "yaw_deg": yaw_deg(float(s["azimuth_deg"])),
                        "tilt_deg": float(s["tilt_deg"]) if s.get("tilt_deg") is not None else tilt0})
        return txs, False
    n = int(config.value("raytrace", "yaws_for_unknown_azimuth"))
    tilt = float(config.value("raytrace", "tilt_deg_when_unknown"))
    return [{"x": 0.0, "y": 0.0, "z": z, "yaw_deg": yaw_deg(k * 360.0 / n), "tilt_deg": tilt}
            for k in range(n)], True


def prepare(site: Mapping[str, Any], radius_m: float, frequency_mhz: float) -> tuple[bytes, dict[str, Any]]:
    """Scene (tar.gz of scene.xml + meshes) and solver parameters for one site."""
    import tarfile
    import tempfile

    from twin.physics.buildings import load_window
    from twin.physics.scene import write_scene

    lon, lat = float(site["lon"]), float(site["lat"])
    city = load_window(lon, lat, radius_m + 50.0)
    if city is None:
        raise FileNotFoundError("city model (buildings_lod1.parquet) not found; see config/physics.yaml")
    txs, unknown = transmitters_for(site)
    cell = float(config.value("raytrace", "cell_size_m"))
    with tempfile.TemporaryDirectory() as tmp:
        write_scene(city, Path(tmp), ground_half_m=radius_m + 100.0)
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            tar.add(tmp, arcname="scene")
    params: dict[str, Any] = {
        "frequency_mhz": frequency_mhz, "transmitters": txs, "center": [0.0, 0.0], "size_m": 2.0 * radius_m,
        "cell_m": cell, "heights_m": [float(h) for h in config.value("raytrace", "heights_m")],
        "samples_per_tx": int(config.value("raytrace", "samples_per_tx")),
        "max_depth": int(config.value("raytrace", "max_depth")),
        "meta": {"lon0": lon, "lat0": lat, "unknown_azimuth": unknown, "buildings": len(city),
                 "radius_m": radius_m, "cell_m": cell, "frequency_mhz": frequency_mhz},
    }
    return buf.getvalue(), params


def run_scene(scene_tar: bytes, params: Mapping[str, Any]) -> bytes:
    """Unpack a prepared scene, trace it and return RadioMaps bytes (runs where sionna-rt is installed)."""
    import tarfile
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(scene_tar), mode="r:gz") as tar:
            tar.extractall(tmp, filter="data")
        out = solve(str(Path(tmp) / "scene" / "scene.xml"), params)
    meta = dict(params.get("meta", {}))
    meta["transmitters"] = list(params["transmitters"])
    return RadioMaps(out["path_gain"], out["cell_centers"], out["heights_m"], meta).to_bytes()
