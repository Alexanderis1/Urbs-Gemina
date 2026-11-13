from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from twin.providers.base import ROME_BBOX, Provider, ProviderNotConfigured
from twin.providers.open.roma_wfs import build_url, drop_personal_fields
from twin.providers.registry import build_providers, load_config
from twin.providers.simulated.loops import SimLoopsProvider

T0 = datetime(2026, 11, 13, 8, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


def test_simulated_loops_follow_the_provider_contract() -> None:
    provider = SimLoopsProvider(seed=1, n_stations=10)
    assert isinstance(provider, Provider)
    info = provider.describe()
    assert info.kind == "simulated" and info.synthetic is True
    observations = list(provider.fetch(ROME_BBOX, T0, T0 + timedelta(minutes=10)))
    assert len(observations) == 10 * 3  # 08:00, 08:05, 08:10
    for obs in observations:
        assert obs.synthetic is True
        assert set(obs.sigma) == set(obs.values)
        assert obs.values["intensity"] >= 0.0


def test_simulated_loops_are_reproducible() -> None:
    first = list(SimLoopsProvider(seed=7, n_stations=5).fetch(ROME_BBOX, T0, T0))
    second = list(SimLoopsProvider(seed=7, n_stations=5).fetch(ROME_BBOX, T0 - timedelta(hours=1), T0))
    assert first == [obs for obs in second if obs.observed_at == T0]


def test_rush_hour_is_busier_than_night() -> None:
    provider = SimLoopsProvider(seed=3, n_stations=20)
    night = datetime(2026, 11, 13, 3, 0, tzinfo=timezone.utc)

    def total(moment: datetime) -> float:
        return sum(obs.values["intensity"] for obs in provider.fetch(ROME_BBOX, moment, moment))

    assert total(T0.replace(hour=8, minute=30)) > 3 * total(night)


def test_config_selects_the_active_provider() -> None:
    config = load_config(ROOT / "config" / "providers.yaml")
    assert config["traffic_flow"] == "sim_loops"
    providers = build_providers(config)
    assert providers["traffic_flow"].describe().id == "sim_loops"


def test_switching_to_the_pa_provider_needs_access() -> None:
    with pytest.raises(ProviderNotConfigured):
        build_providers({"traffic_flow": "pa_datex"})


def test_unknown_provider_is_an_error_when_strict() -> None:
    with pytest.raises(KeyError):
        build_providers({"traffic_flow": "does_not_exist"}, skip_unknown=False)


def test_wfs_url_requests_wgs84_json() -> None:
    url = build_url("DIPAU:ReteEcologicaPoligono", bbox=(12.47, 41.89, 12.49, 41.90), max_features=5)
    assert "srsName=EPSG%3A4326" in url and "outputFormat=application%2Fjson" in url
    assert "bbox=12.470000%2C41.890000%2C12.490000%2C41.900000%2CEPSG%3A4326" in url


def test_personal_fields_are_dropped() -> None:
    collection = {"features": [{"properties": {"nome": "Ospedale", "ref-nome": "x", "ref-cell": "y", "tel1": "z", "email1": "w", "mun": "1"}}]}
    cleaned = drop_personal_fields(collection)
    assert cleaned["features"][0]["properties"] == {"nome": "Ospedale", "mun": "1"}
