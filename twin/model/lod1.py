"""G0: LoD1 block model (footprint + one height + ground level per building)."""
from __future__ import annotations

from typing import Any, Callable, Optional

import geopandas as gpd
import numpy as np
import numpy.typing as npt
import shapely

from twin.model.config import ModelConfig
from twin.model.fusion import SourceObs, calibrate, fuse
from twin.model.heights import HeightConfig, resolve_height

#: UTM zone 33N: metric frame for areas, rings and simulations around Rome.
METRIC_CRS = "EPSG:32633"
WGS84 = "EPSG:4326"

Sampler = Callable[[gpd.GeoDataFrame], npt.NDArray[np.float64]]

#: Columns written to tiles and GeoParquet (h_* are the candidate heights, kept for the height check).
OUTPUT_COLUMNS = [
    "id", "height_m", "height_sd_m", "height_source", "height_sources", "height_conflict", "data_kind",
    "height_licence", "ground_m", "roof_m",
    "num_floors", "class", "h_osm_tag", "h_gba", "h_raster", "raster_class", "raster_low_m", "raster_high_m",
    "h_floors", "h_fused_noref", "synthetic",
]


def frame_from_overture(table: Any) -> gpd.GeoDataFrame:
    """Overture buildings Arrow table (geometry as WKB) -> GeoDataFrame in WGS84."""
    df = table.drop_columns(["geometry"]).to_pandas()
    geoms = shapely.from_wkb(np.asarray(table.column("geometry").to_pylist(), dtype=object))
    return gpd.GeoDataFrame(df, geometry=geoms, crs=WGS84)


def _float_column(frame: gpd.GeoDataFrame, name: str) -> npt.NDArray[np.float64]:
    if name not in frame.columns:
        return np.full(len(frame), np.nan)
    return np.asarray(frame[name].astype("float64").to_numpy(na_value=np.nan), dtype="float64")


