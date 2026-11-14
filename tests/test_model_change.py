"""WS2: construction period from the photo time series (1998-2023)."""
import numpy as np
import pytest

from twin.model.change import appearance_period, ncc_per_label


def test_ncc_is_high_for_the_same_roof_and_low_for_a_field() -> None:
    rng = np.random.default_rng(0)
    roof = rng.uniform(0, 1, (40, 40))
    labels = np.zeros((40, 40), dtype=np.int32)
    labels[5:20, 5:20] = 1
    labels[22:38, 22:38] = 2
    later = roof.copy()
    earlier = roof.copy()
    earlier[22:38, 22:38] = rng.uniform(0, 1, (16, 16))  # building 2 was not there
    ncc = ncc_per_label(earlier, later, labels, n=2)
    assert ncc[0] == pytest.approx(1.0, abs=1e-6)
    assert ncc[1] < 0.3


def test_appearance_period_picks_the_first_year_the_roof_matches() -> None:
    years = [1998, 2005, 2011, 2017]
    ncc = {1998: np.array([0.9, 0.1, 0.1, np.nan]), 2005: np.array([0.9, 0.2, 0.1, np.nan]),
           2011: np.array([0.8, 0.7, 0.2, np.nan]), 2017: np.array([0.9, 0.8, 0.1, 0.9])}
    first, label = appearance_period(ncc, years, latest_year=2023, threshold=0.5)
    assert list(label) == ["before 1998", "2005-2011", "2017-2023", "before 2017"]  # 4: no older photo
    assert list(first) == [1998, 2011, 2023, 2017]


def test_no_photo_at_all_is_unknown() -> None:
    first, label = appearance_period({2005: np.array([np.nan])}, [2005], latest_year=2023, threshold=0.5)
    assert label[0] == "unknown" and first[0] == -1


def test_tile_shift_is_recovered() -> None:
    from twin.model.change import align_shift

    rng = np.random.default_rng(3)
    base = rng.uniform(0, 1, (128, 128))
    from scipy import ndimage

    base = ndimage.gaussian_filter(base, 2)
    moved = np.roll(base, (3, -2), axis=(0, 1))
    dy, dx = align_shift(moved, base, max_shift=8)
    assert (dy, dx) == (3, -2)
