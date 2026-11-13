"""WS3: Gate C (switch a provider in YAML, data changes, no code change) and data_status()."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from twin.providers.base import ROME_BBOX, ProviderNotConfigured
from twin.providers.registry import DATA_KIND, FACTORIES, build_providers, load_config
from twin.providers.settings import Settings
from twin.providers.status import data_status

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = Settings.load()
T0 = datetime(2026, 11, 13, 8, 0, tzinfo=timezone.utc)


def test_every_configured_provider_is_known_and_labelled() -> None:
    config = load_config(ROOT / "config" / "providers.yaml")
    for layer, provider_id in config.items():
        assert provider_id in FACTORIES or provider_id == "roma_wfs", layer
        assert provider_id in DATA_KIND, provider_id
    assert set(FACTORIES) <= set(DATA_KIND)


def test_the_default_config_builds_every_layer_offline() -> None:
    providers = build_providers(load_config(ROOT / "config" / "providers.yaml"), settings=SETTINGS)
    for layer, provider in providers.items():
        assert provider.describe().layer == layer
    assert providers["emf_baseline"].describe().redistribution is False
    for layer in ("traffic_flow", "antenna_register", "emf_measurements", "antenna_applications"):
        assert providers[layer].describe().synthetic is True


def _register_export(tmp_path: Path) -> Path:
    export = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "geometry": {"type": "Point", "coordinates": [12.49, 41.90]},
        "properties": {"site_id": "RM-0001", "operator": "TIM", "application_date": "2024-05-02",
                       "antenna_height_agl_m": 24.0,
                       "sectors": [{"azimuth_deg": 10, "mechanical_tilt_deg": 4, "eirp_w": 1500.0}] * 3},
    }]}
    path = tmp_path / "register_export.geojson"
    path.write_text(json.dumps(export), encoding="utf-8")
    return path


def test_gate_c_switching_the_register_in_yaml_changes_the_data(tmp_path: Path) -> None:
    providers_yaml = tmp_path / "providers.yaml"
    providers_yaml.write_text("antenna_register: sim_register\n", encoding="utf-8")
    simulated = build_providers(load_config(providers_yaml), settings=SETTINGS)["antenna_register"]
    sim_obs = list(simulated.fetch(ROME_BBOX, T0, T0))
    assert sim_obs and all(obs.synthetic for obs in sim_obs)

    # Only YAML changes from here on: point the layer at the administration's export.
    providers_yaml.write_text("antenna_register: pa_register_file\n", encoding="utf-8")
    pa_settings = Settings(
        providers={**SETTINGS.providers, "pa": {"register_file": {"path": str(_register_export(tmp_path))}}},
        emf=SETTINGS.emf, root=SETTINGS.root)
    real = build_providers(load_config(providers_yaml), settings=pa_settings)["antenna_register"]
    assert real.describe().kind == "pa" and real.describe().synthetic is False
    real_obs = list(real.fetch(ROME_BBOX, T0, T0))
    assert len(real_obs) == 1 and real_obs[0].synthetic is False
    assert real_obs[0].values["total_eirp_w"] == 4500.0
    assert real_obs[0].entity_type == sim_obs[0].entity_type == "AntennaSite"


def test_pa_register_without_an_export_says_what_is_missing() -> None:
    with pytest.raises(ProviderNotConfigured, match="pa.register_file.path"):
        build_providers({"antenna_register": "pa_register_file"}, settings=SETTINGS)


def test_data_status_lists_every_layer_honestly() -> None:
    rows = {row["layer"]: row for row in data_status(settings=SETTINGS)}
    assert set(rows) == set(load_config(ROOT / "config" / "providers.yaml"))
    assert rows["traffic_flow"]["data_kind"] == "simulated" and rows["traffic_flow"]["synthetic"] is True
    assert rows["transit"]["data_kind"] == "real" and rows["transit"]["synthetic"] is False
    assert rows["emf_baseline"]["data_kind"] == "estimated"
    assert rows["emf_baseline"]["redistribution"] is False
    assert "Cartoradio" in rows["emf_baseline"]["notes"]
    assert rows["context_layers"]["state"] == "active"
    assert all(row["state"] == "active" for row in rows.values())


def test_data_status_reports_providers_that_need_access(tmp_path: Path) -> None:
    config = tmp_path / "providers.yaml"
    config.write_text("traffic_flow: pa_datex\nnoise: sim_noise\n", encoding="utf-8")
    rows = {row["layer"]: row for row in data_status(config, settings=SETTINGS)}
    assert rows["traffic_flow"]["state"] == "needs_access" and "DATEX" in rows["traffic_flow"]["reason"]
    assert rows["noise"]["state"] == "not_implemented"
