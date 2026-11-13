"""Terrain grid for the physical scenarios (floods, plumes, access).

A ``Grid`` is a north-up raster in UTM 33N (EPSG:32633) metres. The DTM is read
from WS1 / WS2 files when they exist, otherwise from the Copernicus GLO-30 COG
tiles on the public AWS bucket, by byte range, into memory only.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import numpy.typing as npt

from twin.providers.base import BBox
from twin.scenarios import config, layers

CRS = "EPSG:32633"
WGS84 = "EPSG:4326"
FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]
IntArray = npt.NDArray[np.int64]


@dataclass(frozen=True)
class Grid:
    """``z[row, col]``; row 0 is the northern edge; NaN where there is no data."""

    z: FloatArray
    x0: float  # west edge, metres
    y0: float  # north edge, metres
    cell: float
    source: Mapping[str, Any] = field(default_factory=dict)

    @property
    def shape(self) -> tuple[int, int]:
        return (int(self.z.shape[0]), int(self.z.shape[1]))

    @property
    def cell_area(self) -> float:
        return self.cell * self.cell

    def transform(self) -> Any:
        from rasterio.transform import from_origin  # type: ignore[import-untyped]

        return from_origin(self.x0, self.y0, self.cell, self.cell)

    def rowcol(self, lons: Sequence[float], lats: Sequence[float]) -> tuple[IntArray, IntArray]:
        """Row and column of each point; -1 outside the grid."""
        xs, ys = to_utm(lons, lats)
        cols = np.floor((np.asarray(xs) - self.x0) / self.cell).astype(np.int64)
        rows = np.floor((self.y0 - np.asarray(ys)) / self.cell).astype(np.int64)
        rows_n, cols_n = self.shape
        outside = (rows < 0) | (rows >= rows_n) | (cols < 0) | (cols >= cols_n)
        rows[outside] = -1
        cols[outside] = -1
        return rows, cols

    def sample(self, values: npt.NDArray[Any], lons: Sequence[float], lats: Sequence[float],
               missing: float = math.nan) -> FloatArray:
        rows, cols = self.rowcol(lons, lats)
        out = np.full(len(rows), missing, dtype=np.float64)
        ok = rows >= 0
        out[ok] = values[rows[ok], cols[ok]]
        return out

    def lonlat(self, rows: IntArray, cols: IntArray) -> tuple[list[float], list[float]]:
        xs = self.x0 + (cols + 0.5) * self.cell
        ys = self.y0 - (rows + 0.5) * self.cell
        return to_wgs84(xs.tolist(), ys.tolist())


def to_utm(lons: Sequence[float], lats: Sequence[float]) -> tuple[list[float], list[float]]:
    from rasterio.warp import transform  # type: ignore[import-untyped]

    xs, ys = transform(WGS84, CRS, list(lons), list(lats))
    return list(xs), list(ys)


def to_wgs84(xs: Sequence[float], ys: Sequence[float]) -> tuple[list[float], list[float]]:
    from rasterio.warp import transform

    lons, lats = transform(CRS, WGS84, list(xs), list(ys))
    return list(lons), list(lats)


def _cfg() -> dict[str, Any]:
    section: dict[str, Any] = config.load("scenarios.yaml")["terrain"]
    return section


def dtm_sources() -> tuple[list[str], dict[str, Any]]:
    """Ordered DTM sources: env override, WS1/WS2 files, then the GLO-30 fallback."""
    cfg = _cfg()
    env = os.environ.get("URBS_DTM")
    if env:
        return [env], {"id": "dtm_env", "kind": "estimated", "path": env}
    for entry in cfg["files"]:
        path = layers.find(str(entry["file"]), dirs=config.value(cfg, "search_dirs"))
        if path is not None:
            return [str(path)], {"id": str(entry["id"]), "kind": str(entry["kind"]), "file": path.name,
                                 "vertical_sigma_m": float(entry["vertical_sigma_m"]),
                                 "is_surface_model": bool(entry.get("is_surface_model", False))}
    fallback = cfg["fallback"]
    return [str(u) for u in fallback["tiles"]], {
        "id": str(fallback["id"]), "kind": str(fallback["kind"]), "url": str(fallback["url"]),
        "vertical_sigma_m": float(fallback["vertical_sigma_m"]), "is_surface_model": True}


def load_dtm(bbox: BBox, cell_m: float | None = None, sources: Iterable[str] | None = None,
             meta: Mapping[str, Any] | None = None) -> Grid:
    """Resample the DTM onto a UTM grid covering ``bbox`` (bilinear), in memory only."""
    import rasterio  # type: ignore[import-untyped]
    from rasterio.warp import Resampling, reproject, transform_bounds

    cell = float(cell_m if cell_m is not None else config.value(_cfg(), "cell_m"))
    if sources is None:
        found, info = dtm_sources()
    else:
        found, info = list(sources), dict(meta or {"id": "dtm", "kind": "estimated"})
    left, bottom, right, top = transform_bounds(WGS84, CRS, *bbox, densify_pts=21)
    x0, y0 = math.floor(left / cell) * cell, math.ceil(top / cell) * cell
    cols, rows = int(math.ceil((right - x0) / cell)), int(math.ceil((y0 - bottom) / cell))
    grid = Grid(np.full((rows, cols), np.nan), x0, y0, cell, info)
    env = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff"}
    with rasterio.Env(**env):
        for src_path in found:
            with rasterio.open(src_path) as src:
                dst = np.full((rows, cols), np.nan)
                reproject(rasterio.band(src, 1), dst, dst_transform=grid.transform(), dst_crs=CRS,
                          dst_nodata=np.nan, src_nodata=src.nodata, resampling=Resampling.bilinear)
                fill = np.isnan(grid.z) & ~np.isnan(dst)
                grid.z[fill] = dst[fill]
    return grid


def _geoms_utm(geometries: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    from rasterio.warp import transform_geom

    return [transform_geom(WGS84, CRS, dict(g)) for g in geometries if g]


def rasterize_mask(grid: Grid, geometries: Iterable[Mapping[str, Any]], all_touched: bool = True) -> BoolArray:
    from rasterio.features import rasterize  # type: ignore[import-untyped]

    shapes = [(g, 1) for g in _geoms_utm(geometries)]
    if not shapes:
        return np.zeros(grid.shape, dtype=bool)
    out = rasterize(shapes, out_shape=grid.shape, transform=grid.transform(), fill=0,
                    all_touched=all_touched, dtype="uint8")
    return np.asarray(out, dtype=bool)


def rasterize_index(grid: Grid, geometries: Sequence[Mapping[str, Any]]) -> IntArray:
    """Each cell gets the index of the polygon covering its centre, -1 elsewhere."""
    from rasterio.features import rasterize

    utm = _geoms_utm(geometries)
    shapes = [(g, i) for i, g in enumerate(utm)]
    if not shapes:
        return np.full(grid.shape, -1, dtype=np.int64)
    out = rasterize(shapes, out_shape=grid.shape, transform=grid.transform(), fill=-1, dtype="int32")
    return np.asarray(out, dtype=np.int64)


def mask_to_geojson(grid: Grid, mask: BoolArray, digits: int = 5) -> dict[str, Any]:
    """Cells of ``mask`` as one WGS84 MultiPolygon (for the map)."""
    from rasterio.features import shapes
    from rasterio.warp import transform_geom

    polys: list[Any] = []
    if mask.any():
        for geom, value in shapes(mask.astype("uint8"), mask=mask, transform=grid.transform()):
            if value == 1:
                g = transform_geom(CRS, WGS84, geom)
                polys.append([[[round(x, digits), round(y, digits)] for x, y in ring] for ring in g["coordinates"]])
    return {"type": "MultiPolygon", "coordinates": polys}
