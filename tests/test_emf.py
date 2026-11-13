import pytest

from twin.tools.emf import add_to_baseline, combine_fields, exceedance_probability, field_range, free_space_field


def test_free_space_reference_value() -> None:
    # sqrt(30 * 1000 W) / 100 m = 1.732 V/m
    assert free_space_field(1000.0, 100.0) == pytest.approx(1.732, abs=0.001)


def test_field_halves_when_distance_doubles() -> None:
    assert free_space_field(500.0, 200.0) == pytest.approx(free_space_field(500.0, 100.0) / 2.0)


def test_negative_eirp_is_rejected() -> None:
    with pytest.raises(ValueError):
        free_space_field(-1.0, 10.0)


def test_sources_combine_as_root_sum_square() -> None:
    assert combine_fields([3.0, 4.0]) == pytest.approx(5.0)
    assert add_to_baseline(3.0, 4.0) == pytest.approx(5.0)


def test_range_is_symmetric_in_decibels() -> None:
    low, median, high = field_range(2.0, 3.0)
    assert median == 2.0
    assert low < median < high
    assert high / median == pytest.approx(median / low)


def test_exceedance_probability_limits() -> None:
    assert exceedance_probability(15.0, 3.0, 15.0) == pytest.approx(0.5)
    assert exceedance_probability(1.0, 3.0, 15.0) < 0.001
    assert exceedance_probability(40.0, 3.0, 15.0) > 0.99
    assert exceedance_probability(0.0, 3.0, 15.0) == 0.0
