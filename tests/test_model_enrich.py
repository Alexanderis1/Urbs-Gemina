"""WS2: per-building facts from other sensors are joined onto the block model by id."""
from pathlib import Path

import pandas as pd
import pytest

gpd = pytest.importorskip("geopandas")
from shapely.geometry import box  # noqa: E402

from twin.model.enrich import ENRICHMENTS, enrich  # noqa: E402


def test_enrich_joins_known_layers_and_ignores_missing(tmp_path: Path) -> None:
    model = gpd.GeoDataFrame({"id": ["a", "b"]}, geometry=[box(0, 0, 1, 1), box(2, 2, 3, 3)], crs="EPSG:4326")
    pd.DataFrame({"id": ["a"], "vertical_mm_yr": [-3.2], "east_mm_yr": [0.4], "n_ps_asc": [12],
                  "n_ps_desc": [9], "los_asc_mm_yr": [-2.0], "los_desc_mm_yr": [-2.5]}).to_parquet(
        tmp_path / "ground_motion.parquet")
    out, used = enrich(model, tmp_path)
    assert used == ["ground_motion"]
    assert out.set_index("id").loc["a", "vertical_mm_yr"] == pytest.approx(-3.2)
    assert pd.isna(out.set_index("id").loc["b", "vertical_mm_yr"])
    assert "roof_material" not in out.columns  # ortho facts file absent
    assert set(ENRICHMENTS) >= {"ground_motion", "ortho_facts"}
