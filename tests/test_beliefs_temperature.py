"""Street temperature layer: weather forecast plus the night-time urban heat island."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from twin.beliefs import landuse
from twin.beliefs.config import load_specs
from twin.beliefs.grid import cell_of, cells_in_bbox
from twin.beliefs.layer import prior_layer
from twin.providers.base import Observation

HERE = (12.4964, 41.9028)
WINDOW = (12.485, 41.895, 12.505, 41.910)


def _forecast(at: datetime) -> list[Observation]:
    return [Observation("f1", "WeatherForecast", HERE[0], HERE[1], at, {"temperature_c": 20.0},
                        {"temperature_c": 1.5}, "om_weather_forecast", False)]


def test_heat_island_counts_at_night_and_not_at_midday(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cells = cells_in_bbox(WINDOW, 9)
    hot = cell_of(*HERE, 9)
    (tmp_path / "uhi.csv").write_text("cell,value\n" + "".join(f"{c},{2.5 if c == hot else 0.5}\n" for c in cells))
    monkeypatch.setattr(landuse, "SEARCH_DIRS", (tmp_path,))
    landuse.load_cell_covariate.cache_clear()
    spec = load_specs()["air_temperature"]
    assert spec.prior_field is not None
    field = replace(spec.prior_field, covariate_file="uhi.csv")
    spec = replace(spec, prior_field=field)
    cool = next(c for c in cells if c != hot)

    night = datetime(2026, 7, 20, 2, tzinfo=timezone.utc)
    layer = prior_layer(spec, cells, night, prior_field=_forecast(night))
    assert layer.belief(hot).mean - layer.belief(cool).mean == pytest.approx(2.0)
    noon = datetime(2026, 7, 20, 11, tzinfo=timezone.utc)
    layer = prior_layer(spec, cells, noon, prior_field=_forecast(noon))
    assert layer.belief(hot).mean == pytest.approx(layer.belief(cool).mean)
    landuse.load_cell_covariate.cache_clear()


def test_temperature_layer_is_estimated_from_real_inputs_only() -> None:
    spec = load_specs()["air_temperature"]
    assert spec.unit == "°C" and spec.prior_field is not None
    assert spec.prior_field.source == "weather_forecast" and spec.prior_field.value_key == "temperature_c"
    weights = spec.prior_field.covariate_weight_by_hour
    assert weights is not None and len(weights) == 24
    assert weights[2] == 1.0 and weights[12] == 0.0  # full heat island at night (UTC), none at midday


def test_night_heat_island_follows_the_heat_model_coefficients() -> None:
    imp = np.array([[0.9, 0.9], [0.1, 0.1]])
    imp_nb = np.array([[0.5, 0.5], [0.5, 0.5]])
    trees = np.array([[0.0, 0.0], [0.6, 0.6]])
    trees_nb = np.array([[0.3, 0.3], [0.3, 0.3]])
    out = landuse.night_heat_island(imp, imp_nb, trees, trees_nb, city=2.9, local=0.6, tree=1.2)
    assert out[0, 0] == pytest.approx(2.9 * 0.5 + 0.6 * 0.4 - 1.2 * -0.3)
    assert out[1, 0] == pytest.approx(2.9 * 0.5 + 0.6 * -0.4 - 1.2 * 0.3)


class _Forecast:
    """A forecast feed: 10 degC at 09:00 UTC, 20 degC at 12:00 UTC."""

    def describe(self) -> object:
        return None

    def fetch(self, bbox: object, start: datetime, end: datetime) -> list[Observation]:
        out = []
        for hour, value in ((9, 10.0), (12, 20.0)):
            at = datetime(2026, 11, 14, hour, tzinfo=timezone.utc)
            if start <= at <= end:
                out.append(Observation("f1", "WeatherForecast", HERE[0], HERE[1], at, {"temperature_c": value},
                                       {"temperature_c": 1.5}, "om_weather_forecast", False))
        return out


def test_a_forecast_map_is_read_at_the_time_asked_not_at_the_start_of_the_look_back(monkeypatch: pytest.MonkeyPatch) -> None:
    from twin.beliefs.api import build_layer

    monkeypatch.setattr(landuse, "SEARCH_DIRS", ())
    landuse.load_cell_covariate.cache_clear()
    cells = cells_in_bbox(WINDOW, 9)
    start, end = datetime(2026, 11, 14, 9, tzinfo=timezone.utc), datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
    layer = build_layer("air_temperature", cells, None, start, end, prior_provider=_Forecast())  # type: ignore[arg-type]
    assert layer.belief(cell_of(*HERE, 9)).mean == pytest.approx(20.0)
    landuse.load_cell_covariate.cache_clear()
