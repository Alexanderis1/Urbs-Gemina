"""Street-level heat: correct the forecast temperature with tree cover and sealed ground.

A 2 m forecast is smooth over kilometres, while in a city leafy blocks are
cooler and sealed (impervious) blocks warmer. Using the Copernicus 2018 Tree
Cover Density and Imperviousness rasters (20 m), each cell is shifted by

    delta = tree_c_per_pct x (tree cover - area mean) + imperv_c_per_pct x (sealed - area mean)

and its variance widened by ``extra_sd_c`` squared, because the coefficients are
assumptions. Settings and their basis: ``microclimate`` in config/beliefs.yaml.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml

from twin.beliefs.config import CONFIG_DIR
from twin.beliefs.grid import cell_center
from twin.beliefs.layer import BeliefLayer

#: Half-width of the window averaged around a cell centre (a resolution-9 cell is about 175 m across its edge).
HALF_WIDTH_M = 170.0


def microclimate_settings(config_dir: Path = CONFIG_DIR) -> dict[str, Any]:
    raw = yaml.safe_load((config_dir / "beliefs.yaml").read_text(encoding="utf-8"))["microclimate"]
    if not isinstance(raw, dict):
        raise ValueError("microclimate must be a mapping")
    return raw


def raster_mean_per_cell(path: Path, cells: Sequence[str]) -> dict[str, float]:
    """Mean raster value (no-data excluded) in a window around each cell centre."""
    import rasterio  # type: ignore[import-untyped]
    from rasterio.warp import transform as warp  # type: ignore[import-untyped]

    out: dict[str, float] = {}
    with rasterio.open(path) as src:
        data = src.read(1).astype(np.float64)
        if src.nodata is not None:
            data[data == src.nodata] = np.nan
        lons, lats = zip(*(cell_center(c) for c in cells))
        xs, ys = warp("EPSG:4326", src.crs, list(lons), list(lats))
        geographic = bool(src.crs.is_geographic)
        # Window size in pixels: metres for projected rasters, about 111 km per degree otherwise.
        px = abs(src.res[0]) * (111_000.0 if geographic else 1.0)
        half = max(1, int(round(HALF_WIDTH_M / px)))
        for cell, x, y in zip(cells, xs, ys):
            row, col = src.index(x, y)
            if not (0 <= row < src.height and 0 <= col < src.width):
                continue
            window = data[max(0, row - half) : row + half + 1, max(0, col - half) : col + half + 1]
            if np.isfinite(window).any():
                out[cell] = float(np.nanmean(window))
    return out


def apply_microclimate(
    layer: BeliefLayer, tree_cover: Mapping[str, float], impervious: Mapping[str, float]
) -> BeliefLayer:
    s = microclimate_settings()
    tree = np.array([tree_cover.get(c, np.nan) for c in layer.cells])
    seal = np.array([impervious.get(c, np.nan) for c in layer.cells])
    tree_dev = np.nan_to_num(tree - np.nanmean(tree)) if np.isfinite(tree).any() else np.zeros(len(tree))
    seal_dev = np.nan_to_num(seal - np.nanmean(seal)) if np.isfinite(seal).any() else np.zeros(len(seal))
    delta = float(s["tree_c_per_pct"]) * tree_dev + float(s["imperv_c_per_pct"]) * seal_dev
    touched = np.isfinite(tree) | np.isfinite(seal)
    extra = float(s["extra_sd_c"]) ** 2
    spec = replace(layer.spec, caveats=layer.spec.caveats + (
        "street-level heat adjusted with Copernicus 2018 tree cover and imperviousness; coefficients are assumptions (C=45)",
    ))
    return replace(
        layer,
        spec=spec,
        mean=layer.mean + delta,
        variance=layer.variance + extra * touched,
        prior_offset=layer.prior_offset + delta,
        prior_var=layer.prior_var + extra * touched,
    )
