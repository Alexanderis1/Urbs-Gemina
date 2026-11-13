"""Vector tiles (PMTiles) for the MapLibre viewer, written with tippecanoe."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from twin.model.config import TileConfig

#: Attributes the viewer needs; the h_* candidates stay in the GeoParquet only.
TILE_COLUMNS = (
    "id", "height_m", "height_sd_m", "height_source", "height_conflict", "data_kind", "ground_m", "roof_m", "class",
    "roof_material", "vertical_mm_yr",
)


def tippecanoe_command(src: Path, dst: Path, cfg: TileConfig) -> list[str]:
    return [
        "tippecanoe",
        f"--output={dst}",
        "--force",
        f"--layer={cfg.layer}",
        f"--minimum-zoom={cfg.min_zoom}",
        f"--maximum-zoom={cfg.max_zoom}",
        "--no-tile-size-limit",
        "--no-feature-limit",
        "--detect-shared-borders",
        "--simplification=2",
        "--read-parallel",
        "--quiet",
        str(src),
    ]


def _clean(v: Any) -> Any:
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (float, np.floating)):
        return None if not np.isfinite(v) else round(float(v), 2)
    if isinstance(v, np.integer):
        return int(v)
    return v


def write_geojsonseq(frame: Any, path: Path, columns: Sequence[str] = TILE_COLUMNS) -> Path:
    """One GeoJSON feature per line (WGS84), only the listed attributes, nulls dropped."""
    import shapely

    g = frame.to_crs("EPSG:4326")
    cols = [c for c in columns if c in g.columns]
    geoms = shapely.to_geojson(np.asarray(g.geometry.values), indent=None)
    with open(path, "w", encoding="utf-8") as fh:
        for geom, rec in zip(geoms, g[cols].itertuples(index=False, name=None)):
            props = {c: _clean(v) for c, v in zip(cols, rec)}
            props = {k: v for k, v in props.items() if v is not None}
            fh.write('{"type":"Feature","properties":' + json.dumps(props) + ',"geometry":' + str(geom) + "}\n")
    return path


def write_tiles(frame: Any, dst: Path, cfg: TileConfig, columns: Sequence[str] = TILE_COLUMNS) -> Path:
    if shutil.which("tippecanoe") is None:
        raise RuntimeError("tippecanoe not found: pip install tippecanoe (or install it from felt/tippecanoe)")
    dst.parent.mkdir(parents=True, exist_ok=True)
    src = dst.with_suffix(".geojsonl")
    write_geojsonseq(frame, src, columns)
    subprocess.run(tippecanoe_command(src, dst, cfg), check=True)
    src.unlink()
    return dst
