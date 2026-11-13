"""Join per-building facts from other sensors onto the block model (by building id).

Each enrichment is produced by its own script into data/processed/model/; missing files are skipped,
so the block model never waits on an optional layer.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

#: file stem -> columns kept (all are estimates or measurements labelled in their own file)
ENRICHMENTS: dict[str, list[str]] = {
    "ground_motion": ["vertical_mm_yr", "east_mm_yr", "los_asc_mm_yr", "los_desc_mm_yr", "n_ps_asc", "n_ps_desc"],
    "ortho_facts": ["roof_material", "share_terracotta", "share_light_flat", "share_green", "shadow_length_m",
                    "h_shadow"],
    "lidar_heights": ["h_lidar_raw", "ground_lidar_m", "n_px_lidar"],
}


def enrich(model: Any, directory: Path) -> tuple[Any, list[str]]:
    import pandas as pd

    used = []
    out = model
    for stem, cols in ENRICHMENTS.items():
        path = directory / f"{stem}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        keep = ["id"] + [c for c in cols if c in df.columns]
        out = out.merge(df[keep].drop_duplicates("id"), on="id", how="left")
        used.append(stem)
    return out, used