def match_gba(
    metric: gpd.GeoDataFrame, gba: gpd.GeoDataFrame
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Height and standard deviation of the GBA polygon containing each footprint's inner point.

    NaN where no GBA polygon contains the point. With overlapping polygons the tallest wins.
    """
    pts = gpd.GeoDataFrame(geometry=metric.geometry.representative_point(), crs=metric.crs)
    other = gba.copy()
    if "var" not in other.columns:
        other["var"] = np.nan
    other = other[["height", "var", "geometry"]].to_crs(metric.crs)
    joined = gpd.sjoin(pts, other, how="left", predicate="within")
    joined = joined.sort_values("height", ascending=False, kind="mergesort")
    best = joined[~joined.index.duplicated(keep="first")].reindex(range(len(metric)))
    height = np.asarray(best["height"].to_numpy(dtype="float64"), dtype="float64")
    var = np.asarray(best["var"].to_numpy(dtype="float64"), dtype="float64")
    sd = np.sqrt(np.where(var >= 0, var, np.nan))  # negative variance = GBA "unknown"
    return height, sd


def fuse_heights(
    cand: dict[str, npt.NDArray[np.float64]],
    per_building_sd: dict[str, npt.NDArray[np.float64]],
    hc: HeightConfig,
) -> tuple[Any, dict[str, Any]]:
    """Calibrate every source against the reference and fuse them (see twin.model.fusion)."""
    ref_name = hc.fusion_reference
    ref = cand[ref_name]
    obs: dict[str, SourceObs] = {}
    calibrations: dict[str, Any] = {}
    for name in hc.priority:
        if name == "default" or name not in cand:
            continue
        value = cand[name]
        if not np.isfinite(value).any():
            continue
        if name == ref_name:
            obs[name] = SourceObs(value, np.full(len(value), hc.fusion_reference_sd))
            calibrations[name] = {"role": "reference", "sd_m": hc.fusion_reference_sd}
            continue
        claimed = per_building_sd.get(name)
        cal = calibrate(
            value, ref, ref_sd=hc.fusion_reference_sd, prior_sd=claimed, min_pairs=hc.fusion_min_pairs,
            fallback_sd=float(np.nanmedian(claimed)) if claimed is not None and np.isfinite(claimed).any() else 3.0,
        )
        if claimed is not None:
            sd = np.where(np.isfinite(claimed) & (claimed > 0), claimed * cal.scale, cal.sd_m)
        else:
            sd = np.full(len(value), cal.sd_m)
        obs[name] = SourceObs(value - cal.bias_m, sd)
        calibrations[name] = {"role": "measurement", **cal.as_dict()}
    prior_mean, prior_sd = hc.fusion_prior
    result = fuse(obs, prior_mean=prior_mean, prior_sd=prior_sd, conflict_chi2=hc.fusion_conflict_chi2)
    # Hold-out check: the same fusion without the reference, to compare against the reference fairly.
    others = {k: v for k, v in obs.items() if k != ref_name}
    held = fuse(others, prior_mean=np.nan, prior_sd=np.nan, conflict_chi2=hc.fusion_conflict_chi2)
    calibrations["_holdout_mean"] = held.mean
    return result, calibrations


def build_lod1(
    footprints: gpd.GeoDataFrame,
    cfg: ModelConfig,
    *,
    gba: Optional[gpd.GeoDataFrame] = None,
    raster_heights: Optional[Sampler] = None,
    ground: Optional[Sampler] = None,
) -> gpd.GeoDataFrame:
    """Resolve one height per building and return the block model in WGS84.

    Samplers receive the footprints in ``METRIC_CRS`` and return one value per row.
    """
    metric = footprints.to_crs(METRIC_CRS)
    keep = metric.geometry.area >= cfg.footprints.min_area_m2
    if cfg.footprints.drop_underground and "is_underground" in metric.columns:
        keep &= ~metric["is_underground"].fillna(False).astype(bool)
    metric = metric[keep].reset_index(drop=True)

    hc = cfg.heights
    nan = np.full(len(metric), np.nan)
    gba_h, gba_sd = match_gba(metric, gba) if gba is not None and "gba" in hc.priority else (nan, nan)
    raw = raster_heights(metric) if raster_heights is not None else nan
    if hc.raster_classes:
        # The raster holds class codes: turn each into its configured height, keep the bounds for the check.
        codes = np.where(np.isfinite(raw), np.round(raw), np.nan)
        missing = (np.nan, np.nan, np.nan)
        lookup = np.array(
            [hc.raster_classes.get(int(c), missing) if np.isfinite(c) else missing for c in codes], dtype="float64"
        ).reshape(len(metric), 3)
        raster_low, raster_high, raster_h = lookup[:, 0], lookup[:, 1], lookup[:, 2]
        raster_class = np.where(np.isfinite(raster_h), codes, np.nan)
    else:
        raster_h, raster_low, raster_high, raster_class = raw, nan, nan, nan
    cand = {
        "osm_tag": _float_column(metric, "height"),
        "gba": gba_h,
        "raster": raster_h,
        "floors": _float_column(metric, "num_floors") * hc.metres_per_floor,
    }
    ground_m = ground(metric) if ground is not None else np.full(len(metric), np.nan)
    out = metric.copy()
    calibrations: dict[str, Any] = {}
    if hc.method == "fusion":
        class_sd = (raster_high - raster_low) / np.sqrt(12.0)  # uniform within the Urban Atlas class
        per_sd = {"gba": gba_sd, "raster": class_sd if hc.raster_classes else nan}
        fused, calibrations = fuse_heights(cand, per_sd, hc)
        out["h_fused_noref"] = calibrations.pop("_holdout_mean")
        lo, hi = hc.clamp
        dominant = np.where(fused.dominant == "prior", "default", fused.dominant).astype(object)
        out["height_m"] = np.clip(fused.mean, lo, hi)
        out["height_sd_m"] = fused.sd
        out["height_source"] = dominant
        out["height_sources"] = fused.sources
        out["height_conflict"] = fused.conflict
        out["data_kind"] = [hc.data_kinds.get(d, "estimated") for d in dominant]
        out["height_licence"] = [
            "; ".join(sorted({hc.licences.get(s, "not stated") for s in srcs.split("+") if s != "prior"})) or "none"
            for srcs in fused.sources
        ]
        used = set("+".join(fused.sources).split("+"))
    else:
        resolved = [resolve_height({k: float(v[i]) for k, v in cand.items()}, hc) for i in range(len(metric))]
        out["height_m"] = [r.height_m for r in resolved]
        out["height_source"] = [r.source for r in resolved]
        out["height_sources"] = out["height_source"]
        out["height_conflict"] = False
        # Spread is known only for GBA (its model variance); other sources leave it empty.
        out["height_sd_m"] = np.where(out["height_source"] == "gba", gba_sd, np.nan)
        out["h_fused_noref"] = np.nan
        out["data_kind"] = [r.data_kind for r in resolved]
        out["height_licence"] = [r.licence for r in resolved]
        used = set(out["height_source"])
    out["ground_m"] = ground_m
    out["roof_m"] = out["ground_m"] + out["height_m"]
    for k, v in cand.items():
        out[f"h_{k}"] = v
    out["raster_class"] = raster_class
    out["raster_low_m"] = raster_low
    out["raster_high_m"] = raster_high
    out["synthetic"] = False
    for col in ("id", "num_floors", "class"):
        if col not in out.columns:
            out[col] = None
    out = gpd.GeoDataFrame(out[OUTPUT_COLUMNS + ["geometry"]], geometry="geometry", crs=METRIC_CRS).to_crs(WGS84)
    out.attrs["non_commercial"] = bool(used & hc.non_commercial)
    out.attrs["calibration"] = calibrations
    return out
