"""Static layers for the heatwave scenario: census ages and tree cover."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fetch_heat_layers import ages_rows, tree_cover_url  # noqa: E402


def test_ages_rows_sum_istat_age_classes() -> None:
    rows = [{"SEZ21_ID": 580911010001, "P27": 1, "P28": 2, "P29": 3, "P1": 10},
            {"SEZ21_ID": 580911010002.0, "P27": None, "P28": 0, "P29": 4, "P1": 9}]
    assert ages_rows(rows) == [("580911010001", 6, 3), ("580911010002", 4, 4)]


def test_tree_cover_url_matches_the_template_grid() -> None:
    url = tree_cover_url((4506280.0, 2064180.0, 4559760.0, 2119700.0), (2674, 2776))
    assert "HRL_TreeCoverDensity_2018" in url
    assert "bbox=4506280,2064180,4559760,2119700" in url and "size=2674,2776" in url and "bboxSR=3035" in url
