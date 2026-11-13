"""WS2: terrain helpers (ground under a building, terrain-RGB tiles)."""
import numpy as np
import pytest

from twin.model.terrain import decode_terrarium, encode_terrarium, ground_from_samples


def test_ground_is_a_low_percentile_of_valid_samples() -> None:
    samples = np.array([20.0, 21.0, 22.0, 45.0, -9999.0])  # one roof, one nodata
    assert ground_from_samples(samples, percentile=0, nodata=-9999.0) == pytest.approx(20.0)
    assert ground_from_samples(samples, percentile=50, nodata=-9999.0) == pytest.approx(21.5)


def test_ground_is_none_when_all_samples_are_nodata() -> None:
    assert ground_from_samples(np.array([np.nan, -9999.0]), percentile=10, nodata=-9999.0) is None


def test_terrarium_round_trip_within_a_centimetre() -> None:
    elev = np.array([[-12.3, 0.0], [21.7, 139.99]])
    rgb = encode_terrarium(elev)
    assert rgb.shape == (2, 2, 3) and rgb.dtype == np.uint8
    assert np.allclose(decode_terrarium(rgb), elev, atol=0.01)
