"""WS2: height resolution and validation for the G0 block model."""
import math
from pathlib import Path

import pytest

from twin.model.heights import HeightConfig, load_height_config, resolve_height
from twin.model.validation import compare_heights, source_shares

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def cfg() -> HeightConfig:
    return load_height_config(ROOT / "config" / "model.yaml")


def test_config_priority_and_labels(cfg: HeightConfig) -> None:
    assert cfg.priority == ("osm_tag", "gba", "raster", "floors", "default")
    assert cfg.data_kinds["osm_tag"] == "real"
    assert all(cfg.data_kinds[s] == "estimated" for s in ("gba", "raster", "floors", "default"))
    assert cfg.licences["gba"] == "CC BY-NC 4.0"
    assert cfg.non_commercial == frozenset({"gba"})
    assert cfg.raster_classes[7] == (20.0, 30.0, 25.0)
    assert cfg.raster_statistic == "mode"
    assert cfg.metres_per_floor == pytest.approx(3.2)


def test_first_source_with_a_value_wins(cfg: HeightConfig) -> None:
    h = resolve_height({"osm_tag": 21.0, "raster": 18.0}, cfg)
    assert (h.height_m, h.source, h.data_kind) == (21.0, "osm_tag", "real")


def test_gba_beats_urban_atlas(cfg: HeightConfig) -> None:
    h = resolve_height({"gba": 17.0, "raster": 18.0}, cfg)
    assert (h.source, h.licence) == ("gba", "CC BY-NC 4.0")


def test_missing_and_invalid_values_are_skipped(cfg: HeightConfig) -> None:
    h = resolve_height({"osm_tag": None, "gba": math.nan, "floors": 4 * 3.2}, cfg)
    assert h.source == "floors" and h.height_m == pytest.approx(12.8)
    assert resolve_height({"osm_tag": -3.0, "raster": 0.0}, cfg).source == "default"


def test_default_height_when_nothing_is_known(cfg: HeightConfig) -> None:
    h = resolve_height({}, cfg)
    assert (h.height_m, h.source, h.data_kind) == (9.0, "default", "estimated")


def test_heights_are_clamped(cfg: HeightConfig) -> None:
    assert resolve_height({"osm_tag": 900.0}, cfg).height_m == 160.0
    assert resolve_height({"osm_tag": 0.5}, cfg).height_m == 2.0


def test_unknown_source_in_priority_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "model.yaml"
    bad.write_text("heights:\n  priority: [osm_tag, magic]\n  sources:\n    osm_tag: {data_kind: real}\n")
    with pytest.raises(ValueError):
        load_height_config(bad)


def test_compare_heights_metrics() -> None:
    pred = [10.0, 12.0, None, 30.0]
    ref = [11.0, 12.0, 9.0, None]
    a = compare_heights(pred, ref, source="raster", within_m=3.0)
    assert a.n == 2
    assert a.bias_m == pytest.approx(-0.5)
    assert a.mae_m == pytest.approx(0.5)
    assert a.rmse_m == pytest.approx(math.sqrt(0.5))
    assert a.share_within == pytest.approx(1.0)


def test_compare_heights_with_no_pairs_is_empty_not_an_error() -> None:
    a = compare_heights([None], [5.0], source="raster", within_m=3.0)
    assert a.n == 0 and a.mae_m is None


def test_source_shares_sum_to_one() -> None:
    shares = source_shares(["osm_tag", "raster", "raster", "default"])
    assert shares == {"osm_tag": 0.25, "raster": 0.5, "default": 0.25}


def test_report_lists_sources_and_agreements() -> None:
    from twin.model.validation import render_report

    a = compare_heights([10.0], [12.0], source="gba", within_m=3.0)
    md = render_report(1, {"gba": 1.0}, [a], ["note"])
    assert "| gba | osm_tag | 1 | -2.0 |" in md and "- note" in md


def test_class_agreement_counts_heights_inside_the_class() -> None:
    from twin.model.validation import class_agreement

    a = class_agreement([25.0, 12.0, None, 40.0], [20.0, 20.0, 20.0, None], [30.0, 30.0, 30.0, None], source="gba")
    assert a.n == 2 and a.share_within == pytest.approx(0.5)
    assert a.reference == "raster_class"
