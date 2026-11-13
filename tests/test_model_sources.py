"""WS2: naming of remote input tiles (no network)."""
from twin.model.sources import dem_tile_urls, gba_tile_name
from twin.providers.base import ROME_BBOX


def test_gba_tile_for_rome() -> None:
    assert gba_tile_name(12.5, 41.9) == "e010_n45_e015_n40"
    assert gba_tile_name(-3.7, 40.4) == "w005_n45_e000_n40"


def test_dem_tiles_cover_the_whole_city() -> None:
    urls = dem_tile_urls(ROME_BBOX)
    assert len(urls) == 2
    assert any("N41_00_E012_00" in u for u in urls) and any("N42_00_E012_00" in u for u in urls)
